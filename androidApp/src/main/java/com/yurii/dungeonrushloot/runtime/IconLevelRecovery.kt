package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.max
import kotlin.math.min

/**
 * Locate each item's icon-level label relative to its OWN rarity heading,
 * not a fixed Y or the text area's variable-length title/affixes.
 *
 * Full-height left-strip OCR supplies rarity anchors; the title-based path
 * remains a fail-closed fallback for a full-popup OCR pass.
 */
internal object IconLevelRecovery {
    private val rarity = Regex(
        """^(?:common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)$""",
        RegexOption.IGNORE_CASE,
    )
    private val rarityInTitle = Regex(
        """\b(?:common|uncommon|rare|epic|legendary|mythic|artifact|ancient|immortal|divine|ultimate)\b""",
        RegexOption.IGNORE_CASE,
    )
    private val item = Regex(
        """\b(?:helm(?:et)?|hat|cap|helmet|gloves?|gauntlets?|mittens?|ring|necklace|backpack|tome|quiver|shield|sword|axe|bow|crossbow|staff|dagger|mace|spear|cape|tiara|book|lyre|javelin|weapon)\b""",
        RegexOption.IGNORE_CASE,
    )
    // Only a short, level-like prefix can introduce the digits; arbitrary
    // non-digit OCR noise between Lv/LU and the number is tolerated.
    // Unlabelled numbers and % affixes are not levels.
    private val levelLabel = Regex(
        """\bL[vu][^\d\n]{0,3}\s*(?:\d{1,3}|\dO\d)\b(?!\s*%)""",
        RegexOption.IGNORE_CASE,
    )

    fun rarityAnchors(spans: List<OcrSpanDto>, screenHeight: Int): List<OcrSpanDto> {
        if (screenHeight < 400) return emptyList()
        val headings = spans
            .filter { rarity.matches(it.text.trim()) }
            .sortedBy { it.top }
        if (headings.size != 2) return emptyList()
        if (headings[1].top - headings[0].top < screenHeight * 0.09f) return emptyList()
        return headings
    }

    /** Normalized ROI directly under one detected rarity word. */
    fun regionForRarity(raritySpan: OcrSpanDto, screenHeight: Int): RelativeRect =
        RelativeRect(
            left = 0.17f,
            top = ((raritySpan.top + screenHeight * 0.035f) / screenHeight).coerceIn(0f, 1f),
            right = 0.335f,
            bottom = ((raritySpan.top + screenHeight * 0.095f) / screenHeight).coerceIn(0f, 1f),
        )

    fun regions(spans: List<OcrSpanDto>, screenWidth: Int, screenHeight: Int): List<RelativeRect> {
        if (screenWidth < 200 || screenHeight < 400) return emptyList()
        val headings = rarityAnchors(spans, screenHeight)
        if (headings.size == 2) return headings.map { regionForRarity(it, screenHeight) }
        // Older/full-popup OCR may combine rarity with title: preserve the
        // original anchoring path if both complete titles are identifiable.
        val titles = spans
            .filter { rarityInTitle.containsMatchIn(it.text) && item.containsMatchIn(it.text) }
            .filter { !it.text.contains('%') }
            .sortedBy { it.top }
        if (titles.size != 2 || titles[1].top - titles[0].top < screenHeight * 0.09f) {
            return emptyList()
        }
        return titles.map { regionForRarity(it, screenHeight) }
    }

    fun eligibleLevel(spans: List<OcrSpanDto>): List<OcrSpanDto> =
        spans.filter {
            levelLabel.containsMatchIn(it.text) && !it.text.contains('%')
        }
}

/**
 * Separates icon badges from the text column at their stable horizontal seam.
 * Both regions retain full card height: nothing assumes fixed card Y positions.
 */
internal object LootOcrColumns {
    fun left(crop: RelativeRect): RelativeRect = RelativeRect(
        left = max(crop.left, 0.155f),
        top = max(crop.top, 0.445f),
        right = min(crop.right, 0.345f),
        bottom = crop.bottom,
    )

    fun right(crop: RelativeRect): RelativeRect = RelativeRect(
        left = max(crop.left, 0.345f),
        top = crop.top,
        right = crop.right,
        bottom = crop.bottom,
    )
}
