package com.yurii.dungeonrushloot.runtime

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import com.paddle.ocr.EngineConfig
import com.paddle.ocr.PaddleOCR
import com.paddle.ocr.PaddleOCRConfig
import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlin.math.roundToInt

/**
 * Fully local PP-OCRv6 Small implementation of the platform-neutral OcrAdapter.
 *
 * Exactly one model pair is lazily loaded per adapter. All inference and
 * disposal are serialized; failures propagate to the controller and never
 * authorize an automated tap. Shared Python parsing/scoring is unchanged.
 */
class PaddleOcrAdapter(context: Context) : OcrAdapter {
    private val appContext = context.applicationContext
    private val mutex = Mutex()
    private val cleanupScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var engine: PaddleOCR? = null
    @Volatile private var closed = false

    override suspend fun recognize(frame: CapturedFrame, crop: RelativeRect): List<OcrSpanDto> =
        recognizeCards(frame, crop, scale = 2.0f)

    override suspend fun recognizeEnhanced(frame: CapturedFrame, crop: RelativeRect): List<OcrSpanDto> =
        recognizeCards(frame, crop, scale = 3.0f)

    /**
     * Read rarity/level badges FIRST, independent of variable-height affixes.
     * Then recognize the right-hand titles/stats. If the rarity geometry
     * cannot be identified safely, fall back to ordinary full-popup OCR.
     */
    private suspend fun recognizeCards(
        frame: CapturedFrame,
        crop: RelativeRect,
        scale: Float,
    ): List<OcrSpanDto> {
        val left = recognizeBadges(frame, "rarity", LootOcrColumns.left(crop), scale)
        val rarities = IconLevelRecovery.rarityAnchors(left, frame.bitmap.height)
        if (rarities.size != 2) return recognizeLines(frame, crop, scale)

        val levels = rarities.flatMap { rarity ->
            val region = IconLevelRecovery.regionForRarity(rarity, frame.bitmap.height)
            val observed = IconLevelRecovery.eligibleLevel(
                left.filter { (it.top + it.bottom) / 2f in
                    region.top * frame.bitmap.height..region.bottom * frame.bitmap.height }
            )
            // A crop anchored to the actual rarity position is much more
            // reliable than enlarging the complete icon column. Independent
            // readings must NOT be made to agree by altering numeric digits.
            val targeted = recognizeBadges(frame, "level", region, scale = 4.0f)
            val validated = IconLevelRecovery.eligibleLevel(observed + targeted)
            if (validated.isEmpty()) {
                IconLevelRecovery.eligibleLevel(
                    recognizeBadges(frame, "level", region, scale = 4.0f, lightText = true)
                )
            } else {
                // Do not pass duplicate text into the row assembler. However,
                // if independent OCR passes disagree on a numeric level, keep
                // both observations: the Python parser rejects the conflict.
                validated.distinctBy { it.text.trim().lowercase() }
            }
        }
        val right = recognizeLines(frame, LootOcrColumns.right(crop), scale)
        return (rarities + levels + right).sortedWith(
            compareBy<OcrSpanDto> { it.top }.thenBy { it.left }
        )
    }

    override suspend fun recognizeIconLevels(
        frame: CapturedFrame,
        crop: RelativeRect,
        spans: List<OcrSpanDto>,
    ): List<OcrSpanDto> {
        val regions = IconLevelRecovery.regions(spans, frame.bitmap.width, frame.bitmap.height)
        return regions.flatMap { region ->
            val first = recognizeBadges(frame, "level_recovery", region, scale = 4.0f)
            val contrast = if (IconLevelRecovery.eligibleLevel(first).isEmpty()) {
                recognizeBadges(frame, "level_recovery", region, scale = 4.0f, lightText = true)
            } else emptyList()
            IconLevelRecovery.eligibleLevel(first + contrast)
        }
    }

