package com.yurii.dungeonrushloot.model

import org.json.JSONArray
import org.json.JSONObject

data class RelativeRect(
    val left: Float,
    val top: Float,
    val right: Float,
    val bottom: Float,
) {
    companion object {
        fun fromJson(value: JSONObject) = RelativeRect(
            value.getDouble("left").toFloat(),
            value.getDouble("top").toFloat(),
            value.getDouble("right").toFloat(),
            value.getDouble("bottom").toFloat(),
        )
    }
}

data class SkillDefinition(
    val name: String,
    val perItemCap: Double,
    val category: String,
    val exceptional: Boolean,
)

data class RarityDefinition(
    val name: String,
    val tier: Int,
)

data class AppConfig(
    val targetPackage: String,
    val crop: RelativeRect,
    val equipmentImportCrop: RelativeRect,
    val equipmentImportLevelCrop: RelativeRect,
    val targets: Map<String, RelativeRect>,
    val slots: List<String>,
    val rarities: List<RarityDefinition>,
    val skills: List<SkillDefinition>,
    val minimumAffixes: Int,
    val maximumAffixes: Int,
    val normalAffixesByRarity: Map<String, Int>,
    val minExceptionalAffixes: Int,
    val maxExceptionalAffixes: Int,
    val divineWingsNormalAffixes: Int,
) {
    companion object {
        fun fromJson(raw: String): AppConfig {
            val json = JSONObject(raw)
            val targetJson = json.getJSONObject("targets")
            val targets = targetJson.keys().asSequence().associateWith {
                RelativeRect.fromJson(targetJson.getJSONObject(it))
            }
            val rarities = json.getJSONArray("rarities").toObjectList {
                RarityDefinition(it.getString("name"), it.getInt("tier"))
            }
            val skills = json.getJSONArray("skills").toObjectList {
                SkillDefinition(
                    it.getString("name"),
                    it.getDouble("per_item_cap"),
                    it.getString("category"),
                    it.getBoolean("exceptional"),
                )
            }
            val slots = json.getJSONArray("slots").toStringList()
            return AppConfig(
                targetPackage = json.getString("target_package"),
                crop = RelativeRect.fromJson(json.getJSONObject("crop")),
                equipmentImportCrop = RelativeRect.fromJson(json.getJSONObject("equipment_import_crop")),
                equipmentImportLevelCrop = RelativeRect.fromJson(json.getJSONObject("equipment_import_level_crop")),
                targets = targets,
                slots = slots,
                rarities = rarities,
                skills = skills,
                minimumAffixes = json.getJSONObject("affix_bounds").getInt("min"),
                maximumAffixes = json.getJSONObject("affix_bounds").getInt("max"),
                normalAffixesByRarity = json.getJSONObject("rarity_normal_affixes").let { rules ->
                    rules.keys().asSequence().associateWith { rules.getInt(it) }
                },
                minExceptionalAffixes = json.getJSONObject("exp_exceptional_bounds").getInt("min"),
                maxExceptionalAffixes = json.getJSONObject("exp_exceptional_bounds").getInt("max"),
                divineWingsNormalAffixes = json.getInt("divine_wings_normal_affixes"),
            )
        }
    }
}

data class EquipmentDraft(
    val title: String,
    val rarity: String,
    val level: Int,
    val stats: LinkedHashMap<String, Double>,
    val primaryAttack: Double? = null,
    val primaryHealth: Double? = null,
    val intrinsicStats: LinkedHashMap<String, Double> = linkedMapOf(),
)

data class EquipmentValidation(
    val valid: Boolean,
    val normalizedJson: String?,
    val error: String?,
)

data class EquipmentImportResult(
    val rawJson: String,
    val status: String,
    var slot: String?,
    val slotConfidence: Double,
    val itemJson: String?,
    val title: String?,
    val rarity: String?,
    val level: Int?,
    val issues: List<String>,
    val rawLines: List<String>,
) {
    val isParsed: Boolean
        get() = itemJson != null

    companion object {
        fun fromJson(raw: String): EquipmentImportResult {
            val json = JSONObject(raw)
            val item = json.optJSONObject("item")
            return EquipmentImportResult(
                rawJson = raw,
                status = json.optString("status"),
                slot = json.optString("slot").takeIf { it.isNotBlank() && it != "null" },
                slotConfidence = json.optDouble("slot_confidence", 0.0),
                itemJson = item?.toString(),
                title = item?.optString("title"),
                rarity = item?.optString("rarity"),
                level = item?.optInt("level"),
                issues = json.optJSONArray("issues")?.toStringList().orEmpty(),
                rawLines = json.optJSONArray("raw_lines")?.toStringList().orEmpty(),
            )
        }
    }
}

