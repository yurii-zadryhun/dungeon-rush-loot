package com.yurii.dungeonrushloot.ui

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.model.EquipmentImportResult
import com.yurii.dungeonrushloot.runtime.EquipmentScreenshotImporter
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject

@Composable
fun EquipmentImportPanel(graph: AppGraph) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var importing by remember { mutableStateOf(false) }
    var results by remember { mutableStateOf<List<EquipmentImportResult>?>(null) }
    var error by remember { mutableStateOf<String?>(null) }

    val launcher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.GetMultipleContents(),
    ) { uris ->
        if (uris.isEmpty()) return@rememberLauncherForActivityResult
        importing = true
        error = null
        scope.launch {
            results = runCatching {
                withContext(Dispatchers.Default) {
                    EquipmentScreenshotImporter(
                        context.applicationContext,
                        graph.bridge,
                        graph.bridge.config.equipmentImportCrop,
                        graph.bridge.config.equipmentImportLevelCrop,
                    ).import(uris)
                }
            }.onFailure {
                error = it.message ?: it::class.simpleName
            }.getOrNull()
            importing = false
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Button(
            onClick = { launcher.launch("image/*") },
            enabled = !importing,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (importing) "Reading screenshots…" else "Import equipment from screenshots")
        }
        Text(
            "Select all 8 current-item screenshots at once. OCR is restricted to the fixed item modal, so the build totals behind it are ignored.",
            style = MaterialTheme.typography.bodySmall,
        )
        if (importing) LinearProgressIndicator(Modifier.fillMaxWidth())
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }

    results?.let { imported ->
        EquipmentImportReviewDialog(
            results = imported,
            slots = graph.bridge.config.slots,
            onDismiss = { results = null },
            onSave = { reviewed ->
                runCatching {
                    graph.bridge.equipmentFromImports(reviewed)
                }.onSuccess { raw ->
                    graph.equipment.replaceRaw(raw)
                    results = null
                }.onFailure {
                    error = it.message ?: it::class.simpleName
                }
            },
        )
    }
}

@Composable
private fun EquipmentImportReviewDialog(
    results: List<EquipmentImportResult>,
    slots: List<String>,
    onDismiss: () -> Unit,
    onSave: (List<EquipmentImportResult>) -> Unit,
) {
    val selectedSlots = remember(results) {
        mutableStateListOf<String?>().apply { addAll(results.map { it.slot }) }
    }
    val uniqueSelected = selectedSlots.filterNotNull().toSet()
    val canSave = results.size == slots.size &&
        results.all { it.itemJson != null && it.issues.isEmpty() } &&
        selectedSlots.none { it == null } &&
        uniqueSelected.size == slots.size &&
        uniqueSelected == slots.toSet()

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Review screenshot import") },
        text = {
            Column(
                Modifier.verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    "Detected " + results.size + "/" + slots.size +
                        " items. Slot detection is automatic; change a slot only if a card is wrong.",
                )
                results.forEachIndexed { index, result ->
                    Column(
                        Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        SlotChooser(
                            value = selectedSlots[index],
                            slots = slots,
                            onSelected = { selectedSlots[index] = it },
                        )
                        Text(
                            listOfNotNull(
                                result.rarity,
                                result.level?.let { "Lv" + it },
                                result.title,
                            ).joinToString(" · ").ifBlank { "Could not parse item" },
                            fontWeight = FontWeight.Bold,
                        )
                        Text(
                            "slot confidence " + (result.slotConfidence * 100).toInt() + "%",
                            style = MaterialTheme.typography.bodySmall,
                        )
                        result.itemJson?.let { ItemImportDetails(it) }
                        result.issues.forEach { issue ->
                            Text("⚠ " + issue, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
                        }
                        if (result.issues.isNotEmpty() && result.rawLines.isNotEmpty()) {
                            ImportOcrDebug(result.rawLines)
                        }
                    }
                }

                if (results.size != slots.size) {
                    Text(
                        "Choose exactly " + slots.size + " screenshots.",
                        color = MaterialTheme.colorScheme.error,
                    )
                } else if (!canSave) {
                    Text(
                        "Every item must parse and map to one unique slot: " + slots.joinToString() + ".",
                        color = MaterialTheme.colorScheme.error,
                    )
                }
            }
        },
        confirmButton = {
            Button(
                enabled = canSave,
                onClick = {
                    onSave(
                        results.mapIndexed { index, result ->
                            result.copy(slot = selectedSlots[index])
                        },
                    )
                },
            ) {
                Text("Save all 8")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

@Composable
private fun ImportOcrDebug(lines: List<String>) {
    var expanded by remember(lines) { mutableStateOf(false) }
    TextButton(onClick = { expanded = !expanded }) {
        Text(if (expanded) "Hide OCR text" else "Show OCR text")
    }
    if (expanded) {
        Text(
            lines.joinToString("\n"),
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun SlotChooser(
    value: String?,
    slots: List<String>,
    onSelected: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text((value ?: "UNKNOWN SLOT").uppercase())
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }) {
            slots.forEach { slot ->
                DropdownMenuItem(
                    text = { Text(slot.uppercase()) },
                    onClick = {
                        onSelected(slot)
                        expanded = false
                    },
                )
            }
        }
    }
}

@Composable
private fun ItemImportDetails(raw: String) {
    val item = remember(raw) { runCatching { JSONObject(raw) }.getOrNull() } ?: return
    val primary = item.optJSONObject("primary")
    if (primary != null) {
        val attack = primary.optDouble("attack", Double.NaN)
        val health = primary.optDouble("health", Double.NaN)
        if (!attack.isNaN()) Text("Primary Damage: " + compactNumber(attack), style = MaterialTheme.typography.bodySmall)
        if (!health.isNaN()) Text("Primary Health: " + compactNumber(health), style = MaterialTheme.typography.bodySmall)
    }
    val intrinsic = item.optJSONObject("intrinsic_stats")
    if (intrinsic != null) {
        intrinsic.keys().forEach { name ->
            Text(
                "Primary " + name + ": " + formatPercent(intrinsic.optDouble(name)),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
    val stats = item.optJSONObject("stats")
    if (stats != null) {
        stats.keys().forEach { name ->
            Text(
                formatPercent(stats.optDouble(name)) + " " + name,
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

private fun compactNumber(value: Double): String = when {
    value >= 1_000_000_000 -> String.format("%.2fB", value / 1_000_000_000)
    value >= 1_000_000 -> String.format("%.2fM", value / 1_000_000)
    value >= 1_000 -> String.format("%.2fK", value / 1_000)
    else -> String.format("%.0f", value)
}
