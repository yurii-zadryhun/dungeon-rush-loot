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
        ocr: OcrAdapter,
    ): EquipmentImportResult {
        val source = ImageDecoder.createSource(context.contentResolver, uri)
        val bitmap = ImageDecoder.decodeBitmap(source) { decoder, _, _ ->
            decoder.allocator = ImageDecoder.ALLOCATOR_SOFTWARE
        }
        return try {
            val spans = ocr.recognize(CapturedFrame(bitmap), crop)
            bridge.importEquipment(spans)
        } finally {
            bitmap.recycle()
        }
    }
}
