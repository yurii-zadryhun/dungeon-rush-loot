package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.DecisionEvent

/**
 * Both independently OCR-validated frames must describe the same complete item
 * identity. A second OCR failure is not proof that the game changed loot.
 * The Python key excludes volatile OCR metadata while preserving numeric rolls.
 */
internal object FreshVerification {
    /** Retry a *new frame* once if ML Kit lost the EXP token on a verification
     * pass. A second failed OCR still fails closed; never fabricate EXP. */
    fun retryMissingExp(first: DecisionEvent, fresh: DecisionEvent): Boolean =
        first.status == "ok" && !first.candidateKey.isNullOrBlank() &&
            fresh.status == "check_ocr" &&
            fresh.message.contains("requires 0-0 exceptional affixes; parsed ")

    fun rejectionReason(first: DecisionEvent, second: DecisionEvent): String? = when {
        first.status != "ok" || first.candidateKey.isNullOrBlank() ->
            "Initial OCR did not provide a verified item identity."
        second.status != "ok" || second.candidateKey.isNullOrBlank() ->
            "Fresh OCR was inconclusive: " + second.message
        first.action != second.action ->
            "Fresh OCR produced a different action (" + first.action + " / " + second.action + ")."
        first.slot != second.slot ->
            "Fresh OCR produced a different equipment slot (" + first.slot + " / " + second.slot + ")."
        first.candidateKey != second.candidateKey ->
            "Fresh OCR did not confirm the same item and complete affixes."
        else -> null
    }
}
