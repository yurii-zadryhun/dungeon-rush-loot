package com.yurii.dungeonrushloot.runtime

import android.content.Context
import android.graphics.ImageDecoder
import android.net.Uri
import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import com.yurii.dungeonrushloot.model.EquipmentImportResult
import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.abs

class EquipmentScreenshotImporter(
    private val context: Context,
    private val bridge: PythonDecisionBridge,
    private val crop: RelativeRect,
    private val levelCrop: RelativeRect,
) {
    suspend fun import(uris: List<Uri>): List<EquipmentImportResult> {
        val ocr = MlKitOcrAdapter()
        return try {
            uris.map { uri -> importOne(uri, ocr) }
        } finally {
            ocr.close()
        }
    }

    private suspend fun importOne(
        uri: Uri,
        ocr: MlKitOcrAdapter,
    ): EquipmentImportResult {
        val source = ImageDecoder.createSource(context.contentResolver, uri)
        val bitmap = ImageDecoder.decodeBitmap(source) { decoder, _, _ ->
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }
        return try {
            val frame = CapturedFrame(bitmap)

            // Current equipment cards are static, so we can afford two OCR
            // scales. ML Kit occasionally misses one outlined row at one scale
            // while recognizing it cleanly at another. Merge by physical row
            // and keep the richer recognition instead of passing duplicates to
            // the shared parser.
            val main25 = ocr.recognizeLines(frame, crop, scale = 2.5f)
            val main35 = ocr.recognizeLines(frame, crop, scale = 3.5f)
            val spans = mergeRows(main25, main35)

            // Level text is drawn over the icon and is much harder than the
            // card text. Run two aggressive passes over only that tiny region.
            // The shared parser can safely accept a lone integer from this crop
            // even when ML Kit misses the outlined "Lvl" glyphs.
            val level35 = ocr.recognizeLines(frame, levelCrop, scale = 3.5f)
            val level50 = ocr.recognizeLines(frame, levelCrop, scale = 5.0f)
            val levelSpans = mergeRows(level35, level50)

            bridge.importEquipment(spans, levelSpans)
        } finally {
            bitmap.recycle()
        }
    }

    private fun mergeRows(
        first: List<OcrSpanDto>,
        second: List<OcrSpanDto>,
    ): List<OcrSpanDto> {
        val merged = first.toMutableList()

        second.forEach { candidate ->
            val index = merged.indices.minByOrNull { index ->
                rowDistance(merged[index], candidate)
            }
            val existing = index?.let(merged::get)
            if (
                index == null ||
                existing == null ||
                rowDistance(existing, candidate) > ROW_MATCH_TOLERANCE_PX
            ) {
                merged += candidate
            } else if (quality(candidate) > quality(existing)) {
                merged[index] = candidate
            }
        }

        return merged.sortedWith(compareBy<OcrSpanDto> { centerY(it) }.thenBy { it.left })
    }

    private fun rowDistance(left: OcrSpanDto, right: OcrSpanDto): Int =
        abs(centerY(left) - centerY(right))

    private fun centerY(span: OcrSpanDto): Int = (span.top + span.bottom) / 2

    private fun quality(span: OcrSpanDto): Double {
        val usefulCharacters = span.text.count { it.isLetterOrDigit() || it in "+-.%[]" }
        return usefulCharacters + span.score.toDouble()
    }

    companion object {
        private const val ROW_MATCH_TOLERANCE_PX = 14
    }
}
