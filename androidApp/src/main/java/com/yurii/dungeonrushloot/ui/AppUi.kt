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
import androidx.compose.material3.TextButton
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.runtime.LootAccessibilityService
import com.yurii.dungeonrushloot.runtime.OcrDebugCapture

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
                0 -> AutoScreen(
                    graph = graph,
                    onOpenEquipment = { tab = 1 },
                    modifier = Modifier.padding(padding),
                )
                1 -> EquipmentScreen(graph, Modifier.padding(padding))
                else -> LogsScreen(graph, Modifier.padding(padding))
            }
        }
    }
}

@Composable
private fun AutoScreen(
    graph: AppGraph,
    onOpenEquipment: () -> Unit,
    modifier: Modifier = Modifier,
) {
    val context = LocalContext.current
    val enabled by graph.preferences.enabled.collectAsState()
    val strategy by graph.preferences.strategy.collectAsState()
    val equipmentJson by graph.equipment.rawJson.collectAsState()
    val serviceConnected by LootAccessibilityService.connected.collectAsState()
    val activeSessionId by graph.logs.activeSessionId.collectAsState()
    val logRevision by graph.logs.revision.collectAsState()
    val debugState by graph.ocrDebugCapture.state.collectAsState()
    val debugPending = debugState is OcrDebugCapture.State.Armed ||
        debugState is OcrDebugCapture.State.Capturing

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
            actionLabel = "Settings",
            onAction = {
                context.startActivity(
                    Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            },
        )
        StatusCard(
            title = "Equipment",
            ok = validation.valid,
            good = "8/8 ready",
            bad = validation.error ?: "Incomplete",
            actionLabel = "Open",
            onAction = onOpenEquipment,
        )

        Text("Strategy", style = MaterialTheme.typography.titleMedium)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            listOf("universal", "pve", "pvp").forEach { value ->
                FilterChip(
                    selected = strategy == value,
                    onClick = { graph.preferences.setStrategy(value) },
                    enabled = !enabled,
                    label = { Text(value.uppercase()) },
                )
            }
        }

        Button(
            onClick = {
                if (enabled) {
                    graph.preferences.setEnabled(false)
                    graph.logs.endSession()
                } else {
                    graph.logs.startSession(strategy)
                    graph.preferences.setEnabled(true)
                }
            },
            enabled = !debugPending && (enabled || (serviceConnected && validation.valid)),
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
        Text("One-shot OCR diagnostic", style = MaterialTheme.typography.titleMedium)
        Text(
            "Open the loot popup in the game, return here and arm capture, then switch " +
                "back to Dungeon Rush. The next Accessibility screenshot and the exact " +
                "ML Kit input are saved as one ZIP in Downloads. No automated taps are sent. " +
                "The ZIP includes your full game screen, so review it before sharing.",
            style = MaterialTheme.typography.bodySmall,
        )
        when (val state = debugState) {
            is OcrDebugCapture.State.Armed -> {
                Text("Armed. Switch to Dungeon Rush with the loot popup open.")
                TextButton(onClick = { graph.ocrDebugCapture.cancel() }) {
                    Text("Cancel capture")
                }
            }
            is OcrDebugCapture.State.Capturing -> Text("Capturing and saving ZIP...")
            is OcrDebugCapture.State.Saved ->
                Text("Saved to Downloads: " + state.filename + ". Share that ZIP here.")
            is OcrDebugCapture.State.Failed ->
                Text("Capture failed: " + state.reason, color = MaterialTheme.colorScheme.error)
            OcrDebugCapture.State.Idle -> Unit
        }
        Button(
            onClick = {
                // Stop Auto before arming, including any pending user session.
                // The controller's diagnostic path never dispatches a touch.
                if (enabled) {
                    graph.preferences.setEnabled(false)
                    graph.logs.endSession()
                }
                graph.ocrDebugCapture.arm()
            },
            enabled = serviceConnected && !debugPending,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(if (debugState is OcrDebugCapture.State.Failed) "Retry OCR capture"
                 else "Capture next game OCR as ZIP")
        }

        Spacer(Modifier.height(4.dp))
        Text("Latest decision", style = MaterialTheme.typography.titleMedium)
        val latest = remember(activeSessionId, logRevision) {
            activeSessionId?.let { graph.logs.loadLatest(it, 1).firstOrNull() }
        }
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
    actionLabel: String,
    onAction: () -> Unit,
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
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 14.dp, end = 6.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Column(Modifier.weight(1f)) {
                Text(title, fontWeight = FontWeight.Bold)
                Text(if (ok) good else bad)
            }
            TextButton(onClick = onAction) {
                Text(actionLabel)
            }
        }
    }
}
