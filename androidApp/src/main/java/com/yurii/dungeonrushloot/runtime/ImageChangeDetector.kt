package com.yurii.dungeonrushloot.runtime

import android.graphics.Bitmap
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.math.abs
import kotlin.math.roundToInt

object ImageChangeDetector {
    fun changed(
        before: Bitmap,
        after: Bitmap,
        region: RelativeRect,
        threshold: Double = 0.010,
    ): Boolean {
        if (before.width != after.width || before.height != after.height) return false
        val beforeSignature = signature(before, region)
        val afterSignature = signature(after, region)
        if (beforeSignature.size != afterSignature.size || beforeSignature.isEmpty()) return false
        val difference = beforeSignature.indices.sumOf {
            abs(beforeSignature[it] - afterSignature[it]).toDouble()
        } / (255.0 * beforeSignature.size)
        return difference >= threshold
    }

    private fun signature(bitmap: Bitmap, region: RelativeRect): IntArray {
        val left = (region.left * bitmap.width).roundToInt().coerceIn(0, bitmap.width - 1)
        val top = (region.top * bitmap.height).roundToInt().coerceIn(0, bitmap.height - 1)
        val right = (region.right * bitmap.width).roundToInt().coerceIn(left + 1, bitmap.width)
        val bottom = (region.bottom * bitmap.height).roundToInt().coerceIn(top + 1, bitmap.height)

        val samplesX = 48
        val samplesY = 32
        return IntArray(samplesX * samplesY) { index ->
            val xIndex = index % samplesX
            val yIndex = index / samplesX
            val x = left + ((right - left - 1) * xIndex / (samplesX - 1).coerceAtLeast(1))
            val y = top + ((bottom - top - 1) * yIndex / (samplesY - 1).coerceAtLeast(1))
            val pixel = bitmap.getPixel(x, y)
            val red = (pixel shr 16) and 0xff
            val green = (pixel shr 8) and 0xff
            val blue = pixel and 0xff
            (red * 299 + green * 587 + blue * 114) / 1000
        }
    }
}
