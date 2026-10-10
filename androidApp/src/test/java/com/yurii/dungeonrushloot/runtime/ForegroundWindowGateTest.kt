package com.yurii.dungeonrushloot.runtime

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ForegroundWindowGateTest {
    private val game = "com.lavalabs.dungeonrush"
    private val launcher = "com.sec.android.app.launcher"

    private fun window(pkg: String?, focused: Boolean, active: Boolean = focused) =
        ForegroundWindow(pkg, focused, active, application = true)

    @Test
    fun focusedGameWindowIsRequired() {
        assertEquals(game, ForegroundWindowGate.currentPackage(listOf(window(game, true))))
        assertNull(ForegroundWindowGate.currentPackage(listOf(window(game, false))))
        assertNull(ForegroundWindowGate.currentPackage(emptyList()))
        assertNull(ForegroundWindowGate.currentPackage(listOf(window(null, true))))
    }

    @Test
    fun recentsWithGameTaskBehindItCannotImpersonateGame() {
        val overview = listOf(
            window(game, focused = false, active = false),
            window(launcher, focused = true, active = true),
        )
        assertEquals(launcher, ForegroundWindowGate.currentPackage(overview))
    }

    @Test
    fun ambiguousMultipleFocusedOrActiveAppsFailClosed() {
        assertNull(ForegroundWindowGate.currentPackage(listOf(
            window(game, true), window(launcher, true),
        )))
        assertNull(ForegroundWindowGate.currentPackage(listOf(
            window(game, true), window(launcher, false, active = true),
        )))
    }

    @Test
    fun transientRecentsTransitionMustSettleBeforeGameCapture() {
        val gate = StableForeground(game, settleMillis = 800)
        assertFalse(gate.confirmed(launcher, 0))
        assertFalse(gate.confirmed(game, 100))
        assertFalse(gate.confirmed(game, 899))
        assertTrue(gate.confirmed(game, 900))
        assertFalse(gate.confirmed(null, 930))
        assertFalse(gate.confirmed(game, 1000))
        assertTrue(gate.confirmed(game, 1800))
    }

    @Test
    fun clockResetAndPackageChangesInvalidatePriorFocus() {
        val gate = StableForeground(game, settleMillis = 800)
        assertFalse(gate.confirmed(game, 1500))
        assertTrue(gate.confirmed(game, 2300))
        assertFalse(gate.confirmed(game, 100))
        assertFalse(gate.confirmed(launcher, 150))
        assertFalse(gate.confirmed(game, 200))
        assertFalse(gate.confirmed(game, 999))
        assertTrue(gate.confirmed(game, 1000))
    }
}
