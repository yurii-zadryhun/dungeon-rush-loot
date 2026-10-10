package com.yurii.dungeonrushloot.runtime

import android.content.Context
import android.graphics.ImageDecoder
import android.net.Uri
import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import com.yurii.dungeonrushloot.model.EquipmentImportResult
import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.abs
import org.json.JSONArray
import org.json.JSONObject

class EquipmentScreenshotImporter(
    private val context: Context,
    private val bridge: PythonDecisionBridge,
    private val appLog: ApplicationLogAdapter,
    private val crop: RelativeRect,
    private val levelCrop: RelativeRect,
) {
    suspend fun import(uris: List<Uri>): List<EquipmentImportResult> {
        val ocr = MlKitOcrAdapter()
        return try {
            uris.mapIndexed { index, uri -> importOne(index, uri, ocr) }
        } finally {
            ocr.close()
        }
    }

    private suspend fun importOne(
        index: Int,
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
            val main25 = recognizePass(ocr, frame, crop, index, "main_2_5x", 2.5f)
            val main35 = recognizePass(ocr, frame, crop, index, "main_3_5x", 3.5f)
            val spans = mergeRows(main25, main35)

            // Level text is drawn over the icon and is much harder than the
            // card text. Run two aggressive passes over only that tiny region.
            // The shared parser can safely accept a lone integer from this crop
            // even when ML Kit misses the outlined "Lvl" glyphs.
            val level35 = recognizePass(ocr, frame, levelCrop, index, "level_3_5x", 3.5f)
            val level50 = recognizePass(ocr, frame, levelCrop, index, "level_5_0x", 5.0f)
            var levelSpans = mergeRows(level35, level50)
            var result = bridge.importEquipment(spans, levelSpans)

            if ("Could not parse level." in result.issues) {
                // Last resort: extract bright level glyphs from the icon on a
                // white background. Run it only when normal OCR could not read
                // the level; both raw passes and this fallback are exported.
                val lightText = recognizePass(
                    ocr, frame, levelCrop, index,
                    "level_light_text_5_0x", 5.0f, lightText = true,
                )
                levelSpans = mergeRows(levelSpans, lightText)
                result = bridge.importEquipment(spans, levelSpans)
            }
            appLog.info(
                category = "equipment_import",
                event = "image_processed",
                message = "Equipment screenshot OCR and parsing completed.",
                details = JSONObject()
                    .put("image_index", index)
                    .put("image_width", bitmap.width)
                    .put("image_height", bitmap.height)
                    .put("main_2_5x", spansJson(main25))
                    .put("main_3_5x", spansJson(main35))
                    .put("main_merged", spansJson(spans))
                    .put("level_3_5x", spansJson(level35))
                    .put("level_5_0x", spansJson(level50))
                    .put("level_merged", spansJson(levelSpans))
                    .put(
                        "parser_result",
                        runCatching { JSONObject(result.rawJson) }
                            .getOrElse { JSONObject().put("raw", result.rawJson) },
                    ),
            )
            result
        } finally {
            bitmap.recycle()
        }
    }

    /**
     * Persist the raw OCR output immediately after each pass. If a later pass or
     * Python parsing fails, earlier evidence still survives in the exported log.
     */
    private suspend fun recognizePass(
        ocr: MlKitOcrAdapter,
        frame: CapturedFrame,
        bounds: RelativeRect,
        imageIndex: Int,
        name: String,
        scale: Float,
        lightText: Boolean = false,
    ): List<OcrSpanDto> {
        return try {
            ocr.recognizeLines(frame, bounds, scale, lightText = lightText).also { spans ->
                appLog.info(
                    category = "equipment_import",
                    event = "ocr_pass",
                    message = "Equipment screenshot OCR pass completed.",
                    details = JSONObject()
                        .put("image_index", imageIndex)
                        .put("pass", name)
                        .put("scale", scale.toDouble())
                        .put("light_text", lightText)
                        .put("lines", spansJson(spans)),
                )
            }
        } catch (error: Exception) {
            appLog.error(
                category = "equipment_import",
                event = "ocr_pass_failed",
                message = "Equipment screenshot OCR pass failed.",
                throwable = error,
                details = JSONObject()
                    .put("image_index", imageIndex)
                    .put("pass", name)
                    .put("scale", scale.toDouble())
                    .put("light_text", lightText),
            )
            throw error
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
        // Preserve a correctly recognized percentage from one pass over a
        // longer but corrupted line from another pass (e.g. "80.0l." vs "80.0%").
        val hasIntactPercent = INTACT_PERCENT_RE.containsMatchIn(span.text)
        return usefulCharacters + span.score.toDouble() + if (hasIntactPercent) 100.0 else 0.0
    }

    private fun spansJson(spans: List<OcrSpanDto>): JSONArray =
        JSONArray().apply {
            spans.forEach { put(it.toJson()) }
        }

    companion object {
        private val INTACT_PERCENT_RE = Regex("""[+-]\s*\d{1,3}(?:[.,]\d{1,2})?\s*%""")
        private const val ROW_MATCH_TOLERANCE_PX = 14
    }
}
