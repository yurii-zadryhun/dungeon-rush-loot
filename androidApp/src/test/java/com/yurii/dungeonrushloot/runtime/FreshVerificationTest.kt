package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.DecisionEvent
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FreshVerificationTest {
    private fun event(
        verificationKey: String? = "canonical-hash-1",
        action: String = "sell",
        status: String = "ok",
        slot: String = "gloves",
        ocrText: String = "+23.09% Triple Hit Chance",
        confidence: Double = 0.99,
    ): DecisionEvent {
        val stat = JSONObject()
            .put("name", "triple hit chance")
            .put("value", 23.09)
            .put("raw_text", ocrText)
            .put("confidence", confidence)
        val item = JSONObject()
            .put("title", "Immortal [EXP] Crimson Gloves")
            .put("rarity", "Immortal")
            .put("level", 124)
            .put("stats", JSONArray().put(stat))
        val event = JSONObject()
            .put("status", status)
            .put("action", action)
            .put("slot", slot)
            .put("message", if (status == "ok") "OK" else "OCR incomplete")
            .put("candidate", item)
            .put("equipped", item)
        if (verificationKey != null) event.put("verification_key", verificationKey)
        return DecisionEvent.fromJson(event.toString())
    }

    @Test
    fun sameSemanticKeyAllowsFreshPassDespiteDifferentRawOcrAndConfidence() {
        val initial = event(ocrText = "+23.09% Triple Hit Chance", confidence = .99)
        val fresh = event(ocrText = "+23.09%% Triple Hit Chanee", confidence = .41)
        assertNotNull(initial.candidateKey)
        assertEquals(initial.candidateKey, fresh.candidateKey)
        assertNull(FreshVerification.rejectionReason(initial, fresh))
    }

    @Test
    fun changedCandidateIdentityFailsClosedEvenWithIdenticalDisplayedScores() {
        val first = event()
        val fresh = event(verificationKey = "canonical-hash-different")
        assertTrue(FreshVerification.rejectionReason(first, fresh)!!.contains("same item"))
    }

    @Test
    fun secondOcrFailureIsNotReportedAsLootChanged() {
        val reason = FreshVerification.rejectionReason(event(), event(status = "check_ocr"))
        assertTrue(reason!!.contains("inconclusive"))
        assertTrue(reason.contains("OCR incomplete"))
    }

    @Test
    fun onlyExactMissingExpMarkerErrorTriggersOneMoreObservation() {
        val first = event()
        val lostMarker = event(status = "check_ocr").copy(
            message = "candidate: Immortal requires 0-0 exceptional affixes; parsed 1.",
        )
        assertTrue(FreshVerification.retryMissingExp(first, lostMarker))
        assertFalse(FreshVerification.retryMissingExp(
            first, event(status = "check_ocr"),
        ))
        assertFalse(FreshVerification.retryMissingExp(
            first, event(status = "ok"),
        ))
        assertFalse(FreshVerification.retryMissingExp(
            event(status = "check_ocr"), lostMarker,
        ))
        assertFalse(FreshVerification.retryMissingExp(
            event(verificationKey = null), lostMarker,
        ))
    }

    @Test
    fun changedActionAndSlotFailClosed() {
        assertTrue(FreshVerification.rejectionReason(event(), event(action = "equip"))!!
            .contains("action"))
        assertTrue(FreshVerification.rejectionReason(event(), event(slot = "helmet"))!!
            .contains("slot"))
    }

    @Test
    fun missingVerificationKeyNeverAuthorizesTouch() {
        val withoutKey = event(verificationKey = null)
        assertNull(withoutKey.candidateKey)
        assertNotNull(FreshVerification.rejectionReason(event(), withoutKey))
        assertNotNull(FreshVerification.rejectionReason(withoutKey, event()))
    }
}
