package com.yurii.dungeonrushloot.data

import android.content.Context
import com.yurii.dungeonrushloot.model.EquipmentDraft
import com.yurii.dungeonrushloot.runtime.EquipmentStateAdapter
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import org.json.JSONObject

class EquipmentStore(context: Context) : EquipmentStateAdapter {
    private val prefs = context.getSharedPreferences("equipment", Context.MODE_PRIVATE)
    private val _rawJson = MutableStateFlow(
        prefs.getString(KEY_JSON, null) ?: defaultEquipmentJson(),
    )
    val rawJson: StateFlow<String> = _rawJson

    fun drafts(): Map<String, EquipmentDraft> {
        val root = JSONObject(_rawJson.value)
        return SLOT_NAMES.associateWith { slot ->
            val item = root.optJSONObject(slot) ?: JSONObject()
            val statsObject = item.optJSONObject("stats") ?: JSONObject()
            val stats = LinkedHashMap<String, Double>()
            statsObject.keys().forEach { name ->
                stats[name] = statsObject.optDouble(name, 0.0)
            }
            EquipmentDraft(
                title = item.optString("title"),
                rarity = item.optString("rarity", "Divine"),
                level = item.optInt("level", 1),
                stats = stats,
            )
        }
    }

    fun save(slot: String, draft: EquipmentDraft) {
        require(slot in SLOT_NAMES)
        val root = JSONObject(_rawJson.value)
        val stats = JSONObject()
        draft.stats.forEach { (name, value) -> stats.put(name, value) }
        root.put(
            slot,
            JSONObject()
                .put("title", draft.title)
                .put("rarity", draft.rarity)
                .put("level", draft.level)
                .put("stats", stats),
        )
        replaceRaw(root.toString())
    }

    override fun currentJson(): String = _rawJson.value

    override fun replaceRaw(raw: String) {
        prefs.edit().putString(KEY_JSON, raw).apply()
        _rawJson.value = raw
    }

    fun reset() {
        replaceRaw(defaultEquipmentJson())
    }

    private fun defaultEquipmentJson(): String {
        val root = JSONObject()
        SLOT_NAMES.forEach { slot ->
            root.put(
                slot,
                JSONObject()
                    .put("title", "")
                    .put("rarity", "Divine")
                    .put("level", 1)
                    .put("stats", JSONObject()),
            )
        }
        return root.toString()
    }

    companion object {
        private const val KEY_JSON = "equipment_json"
        val SLOT_NAMES = listOf("weapon", "helmet", "backpack", "gloves", "necklace", "ring")
    }
}
