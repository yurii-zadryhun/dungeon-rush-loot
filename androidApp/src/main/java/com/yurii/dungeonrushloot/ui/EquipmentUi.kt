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
import androidx.compose.foundation.text.KeyboardOptions
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
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
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
                "Ready. Successful auto-equips update the six normal loot slots automatically."
            } else {
                "Configure all 8 slots: six normal items, wings and cape."
            },
            color = if (validation.valid) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.error,
        )

        Column(
            Modifier.fillMaxWidth().padding(top = 12.dp, bottom = 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            EquipmentImportPanel(graph)
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize(),
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
            normalByRarity = graph.bridge.config.normalAffixesByRarity,
            expBounds = graph.bridge.config.minExceptionalAffixes to
                graph.bridge.config.maxExceptionalAffixes,
            divineWingsNormal = graph.bridge.config.divineWingsNormalAffixes,
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

            if (slot == "wings") {
                draft.primaryAttack?.let { Text("Primary Damage " + compactEquipmentNumber(it)) }
                draft.primaryHealth?.let { Text("Primary Health " + compactEquipmentNumber(it)) }
            }
            if (slot == "cape") {
                draft.intrinsicStats.forEach { (name, value) ->
                    Text("Primary " + name + " " + formatPercent(value))
                }
            }

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
    normalByRarity: Map<String, Int>,
    expBounds: Pair<Int, Int>,
    divineWingsNormal: Int,
    onDismiss: () -> Unit,
    onSave: (EquipmentDraft) -> Unit,
) {
    var title by remember(initial) { mutableStateOf(initial.title) }
    val hasExp = EXP_MARKER.containsMatchIn(title)
    val exceptionalNames = skills.asSequence().filter { it.exceptional }.map { it.name }.toSet()
    val availableSkills = if (hasExp) skills else skills.filterNot { it.exceptional }
    var rarity by remember(initial) { mutableStateOf(initial.rarity) }
    val rarityKey = rarity.lowercase(Locale.ROOT)
    val normalRequired = if (
        slot == "wings" && rarityKey == "divine" && !hasExp
    ) divineWingsNormal else normalByRarity[rarityKey]
    val exceptionalMinimum = if (hasExp) expBounds.first else 0
    val exceptionalMaximum = if (hasExp) expBounds.second else 0
    // Ultimate has no validated normal-roll count; prevent saving it.
    val bounds = if (normalRequired != null) {
        (normalRequired + exceptionalMinimum) to (normalRequired + exceptionalMaximum)
    } else 1 to 5
    var levelText by remember(initial) { mutableStateOf(initial.level.toString()) }
    var primaryAttackText by remember(initial) { mutableStateOf(initial.primaryAttack?.toString().orEmpty()) }
    var primaryHealthText by remember(initial) { mutableStateOf(initial.primaryHealth?.toString().orEmpty()) }
    var capeDamageText by remember(initial) {
        mutableStateOf(initial.intrinsicStats["damage"]?.toString().orEmpty())
    }
    var capeHealthText by remember(initial) {
        mutableStateOf(initial.intrinsicStats["health"]?.toString().orEmpty())
    }
    val rows = remember(initial, slot) {
        mutableStateListOf<EditableStat>().apply {
            initial.stats.forEach { (name, value) -> add(EditableStat(name, value.toString())) }
            while (size < bounds.first) add(EditableStat("", ""))
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
                    label = { Text("Title (include [EXP] for exceptional skills)") },
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

                if (slot == "wings") {
                    NumberField("Primary Damage", primaryAttackText) { primaryAttackText = it }
                    NumberField("Primary Health", primaryHealthText) { primaryHealthText = it }
                }
                if (slot == "cape") {
                    NumberField("Primary Damage %", capeDamageText) { capeDamageText = it }
                    NumberField("Primary Health %", capeHealthText) { capeHealthText = it }
                }

                val affixLabel = if (bounds.first == bounds.second) {
                    "Affixes (" + bounds.first + ")"
                } else {
                    "Affixes (" + bounds.first + "–" + bounds.second + ")"
                }
                Text(affixLabel, fontWeight = FontWeight.Bold)
                Text(
                    if (normalRequired == null) "Unverified rarity: affix rules are unknown."
                    else "$normalRequired normal + $exceptionalMinimum–$exceptionalMaximum exceptional",
                    style = MaterialTheme.typography.bodySmall,
                    color = if (normalRequired == null) MaterialTheme.colorScheme.error
                        else MaterialTheme.colorScheme.onSurfaceVariant,
                )

                rows.forEachIndexed { index, row ->
                    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        DropdownField(
                            value = row.name.ifBlank { "Select stat" },
                            options = availableSkills.map { it.name },
                            label = "Stat " + (index + 1),
                            onSelected = { rows[index] = row.copy(name = it) },
                        )
                        NumberField("Value %", row.value) { value ->
                            rows[index] = rows[index].copy(value = value)
                        }
                        if (rows.size > bounds.first) {
                            TextButton(onClick = { rows.removeAt(index) }) {
                                Text("Remove")
                            }
                        }
                    }
                }
                if (rows.size < bounds.second) {
                    OutlinedButton(onClick = { rows.add(EditableStat("", "")) }) {
                        Text("+ Add affix")
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
                        val value = parseNumber(row.value)
                        if (row.name.isBlank() || value == null) return@mapNotNull null
                        row.name to value
                    }
                    val primaryAttack = parseNumber(primaryAttackText)
                    val primaryHealth = parseNumber(primaryHealthText)
                    val capeDamage = parseNumber(capeDamageText)
                    val capeHealth = parseNumber(capeHealthText)

                    error = when {
                        level == null || level !in 1..130 -> "Level must be 1–130."
                        normalRequired == null -> "No verified affix rule for $rarity."
                        parsedRows.size !in bounds.first..bounds.second ->
                            "Expected " + bounds.first + "–" + bounds.second + " valid affixes."
                        parsedRows.map { it.first }.distinct().size != parsedRows.size -> "Affixes must be unique."
                        parsedRows.count { it.first !in exceptionalNames } != normalRequired ->
                            "$rarity requires exactly $normalRequired normal affixes."
                        parsedRows.count { it.first in exceptionalNames } !in
                            exceptionalMinimum..exceptionalMaximum ->
                            if (hasExp) "[EXP] requires 1–2 exceptional affixes."
                            else "Exceptional affixes require [EXP] in the title."
                        slot == "wings" && (primaryAttack == null || primaryAttack <= 0) ->
                            "Wings require positive primary Damage."
                        slot == "wings" && (primaryHealth == null || primaryHealth <= 0) ->
                            "Wings require positive primary Health."
                        slot == "cape" && capeDamage == null -> "Cape requires primary Damage %."
                        slot == "cape" && capeHealth == null -> "Cape requires primary Health %."
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
                                primaryAttack = if (slot == "wings") primaryAttack else null,
                                primaryHealth = if (slot == "wings") primaryHealth else null,
                                intrinsicStats = linkedMapOf<String, Double>().apply {
                                    if (slot == "cape") {
                                        put("damage", capeDamage!!)
                                        put("health", capeHealth!!)
                                    }
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
private fun NumberField(
    label: String,
    value: String,
    onValueChange: (String) -> Unit,
) {
    OutlinedTextField(
        value = value,
        onValueChange = { raw ->
            onValueChange(
                raw.filter { char ->
                    char.isDigit() || char == '.' || char == ',' || char == '-'
                },
            )
        },
        label = { Text(label) },
        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
        modifier = Modifier.fillMaxWidth(),
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

private val EXP_MARKER = Regex("""(?i)(?<![a-z0-9])(?:[\[(]\s*)?exp\s*[\])]""")

private fun parseNumber(value: String): Double? =
    value.replace(',', '.').toDoubleOrNull()

internal fun formatPercent(value: Double): String =
    String.format(Locale.US, "%+.2f%%", value)

private fun compactEquipmentNumber(value: Double): String = when {
    value >= 1_000_000_000 -> String.format(Locale.US, "%.2fB", value / 1_000_000_000)
    value >= 1_000_000 -> String.format(Locale.US, "%.2fM", value / 1_000_000)
    value >= 1_000 -> String.format(Locale.US, "%.2fK", value / 1_000)
    else -> String.format(Locale.US, "%.0f", value)
}
