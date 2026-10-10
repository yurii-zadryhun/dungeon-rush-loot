package com.yurii.dungeonrushloot.runtime

import android.content.Context
import android.graphics.ImageDecoder
import android.net.Uri
import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import com.yurii.dungeonrushloot.model.EquipmentImportResult
import com.yurii.dungeonrushloot.model.RelativeRect

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

            // Main modal: line-level OCR is materially more stable here than
            // reassembling individual ML Kit words, especially for long titles
            // and outlined affix rows.
            val spans = ocr.recognizeLines(frame, crop, scale = 2.5f)

            // Level text lives inside the item icon and is visually the hardest
            // text on the card. A second tight 4x pass lets the shared parser
            // safely use a lone number when the "Lvl" glyphs are missed.
            val levelSpans = ocr.recognizeLines(frame, levelCrop, scale = 4.0f)

            bridge.importEquipment(spans, levelSpans)
        } finally {
            bitmap.recycle()
        }
    }
}
