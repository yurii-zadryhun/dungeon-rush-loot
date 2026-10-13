package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import org.junit.Assert.*
import org.junit.Test

class BadgeOcrPassTest {
    @Test fun diagnosticsKeepUnfilteredTextConfidenceAndScreenCoordinates() {
        val pass = BadgeOcrPass(
            "level", RelativeRect(0.17f, 0.4f, 0.335f, 0.5f), 4f, true,
            listOf(
                OcrSpanDto("Lv?", 0.12f, 180, 440, 230, 460),
                OcrSpanDto("Lvl 87", 0.98f, 180, 470, 240, 490),
            ),
        )
        val json = pass.toJson()
        assertEquals("level", json.getString("kind"))
        assertEquals(4.0, json.getDouble("scale"), 0.0)
        assertTrue(json.getBoolean("light_text"))
        assertEquals(0.17, json.getJSONObject("crop").getDouble("left"), 0.0001)
        val lines = json.getJSONArray("ocr_lines")
        assertEquals(2, lines.length())
        assertEquals("Lv?", lines.getJSONObject(0).getString("text"))
        assertEquals(0.12, lines.getJSONObject(0).getDouble("score"), 0.0001)
        assertEquals(180, lines.getJSONObject(0).getJSONObject("box").getInt("left"))
        assertEquals(490, lines.getJSONObject(1).getJSONObject("box").getInt("bottom"))
    }

    @Test fun emptyRecognitionStillRecordsAttemptedRegion() {
        val json = BadgeOcrPass(
            "rarity", RelativeRect(0.155f, 0.3f, 0.345f, 0.9f), 2f, false, emptyList(),
        ).toJson()
        assertEquals(0, json.getJSONArray("ocr_lines").length())
        assertFalse(json.getBoolean("light_text"))
        assertTrue(json.has("crop"))
    }
}