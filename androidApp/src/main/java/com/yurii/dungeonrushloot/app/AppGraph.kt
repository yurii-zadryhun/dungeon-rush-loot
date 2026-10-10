package com.yurii.dungeonrushloot.app

import android.content.Context
import com.yurii.dungeonrushloot.bridge.PythonDecisionBridge
import com.yurii.dungeonrushloot.data.AutomationPreferences
import com.yurii.dungeonrushloot.data.DecisionLogStore
import com.yurii.dungeonrushloot.data.EquipmentStore

class AppGraph private constructor(context: Context) {
    private val appContext = context.applicationContext

    val bridge: PythonDecisionBridge by lazy { PythonDecisionBridge() }
    val preferences: AutomationPreferences by lazy { AutomationPreferences(appContext) }
    val equipment: EquipmentStore by lazy { EquipmentStore(appContext) }
    val logs: DecisionLogStore by lazy { DecisionLogStore(appContext) }

    companion object {
        @Volatile
        private var instance: AppGraph? = null

        fun get(context: Context): AppGraph =
            instance ?: synchronized(this) {
                instance ?: AppGraph(context).also { instance = it }
            }
    }
}
