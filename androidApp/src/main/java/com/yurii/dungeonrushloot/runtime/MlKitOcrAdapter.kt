package com.yurii.dungeonrushloot.runtime

import android.graphics.Bitmap
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
    ): List<OcrSpanDto> = recognizeElements(frame, crop)

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
    ): List<OcrSpanDto> = recognizeInternal(frame, crop, scale, lines = true)

    private suspend fun recognizeElements(
        frame: CapturedFrame,
        crop: RelativeRect,
    ): List<OcrSpanDto> = recognizeInternal(frame, crop, 1f, lines = false)

    private suspend fun recognizeInternal(
        frame: CapturedFrame,
        crop: RelativeRect,
        scale: Float,
        lines: Boolean,
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

        return try {
            val result = recognizer.process(InputImage.fromBitmap(processed, 0)).await()
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
            if (processed !== cropped) processed.recycle()
            cropped.recycle()
        }
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
}
