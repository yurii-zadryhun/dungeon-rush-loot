package com.yurii.dungeonrushloot.runtime

/**
 * An Accessibility event's last package is NOT evidence of the displayed app:
 * Android Recents can show a snapshot of Dungeon Rush while the launcher is
 * focused, and the last game event can remain cached indefinitely.
 *
 * Fail closed if we cannot determine a *single focused application*.
 */
internal data class ForegroundWindow(
    val packageName: String?,
    val focused: Boolean,
    val active: Boolean,
    val application: Boolean,
)

internal object ForegroundWindowGate {
    fun currentPackage(windows: List<ForegroundWindow>): String? {
        val focusedApps = windows.filter { it.application && it.focused }
        if (focusedApps.size != 1) return null
        val packageName = focusedApps.single().packageName
        if (packageName.isNullOrBlank()) return null
        // If a different application is reported active simultaneously, the
        // transition is incomplete: do not assume it's safe to interact.
        if (windows.any {
            it.application && it.active &&
                !it.packageName.isNullOrBlank() && it.packageName != packageName
        }) return null
        return packageName
    }
}
