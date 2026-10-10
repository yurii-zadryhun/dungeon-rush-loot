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
            val stats = item.optJSONObject("stats").toDoubleMap()
            val intrinsic = item.optJSONObject("intrinsic_stats").toDoubleMap()
            val primary = item.optJSONObject("primary")
            EquipmentDraft(
                title = item.optString("title"),
                rarity = item.optString("rarity", defaultRarity(slot)),
                level = item.optInt("level", 1),
                stats = stats,
                primaryAttack = primary?.optNullableDouble("attack"),
                primaryHealth = primary?.optNullableDouble("health"),
                intrinsicStats = intrinsic,
            )
        }
    }

    fun save(slot: String, draft: EquipmentDraft) {
        require(slot in SLOT_NAMES)
        val root = JSONObject(_rawJson.value)
        val item = JSONObject()
            .put("title", draft.title)
            .put("rarity", draft.rarity)
            .put("level", draft.level)
            .put("stats", JSONObject(draft.stats as Map<*, *>))

        if (draft.primaryAttack != null || draft.primaryHealth != null) {
            item.put(
                "primary",
                JSONObject()
                    .put("attack", draft.primaryAttack)
                    .put("health", draft.primaryHealth),
            )
        }
        if (draft.intrinsicStats.isNotEmpty()) {
            item.put("intrinsic_stats", JSONObject(draft.intrinsicStats as Map<*, *>))
        }

        root.put(slot, item)
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
                    .put("rarity", defaultRarity(slot))
                    .put("level", 1)
                    .put("stats", JSONObject()),
            )
        }
        return root.toString()
    }

    private fun defaultRarity(slot: String): String =
        if (slot == "cape") "Mythic" else "Divine"

    private fun JSONObject?.toDoubleMap(): LinkedHashMap<String, Double> {
        val result = linkedMapOf<String, Double>()
        if (this == null) return result
        keys().forEach { name -> result[name] = optDouble(name, 0.0) }
        return result
    }

    private fun JSONObject.optNullableDouble(name: String): Double? =
        if (!has(name) || isNull(name)) null else optDouble(name)

    companion object {
        private const val KEY_JSON = "equipment_json"
        val SLOT_NAMES = listOf(
            "weapon",
            "helmet",
            "backpack",
            "gloves",
            "necklace",
            "ring",
            "wings",
            "cape",
        )
    }
}
