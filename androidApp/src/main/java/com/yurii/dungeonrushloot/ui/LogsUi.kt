package com.yurii.dungeonrushloot.ui

import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.data.DownloadsLogExporter
import com.yurii.dungeonrushloot.model.DecisionLogEntry
import com.yurii.dungeonrushloot.model.LogSession
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject

private const val LOG_PAGE_SIZE = 50
private const val APPLICATION_LOG_ID = "application"

@Composable
fun LogsScreen(graph: AppGraph, modifier: Modifier = Modifier) {
    val sessions by graph.logs.sessions.collectAsState()
    val logRevision by graph.logs.revision.collectAsState()
    val appRevision by graph.appLog.revision.collectAsState()
    val appLines by graph.appLog.lineCount.collectAsState()
    var openedLogId by rememberSaveable { mutableStateOf<String?>(null) }
    val activeLog = sessions.firstOrNull { it.id == openedLogId }

    BackHandler(enabled = openedLogId != null) { openedLogId = null }

    if (openedLogId == null) {
        LogsBrowser(
            sessions = sessions,
            appLines = appLines,
            appBytes = remember(appRevision) { graph.appLog.sizeBytes },
            sessionSize = graph.logs::sizeBytes,
            onOpen = { openedLogId = it },
            modifier = modifier,
        )
    } else if (openedLogId == APPLICATION_LOG_ID || activeLog != null) {
        LogsDetail(
            graph = graph,
            session = activeLog,
            application = openedLogId == APPLICATION_LOG_ID,
            revision = if (openedLogId == APPLICATION_LOG_ID) appRevision else logRevision,
            onBack = { openedLogId = null },
            modifier = modifier,
        )
    } else {
        // A session may be removed while its detail screen is open.
        LaunchedEffect(openedLogId) { openedLogId = null }
    }
}

