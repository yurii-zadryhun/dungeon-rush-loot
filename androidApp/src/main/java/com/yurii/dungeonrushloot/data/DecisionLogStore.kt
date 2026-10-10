package com.yurii.dungeonrushloot.data

import android.content.Context
import com.yurii.dungeonrushloot.model.DecisionEvent
import com.yurii.dungeonrushloot.model.DecisionLogEntry
import com.yurii.dungeonrushloot.runtime.DecisionLogAdapter
import java.io.File
import java.time.Instant
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

class DecisionLogStore(context: Context) : DecisionLogAdapter {
    private val file = File(context.filesDir, "decisions.jsonl")
    private val _entries = MutableStateFlow(loadEntries())
    val entries: StateFlow<List<DecisionLogEntry>> = _entries

    @Synchronized
    override fun append(event: DecisionEvent, runtimeMessage: String?) {
        val json = JSONObject(event.rawJson)
        json.put(
            "runtime",
            JSONObject()
                .put("message", runtimeMessage ?: "")
                .put("logged_at", Instant.now().toString()),
        )
        appendRaw(json.toString())
    }

    @Synchronized
    override fun appendSystem(message: String) {
        val json = JSONObject()
            .put("schema", 1)
            .put("timestamp", Instant.now().toString())
            .put("source", "android")
            .put("strategy", JSONObject.NULL)
            .put("status", "runtime")
            .put("action", "check")
            .put("slot", JSONObject.NULL)
            .put("message", message)
            .put("equipped_score", JSONObject.NULL)
            .put("candidate_score", JSONObject.NULL)
            .put("runtime", JSONObject().put("message", message))
        appendRaw(json.toString())
    }

    @Synchronized
    fun clear() {
        if (file.exists()) file.writeText("")
        _entries.value = emptyList()
    }

    private fun appendRaw(raw: String) {
        file.parentFile?.mkdirs()
        file.appendText(raw + "\n")
        val entry = DecisionLogEntry.fromJson(raw)
        _entries.value = (_entries.value + entry).takeLast(MAX_ENTRIES)
    }

    private fun loadEntries(): List<DecisionLogEntry> {
        if (!file.exists()) return emptyList()
        return file.useLines { lines ->
            lines.takeLastSafe(MAX_ENTRIES)
                .mapNotNull { raw -> runCatching { DecisionLogEntry.fromJson(raw) }.getOrNull() }
        }
    }

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
        private const val MAX_ENTRIES = 500
    }
}
