package com.yurii.dungeonrushloot.runtime

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** One latest diagnostic image in Downloads, rather than unbounded screenshots. */
class BadgeOcrImageWriter(context: Context) {
    private val resolver = context.applicationContext.contentResolver
    private val preferences = context.applicationContext.getSharedPreferences("ocr-diagnostics", Context.MODE_PRIVATE)

    suspend fun save(frame: CapturedFrame): String? = withContext(Dispatchers.IO) {
        if (frame.badgeOcrPasses.isEmpty()) return@withContext null
        val image = requireNotNull(frame.bitmap.copy(Bitmap.Config.ARGB_8888, true))
        try {
            val canvas = Canvas(image)
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                strokeWidth = 2f
                textSize = (image.width / 55f).coerceAtLeast(14f)
            }
            frame.badgeOcrPasses.forEachIndexed { index, pass ->
                paint.color = Color.CYAN
                paint.style = Paint.Style.STROKE
                val roi = OcrCropPixels.from(pass.crop, image.width, image.height)
                canvas.drawRect(roi.left.toFloat(), roi.top.toFloat(), roi.right.toFloat(), roi.bottom.toFloat(), paint)
                pass.lines.forEach { line ->
                    canvas.drawRect(line.left.toFloat(), line.top.toFloat(), line.right.toFloat(), line.bottom.toFloat(), paint)
                }
                paint.style = Paint.Style.FILL
                val label = "${index + 1}: ${pass.kind} ${pass.scale}x" +
                    if (pass.lightText) " light" else " normal"
                canvas.drawText(label, roi.right + 4f, roi.top + paint.textSize * (index + 1), paint)
                pass.lines.forEach { line ->
                    canvas.drawText("${index + 1}: ${line.text}", line.right + 4f, line.bottom.toFloat(), paint)
                }
            }
            paint.color = Color.WHITE
            paint.style = Paint.Style.FILL
            canvas.drawText("Rarity / level OCR - ${frame.capturedAtMillis}", 16f, paint.textSize * 2, paint)
            write(image).toString()
        } finally {
            image.recycle()
        }
    }

    private fun write(image: Bitmap): Uri {
        val previous = preferences.getString("image_uri", null)?.let(Uri::parse)
        val existing = previous?.takeIf { uri ->
            resolver.query(uri, arrayOf(MediaStore.MediaColumns._ID), null, null, null)?.use {
                it.moveToFirst()
            } == true
        }
        val uri = existing ?: requireNotNull(resolver.insert(
            MediaStore.Downloads.EXTERNAL_CONTENT_URI,
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, "rarity-level-annotated.jpg")
                put(MediaStore.MediaColumns.MIME_TYPE, "image/jpeg")
                put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/DungeonRushLoot/")
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            },
        )) { "Unable to create rarity/level image in Downloads." }
        try {
            requireNotNull(resolver.openOutputStream(uri, "wt")) {
                "Unable to open rarity/level image."
            }.use { output ->
                check(image.compress(Bitmap.CompressFormat.JPEG, 95, output)) { "Unable to encode rarity/level image." }
            }
            check(resolver.update(uri, ContentValues().apply {
                put(MediaStore.MediaColumns.IS_PENDING, 0)
            }, null, null) == 1) { "Unable to publish rarity/level image." }
            preferences.edit().putString("image_uri", uri.toString()).apply()
            return uri
        } catch (error: Exception) {
            if (existing == null) resolver.delete(uri, null, null)
            throw error
        }
    }
}