@Composable
private fun LogsBrowser(
    sessions: List<LogSession>,
    appLines: Int,
    appBytes: Long,
    sessionSize: (String) -> Long,
    onOpen: (String) -> Unit,
    modifier: Modifier,
) {
    LazyColumn(
        modifier = modifier.fillMaxSize().padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        item {
            Text("Logs", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
            Text("Open a log to inspect its events or export its JSONL file to Downloads.",
                style = MaterialTheme.typography.bodySmall)
        }
        item {
            LogFileRow(
                title = "Application log",
                subtitle = "$appLines events · ${formatBytes(appBytes)}",
                onClick = { onOpen(APPLICATION_LOG_ID) },
            )
        }
        item {
            HorizontalDivider()
            Text(
                "Session logs",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.padding(top = 8.dp),
                fontWeight = FontWeight.Bold,
            )
        }
        if (sessions.isEmpty()) {
            item { Text("No Auto sessions yet.", color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        items(sessions, key = { it.id }) { session ->
            LogFileRow(
                title = "${session.id}.jsonl",
                subtitle = "${session.strategy?.uppercase() ?: "UNKNOWN"} · " +
                    "${session.eventCount} decisions · ${formatBytes(sessionSize(session.id))}" +
                    if (session.active) " · ACTIVE" else "",
                onClick = { onOpen(session.id) },
            )
        }
    }
}

@Composable
private fun LogFileRow(title: String, subtitle: String, onClick: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth().clickable(onClick = onClick)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(modifier = Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(title, fontWeight = FontWeight.Bold, style = MaterialTheme.typography.bodyMedium)
                Text(subtitle, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text("›", style = MaterialTheme.typography.headlineSmall)
        }
    }
}

@Composable
private fun LogsDetail(
    graph: AppGraph,
    session: LogSession?,
    application: Boolean,
    revision: Long,
    onBack: () -> Unit,
    modifier: Modifier,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val fileName = if (application) graph.appLog.exportFileName else "${requireNotNull(session).id}.jsonl"
    var exporting by remember { mutableStateOf(false) }
    var visibleCount by rememberSaveable(fileName) { mutableIntStateOf(LOG_PAGE_SIZE) }
    val listState = rememberLazyListState()
    val appEntries = if (application) {
        remember(revision, visibleCount) { graph.appLog.loadLatest(visibleCount) }
    } else emptyList()
    val sessionEntries = if (!application && session != null) {
        remember(fileName, revision, visibleCount) {
            graph.logs.loadLatest(session.id, visibleCount)
        }
    } else emptyList()

    LaunchedEffect(fileName) {
        visibleCount = LOG_PAGE_SIZE
        listState.scrollToItem(0)
    }
    val rowCount = if (application) appEntries.size else sessionEntries.size
    LaunchedEffect(fileName, listState, rowCount, visibleCount) {
        snapshotFlow { listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }
            .distinctUntilChanged()
            .collect { last ->
                if (rowCount >= visibleCount && last >= rowCount - 5) {
                    visibleCount += LOG_PAGE_SIZE
                }
            }
    }

    Column(modifier.fillMaxSize().padding(16.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            TextButton(onClick = onBack) { Text("‹ Back") }
            Text(if (application) "Application log" else "Session log",
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
                fontWeight = FontWeight.Bold)
            OutlinedButton(
                enabled = !exporting,
                onClick = {
                    exporting = true
                    scope.launch {
                        val failure = runCatching {
                            withContext(Dispatchers.IO) {
                                DownloadsLogExporter(context.applicationContext).save(fileName) { output ->
                                    if (application) graph.appLog.exportTo(output)
                                    else graph.logs.exportTo(requireNotNull(session).id, output)
                                }
                            }
                        }.exceptionOrNull()
                        exporting = false
                        if (failure == null) {
                            Toast.makeText(context, "Saved to Downloads: $fileName", Toast.LENGTH_LONG).show()
                        } else {
                            graph.appLog.error(
                                category = "log_export",
                                event = "failed",
                                message = "Could not export $fileName to Downloads.",
                                throwable = failure,
                            )
                            Toast.makeText(context, failure.message ?: "Export failed", Toast.LENGTH_LONG).show()
                        }
                    }
                },
            ) { Text(if (exporting) "Saving…" else "Export") }
        }
        Text(fileName, style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(bottom = 10.dp))
        if (rowCount == 0) {
            Text("No entries yet.", modifier = Modifier.padding(top = 12.dp))
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (application) {
                    itemsIndexed(appEntries, key = { index, raw -> index.toString() + "-" + raw.hashCode() }) { _, raw ->
                        ApplicationEventCard(raw)
                    }
                } else {
                    items(sessionEntries, key = { it.timestamp + it.rawJson.hashCode() }) { entry ->
                        DecisionSummaryCard(entry)
                    }
                }
            }
        }
    }
}

@Composable
private fun ApplicationEventCard(raw: String) {
    val json = remember(raw) { runCatching { JSONObject(raw) }.getOrNull() }
    var expanded by remember(raw) { mutableStateOf(false) }
    val level = json?.optString("level").orEmpty()
    val name = json?.optString("category").orEmpty() + " · " +
        json?.optString("event").orEmpty()

    Card(modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded }) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(name, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f))
                Text(shortTime(json?.optString("timestamp").orEmpty()))
            }
            Text("${level.uppercase()} · ${json?.optString("message").orEmpty()}",
                style = MaterialTheme.typography.bodySmall)
            if (expanded) {
                Text(json?.toString(2) ?: raw,
                    style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
fun DecisionSummaryCard(entry: DecisionLogEntry) {
    var expanded by remember(entry.rawJson) { mutableStateOf(false) }
    val container = when {
        entry.status == "session" -> MaterialTheme.colorScheme.surfaceVariant
        entry.status == "runtime" -> MaterialTheme.colorScheme.tertiaryContainer
        entry.status != "ok" -> MaterialTheme.colorScheme.tertiaryContainer
        entry.action == "equip" -> MaterialTheme.colorScheme.primaryContainer
        else -> MaterialTheme.colorScheme.errorContainer
    }

    Card(
        colors = CardDefaults.cardColors(containerColor = container),
        modifier = Modifier.fillMaxWidth().clickable { expanded = !expanded },
    ) {
        Column(Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(label(entry), fontWeight = FontWeight.Bold)
                Text(shortTime(entry.timestamp))
            }

            val scores = scoreText(entry)
            if (scores.isNotBlank()) Text(scores)
            entry.runtimeMessage?.let { Text(it, style = MaterialTheme.typography.bodySmall) }

            if (expanded) {
                Text(entry.message, style = MaterialTheme.typography.bodySmall)
                val json = remember(entry.rawJson) { runCatching { JSONObject(entry.rawJson) }.getOrNull() }
                json?.let { ComparisonDetails(it) }
            }
        }
    }
}

@Composable
private fun ComparisonDetails(json: JSONObject) {
    val equipped = json.optJSONObject("equipped")
    val candidate = json.optJSONObject("candidate")
    if (equipped == null && candidate == null) return

    Row(
        Modifier.fillMaxWidth().padding(top = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        ItemColumn("EQUIPPED", equipped, Modifier.weight(1f))
        ItemColumn("CANDIDATE", candidate, Modifier.weight(1f))
    }

    val equippedScore = json.optJSONObject("equipped_score")
    val candidateScore = json.optJSONObject("candidate_score")
    if (equippedScore != null || candidateScore != null) {
        Row(
            Modifier.fillMaxWidth().padding(top = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            ScoreColumn("BUILD BEFORE", equippedScore, Modifier.weight(1f))
            ScoreColumn("BUILD AFTER", candidateScore, Modifier.weight(1f))
        }
    }
}

@Composable
private fun ItemColumn(title: String, item: JSONObject?, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        if (item == null) {
            Text("—")
            return
        }
        Text(item.optString("rarity") + " Lv" + item.optInt("level"))
        val stats = item.optJSONArray("stats") ?: JSONArray()
        repeat(stats.length()) { index ->
            val stat = stats.optJSONObject(index) ?: return@repeat
            Text(
                formatStat(stat.optDouble("value"), stat.optString("name")),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

@Composable
private fun ScoreColumn(title: String, score: JSONObject?, modifier: Modifier) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(title, style = MaterialTheme.typography.labelMedium, fontWeight = FontWeight.Bold)
        if (score == null) {
            Text("—")
            return
        }
        Text("Total " + formatOne(score.optDouble("total")))
        Text("Combat " + formatOne(score.optDouble("combat")), style = MaterialTheme.typography.bodySmall)
        Text("Flex " + formatOne(score.optDouble("flexibility")), style = MaterialTheme.typography.bodySmall)
        val stats = score.optJSONArray("stats") ?: JSONArray()
        repeat(stats.length()) { index ->
            val stat = stats.optJSONObject(index) ?: return@repeat
            val raw = stat.optDouble("raw")
            val effective = stat.optDouble("effective")
            if (effective + 0.001 < raw) {
                Text(
                    stat.optString("name") + " " + formatOne(raw) + "→" + formatOne(effective),
                    color = MaterialTheme.colorScheme.error,
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

private fun label(entry: DecisionLogEntry): String = when {
    entry.status == "session" && entry.action == "start" -> "SESSION START"
    entry.status == "session" && entry.action == "stop" -> "SESSION STOP"
    entry.status == "runtime" -> "RUNTIME"
    entry.status != "ok" -> "CHECK OCR"
    entry.action == "equip" -> "EQUIP" + (entry.slot?.let { " · " + it.uppercase() } ?: "")
    else -> "SELL" + (entry.slot?.let { " · " + it.uppercase() } ?: "")
}

private fun scoreText(entry: DecisionLogEntry): String {
    val before = entry.equippedScore
    val after = entry.candidateScore
    if (before == null || after == null) return entry.strategy?.uppercase().orEmpty()
    val arrow = if (entry.action == "equip") " → " else " vs "
    return (entry.strategy?.uppercase()?.plus(" · ") ?: "") +
        formatOne(before) + arrow + formatOne(after)
}

private fun shortTime(value: String): String =
    value.substringAfter('T', value).take(8)

private fun shortDateTime(value: String): String {
    val date = value.take(10)
    val time = shortTime(value)
    return date + " " + time
}

private fun formatOne(value: Double): String =
    if (value.isNaN()) "—" else String.format(Locale.US, "%.1f", value)

private fun formatBytes(bytes: Long): String = when {
    bytes >= 1024L * 1024L -> String.format(Locale.US, "%.1f MB", bytes / (1024.0 * 1024.0))
    bytes >= 1024L -> String.format(Locale.US, "%.1f KB", bytes / 1024.0)
    else -> "$bytes B"
}

private fun formatStat(value: Double, name: String): String =
    String.format(Locale.US, "%+.2f%% %s", value, name)
