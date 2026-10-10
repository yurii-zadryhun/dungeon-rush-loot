package com.yurii.dungeonrushloot.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.data.EquipmentStore
import com.yurii.dungeonrushloot.model.EquipmentDraft
import com.yurii.dungeonrushloot.model.SkillDefinition
import java.util.Locale

private data class EditableStat(val name: String, val value: String)

@Composable
fun EquipmentScreen(graph: AppGraph, modifier: Modifier = Modifier) {
    val raw by graph.equipment.rawJson.collectAsState()
    val drafts = remember(raw) { graph.equipment.drafts() }
    val validation = remember(raw) { graph.bridge.validateEquipment(raw) }
    var editingSlot by remember { mutableStateOf<String?>(null) }

    Column(modifier.fillMaxSize().padding(16.dp)) {
        Text("Equipment", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(
            if (validation.valid) {
                "Ready. Successful auto-equips update this state automatically."
            } else {
                "Configure all six slots with 4–5 affixes before enabling auto."
            },
            color = if (validation.valid) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        )

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            items(EquipmentStore.SLOT_NAMES) { slot ->
                val draft = drafts.getValue(slot)
                EquipmentCard(slot, draft) { editingSlot = slot }
            }
        }
    }

    val slot = editingSlot
    if (slot != null) {
        EquipmentEditorDialog(
            slot = slot,
            initial = drafts.getValue(slot),
            rarities = graph.bridge.config.rarities.map { it.name },
            skills = graph.bridge.config.skills,
            onDismiss = { editingSlot = null },
            onSave = {
                graph.equipment.save(slot, it)
                editingSlot = null
            },
        )
    }
}

@Composable
private fun EquipmentCard(slot: String, draft: EquipmentDraft, onEdit: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onEdit),
    ) {
        Column(Modifier.padding(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(slot.uppercase(), fontWeight = FontWeight.Bold)
                Text(draft.rarity + " · Lv" + draft.level)
            }
            Text(draft.title.ifBlank { "Unnamed / not configured" })
            if (draft.stats.isEmpty()) {
                Text("No affixes", color = MaterialTheme.colorScheme.error)
            } else {
                draft.stats.forEach { (name, value) ->
                    Text(formatPercent(value) + "  " + name)
                }
            }
        }
    }
}

@Composable
private fun EquipmentEditorDialog(
    slot: String,
    initial: EquipmentDraft,
    rarities: List<String>,
    skills: List<SkillDefinition>,
    onDismiss: () -> Unit,
    onSave: (EquipmentDraft) -> Unit,
) {
    var title by remember(initial) { mutableStateOf(initial.title) }
    var rarity by remember(initial) { mutableStateOf(initial.rarity) }
    var levelText by remember(initial) { mutableStateOf(initial.level.toString()) }
    val rows = remember(initial) {
        mutableStateListOf<EditableStat>().apply {
            initial.stats.forEach { (name, value) ->
                add(EditableStat(name, value.toString()))
            }
            while (size < 4) add(EditableStat("", ""))
        }
    }
    var error by remember { mutableStateOf<String?>(null) }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Edit " + slot) },
        text = {
            Column(
                Modifier
                    .widthIn(max = 560.dp)
                    .verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    label = { Text("Title (optional)") },
                    modifier = Modifier.fillMaxWidth(),
                )
                DropdownField(
                    value = rarity,
                    options = rarities,
                    label = "Rarity",
                    onSelected = { rarity = it },
                )
                OutlinedTextField(
                    value = levelText,
                    onValueChange = { levelText = it.filter(Char::isDigit).take(3) },
                    label = { Text("Level") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth(),
                )

                Text("Affixes (4–5)", fontWeight = FontWeight.Bold)
                rows.forEachIndexed { index, row ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        DropdownField(
                            value = row.name.ifBlank { "Select stat" },
                            options = skills.map { it.name },
                            label = "Stat " + (index + 1),
                            onSelected = { rows[index] = row.copy(name = it) },
                        )
                        OutlinedTextField(
                            value = row.value,
                            onValueChange = { value ->
                                val filtered = value.filter { char ->
                                    char.isDigit() || char == '.' || char == ',' || char == '-'
                                }
                                rows[index] = rows[index].copy(value = filtered)
                            },
                            label = { Text("Value %") },
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            modifier = Modifier.fillMaxWidth(),
                        )
                        if (rows.size > 4) {
                            TextButton(onClick = { rows.removeAt(index) }) {
                                Text("Remove")
                            }
                        }
                    }
                }
                if (rows.size < 5) {
                    OutlinedButton(onClick = { rows.add(EditableStat("", "")) }) {
                        Text("+ Add fifth affix")
                    }
                }
                error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            }
        },
        confirmButton = {
            Button(
                onClick = {
                    val level = levelText.toIntOrNull()
                    val parsedRows = rows.mapNotNull { row ->
                        if (row.name.isBlank() && row.value.isBlank()) return@mapNotNull null
                        val value = row.value.replace(',', '.').toDoubleOrNull()
                        if (row.name.isBlank() || value == null) return@mapNotNull null
                        row.name to value
                    }
                    error = when {
                        level == null || level !in 1..130 -> "Level must be 1–130."
                        parsedRows.size !in 4..5 -> "Exactly 4 or 5 valid affixes are required."
                        parsedRows.map { it.first }.distinct().size != parsedRows.size -> "Affixes must be unique."
                        else -> null
                    }
                    if (error == null) {
                        onSave(
                            EquipmentDraft(
                                title = title.trim(),
                                rarity = rarity,
                                level = level!!,
                                stats = LinkedHashMap<String, Double>().apply {
                                    parsedRows.forEach { (name, value) -> put(name, value) }
                                },
                            ),
                        )
                    }
                },
            ) {
                Text("Save")
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

@Composable
private fun DropdownField(
    value: String,
    options: List<String>,
    label: String,
    onSelected: (String) -> Unit,
) {
    var expanded by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth()) {
        OutlinedButton(
            onClick = { expanded = true },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Column(Modifier.fillMaxWidth()) {
                Text(label, style = MaterialTheme.typography.labelSmall)
                Text(value)
            }
        }
        DropdownMenu(
            expanded = expanded,
            onDismissRequest = { expanded = false },
        ) {
            options.forEach { option ->
                DropdownMenuItem(
                    text = { Text(option) },
                    onClick = {
                        onSelected(option)
                        expanded = false
                    },
                )
            }
        }
    }
}

private fun formatPercent(value: Double): String =
    String.format(Locale.US, "%+.2f%%", value)
