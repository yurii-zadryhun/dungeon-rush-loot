package com.yurii.dungeonrushloot.data

import android.content.Context
import com.yurii.dungeonrushloot.model.DecisionEvent
import com.yurii.dungeonrushloot.model.DecisionLogEntry
import com.yurii.dungeonrushloot.model.LogSession
import com.yurii.dungeonrushloot.runtime.DecisionLogAdapter
import java.io.File
import java.io.FileOutputStream
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

class DecisionLogStore(context: Context) : DecisionLogAdapter {
    private val directory = File(context.filesDir, "decision-sessions").apply { mkdirs() }
    private val _sessions = MutableStateFlow<List<LogSession>>(emptyList())
    val sessions: StateFlow<List<LogSession>> = _sessions

    private val _activeSessionId = MutableStateFlow<String?>(null)
    val activeSessionId: StateFlow<String?> = _activeSessionId

    private val _revision = MutableStateFlow(0L)
    val revision: StateFlow<Long> = _revision

    init {
        migrateLegacyFile(context)
        closeInterruptedSessions()
        refreshSessions()
    }

    @Synchronized
    fun startSession(strategy: String): LogSession {
        endSession("Auto session replaced by a new start.")
        val now = Instant.now()
        val id = "session-" + SESSION_ID_FORMATTER.format(now)
        _activeSessionId.value = id
        appendRaw(
            id,
            sessionEvent(
                timestamp = now.toString(),
                strategy = strategy,
                action = "start",
                message = "Auto session started.",
            ),
        )
        refreshSessions()
        return requireNotNull(_sessions.value.firstOrNull { it.id == id })
    }

    @Synchronized
    fun endSession(message: String = "Auto session stopped.") {
        val id = _activeSessionId.value ?: return
        val strategy = sessionById(id)?.strategy
        appendRaw(
            id,
            sessionEvent(
                timestamp = Instant.now().toString(),
                strategy = strategy,
                action = "stop",
                message = message,
            ),
        )
        _activeSessionId.value = null
        refreshSessions()
    }

    @Synchronized
    override fun append(event: DecisionEvent, runtimeMessage: String?) {
        val id = _activeSessionId.value ?: return
        val json = JSONObject(event.rawJson)
        json.put(
            "runtime",
            JSONObject()
                .put("message", runtimeMessage ?: "")
                .put("logged_at", Instant.now().toString()),
        )
        appendRaw(id, json.toString())
    }

    @Synchronized
    override fun appendSystem(message: String) {
        val id = _activeSessionId.value ?: return
        appendRaw(
            id,
            JSONObject()
                .put("schema", 1)
                .put("timestamp", Instant.now().toString())
                .put("source", "android")
                .put("strategy", sessionById(id)?.strategy ?: JSONObject.NULL)
                .put("status", "runtime")
                .put("action", "check")
                .put("slot", JSONObject.NULL)
                .put("message", message)
                .put("equipped_score", JSONObject.NULL)
                .put("candidate_score", JSONObject.NULL)
                .put("runtime", JSONObject().put("message", message))
                .toString(),
        )
    }

    @Synchronized
    fun sizeBytes(sessionId: String): Long =
        existingSessionFile(sessionId).length()

    @Synchronized
    fun exportTo(sessionId: String, output: java.io.OutputStream) {
        existingSessionFile(sessionId).inputStream().use { it.copyTo(output) }
        output.flush()
    }

    private fun existingSessionFile(sessionId: String): File {
        require(sessionId.matches(Regex("""session-[A-Za-z0-9_-]+"""))) {
            "Invalid session file identifier."
        }
        val file = sessionFile(sessionId)
        require(file.isFile) { "Session log does not exist." }
        return file
    }

    fun loadLatest(sessionId: String, limit: Int): List<DecisionLogEntry> {
        val file = sessionFile(sessionId)
        if (!file.exists() || limit <= 0) return emptyList()
        return file.useLines { lines ->
            lines.takeLastSafe(limit)
                .mapNotNull { raw -> runCatching { DecisionLogEntry.fromJson(raw) }.getOrNull() }
                .asReversed()
        }
    }

