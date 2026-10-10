package com.yurii.dungeonrushloot.runtime

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import com.yurii.dungeonrushloot.app.AppGraph
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class LootAccessibilityService : AccessibilityService() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var foreground: AccessibilityForegroundAdapter
    private var ocr: MlKitOcrAdapter? = null
    private var controllerJob: Job? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        val graph = AppGraph.get(this)
        foreground = AccessibilityForegroundAdapter(this)
        val ocrAdapter = MlKitOcrAdapter().also { ocr = it }
        val controller = AndroidLootController(
            screenCapture = AccessibilityScreenshotAdapter(this),
            ocr = ocrAdapter,
            touch = AccessibilityTouchAdapter(this),
            foreground = foreground,
            equipment = graph.equipment,
            automation = graph.preferences,
            log = graph.logs,
            appLog = graph.appLog,
            bridge = graph.bridge,
            config = graph.bridge.config,
            debugCapture = graph.ocrDebugCapture,
            debugExporter = graph.ocrDebugExporter,
        )
        _connected.value = true
        graph.appLog.info(
            category = "accessibility",
            event = "service_connected",
            message = "Accessibility service connected.",
        )
        controllerJob = scope.launch { controller.run() }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (::foreground.isInitialized) {
            foreground.onAccessibilityEvent(event)
        }
    }

    override fun onInterrupt() {
        val graph = AppGraph.get(this)
        graph.logs.appendSystem("Accessibility service interrupted.")
        graph.appLog.warning(
            category = "accessibility",
            event = "service_interrupted",
            message = "Accessibility service interrupted.",
        )
    }

    override fun onDestroy() {
        _connected.value = false
        runCatching {
            AppGraph.get(this).appLog.info(
                category = "accessibility",
                event = "service_destroyed",
                message = "Accessibility service destroyed.",
            )
        }
        controllerJob?.cancel()
        ocr?.close()
        scope.cancel()
        super.onDestroy()
    }

    companion object {
        private val _connected = MutableStateFlow(false)
        val connected: StateFlow<Boolean> = _connected
    }
}
