package com.yurii.dungeonrushloot.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.model.DecisionLogEntry
import java.util.Locale
import org.json.JSONArray
import org.json.JSONObject

@Composable
fun LogsScreen(graph: AppGraph, modifier: Modifier = Modifier) {
    val entries by graph.logs.entries.collectAsState()

    Column(modifier.fillMaxSize().padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Column {
                Text("Logs", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
                Text(entries.size.toString() + " structured events")
            }
            OutlinedButton(onClick = { graph.logs.clear() }, enabled = entries.isNotEmpty()) {
                Text("Clear")
            }
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(entries.asReversed(), key = { it.timestamp + it.rawJson.hashCode() }) { entry ->
                DecisionSummaryCard(entry)
            }
        }
    }
}

@Composable
fun DecisionSummaryCard(entry: DecisionLogEntry) {
    var expanded by remember(entry.rawJson) { mutableStateOf(false) }
    val container = when {
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
                Text(
                    label(entry),
                    fontWeight = FontWeight.Bold,
                )
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

private fun formatOne(value: Double): String =
    if (value.isNaN()) "—" else String.format(Locale.US, "%.1f", value)

private fun formatStat(value: Double, name: String): String =
    String.format(Locale.US, "%+.2f%% %s", value, name)
