package com.yurii.dungeonrushloot.runtime

import org.junit.Assert.*
import org.junit.Test

class PaddleOcrCoordinatesTest {
    @Test fun scaledCropIsReprojectedToFullScreen() {
        val rect = PaddleOcrCoordinates.toScreen(
            listOf(20f, 220f, 220f, 20f), listOf(40f, 40f, 80f, 80f),
            cropLeft = 135, cropTop = 936, scale = 2f,
            screenWidth = 1080, screenHeight = 2340,
        )
        assertEquals(PaddleOcrCoordinates.Rect(145, 956, 245, 976), rect)
    }

    @Test fun angledBoxesAreClippedSafely() {
        val rect = PaddleOcrCoordinates.toScreen(
            listOf(-30f, 60f, 65f, -35f), listOf(-20f, -10f, 90f, 80f),
            0, 0, 3f, 200, 100,
        )
        assertEquals(PaddleOcrCoordinates.Rect(0, 0, 22, 30), rect)
    }

    @Test fun malformedCoordinatesAreRejected() {
        assertNull(PaddleOcrCoordinates.toScreen(listOf(1f), listOf(1f), 0, 0, 2f, 300, 500))
        assertNull(PaddleOcrCoordinates.toScreen(
            listOf(1f, 2f, Float.NaN, 4f), listOf(1f, 2f, 3f, 4f),
            0, 0, 2f, 300, 500,
        ))
        assertNull(PaddleOcrCoordinates.toScreen(
            List(4) { 1f }, List(4) { 1f }, 0, 0, 0f, 300, 500,
        ))
    }
}
