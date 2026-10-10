package com.yurii.dungeonrushloot.runtime

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Bitmap
import android.graphics.Path
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import com.yurii.dungeonrushloot.model.RelativeRect
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.coroutines.suspendCoroutine
import kotlin.math.roundToInt
import kotlin.random.Random
import kotlinx.coroutines.delay

class AccessibilityScreenshotAdapter(
    private val service: AccessibilityService,
) : ScreenCaptureAdapter {
    override suspend fun capture(): CapturedFrame = suspendCoroutine { continuation ->
        service.takeScreenshot(
            Display.DEFAULT_DISPLAY,
            service.mainExecutor,
            object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                    try {
                        val hardware = result.hardwareBuffer
                        val wrapped = Bitmap.wrapHardwareBuffer(hardware, result.colorSpace)
                            ?: error("Could not wrap accessibility screenshot buffer.")
                        val bitmap = wrapped.copy(Bitmap.Config.ARGB_8888, false)
                            ?: error("Could not copy accessibility screenshot.")
                        hardware.close()
                        continuation.resume(CapturedFrame(bitmap))
                    } catch (error: Throwable) {
                        continuation.resumeWithException(error)
                    }
                }

                override fun onFailure(errorCode: Int) {
                    continuation.resumeWithException(
                        IllegalStateException("Accessibility screenshot failed with code $errorCode"),
                    )
                }
            },
        )
    }
}

class AccessibilityTouchAdapter(
    private val service: AccessibilityService,
    private val random: Random = Random.Default,
) : TouchAdapter {
    override suspend fun tap(
        target: RelativeRect,
        screenWidth: Int,
        screenHeight: Int,
    ): Boolean {
        val left = (target.left * screenWidth).roundToInt()
        val right = (target.right * screenWidth).roundToInt()
        val top = (target.top * screenHeight).roundToInt()
        val bottom = (target.bottom * screenHeight).roundToInt()

        val startX = random.nextInt(left, right.coerceAtLeast(left + 1))
        val startY = random.nextInt(top, bottom.coerceAtLeast(top + 1))
        val endX = (startX + random.nextInt(-7, 8)).coerceIn(left, right)
        val endY = (startY + random.nextInt(-7, 8)).coerceIn(top, bottom)
        val duration = random.nextLong(55, 126)

        delay(random.nextLong(80, 221))
        return suspendCoroutine { continuation ->
            val path = Path().apply {
                moveTo(startX.toFloat(), startY.toFloat())
                lineTo(endX.toFloat(), endY.toFloat())
            }
            val gesture = GestureDescription.Builder()
                .addStroke(GestureDescription.StrokeDescription(path, 0, duration))
                .build()
            val accepted = service.dispatchGesture(
                gesture,
                object : AccessibilityService.GestureResultCallback() {
                    override fun onCompleted(gestureDescription: GestureDescription) {
                        continuation.resume(true)
                    }

                    override fun onCancelled(gestureDescription: GestureDescription) {
                        continuation.resume(false)
                    }
                },
                null,
            )
            if (!accepted) {
                continuation.resume(false)
            }
        }
    }
}

class AccessibilityForegroundAdapter(
    private val service: AccessibilityService,
) : ForegroundAppAdapter {
    @Volatile
    private var lastEventPackage: String? = null

    fun onAccessibilityEvent(event: AccessibilityEvent?) {
        event?.packageName?.toString()?.let { lastEventPackage = it }
    }

    override fun currentPackage(): String? =
        service.rootInActiveWindow?.packageName?.toString() ?: lastEventPackage
}
