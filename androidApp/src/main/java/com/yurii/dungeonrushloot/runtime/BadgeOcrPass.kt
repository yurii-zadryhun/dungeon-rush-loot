package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import org.json.JSONArray
import org.json.JSONObject

data class BadgeOcrPass(
    val kind: String,
    val crop: RelativeRect,
    val scale: Float,
    val lightText: Boolean,
    val lines: List<OcrSpanDto>,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("kind", kind)
        .put("scale", scale)
        .put("light_text", lightText)
        .put("crop", JSONObject()
            .put("left", crop.left).put("top", crop.top)
            .put("right", crop.right).put("bottom", crop.bottom))
        .put("ocr_lines", JSONArray().apply { lines.forEach { put(it.toJson()) } })
}