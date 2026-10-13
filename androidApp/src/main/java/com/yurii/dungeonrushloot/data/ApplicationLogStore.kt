package com.yurii.dungeonrushloot.data

import android.os.Build
import com.yurii.dungeonrushloot.BuildConfig
import com.yurii.dungeonrushloot.runtime.ApplicationLogAdapter
import java.io.File
import java.io.FileOutputStream
import java.io.OutputStream
import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

class ApplicationLogStore(
    private val file: File,
) : ApplicationLogAdapter {
    private val _revision = MutableStateFlow(0L)
    val revision: StateFlow<Long> = _revision

    private val _lineCount = MutableStateFlow(countExistingLines())
    val lineCount: StateFlow<Int> = _lineCount

    val sizeBytes: Long
        get() = file.length()

    val exportFileName: String
        get() = "dungeon-rush-app-log.jsonl"

    init {
        info(
            category = "app",
            event = "log_opened",
            message = "Application log opened.",
            details = JSONObject()
                .put("app_version", BuildConfig.VERSION_NAME)
                .put("version_code", BuildConfig.VERSION_CODE)
                .put("manufacturer", Build.MANUFACTURER)
                .put("model", Build.MODEL)
                .put("sdk", Build.VERSION.SDK_INT),
        )
    }

    override fun info(
        category: String,
        event: String,
        message: String,
        details: JSONObject?,
    ) {
        append("info", category, event, message, details, null)
    }

    override fun warning(
        category: String,
        event: String,
        message: String,
        details: JSONObject?,
    ) {
        append("warning", category, event, message, details, null)
    }

    override fun error(
        category: String,
        event: String,
        message: String,
        throwable: Throwable?,
        details: JSONObject?,
    ) {
        append("error", category, event, message, details, throwable)
    }

    @Synchronized
    fun loadLatest(limit: Int): List<String> {
        if (limit <= 0 || !file.exists()) return emptyList()
        val tail = ArrayDeque<String>(limit)
        file.forEachLine { raw ->
            if (raw.isNotBlank()) {
                if (tail.size == limit) tail.removeFirst()
                tail.addLast(raw)
            }
        }
        return tail.toList().asReversed()
    }

    @Synchronized
    fun exportTo(output: OutputStream) {
        FileOutputStream(file, true).use { stream ->
            stream.flush()
            stream.fd.sync()
        }
        file.inputStream().use { input ->
            input.copyTo(output)
            output.flush()
        }
    }

    @Synchronized
    private fun append(
        level: String,
        category: String,
        event: String,
        message: String,
        details: JSONObject?,
        throwable: Throwable?,
    ) {
        val json = JSONObject()
            .put("schema", 1)
            .put("timestamp", Instant.now().toString())
            .put("level", level)
            .put("category", category)
            .put("event", event)
            .put("message", message)
            .put("app_version", BuildConfig.VERSION_NAME)
            .put("version_code", BuildConfig.VERSION_CODE)

        if (details != null) {
            json.put("details", details)
        }
        if (throwable != null) {
            json.put(
                "exception",
                JSONObject()
                    .put("type", throwable::class.java.name)
                    .put("message", throwable.message ?: JSONObject.NULL)
                    .put("stacktrace", throwable.stackTraceToString()),
            )
        }

        file.parentFile?.mkdirs()
        FileOutputStream(file, true).use { stream ->
            stream.write((json.toString() + "\n").toByteArray(Charsets.UTF_8))
            stream.flush()
            stream.fd.sync()
        }
        _lineCount.value += 1
        _revision.value += 1
    }

    private fun countExistingLines(): Int {
        if (!file.exists()) return 0
        return file.useLines { lines -> lines.count { it.isNotBlank() } }
    }

    companion object {
        fun createIn(filesDir: File): ApplicationLogStore =
            ApplicationLogStore(File(filesDir, "application-log.jsonl"))
    }
}
