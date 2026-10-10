package com.yurii.dungeonrushloot.ui

import android.content.Intent
import android.provider.Settings
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.FilterChip
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.runtime.LootAccessibilityService

@Composable
fun DungeonRushLootApp(graph: AppGraph) {
    val dark = isSystemInDarkTheme()
    MaterialTheme(colorScheme = if (dark) darkColorScheme() else lightColorScheme()) {
        var tab by remember { mutableIntStateOf(0) }
        Scaffold(
            bottomBar = {
                NavigationBar {
                    NavigationBarItem(
                        selected = tab == 0,
                        onClick = { tab = 0 },
                        icon = { Text("▶") },
                        label = { Text("Auto") },
                    )
                    NavigationBarItem(
                        selected = tab == 1,
                        onClick = { tab = 1 },
                        icon = { Text("⚙") },
                        label = { Text("Equipment") },
                    )
                    NavigationBarItem(
                        selected = tab == 2,
                        onClick = { tab = 2 },
                        icon = { Text("≡") },
                        label = { Text("Logs") },
                    )
                }
            },
        ) { padding ->
            when (tab) {
                0 -> AutoScreen(graph, Modifier.padding(padding))
                1 -> EquipmentScreen(graph, Modifier.padding(padding))
                else -> LogsScreen(graph, Modifier.padding(padding))
            }
        }
    }
}

@Composable
private fun AutoScreen(graph: AppGraph, modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val enabled by graph.preferences.enabled.collectAsState()
    val strategy by graph.preferences.strategy.collectAsState()
    val equipmentJson by graph.equipment.rawJson.collectAsState()
    val serviceConnected by LootAccessibilityService.connected.collectAsState()
    val logs by graph.logs.entries.collectAsState()

    val validation = remember(equipmentJson) {
        graph.bridge.validateEquipment(equipmentJson)
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Dungeon Rush Loot", style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold)
        Text(
            "Android auto mode uses Accessibility screenshots + ML Kit OCR. " +
                "The parser, equipment model and scorer are the same Python code as desktop.",
            style = MaterialTheme.typography.bodyMedium,
        )

        StatusCard(
            title = "Accessibility service",
            ok = serviceConnected,
            good = "Connected",
            bad = "Not connected",
        )
        StatusCard(
            title = "Equipment",
            ok = validation.valid,
            good = "6/6 ready",
            bad = validation.error ?: "Incomplete",
        )

        Text("Strategy", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("universal", "pve", "pvp").forEach { value ->
                FilterChip(
                    selected = strategy == value,
                    onClick = { graph.preferences.setStrategy(value) },
                    label = { Text(value.uppercase()) },
                )
            }
        }

        if (!serviceConnected) {
            Button(
                onClick = {
                    context.startActivity(
                        Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                },
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Open Accessibility settings")
            }
        }

        Button(
            onClick = { graph.preferences.setEnabled(!enabled) },
            enabled = serviceConnected && validation.valid,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (enabled) "STOP AUTO" else "START AUTO")
        }

        if (enabled) {
            Text(
                "AUTO ON · " + strategy.uppercase() +
                    " · only acts while Dungeon Rush is the foreground app",
                color = MaterialTheme.colorScheme.primary,
                fontWeight = FontWeight.Bold,
            )
        }

        Spacer(Modifier.height(4.dp))
        Text("Latest decision", style = MaterialTheme.typography.titleMedium)
        val latest = logs.lastOrNull()
        if (latest == null) {
            Text("No decisions yet.")
        } else {
            DecisionSummaryCard(latest)
        }
    }
}

@Composable
private fun StatusCard(
    title: String,
    ok: Boolean,
    good: String,
    bad: String,
) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = if (ok) {
                MaterialTheme.colorScheme.primaryContainer
            } else {
                MaterialTheme.colorScheme.errorContainer
            },
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontWeight = FontWeight.Bold)
            Text(if (ok) good else bad)
        }
    }
}
