package com.yurii.dungeonrushloot.runtime

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CandidateRetryGateTest {
    @Test fun allowsRetryAfterFiveSeconds() {
        val gate = CandidateRetryGate(5_000L)
        assertFalse(gate.isSuppressed("item-A", 100L))
        gate.markHandled("item-A", 100L)
        assertTrue(gate.isSuppressed("item-A", 5_099L))
        assertFalse(gate.isSuppressed("item-A", 5_100L))
        assertFalse(gate.isSuppressed("item-A", 10_000L))
    }

    @Test fun aDifferentCandidateAndUnmarkedFailedTouchesRemainRetryable() {
        val gate = CandidateRetryGate()
        gate.markHandled("item-A", 100L)
        assertFalse(gate.isSuppressed("item-B", 101L))
        // A rejected touch has no markHandled call.
        assertFalse(gate.isSuppressed("item-B", 102L))
        assertTrue(gate.isSuppressed("item-A", 102L))
    }

    @Test fun monotonicClockRegressionDoesNotExtendSuppression() {
        val gate = CandidateRetryGate()
        gate.markHandled("item-A", 10_000L)
        assertFalse(gate.isSuppressed("item-A", 100L))
    }
}
