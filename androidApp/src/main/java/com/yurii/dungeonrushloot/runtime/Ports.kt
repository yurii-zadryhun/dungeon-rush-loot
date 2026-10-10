package com.yurii.dungeonrushloot.runtime

import android.graphics.Bitmap
import com.yurii.dungeonrushloot.model.DecisionEvent
import com.yurii.dungeonrushloot.model.OcrSpanDto
import com.yurii.dungeonrushloot.model.RelativeRect
import org.json.JSONObject

data class CapturedFrame(
    val bitmap: Bitmap,
    val capturedAtMillis: Long = System.currentTimeMillis(),
)

interface ScreenCaptureAdapter {
    suspend fun capture(): CapturedFrame
}

interface OcrAdapter : AutoCloseable {
    suspend fun recognize(frame: CapturedFrame, crop: RelativeRect): List<OcrSpanDto>
    suspend fun recognizeEnhanced(frame: CapturedFrame, crop: RelativeRect): List<OcrSpanDto> =
        recognize(frame, crop)

    /** Read level labels from the bottom of item icons if full-popup OCR missed them. */
    suspend fun recognizeIconLevels(
        frame: CapturedFrame, crop: RelativeRect, spans: List<OcrSpanDto>,
    ): List<OcrSpanDto> = emptyList()
}

interface TouchAdapter {
    suspend fun tap(target: RelativeRect, screenWidth: Int, screenHeight: Int): Boolean
}

interface ForegroundAppAdapter {
    fun currentPackage(): String?
}

interface EquipmentStateAdapter {
    fun currentJson(): String
    fun replaceRaw(raw: String)
}

interface AutomationStateAdapter {
    fun isEnabled(): Boolean
    fun strategyName(): String
}

interface DecisionLogAdapter {
    fun append(event: DecisionEvent, runtimeMessage: String? = null)
    fun appendSystem(message: String)
}


interface ApplicationLogAdapter {
    fun info(
        category: String,
        event: String,
        message: String,
        details: JSONObject? = null,
    )

    fun warning(
        category: String,
        event: String,
        message: String,
        details: JSONObject? = null,
    )

    fun error(
        category: String,
        event: String,
        message: String,
        throwable: Throwable? = null,
        details: JSONObject? = null,
    )
}
