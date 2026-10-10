package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import com.yurii.dungeonrushloot.model.AppConfig
import com.yurii.dungeonrushloot.model.DecisionEvent
import kotlin.coroutines.coroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive

class AndroidLootController(
    private val screenCapture: ScreenCaptureAdapter,
    private val ocr: OcrAdapter,
    private val touch: TouchAdapter,
    private val foreground: ForegroundAppAdapter,
    private val equipment: EquipmentStateAdapter,
    private val automation: AutomationStateAdapter,
    private val log: DecisionLogAdapter,
    private val appLog: ApplicationLogAdapter,
    private val bridge: PythonDecisionBridge,
    private val config: AppConfig,
) {
    private var lastHandledCandidate: String? = null
    private var lastHandledAt: Long = 0
    private var lastCheckMessage: String? = null
    private var lastCheckAt: Long = 0
    private var lastRuntimeError: String? = null
    private var lastRuntimeErrorAt: Long = 0

    suspend fun run() {
        while (coroutineContext.isActive) {
            try {
                tick()
            } catch (error: Throwable) {
                reportRuntimeError(
                    message = (error::class.simpleName ?: "Error") + ": " + (error.message ?: "unknown error"),
                    throwable = error,
                )
            }
            delay(POLL_INTERVAL_MS)
        }
    }

    private suspend fun tick() {
        if (!automation.isEnabled()) return
        if (foreground.currentPackage() != config.targetPackage) return

        val equipmentJson = equipment.currentJson()
        val validation = bridge.validateEquipment(equipmentJson)
        if (!validation.valid) {
            reportRuntimeError("Auto paused: " + (validation.error ?: "equipment is incomplete"))
            return
        }

        val strategy = automation.strategyName()
        val first = observe(equipmentJson, strategy)
        try {
            if (first.event.status != "ok") {
                reportCheck(first.event)
                return
            }

            val candidateKey = first.event.candidateKey ?: return
            if (recentlyHandled(candidateKey)) return

            delay(FRESH_VERIFY_DELAY_MS)
            if (!automation.isEnabled() || foreground.currentPackage() != config.targetPackage) return

            val verified = observe(equipmentJson, strategy)
            try {
                if (
                    verified.event.status != "ok" ||
                    verified.event.action != first.event.action ||
                    verified.event.candidateKey != candidateKey
                ) {
                    log.append(first.event, "Auto cancelled: loot changed during fresh verification.")
                    return
                }

                if (!automation.isEnabled() || foreground.currentPackage() != config.targetPackage) return
                val target = verified.event.touchTarget
                if (target == null) {
                    log.append(
                        verified.event,
                        "Auto cancelled: no touch target for " + verified.event.action + ".",
                    )
                    markHandled(candidateKey)
                    return
                }

                val touched = touch.tap(target, verified.frame.bitmap.width, verified.frame.bitmap.height)
                if (!touched) {
                    log.append(verified.event, "Gesture was rejected or cancelled by Android.")
                    markHandled(candidateKey)
                    return
                }

                var runtimeMessage = "Touch " + verified.event.action.uppercase() + " sent."

                if (verified.event.action == "sell" && verified.event.needsSellConfirmation) {
                    delay(SELL_CONFIRM_DELAY_MS)
                    if (foreground.currentPackage() == config.targetPackage) {
                        val confirm = verified.event.confirmSellTarget
                        if (confirm != null) {
                            val confirmed = touch.tap(
                                confirm,
                                verified.frame.bitmap.width,
                                verified.frame.bitmap.height,
                            )
                            runtimeMessage += if (confirmed) {
                                " Sell confirmation sent."
                            } else {
                                " Sell confirmation gesture was cancelled."
                            }
                        }
                    }
                }

                if (verified.event.action == "equip") {
                    runtimeMessage += handleVerifiedEquip(verified, equipmentJson)
                }

                log.append(verified.event, runtimeMessage)
                markHandled(candidateKey)
            } finally {
                verified.frame.bitmap.recycle()
            }
        } finally {
            first.frame.bitmap.recycle()
        }
    }

    private suspend fun handleVerifiedEquip(
        verified: Observation,
        equipmentJson: String,
    ): String {
        val slot = verified.event.slot
        val candidate = verified.event.candidateJson
        if (slot == null || candidate == null) {
            return " Equipment state was not updated: decision payload was incomplete."
        }

        delay(POST_TOUCH_DELAY_MS)
        if (foreground.currentPackage() != config.targetPackage) {
            return " Equipment state was not updated: game left foreground."
        }

        val after = screenCapture.capture()
        return try {
            if (!ImageChangeDetector.changed(verified.frame.bitmap, after.bitmap, config.crop)) {
                " Equipment state was not updated: UI change was not visually confirmed."
            } else {
                val updated = bridge.replaceEquipment(equipmentJson, slot, candidate)
                equipment.replaceRaw(updated)
                " Equipment state updated: " + slot + "."
            }
        } finally {
            after.bitmap.recycle()
        }
    }

    private suspend fun observe(equipmentJson: String, strategy: String): Observation {
        val frame = screenCapture.capture()
        return try {
            val spans = ocr.recognize(frame, config.crop)
            val event = bridge.evaluate(spans, equipmentJson, strategy)
            Observation(frame, event)
        } catch (error: Throwable) {
            frame.bitmap.recycle()
            throw error
        }
    }

    private fun reportCheck(event: DecisionEvent) {
        val now = System.currentTimeMillis()
        if (event.message != lastCheckMessage || now - lastCheckAt >= CHECK_LOG_TTL_MS) {
            log.append(event, null)
            lastCheckMessage = event.message
            lastCheckAt = now
        }
    }

    private fun reportRuntimeError(message: String, throwable: Throwable? = null) {
        val now = System.currentTimeMillis()
        if (message != lastRuntimeError || now - lastRuntimeErrorAt >= RUNTIME_ERROR_TTL_MS) {
            log.appendSystem(message)
            if (throwable != null) {
                appLog.error(
                    category = "auto_runtime",
                    event = "controller_error",
                    message = message,
                    throwable = throwable,
                )
            } else {
                appLog.warning(
                    category = "auto_runtime",
                    event = "controller_warning",
                    message = message,
                )
            }
            lastRuntimeError = message
            lastRuntimeErrorAt = now
        }
    }

    private fun recentlyHandled(candidateKey: String): Boolean =
        candidateKey == lastHandledCandidate &&
            System.currentTimeMillis() - lastHandledAt < CANDIDATE_TTL_MS

    private fun markHandled(candidateKey: String) {
        lastHandledCandidate = candidateKey
        lastHandledAt = System.currentTimeMillis()
    }

    private data class Observation(
        val frame: CapturedFrame,
        val event: DecisionEvent,
    )

    companion object {
        private const val POLL_INTERVAL_MS = 650L
        private const val FRESH_VERIFY_DELAY_MS = 380L
        private const val POST_TOUCH_DELAY_MS = 450L
        private const val SELL_CONFIRM_DELAY_MS = 500L
        private const val CANDIDATE_TTL_MS = 10_000L
        private const val CHECK_LOG_TTL_MS = 10_000L
        private const val RUNTIME_ERROR_TTL_MS = 15_000L
    }
}