    fun sessionById(id: String): LogSession? =
        _sessions.value.firstOrNull { it.id == id } ?: inspectSession(sessionFile(id))

    @Synchronized
    fun deleteSession(id: String) {
        if (_activeSessionId.value == id) return
        sessionFile(id).delete()
        refreshSessions()
        _revision.value += 1
    }

    private fun appendRaw(sessionId: String, raw: String) {
        val file = sessionFile(sessionId)
        file.parentFile?.mkdirs()
        FileOutputStream(file, true).use { stream ->
            val bytes = (raw + "\n").toByteArray(Charsets.UTF_8)
            stream.write(bytes)
            stream.flush()
            stream.fd.sync()
        }
        _revision.value += 1
    }

    private fun sessionEvent(
        timestamp: String,
        strategy: String?,
        action: String,
        message: String,
    ): String = JSONObject()
        .put("schema", 1)
        .put("timestamp", timestamp)
        .put("source", "android")
        .put("strategy", strategy ?: JSONObject.NULL)
        .put("status", "session")
        .put("action", action)
        .put("slot", JSONObject.NULL)
        .put("message", message)
        .put("equipped_score", JSONObject.NULL)
        .put("candidate_score", JSONObject.NULL)
        .put("runtime", JSONObject().put("message", message))
        .toString()

    private fun refreshSessions() {
        _sessions.value = directory
            .listFiles { file -> file.isFile && file.name.endsWith(".jsonl") }
            .orEmpty()
            .mapNotNull(::inspectSession)
            .sortedByDescending { it.startedAt }
    }

    private fun inspectSession(file: File): LogSession? {
        if (!file.exists()) return null
        var first: JSONObject? = null
        var last: JSONObject? = null
        var count = 0
        file.useLines { lines ->
            lines.forEach { raw ->
                if (raw.isBlank()) return@forEach
                val json = runCatching { JSONObject(raw) }.getOrNull() ?: return@forEach
                if (first == null) first = json
                last = json
                if (json.optString("status") !in setOf("session")) count += 1
            }
        }
        val start = first ?: return null
        val end = last
        val ended = end
            ?.takeIf { it.optString("status") == "session" && it.optString("action") == "stop" }
            ?.optString("timestamp")
            ?.takeIf(String::isNotBlank)
        return LogSession(
            id = file.name.removeSuffix(".jsonl"),
            startedAt = start.optString("timestamp"),
            endedAt = ended,
            strategy = start.optString("strategy").takeIf { it.isNotBlank() && it != "null" },
            eventCount = count,
            active = file.name.removeSuffix(".jsonl") == _activeSessionId.value,
        )
    }

    private fun closeInterruptedSessions() {
        directory
            .listFiles { file -> file.isFile && file.name.endsWith(".jsonl") }
            .orEmpty()
            .forEach { file ->
                val session = inspectSession(file) ?: return@forEach
                if (session.endedAt == null) {
                    appendRaw(
                        session.id,
                        sessionEvent(
                            timestamp = Instant.now().toString(),
                            strategy = session.strategy,
                            action = "stop",
                            message = "Session ended because the app process restarted.",
                        ),
                    )
                }
            }
    }

    private fun migrateLegacyFile(context: Context) {
        val legacy = File(context.filesDir, "decisions.jsonl")
        if (!legacy.exists() || legacy.length() == 0L) return
        val destination = File(directory, "session-legacy.jsonl")
        if (!destination.exists()) {
            legacy.renameTo(destination)
        }
    }

    private fun sessionFile(id: String): File = File(directory, "$id.jsonl")

    private fun Sequence<String>.takeLastSafe(count: Int): List<String> {
        val buffer = ArrayDeque<String>(count)
        for (line in this) {
            if (line.isBlank()) continue
            if (buffer.size == count) buffer.removeFirst()
            buffer.addLast(line)
        }
        return buffer.toList()
    }

    companion object {
        private val SESSION_ID_FORMATTER: DateTimeFormatter =
            DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss-SSS").withZone(ZoneOffset.UTC)
    }
}
