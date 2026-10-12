package com.yurii.dungeonrushloot.runtime

import kotlin.math.roundToInt

/** Projects upstream PaddleOCR quadrilateral coordinates to original screen pixels. */
internal object PaddleOcrCoordinates {
    data class Rect(val left: Int, val top: Int, val right: Int, val bottom: Int)

    fun toScreen(
        xs: List<Float>, ys: List<Float>,
        cropLeft: Int, cropTop: Int, scale: Float,
        screenWidth: Int, screenHeight: Int,
    ): Rect? {
        if (xs.size != 4 || ys.size != 4 || scale <= 0f || !scale.isFinite() ||
            screenWidth <= 0 || screenHeight <= 0 ||
            xs.any { !it.isFinite() } || ys.any { !it.isFinite() }) return null
        val left = (cropLeft + xs.min() / scale).roundToInt().coerceIn(0, screenWidth - 1)
        val top = (cropTop + ys.min() / scale).roundToInt().coerceIn(0, screenHeight - 1)
        val right = (cropLeft + xs.max() / scale).roundToInt().coerceIn(left + 1, screenWidth)
        val bottom = (cropTop + ys.max() / scale).roundToInt().coerceIn(top + 1, screenHeight)
        return Rect(left, top, right, bottom)
    }
}