data class OcrSpanDto(
    val text: String,
    val score: Float,
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    fun toJson(): JSONObject = JSONObject()
        .put("text", text)
        .put("score", score)
        .put(
            "box",
            JSONObject()
                .put("left", left)
                .put("top", top)
                .put("right", right)
                .put("bottom", bottom),
        )
}

data class DecisionEvent(
    val rawJson: String,
    val timestamp: String,
    val status: String,
    val action: String,
    val strategy: String?,
    val slot: String?,
    val message: String,
    val candidateJson: String?,
    val candidateKey: String?,
    val equippedScore: Double?,
    val candidateScore: Double?,
    val touchTarget: RelativeRect?,
    val confirmSellTarget: RelativeRect?,
    val needsSellConfirmation: Boolean,
) {
    companion object {
        fun fromJson(raw: String): DecisionEvent {
            val json = JSONObject(raw)
            val candidate = json.optJSONObject("candidate")
            return DecisionEvent(
                rawJson = raw,
                timestamp = json.optString("timestamp"),
                status = json.optString("status"),
                action = json.optString("action"),
                strategy = json.optString("strategy").takeIf { it.isNotBlank() && it != "null" },
                slot = json.optString("slot").takeIf { it.isNotBlank() && it != "null" },
                message = json.optString("message"),
                candidateJson = candidate?.toString(),
                // Backend key is canonical and excludes OCR raw_text/confidence.
                // A missing key on an otherwise OK event must fail closed.
                candidateKey = json.optString("verification_key")
                    .takeIf { !json.isNull("verification_key") && it.isNotBlank() && it != "null" },
                equippedScore = json.optJSONObject("equipped_score")?.optDouble("total"),
                candidateScore = json.optJSONObject("candidate_score")?.optDouble("total"),
                touchTarget = json.optJSONObject("touch_target")?.let(RelativeRect::fromJson),
                confirmSellTarget = json.optJSONObject("confirm_sell_target")?.let(RelativeRect::fromJson),
                needsSellConfirmation = json.optBoolean("needs_sell_confirmation"),
            )
        }
    }
}

data class DecisionLogEntry(
    val rawJson: String,
    val timestamp: String,
    val status: String,
    val action: String,
    val strategy: String?,
    val slot: String?,
    val message: String,
    val equippedScore: Double?,
    val candidateScore: Double?,
    val runtimeMessage: String?,
) {
    companion object {
        fun fromJson(raw: String): DecisionLogEntry {
            val json = JSONObject(raw)
            val runtime = json.optJSONObject("runtime")
            return DecisionLogEntry(
                rawJson = raw,
                timestamp = json.optString("timestamp"),
                status = json.optString("status"),
                action = json.optString("action"),
                strategy = json.optString("strategy").takeIf { it.isNotBlank() && it != "null" },
                slot = json.optString("slot").takeIf { it.isNotBlank() && it != "null" },
                message = json.optString("message"),
                equippedScore = json.optJSONObject("equipped_score")?.optDouble("total"),
                candidateScore = json.optJSONObject("candidate_score")?.optDouble("total"),
                runtimeMessage = runtime?.optString("message")?.takeIf { it.isNotBlank() },
            )
        }
    }
}

data class LogSession(
    val id: String,
    val startedAt: String,
    val endedAt: String?,
    val strategy: String?,
    val eventCount: Int,
    val active: Boolean,
)

internal fun <T> JSONArray.toObjectList(transform: (JSONObject) -> T): List<T> =
    List(length()) { index -> transform(getJSONObject(index)) }

internal fun JSONArray.toStringList(): List<String> =
    List(length()) { index -> getString(index) }
