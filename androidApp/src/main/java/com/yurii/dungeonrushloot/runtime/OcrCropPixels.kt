package com.yurii.dungeonrushloot.runtime

import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.roundToInt

/** Exact bitmap coordinates of the source image passed to the ML Kit crop. */
internal data class OcrCropPixels(
    val left: Int,
    val top: Int,
    val right: Int,
    val bottom: Int,
) {
    val width: Int get() = right - left
    val height: Int get() = bottom - top

    companion object {
        fun from(rect: RelativeRect, width: Int, height: Int): OcrCropPixels {
            require(width > 0 && height > 0)
            require(rect.left >= 0f && rect.top >= 0f)
            require(rect.right <= 1f && rect.bottom <= 1f)
            require(rect.left < rect.right && rect.top < rect.bottom)
            val left = (rect.left * width).roundToInt().coerceIn(0, width - 1)
            val top = (rect.top * height).roundToInt().coerceIn(0, height - 1)
            val right = (rect.right * width).roundToInt().coerceIn(left + 1, width)
            val bottom = (rect.bottom * height).roundToInt().coerceIn(top + 1, height)
            return OcrCropPixels(left, top, right, bottom)
        }
    }
}
