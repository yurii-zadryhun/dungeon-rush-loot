package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class IconLevelRecoveryTest {
    private fun span(text: String, x: Int, y: Int, w: Int = 440): OcrSpanDto =
        OcrSpanDto(text, 0.88f, x, y, x + w, y + 38)

    @Test
    fun realScreenHasTwoIndependentIconRegionsOutsideAffixColumn() {
        val lines = listOf(
            span("Divine (EXP] Celestial Helmet", 218, 1162),
            span("Immortal [EXP] Dread Helm", 195, 1587),
            span("+18.92% Lifesteal", 390, 1288),
            span("+10.60% Movement Speed", 390, 1857),
        )
        val regions = IconLevelRecovery.regions(lines, 1080, 2340)
        assertEquals(2, regions.size)
        assertTrue(regions[0].top < regions[1].top)
        assertEquals(0.16f, regions[0].left)
        assertEquals(0.36f, regions[0].right)
        // The labels are on top of the icon around x=220..340;
        // affix lines begin around x=390.
        assertTrue(regions.all { it.right * 1080 < 390 })
        assertTrue(regions[0].top * 2340 < 1370)
        assertTrue(regions[0].bottom * 2340 > 1330)
        assertTrue(regions[1].top * 2340 < 1830)
        assertTrue(regions[1].bottom * 2340 > 1800)
    }

    @Test
    fun titleAnchoringAlsoWorksAt709x1536AndWithUpgradeMarker() {
        val lines = listOf(
            span("Divine [EXP] +11 Celestial Helmet", 145, 765),
            span("Immortal [EXP] +11 Dread Helm", 123, 1045),
        )
        val regions = IconLevelRecovery.regions(lines, 709, 1536)
        assertEquals(2, regions.size)
        assertTrue(regions[0].top * 1536 <= 867)
        assertTrue(regions[0].bottom * 1536 >= 886)
        assertTrue(regions[1].top * 1536 <= 1150)
        assertTrue(regions[1].bottom * 1536 >= 1170)
    }

    @Test
    fun allAllowedItemLevelsProduceARecognizableLabel() {
        for (level in 1..130) {
            for (prefix in listOf("Lvl ", "LvI ", "LvU ", "LU ")) {
                val found = IconLevelRecovery.eligibleLevel(listOf(span("$prefix$level", 220, 1320)))
                assertEquals("$prefix$level", 1, found.size)
            }
        }
    }

    @Test
    fun garbageNumbersAndAffixesNeverBecomeIconLevels() {
        val garbage = listOf(
            "87", "4", "Level 87", "Damage 477.00K", "Lvl", "Lvl ???",
            "x4", "123", "+18.92% Lifesteal", "Lvl 87 +18.92% Lifesteal",
            "LvI83%", "Health 3.28M", "LVL 4% Damage",
        )
        for (value in garbage) {
            assertTrue(value, IconLevelRecovery.eligibleLevel(listOf(span(value, 220, 1320))).isEmpty())
        }
    }

    @Test
    fun missingOrAmbiguousTitlesCannotTriggerIconRecovery() {
        val a = span("Divine (EXP] Celestial Helmet", 218, 1162)
        val b = span("Immortal [EXP] Dread Helm", 195, 1587)
        for (lines in listOf(
            emptyList(), listOf(a), listOf(a, a), listOf(a, b, b),
            listOf(span("Lvl 123", 875, 1360), span("x4", 900, 1900)),
            listOf(span("Health 3.28M", 400, 1250), span("Health 477K", 400, 1660)),
        )) {
            assertTrue(IconLevelRecovery.regions(lines, 1080, 2340).isEmpty())
        }
    }

    @Test
    fun productionCropRoundingIsPreserved() {
        val crop = RelativeRect(0.125f, 0.40f, 0.875f, 0.82f)
        assertEquals(OcrCropPixels(89, 614, 620, 1260),
                     OcrCropPixels.from(crop, 709, 1536))
        assertEquals(OcrCropPixels(135, 936, 945, 1919),
                     OcrCropPixels.from(crop, 1080, 2340))
    }

    @Test
    fun screenAndTitleGeometryMustBeValid() {
        val lines = listOf(span("Divine Celestial Helmet", 218, 1162),
                           span("Immortal Dread Helm", 195, 1587))
        assertTrue(IconLevelRecovery.regions(lines, 0, 0).isEmpty())
        assertTrue(IconLevelRecovery.regions(lines, 100, 300).isEmpty())
        assertEquals(2, IconLevelRecovery.regions(lines, 1080, 2340).size)
    }
}
