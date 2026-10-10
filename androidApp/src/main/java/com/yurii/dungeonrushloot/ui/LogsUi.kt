package com.yurii.dungeonrushloot.ui

import android.widget.Toast
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
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

@Composable
fun LogsScreen(graph: AppGraph, modifier: Modifier = Modifier) {
    val sessions by graph.logs.sessions.collectAsState()
    val activeSessionId by graph.logs.activeSessionId.collectAsState()
    val revision by graph.logs.revision.collectAsState()
    val appLogRevision by graph.appLog.revision.collectAsState()
    val appLogLineCount by graph.appLog.lineCount.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()

    val exportAppLog = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.CreateDocument("application/x-ndjson"),
    ) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            val failure = runCatching {
                withContext(Dispatchers.IO) {
                    graph.appLog.info(
                        category = "app_log",
                        event = "export_started",
                        message = "Application log export started.",
                    )
                    val output = requireNotNull(context.contentResolver.openOutputStream(uri, "w")) {
                        "Could not open export destination."
                    }
                    output.use(graph.appLog::exportTo)
                }
            }.exceptionOrNull()

            if (failure == null) {
                Toast.makeText(context, "Application log exported", Toast.LENGTH_SHORT).show()
            } else {
                graph.appLog.error(
                    category = "app_log",
                    event = "export_failed",
                    message = "Application log export failed.",
                    throwable = failure,
                )
                Toast.makeText(
                    context,
                    failure.message ?: "Export failed",
                    Toast.LENGTH_LONG,
                ).show()
            }
        }
    }

    var selectedId by rememberSaveable { mutableStateOf<String?>(null) }
    var visibleCount by rememberSaveable { mutableIntStateOf(LOG_PAGE_SIZE) }
    val listState = rememberLazyListState()

    LaunchedEffect(activeSessionId, sessions) {
        val available = sessions.map { it.id }.toSet()
        selectedId = when {
            activeSessionId != null -> activeSessionId
            selectedId in available -> selectedId
            else -> sessions.firstOrNull()?.id
        }
    }

    LaunchedEffect(selectedId) {
        visibleCount = LOG_PAGE_SIZE
        listState.scrollToItem(0)
    }

    val selectedSession = sessions.firstOrNull { it.id == selectedId }
    val entries = remember(selectedId, visibleCount, revision) {
        selectedId?.let { graph.logs.loadLatest(it, visibleCount) }.orEmpty()
    }

    LaunchedEffect(listState, selectedId, entries.size, visibleCount) {
        snapshotFlow {
            listState.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0
        }
            .distinctUntilChanged()
            .collect { lastIndex ->
                if (
                    entries.isNotEmpty() &&
                    lastIndex >= entries.lastIndex - 5 &&
                    entries.size >= visibleCount
                ) {
                    visibleCount += LOG_PAGE_SIZE
                }
            }
    }

    Column(modifier.fillMaxSize().padding(16.dp)) {
        Text("Logs", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(
            "One JSONL file per Auto session. Entries are flushed to disk immediately.",
            style = MaterialTheme.typography.bodySmall,
        )

        ApplicationLogRow(
            lineCount = appLogLineCount,
            sizeBytes = remember(appLogRevision) { graph.appLog.sizeBytes },
            onExport = { exportAppLog.launch(graph.appLog.exportFileName) },
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        )

        SessionChooser(
            sessions = sessions,
            selected = selectedSession,
            onSelected = { selectedId = it.id },
            modifier = Modifier.fillMaxWidth().padding(top = 10.dp),
        )

        if (selectedSession == null) {
            Text("No sessions yet.", modifier = Modifier.padding(top = 16.dp))
            return@Column
        }

        Text(
            (if (selectedSession.active) "ACTIVE · " else "") +
                (selectedSession.strategy?.uppercase()?.plus(" · ") ?: "") +
                "showing " + entries.size + " newest events",
            modifier = Modifier.padding(top = 8.dp),
            fontWeight = if (selectedSession.active) FontWeight.Bold else FontWeight.Normal,
            color = if (selectedSession.active) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface,
        )

        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(top = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(entries, key = { it.timestamp + it.rawJson.hashCode() }) { entry ->
                DecisionSummaryCard(entry)
            }
            if (entries.size >= visibleCount) {
                item {
                    Text(
                        "Scroll for " + LOG_PAGE_SIZE + " more…",
                        modifier = Modifier.padding(12.dp),
                        style = MaterialTheme.typography.bodySmall,
                    )
                }
            }
        }
    }
}

@Composable
private fun ApplicationLogRow(
    lineCount: Int,
    sizeBytes: Long,
    onExport: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(
        modifier = modifier,
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text("Application log", fontWeight = FontWeight.Bold)
            Text(
                "$lineCount events · " + formatBytes(sizeBytes),
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        OutlinedButton(onClick = onExport) {
            Text("Export")
        }
    }
}

@Composable
private fun SessionChooser(
    sessions: List<LogSession>,
    selected: LogSession?,
    onSelected: (LogSession) -> Unit,
    modifier: Modifier = Modifier,
) {
    var expanded by remember { mutableStateOf(false) }
    Box(modifier) {
        OutlinedButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
            enabled = sessions.isNotEmpty(),
        ) {
            val label = selected?.let {
                shortDateTime(it.startedAt) +
                    (it.strategy?.let { strategy -> " · " + strategy.uppercase() } ?: "") +
                    if (it.active) " · ACTIVE" else ""
            } ?: "Select session"
            Text(label)
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            sessions.forEach { session ->
                DropdownMenuItem(
                    text = {
                        Column {
                            Text(
                                shortDateTime(session.startedAt) +
                                    (if (session.active) " · ACTIVE" else ""),
                                fontWeight = if (session.active) FontWeight.Bold else FontWeight.Normal,
                            )
                            Text(
                                (session.strategy?.uppercase() ?: "UNKNOWN") +
                                    " · " + session.eventCount + " events",
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    },
                    onClick = {
                        onSelected(session)
                        expanded = false
                    },
                )
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
