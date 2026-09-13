package com.rentshield.passportreader

import android.app.Application
import android.content.Intent
import android.os.Process
import java.io.PrintWriter
import java.io.StringWriter
import kotlin.system.exitProcess

/**
 * Installed before any Activity starts (Application.onCreate() runs
 * first) specifically because a real crash was reported ("app crashes
 * and logs me out" right after an NFC scan) with zero visibility into
 * why -- this sandbox has no device to attach a debugger/logcat to, and
 * the narrower fix in MainActivity's NFC read thread (catching Throwable,
 * not just Exception) only covers that one call site. This is the
 * safety net for anywhere else an Error subtype (not a plain Exception)
 * might slip through uncaught -- shows the real stack trace on screen
 * instead of the app silently vanishing back to the login screen.
 */
class CrashReportingApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        val defaultHandler = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            try {
                val writer = StringWriter()
                throwable.printStackTrace(PrintWriter(writer))
                val intent = Intent(this, CrashDisplayActivity::class.java).apply {
                    putExtra(CrashDisplayActivity.EXTRA_STACK_TRACE, writer.toString())
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
                }
                startActivity(intent)
            } catch (t: Throwable) {
                // Reporting the crash must never itself throw and mask
                // the original crash -- fall through to the default
                // handler either way.
            }
            defaultHandler?.uncaughtException(thread, throwable)
            Process.killProcess(Process.myPid())
            exitProcess(1)
        }
    }
}
