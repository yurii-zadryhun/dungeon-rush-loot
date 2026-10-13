package com.yurii.dungeonrushloot.runtime

/**
 * Bounded deduplication of *completed* automation actions, not an OCR cache.
 *
 * Failed gestures and unconfirmed equips are intentionally never recorded.
 * Callers supply Android's monotonic SystemClock.elapsedRealtime() to avoid
 * time-of-day changes extending a cooldown indefinitely.
 */
internal class CandidateRetryGate(private val ttlMillis: Long = 5_000L) {
    init { require(ttlMillis > 0) }

    private var lastKey: String? = null
    private var handledAtMillis: Long = 0L

    fun isSuppressed(key: String, nowMillis: Long): Boolean =
        key == lastKey && nowMillis >= handledAtMillis &&
            nowMillis - handledAtMillis < ttlMillis

    fun markHandled(key: String, nowMillis: Long) {
        lastKey = key
        handledAtMillis = nowMillis
    }
}
