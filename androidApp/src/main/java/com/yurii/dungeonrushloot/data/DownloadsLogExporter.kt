package com.yurii.dungeonrushloot.data

import android.content.ContentValues
import android.content.Context
import android.os.Environment
import android.provider.MediaStore
import java.io.OutputStream

/**
 * Exports a snapshot of an app-owned JSONL file straight to public Downloads.
 *
 * Android 11+ (minSdk=30): MediaStore.Downloads does not require storage
 * permissions or a system document-picker confirmation. A pending entry is
 * never exposed if the write fails.
 */
class DownloadsLogExporter(private val context: Context) {
    fun save(fileName: String, write: (OutputStream) -> Unit): String {
        require(fileName.matches(Regex("""[A-Za-z0-9._-]+\\.jsonl"""))) {
            "Invalid JSONL export filename."
        }

        val resolver = context.contentResolver
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, fileName)
            put(MediaStore.MediaColumns.MIME_TYPE, "application/x-ndjson")
            put(
                MediaStore.MediaColumns.RELATIVE_PATH,
                Environment.DIRECTORY_DOWNLOADS + "/",
            )
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = requireNotNull(resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)) {
            "Unable to create file in Downloads."
        }
        try {
            requireNotNull(resolver.openOutputStream(uri, "w")) {
                "Unable to open Downloads file."
            }.use(write)

            resolver.update(
                uri,
                ContentValues().apply { put(MediaStore.MediaColumns.IS_PENDING, 0) },
                null,
                null,
            )
            return fileName
        } catch (error: Exception) {
            resolver.delete(uri, null, null)
            throw error
        }
    }
}
