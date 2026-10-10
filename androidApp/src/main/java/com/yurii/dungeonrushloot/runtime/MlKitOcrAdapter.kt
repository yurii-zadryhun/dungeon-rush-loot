package com.yurii.dungeonrushloot.runtime

import android.graphics.Bitmap
import com.google.mlkit.vision.common.InputImage
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
    ): List<OcrSpanDto> {
        val bitmap = frame.bitmap
        val left = (crop.left * bitmap.width).roundToInt().coerceIn(0, bitmap.width - 1)
        val top = (crop.top * bitmap.height).roundToInt().coerceIn(0, bitmap.height - 1)
        val right = (crop.right * bitmap.width).roundToInt().coerceIn(left + 1, bitmap.width)
        val bottom = (crop.bottom * bitmap.height).roundToInt().coerceIn(top + 1, bitmap.height)
        val cropped = Bitmap.createBitmap(bitmap, left, top, right - left, bottom - top)

        return try {
            val result = recognizer.process(InputImage.fromBitmap(cropped, 0)).await()
            buildList {
                result.textBlocks.forEach { block ->
                    block.lines.forEach { line ->
                        line.elements.forEach { element ->
                            val box = element.boundingBox ?: return@forEach
                            val confidence = when {
                                element.confidence > 0f -> element.confidence
                                line.confidence > 0f -> line.confidence
                                else -> 0.90f
                            }
                            add(
                                OcrSpanDto(
                                    text = element.text,
                                    score = confidence,
                                    left = box.left,
                                    top = box.top,
                                    right = box.right,
                                    bottom = box.bottom,
                                ),
                            )
                        }
                    }
                }
            }
        } finally {
            cropped.recycle()
        }
    }

    override fun close() {
        recognizer.close()
    }
}