    private suspend fun recognizeBadges(
        frame: CapturedFrame,
        kind: String,
        crop: RelativeRect,
        scale: Float,
        lightText: Boolean = false,
    ): List<OcrSpanDto> {
        val lines = recognizeLines(frame, crop, scale, lightText)
        frame.badgeOcrPasses += BadgeOcrPass(kind, crop, scale, lightText, lines)
        return lines
    }

    /** Used by equipment import to read main card text and icon-level labels. */
    suspend fun recognizeLines(
        frame: CapturedFrame,
        crop: RelativeRect,
        scale: Float = 2.0f,
        lightText: Boolean = false,
    ): List<OcrSpanDto> {
        require(scale >= 1f && scale.isFinite())
        return mutex.withLock {
            check(!closed) { "PaddleOCR adapter has been closed." }
            val roi = OcrCropPixels.from(crop, frame.bitmap.width, frame.bitmap.height)
            val cropped = Bitmap.createBitmap(frame.bitmap, roi.left, roi.top, roi.width, roi.height)
            try {
                val scaled = if (scale == 1f) cropped else Bitmap.createScaledBitmap(
                    cropped,
                    (cropped.width * scale).roundToInt(),
                    (cropped.height * scale).roundToInt(),
                    true,
                )
                try {
                    val processed = if (lightText) isolateLightText(scaled) else scaled
                    try {
                        initializedEngine().recognize(processed).results.mapNotNull { item ->
                            if (item.text.isBlank()) return@mapNotNull null
                            val rect = PaddleOcrCoordinates.toScreen(
                                xs = item.box.points.map { it.x },
                                ys = item.box.points.map { it.y },
                                cropLeft = roi.left, cropTop = roi.top, scale = scale,
                                screenWidth = frame.bitmap.width, screenHeight = frame.bitmap.height,
                            ) ?: return@mapNotNull null
                            OcrSpanDto(
                                text = item.text.trim(),
                                score = item.confidence,
                                left = rect.left, top = rect.top,
                                right = rect.right, bottom = rect.bottom,
                            )
                        }
                    } finally {
                        if (processed !== scaled) processed.recycle()
                    }
                } finally {
                    if (scaled !== cropped) scaled.recycle()
                }
            } finally {
                cropped.recycle()
            }
        }
    }

    private suspend fun initializedEngine(): PaddleOCR {
        engine?.let { return it }
        // Upstream OpenCVUtils.init() catches UnsatisfiedLinkError and only
        // returns false. Preserve the original dlopen error in exported logs.
        try {
            System.loadLibrary("opencv_java4")
        } catch (error: UnsatisfiedLinkError) {
            throw IllegalStateException(
                "PaddleOCR could not load libopencv_java4.so: ${error.message}",
                error,
            )
        }
        return PaddleOCR.create(
            context = appContext,
            config = PaddleOCRConfig(
                detThresh = 0.25f,
                detBoxThresh = 0.45f,
                recScoreThresh = 0.0f,
                recBatchSize = 1,
            ),
            engineConfig = EngineConfig(numThreads = 4),
        ).also { engine = it }
    }

    override fun close() {
        if (closed) return
        closed = true
        // Android invokes service teardown on the UI thread; never block it
        // on ONNX session disposal or an in-flight OCR pass.
        cleanupScope.launch {
            try {
                mutex.withLock {
                    engine?.release()
                    engine = null
                }
            } finally {
                cleanupScope.cancel()
            }
        }
    }

    private fun isolateLightText(source: Bitmap): Bitmap {
        val pixels = IntArray(source.width * source.height)
        source.getPixels(pixels, 0, source.width, 0, 0, source.width, source.height)
        for (index in pixels.indices) {
            val color = pixels[index]
            val luminance = (
                299 * Color.red(color) + 587 * Color.green(color) + 114 * Color.blue(color)
            ) / 1000
            pixels[index] = if (luminance >= 215) Color.BLACK else Color.WHITE
        }
        return Bitmap.createBitmap(pixels, source.width, source.height, Bitmap.Config.ARGB_8888)
    }
}
