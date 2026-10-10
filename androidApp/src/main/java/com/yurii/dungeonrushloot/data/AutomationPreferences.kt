package com.yurii.dungeonrushloot.data

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

class AutomationPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("automation", Context.MODE_PRIVATE)

    private val _enabled = MutableStateFlow(prefs.getBoolean(KEY_ENABLED, false))
    val enabled: StateFlow<Boolean> = _enabled

    private val _strategy = MutableStateFlow(prefs.getString(KEY_STRATEGY, "universal") ?: "universal")
    val strategy: StateFlow<String> = _strategy

    fun setEnabled(value: Boolean) {
        prefs.edit().putBoolean(KEY_ENABLED, value).apply()
        _enabled.value = value
    }

    fun setStrategy(value: String) {
        require(value in setOf("universal", "pve", "pvp"))
        prefs.edit().putString(KEY_STRATEGY, value).apply()
        _strategy.value = value
    }

    companion object {
        private const val KEY_ENABLED = "enabled"
        private const val KEY_STRATEGY = "strategy"
    }
}
