package com.yurii.dungeonrushloot.runtime

/**
 * The game must hold the actual window focus long enough for Android's Recents
 * transition to finish. No reference to cached event packages or screenshots
 * of task thumbnails is considered evidence of foreground ownership.
 */
internal class StableForeground(
    private val expectedPackage: String,
    private val settleMillis: Long = 800L,
) {
    private var focusedSince: Long? = null

    fun confirmed(packageName: String?, elapsedMillis: Long): Boolean {
        if (packageName != expectedPackage) {
            focusedSince = null
            return false
        }
        val since = focusedSince
        if (since == null || elapsedMillis < since) {
            focusedSince = elapsedMillis
            return false
        }
        return elapsedMillis - since >= settleMillis
    }
}
