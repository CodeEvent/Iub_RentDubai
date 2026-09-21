package com.rentshield.passportreader

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.util.AttributeSet
import android.view.View

/**
 * Live selfie-alignment guide drawn over the camera preview: an oval
 * outline that's red by default and turns green once MainActivity's
 * face-detection analyzer reports a single, roughly centered face --
 * requested explicitly so there's a real-time signal of "ok to capture"
 * instead of only finding out a selfie was framed badly after uploading
 * it (see onSelfieCaptured's now-retryable "failed" path).
 */
class FaceGuideOverlay @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    private var aligned = false
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        style = Paint.Style.STROKE
        strokeWidth = 10f
    }

    fun setAligned(value: Boolean) {
        if (aligned == value) return
        aligned = value
        invalidate()
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        paint.color = if (aligned) Color.parseColor("#2E7D32") else Color.parseColor("#C62828")
        val ovalWidth = width * 0.62f
        val ovalHeight = height * 0.78f
        val centerX = width / 2f
        val centerY = height / 2f
        canvas.drawOval(
            RectF(
                centerX - ovalWidth / 2f, centerY - ovalHeight / 2f,
                centerX + ovalWidth / 2f, centerY + ovalHeight / 2f,
            ),
            paint,
        )
    }
}
