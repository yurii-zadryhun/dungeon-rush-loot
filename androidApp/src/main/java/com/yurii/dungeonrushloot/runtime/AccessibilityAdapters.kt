package com.yurii.dungeonrushloot.runtime

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Bitmap
import android.graphics.Path
import android.view.Display
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityWindowInfo
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
    private val foreground: ForegroundAppAdapter,
    private val gamePackage: String,
    private val random: Random = Random.Default,
) : TouchAdapter {
    override suspend fun tap(
        target: RelativeRect,
        screenWidth: Int,
        screenHeight: Int,
    ): Boolean {
        if (foreground.currentPackage() != gamePackage) return false
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
        // Recheck immediately before dispatch: the user may open Recents
        // during the randomized gesture delay.
        if (foreground.currentPackage() != gamePackage) return false
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
    override fun currentPackage(): String? {
        // Requires FLAG_RETRIEVE_INTERACTIVE_WINDOWS. The last event or the
        // root of an inactive task is NOT proof that Dungeon Rush is foreground.
        val windows = service.windows.map { window ->
            ForegroundWindow(
                packageName = window.root?.packageName?.toString(),
                focused = window.isFocused,
                active = window.isActive,
                application = window.type == AccessibilityWindowInfo.TYPE_APPLICATION,
            )
        }
        return ForegroundWindowGate.currentPackage(windows)
    }
}
