package com.yurii.dungeonrushloot.runtime

import android.graphics.Bitmap
import android.graphics.Color
import java.io.ByteArrayOutputStream
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.Text
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.roundToInt
import kotlinx.coroutines.tasks.await

class MlKitOcrAdapter : OcrAdapter {
    private val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)

    override suspend fun recognize(
        frame: CapturedFrame,
        crop: RelativeRect,
    ): List<OcrSpanDto> = recognizeLines(frame, crop, scale = 2.5f)

    override suspend fun recognizeEnhanced(
        frame: CapturedFrame,
        crop: RelativeRect,
    ): List<OcrSpanDto> = recognizeLines(frame, crop, scale = 3.5f)

    override suspend fun recognizeForDebug(frame: CapturedFrame, crop: RelativeRect): OcrDebugSnapshot {
        var captured: OcrDebugSnapshot? = null
        val spans = recognizeInternal(
            frame, crop, scale = 2.5f, lines = true,
            debugSink = { snapshot -> captured = snapshot },
        )
        return checkNotNull(captured) { "OCR ran without diagnostic input capture." }
            .copy(spans = spans)
    }

    /**
     * Import-specific OCR mode.
     *
     * Current-equipment screenshots are static and text is relatively small with
     * a heavy outline. Using ML Kit's already-grouped lines avoids reassembling
     * words such as "[EXP] +11 Crimson Backpack" in Python, while upscaling the
     * crop substantially improves the icon-level and affix text.
     *
     * Returned coordinates are converted back into full-screen coordinates so
     * results from multiple crops can be combined safely.
     */
    suspend fun recognizeLines(
        frame: CapturedFrame,
        crop: RelativeRect,
        scale: Float = 1f,
        lightText: Boolean = false,
    ): List<OcrSpanDto> = recognizeInternal(frame, crop, scale, lines = true, lightText = lightText)

    private suspend fun recognizeElements(
        frame: CapturedFrame,
        crop: RelativeRect,
    ): List<OcrSpanDto> = recognizeInternal(frame, crop, 1f, lines = false)

    private suspend fun recognizeInternal(
        frame: CapturedFrame,
        crop: RelativeRect,
        scale: Float,
        lines: Boolean,
        lightText: Boolean = false,
        debugSink: ((OcrDebugSnapshot) -> Unit)? = null,
    ): List<OcrSpanDto> {
        require(scale >= 1f)

        val bitmap = frame.bitmap
        val left = (crop.left * bitmap.width).roundToInt().coerceIn(0, bitmap.width - 1)
        val top = (crop.top * bitmap.height).roundToInt().coerceIn(0, bitmap.height - 1)
        val right = (crop.right * bitmap.width).roundToInt().coerceIn(left + 1, bitmap.width)
        val bottom = (crop.bottom * bitmap.height).roundToInt().coerceIn(top + 1, bitmap.height)

        val cropped = Bitmap.createBitmap(bitmap, left, top, right - left, bottom - top)
        val processed = if (scale > 1.001f) {
            Bitmap.createScaledBitmap(
                cropped,
                (cropped.width * scale).roundToInt(),
                (cropped.height * scale).roundToInt(),
                true,
            )
        } else {
            cropped
        }

        // Light letters with dark outlines on a yellow item icon can disappear
        // during normal OCR. The optional fallback isolates only bright glyphs
        // as dark text on white, without ever transforming the numeric output.
        val inputBitmap = if (lightText) isolateLightText(processed) else processed
        return try {
            // Export from the *same* bitmap used in InputImage.fromBitmap.
            // Never recreate the ROI later with potentially different dimensions.
            if (debugSink != null) {
                debugSink(
                    OcrDebugSnapshot(
                        spans = emptyList(),
                        cropPng = png(cropped),
                        inputPng = png(inputBitmap),
                        cropLeft = left,
                        cropTop = top,
                        cropRight = right,
                        cropBottom = bottom,
                        inputWidth = inputBitmap.width,
                        inputHeight = inputBitmap.height,
                        scale = scale,
                    ),
                )
            }
            val result = recognizer.process(InputImage.fromBitmap(inputBitmap, 0)).await()
            if (lines) {
                result.textBlocks.flatMap { block ->
                    block.lines.mapNotNull { line ->
                        line.toDto(left, top, scale)
                    }
                }
            } else {
                result.textBlocks.flatMap { block ->
                    block.lines.flatMap { line ->
                        line.elements.mapNotNull { element ->
                            val box = element.boundingBox ?: return@mapNotNull null
                            OcrSpanDto(
                                text = element.text,
                                score = confidence(element.confidence, line.confidence),
                                left = box.left,
                                top = box.top,
                                right = box.right,
                                bottom = box.bottom,
                            )
                        }
                    }
                }
            }
        } finally {
            if (inputBitmap !== processed) inputBitmap.recycle()
            if (processed !== cropped) processed.recycle()
            cropped.recycle()
        }
    }

    private fun png(source: Bitmap): ByteArray = ByteArrayOutputStream().use { bytes ->
        check(source.compress(Bitmap.CompressFormat.PNG, 100, bytes)) {
            "Could not encode OCR diagnostic PNG."
        }
        bytes.toByteArray()
    }

    private fun isolateLightText(source: Bitmap): Bitmap {
        val pixels = IntArray(source.width * source.height)
        source.getPixels(pixels, 0, source.width, 0, 0, source.width, source.height)
        for (index in pixels.indices) {
            val pixel = pixels[index]
            val brightness = (
                299 * Color.red(pixel) +
                    587 * Color.green(pixel) +
                    114 * Color.blue(pixel)
                ) / 1000
            pixels[index] = if (brightness >= LIGHT_TEXT_THRESHOLD) Color.BLACK else Color.WHITE
        }
        return Bitmap.createBitmap(
            pixels, source.width, source.height, Bitmap.Config.ARGB_8888,
        )
    }

    private fun Text.Line.toDto(
        cropLeft: Int,
        cropTop: Int,
        scale: Float,
    ): OcrSpanDto? {
        val box = boundingBox ?: return null
        return OcrSpanDto(
            text = text,
            score = confidence(confidence, 0.90f),
            left = cropLeft + (box.left / scale).roundToInt(),
            top = cropTop + (box.top / scale).roundToInt(),
            right = cropLeft + (box.right / scale).roundToInt(),
            bottom = cropTop + (box.bottom / scale).roundToInt(),
        )
    }

    private fun confidence(primary: Float, fallback: Float): Float =
        when {
            primary > 0f -> primary
            fallback > 0f -> fallback
            else -> 0.90f
        }

    override fun close() {
        recognizer.close()
    }

    companion object {
        private const val LIGHT_TEXT_THRESHOLD = 215
    }
}
