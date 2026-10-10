package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import android.os.SystemClock
import com.yurii.dungeonrushloot.model.AppConfig
import com.yurii.dungeonrushloot.model.DecisionEvent
import kotlin.coroutines.coroutineContext
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import org.json.JSONArray
import org.json.JSONObject
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
    private val stableForeground = StableForeground(config.targetPackage)
    private var lastHandledCandidate: String? = null
    private var lastHandledAt: Long = 0
    private var lastCheckMessage: String? = null
    private var lastCheckAt: Long = 0
    private var lastRuntimeError: String? = null
    private var lastRuntimeErrorAt: Long = 0
    private var lastOcrDiagnosticAt: Long = 0
    private var lastOcrDiagnosticSignature: String? = null

    suspend fun run() {
        while (coroutineContext.isActive) {
            try {
                tick()
            } catch (cancelled: CancellationException) {
                throw cancelled
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
        val gameReady = stableForeground.confirmed(foreground.currentPackage(), SystemClock.elapsedRealtime())
        if (!automation.isEnabled() || !gameReady) return

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
                delay(CHECK_BACKOFF_MS)
                return
            }

            val candidateKey = first.event.candidateKey
            if (candidateKey.isNullOrBlank()) {
                log.append(first.event, "Auto cancelled: initial item identity was not verifiable.")
                return
            }
            if (recentlyHandled(candidateKey)) return

            delay(FRESH_VERIFY_DELAY_MS)
            if (!automation.isEnabled() || foreground.currentPackage() != config.targetPackage) return

            val fresh = observe(equipmentJson, strategy)
            var verified = fresh
            try {
                if (FreshVerification.retryMissingExp(first.event, fresh.event)) {
                    delay(220L)
                    if (!automation.isEnabled() ||
                        foreground.currentPackage() != config.targetPackage
                    ) return
                    verified = observe(equipmentJson, strategy)
                }
                val rejection = FreshVerification.rejectionReason(first.event, verified.event)
                if (rejection != null) {
                    log.append(first.event, "Auto cancelled: " + rejection)
                    appLog.warning(
                        category = "auto_verification",
                        event = "fresh_check_rejected",
                        message = rejection,
                        details = JSONObject()
                            .put("first_status", first.event.status)
                            .put("fresh_status", verified.event.status)
                            .put("first_action", first.event.action)
                            .put("fresh_action", verified.event.action)
                            .put("first_slot", first.event.slot)
                            .put("fresh_slot", verified.event.slot)
                            .put("first_key", first.event.candidateKey)
                            .put("fresh_key", verified.event.candidateKey)
                            .put("fresh_ocr_message", verified.event.message),
                    )
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

                if (verified.event.action == "sell" && verified.event.needsSellConfirmation) {
                    // A confirmation modal cannot safely be handled by a tap
                    // at a fixed screen coordinate. Leave it for manual review.
                    log.append(verified.event, "Sell needs a confirmation modal; no automated tap was sent.")
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

                if (verified.event.action == "equip") {
                    runtimeMessage += handleVerifiedEquip(verified, equipmentJson)
                }

                log.append(verified.event, runtimeMessage)
                markHandled(candidateKey)
            } finally {
                if (verified !== fresh) verified.frame.bitmap.recycle()
                fresh.frame.bitmap.recycle()
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
            val primary = ocr.recognize(frame, config.crop)
            val first = bridge.evaluate(primary, equipmentJson, strategy)
            var enhanced: List<com.yurii.dungeonrushloot.model.OcrSpanDto>? = null
            var iconLevels: List<com.yurii.dungeonrushloot.model.OcrSpanDto>? = null
            var event = first
            if (first.status != "ok") {
                // A higher-scale full-popup pass can improve item text.
                val retrySpans = ocr.recognizeEnhanced(frame, config.crop)
                enhanced = retrySpans
                val retried = bridge.evaluate(retrySpans, equipmentJson, strategy)
                if (retried.status == "ok") event = retried
            }
            if (event.status != "ok" &&
                event.message.contains("rarity/level", ignoreCase = true)
            ) {
                // The level is painted over the item ICON, not in the affix
                // column. ML Kit can read every affix but omit both levels.
                // OCR a small icon ROI, then pass the ACTUAL recognized text
                // back through the complete Python validator. No guessed levels.
                val sourceSpans = if (enhanced != null) enhanced else primary
                val recovered = ocr.recognizeIconLevels(frame, config.crop, sourceSpans)
                iconLevels = recovered
                if (recovered.isNotEmpty()) {
                    val validated = bridge.evaluate(sourceSpans + recovered, equipmentJson, strategy)
                    if (validated.status == "ok") event = validated
                }
            }
            logOcrObservation(frame, first, event, primary, enhanced, iconLevels)
            Observation(frame, event)
        } catch (error: Throwable) {
            frame.bitmap.recycle()
            throw error
        }
    }

    private fun logOcrObservation(
        frame: CapturedFrame,
        initial: DecisionEvent,
        result: DecisionEvent,
        primary: List<com.yurii.dungeonrushloot.model.OcrSpanDto>,
        enhanced: List<com.yurii.dungeonrushloot.model.OcrSpanDto>?,
        iconLevels: List<com.yurii.dungeonrushloot.model.OcrSpanDto>?,
    ) {
        val now = System.currentTimeMillis()
        val signature = listOf(
            result.status,
            result.action,
            result.candidateKey ?: result.message,
        ).joinToString("|")
        if (
            signature == lastOcrDiagnosticSignature &&
            now - lastOcrDiagnosticAt < OCR_DIAGNOSTIC_INTERVAL_MS
        ) return
        lastOcrDiagnosticSignature = signature
        lastOcrDiagnosticAt = now

        fun spansJson(spans: List<com.yurii.dungeonrushloot.model.OcrSpanDto>): JSONArray =
            JSONArray().apply { spans.forEach { put(it.toJson()) } }

        appLog.info(
            category = "auto_ocr",
            event = "observation",
            message = "Live loot OCR and parser diagnostics.",
            details = JSONObject()
                .put("width", frame.bitmap.width)
                .put("height", frame.bitmap.height)
                // The OCR adapter receives this exact ROI. Keeping it in the
                // raw diagnostics separates crop regressions from background
                // HUD text physically inside the correctly cropped region.
                .put("ocr_crop", JSONObject()
                    .put("left", config.crop.left)
                    .put("top", config.crop.top)
                    .put("right", config.crop.right)
                    .put("bottom", config.crop.bottom))
                .put("primary_scale", 2.5)
                .put("primary_spans", spansJson(primary))
                .put("primary_result", JSONObject(initial.rawJson))
                .put("enhanced_scale", if (enhanced == null) JSONObject.NULL else 3.5)
                .put("enhanced_spans", if (enhanced == null) JSONObject.NULL else spansJson(enhanced))
                .put("icon_level_spans", if (iconLevels == null) JSONObject.NULL else spansJson(iconLevels))
                .put("selected_result", JSONObject(result.rawJson)),
        )
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
        private const val CHECK_BACKOFF_MS = 1_500L
        private const val OCR_DIAGNOSTIC_INTERVAL_MS = 15_000L
        private const val CANDIDATE_TTL_MS = 10_000L
        private const val CHECK_LOG_TTL_MS = 10_000L
        private const val RUNTIME_ERROR_TTL_MS = 15_000L
    }
}
