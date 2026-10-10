package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.data.OcrDebugZip
import com.yurii.dungeonrushloot.model.RelativeRect
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.zip.ZipInputStream
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

class OcrDebugCaptureTest {
    @Test
    fun oneShotClaimCannotBeReplayedOrRearmedWhileCapturing() {
        val state = OcrDebugCapture()
        assertFalse(state.claim())
        assertTrue(state.arm())
        assertFalse(state.arm())
        assertTrue(state.claim())
        assertFalse(state.claim())
        assertFalse(state.arm())
        assertFalse(state.cancel())
        state.saved("dungeon-rush-ocr-debug-20261010-202000.zip")
        assertTrue(state.state.value is OcrDebugCapture.State.Saved)
        assertFalse(state.claim())
        assertTrue(state.arm()) // explicit second user action only
    }

    @Test
    fun cancellationAndFailureAllowUserToRetry() {
        val state = OcrDebugCapture()
        assertTrue(state.arm())
        assertTrue(state.cancel())
        assertFalse(state.claim())
        assertTrue(state.arm())
        assertTrue(state.claim())
        state.failed("No screenshot")
        assertEquals("No screenshot", (state.state.value as OcrDebugCapture.State.Failed).reason)
        assertTrue(state.arm())
        assertTrue(state.claim())
    }

    @Test
    fun cropUsesActualBitmapRoundingForSourceScreenshotAndAlternateResolution() {
        val rect = RelativeRect(0.125f, 0.40f, 0.875f, 0.82f)
        val source = OcrCropPixels.from(rect, 709, 1536)
        assertEquals(OcrCropPixels(89, 614, 620, 1260), source)
        assertEquals(531, source.width)
        assertEquals(646, source.height)

        assertEquals(
            OcrCropPixels(135, 936, 945, 1919),
            OcrCropPixels.from(rect, 1080, 2340),
        )
    }

    @Test
    fun cropValidationRejectsInvalidInput() {
        for (rect in listOf(
            RelativeRect(-0.1f, 0.1f, 0.9f, 0.8f),
            RelativeRect(0.5f, 0.1f, 0.5f, 0.8f),
            RelativeRect(0.1f, 0.9f, 0.9f, 0.8f),
        )) {
            try {
                OcrCropPixels.from(rect, 709, 1536)
                fail("Accepted invalid ROI: $rect")
            } catch (_: IllegalArgumentException) {
                // Expected.
            }
        }
    }

    @Test
    fun debugZipContainsAllImagesAndOcrMetadataWithoutLoss() {
        val files = linkedMapOf(
            "screen.png" to byteArrayOf(1, 2, 3),
            "ocr-crop.png" to byteArrayOf(4, 5),
            "ocr-input.png" to byteArrayOf(6, 7, 8, 9),
            "ocr.json" to """{"ocr_scale":2.5,"ocr_lines":[]}""".toByteArray(),
        )
        val zipped = ByteArrayOutputStream().apply { OcrDebugZip.write(this, files) }.toByteArray()
        val restored = linkedMapOf<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(zipped)).use { zip ->
            while (true) {
                val entry = zip.nextEntry ?: break
                restored[entry.name] = zip.readBytes()
                zip.closeEntry()
            }
        }
        assertEquals(OcrDebugZip.filenames, restored.keys.toList())
        files.forEach { (name, bytes) -> assertArrayEquals(bytes, restored[name]) }
    }

    @Test
    fun debugZipRejectsMissingAndAdditionalFiles() {
        for (files in listOf(
            linkedMapOf("screen.png" to byteArrayOf(1)),
            linkedMapOf(
                "screen.png" to byteArrayOf(1),
                "ocr-crop.png" to byteArrayOf(2),
                "ocr-input.png" to byteArrayOf(3),
                "unexpected.txt" to byteArrayOf(4),
            ),
        )) {
            try {
                OcrDebugZip.write(ByteArrayOutputStream(), files)
                fail("Accepted incomplete or extra entries")
            } catch (_: IllegalArgumentException) {
                // Expected.
            }
        }
    }
}
