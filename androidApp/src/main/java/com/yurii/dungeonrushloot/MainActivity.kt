package com.yurii.dungeonrushloot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.yurii.dungeonrushloot.app.AppGraph
import com.yurii.dungeonrushloot.ui.DungeonRushLootApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val graph = AppGraph.get(this)
        setContent {
            DungeonRushLootApp(graph)
        }
    }
}
