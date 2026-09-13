package com.rentshield.passportreader

import android.graphics.Color
import android.os.Bundle
import android.text.InputType
import android.view.Gravity
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

/** Minimal, standalone screen (no ties to MainActivity's own state,
 * deliberately -- it has to still work when MainActivity itself is
 * what just crashed) that shows the last crash's full stack trace as
 * selectable/copyable text, so it can be read out or copied and sent
 * back for a real diagnosis instead of the app just vanishing. */
class CrashDisplayActivity : AppCompatActivity() {
    companion object {
        const val EXTRA_STACK_TRACE = "stack_trace"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val stackTrace = intent.getStringExtra(EXTRA_STACK_TRACE) ?: "(no stack trace captured)"

        val title = TextView(this).apply {
            text = "RentShield Verification crashed"
            textSize = 18f
            setPadding(32, 32, 32, 16)
            gravity = Gravity.START
        }
        val subtitle = TextView(this).apply {
            text = "Copy the text below and send it back so this can be fixed for real."
            setPadding(32, 0, 32, 16)
        }
        val traceField = EditText(this).apply {
            setText(stackTrace)
            isFocusable = true
            isFocusableInTouchMode = true
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE
            setTextIsSelectable(true)
            setBackgroundColor(Color.parseColor("#F5F5F5"))
            setPadding(24, 24, 24, 24)
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(title)
            addView(subtitle)
            addView(traceField)
        }
        setContentView(ScrollView(this).apply { addView(layout) })
    }
}
