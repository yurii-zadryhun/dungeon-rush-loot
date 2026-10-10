package com.yurii.dungeonrushloot.data

import android.content.Context
import android.graphics.Bitmap
import com.yurii.dungeonrushloot.model.DecisionEvent
import com.yurii.dungeonrushloot.model.RelativeRect
import com.yurii.dungeonrushloot.runtime.CapturedFrame
import com.yurii.dungeonrushloot.runtime.OcrDebugSnapshot
import java.io.ByteArrayOutputStream
import java.io.OutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.json.JSONArray
import org.json.JSONObject

/** Single diagnostic ZIP: no screenshots are retained in app storage. */
class OcrDebugExporter(private val context: Context) {
    fun export(
        frame: CapturedFrame,
        snapshot: OcrDebugSnapshot,
        relativeCrop: RelativeRect,
        decision: DecisionEvent?,
    ): String {
        val timestamp = SimpleDateFormat("yyyyMMdd-HHmmss-SSS", Locale.US).apply {
            timeZone = TimeZone.getTimeZone("UTC")
        }.format(Date(frame.capturedAtMillis))
        val name = "dungeon-rush-ocr-debug-$timestamp.zip"

        val meta = JSONObject()
            .put("schema_version", 1)
            .put("capture_timestamp_ms", frame.capturedAtMillis)
            .put("frame_width", frame.bitmap.width)
            .put("frame_height", frame.bitmap.height)
            .put("ocr_scale", snapshot.scale.toDouble())
            .put("ocr_crop_relative", JSONObject()
                .put("left", relativeCrop.left.toDouble())
                .put("top", relativeCrop.top.toDouble())
                .put("right", relativeCrop.right.toDouble())
                .put("bottom", relativeCrop.bottom.toDouble()))
            .put("ocr_crop_pixels", JSONObject()
                .put("left", snapshot.cropLeft)
                .put("top", snapshot.cropTop)
                .put("right", snapshot.cropRight)
                .put("bottom", snapshot.cropBottom))
            .put("ocr_input_width", snapshot.inputWidth)
            .put("ocr_input_height", snapshot.inputHeight)
            .put("ocr_input_rotation_degrees", 0)
            .put("span_coordinate_space", "original full-screen screenshot pixels")
            .put("ocr_lines", JSONArray().apply {
                snapshot.spans.forEach { put(it.toJson()) }
            })
            .put("parser_decision", decision?.let { JSONObject(it.rawJson) } ?: JSONObject.NULL)

        return DownloadsLogExporter(context).saveZip(name) { output ->
            OcrDebugZip.write(
                output,
                linkedMapOf(
                    "screen.png" to encodePng(frame.bitmap),
                    "ocr-crop.png" to snapshot.cropPng,
                    "ocr-input.png" to snapshot.inputPng,
                    "ocr.json" to meta.toString(2).toByteArray(Charsets.UTF_8),
                ),
            )
        }
    }

    private fun encodePng(bitmap: Bitmap): ByteArray = ByteArrayOutputStream().use { output ->
        check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, output)) {
            "Could not encode original accessibility screenshot."
        }
        output.toByteArray()
    }
}

/** Pure JDK implementation; unit tests can inspect all four entries. */
object OcrDebugZip {
    val filenames = listOf("screen.png", "ocr-crop.png", "ocr-input.png", "ocr.json")

    fun write(output: OutputStream, files: Map<String, ByteArray>) {
        require(files.keys.toList() == filenames) {
            "Invalid OCR debug ZIP contents or entry order."
        }
        ZipOutputStream(output).use { zip ->
            files.forEach { (name, bytes) ->
                zip.putNextEntry(ZipEntry(name))
                zip.write(bytes)
                zip.closeEntry()
            }
        }
    }
}
