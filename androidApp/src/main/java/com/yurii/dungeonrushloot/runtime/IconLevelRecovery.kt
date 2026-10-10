package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.max
import kotlin.math.min

/**
 * The popup renders each item level inside the bottom of the icon, away from
 * the right-hand affix text. Full-popup ML Kit line OCR can omit BOTH labels
 * while reading every affix. Plan small independent crops using title positions.
 *
 * These crops are evidence-gathering, not inferred level values. If an icon
 * still cannot be read, the Python parser continues to reject the decision.
 */
internal object IconLevelRecovery {
    private val rarity = Regex(
        """\b(?:common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine)\b""",
        RegexOption.IGNORE_CASE,
    )
    private val item = Regex(
        """\b(?:helm(?:et)?|hat|cap|helmet|gloves?|gauntlets?|mittens?|ring|necklace|backpack|tome|quiver|shield|sword|axe|bow|crossbow|staff|dagger|mace|spear|cape|tiara|book|lyre|javelin|weapon)\b""",
        RegexOption.IGNORE_CASE,
    )
    // Deliberately anchored: unrelated numbers or Damage values are not levels.
    private val levelLabel = Regex(
        """\b(?:lvl|lvi|lvu|lu|lv|lv0)\s*[-:.]?\s*(?:\d{1,3}|\dO\d)\b""",
        RegexOption.IGNORE_CASE,
    )

    fun regions(spans: List<OcrSpanDto>, screenWidth: Int, screenHeight: Int): List<RelativeRect> {
        if (screenWidth < 200 || screenHeight < 400) return emptyList()
        val titles = spans
            .filter { rarity.containsMatchIn(it.text) && item.containsMatchIn(it.text) }
            .filter { !it.text.contains('%') && it.text.none(Char::isDigit) }
            .sortedBy { it.top }
        if (titles.size != 2) return emptyList()
        if (titles[1].top - titles[0].top < screenHeight * 0.09f) return emptyList()
        return titles.map { title ->
            // Measured from the real 709x1536 two-card popup:
            // title to icon-level text: ~110-120 px. Keep an ample margin.
            // X=0.17..0.35 covers only the icon, not affix values on its right.
            val top = (title.top + screenHeight * 0.055f) / screenHeight
            val bottom = (title.top + screenHeight * 0.105f) / screenHeight
            RelativeRect(
                0.16f,
                max(0f, top),
                0.36f,
                min(1f, bottom),
            )
        }.filter { it.bottom > it.top }
    }

    fun eligibleLevel(spans: List<OcrSpanDto>): List<OcrSpanDto> =
        spans.filter {
            // No unlabelled bare numbers, even if they happen to be 4 or 87.
            levelLabel.containsMatchIn(it.text) && !it.text.contains('%')
        }
}
