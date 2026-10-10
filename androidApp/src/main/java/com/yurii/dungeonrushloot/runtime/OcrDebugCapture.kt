package com.yurii.dungeonrushloot.runtime

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * Ephemeral opt-in, one-shot capture. Never survives a process restart.
 * Only one OCR attempt can consume a request; users explicitly arm again.
 */
class OcrDebugCapture {
    sealed interface State {
        data object Idle : State
        data object Armed : State
        data object Capturing : State
        data class Saved(val filename: String) : State
        data class Failed(val reason: String) : State
    }

    private val mutableState = MutableStateFlow<State>(State.Idle)
    val state: StateFlow<State> = mutableState

    @Synchronized
    fun arm(): Boolean {
        if (mutableState.value is State.Armed || mutableState.value is State.Capturing) return false
        mutableState.value = State.Armed
        return true
    }

    @Synchronized
    fun cancel(): Boolean {
        if (mutableState.value !is State.Armed) return false
        mutableState.value = State.Idle
        return true
    }

    @Synchronized
    fun claim(): Boolean {
        if (mutableState.value !is State.Armed) return false
        mutableState.value = State.Capturing
        return true
    }

    @Synchronized
    fun saved(filename: String) {
        check(mutableState.value is State.Capturing)
        mutableState.value = State.Saved(filename)
    }

    @Synchronized
    fun failed(reason: String) {
        check(mutableState.value is State.Capturing)
        mutableState.value = State.Failed(reason)
    }
}
