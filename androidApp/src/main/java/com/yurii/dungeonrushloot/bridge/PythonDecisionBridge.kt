package com.yurii.dungeonrushloot.bridge

import com.chaquo.python.Python
import com.yurii.dungeonrushloot.model.AppConfig
import com.yurii.dungeonrushloot.model.DecisionEvent
import com.yurii.dungeonrushloot.model.EquipmentValidation
import com.yurii.dungeonrushloot.model.OcrSpanDto
import org.json.JSONArray
import org.json.JSONObject

class PythonDecisionBridge {
    private val module by lazy { Python.getInstance().getModule("src.android_bridge") }

    val config: AppConfig by lazy {
        AppConfig.fromJson(module.callAttr("app_config_json").toString())
    }

    fun validateEquipment(raw: String): EquipmentValidation {
        val result = JSONObject(module.callAttr("validate_equipment_json", raw).toString())
        return EquipmentValidation(
            valid = result.getBoolean("valid"),
            normalizedJson = result.optJSONObject("normalized")?.toString(),
            error = result.optString("error").takeIf { it.isNotBlank() && it != "null" },
        )
    }

    fun evaluate(
        spans: List<OcrSpanDto>,
        equipmentJson: String,
        strategy: String,
    ): DecisionEvent {
        val payload = JSONArray()
        spans.forEach { payload.put(it.toJson()) }
        val raw = module.callAttr(
            "evaluate_spans_json",
            payload.toString(),
            equipmentJson,
            strategy,
        ).toString()
        return DecisionEvent.fromJson(raw)
    }

    fun replaceEquipment(
        equipmentJson: String,
        slot: String,
        candidateJson: String,
    ): String = module.callAttr(
        "replace_equipment_json",
        equipmentJson,
        slot,
        candidateJson,
    ).toString()
}
