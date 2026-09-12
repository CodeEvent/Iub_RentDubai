package com.rentshield.passportreader

import android.content.Context
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper

data class CapturedLocation(val latitude: Double, val longitude: Double, val accuracyMeters: Float?)

/**
 * One-shot, best-effort location fetch -- plain platform LocationManager,
 * no Play Services dependency needed for a single reading. Mirrors the
 * web app's `navigator.geolocation.getCurrentPosition()` and the iOS
 * build's LocationService: evidence of where verification happened for
 * the admin review page, never a gate on the result. Times out to null
 * rather than blocking if permission is denied or no fix arrives -- the
 * caller must already hold ACCESS_FINE_LOCATION before calling this.
 */
object LocationHelper {
    fun requestOnce(context: Context, onResult: (CapturedLocation?) -> Unit) {
        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val provider = when {
            manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> return onResult(null)
        }

        var finished = false
        val handler = Handler(Looper.getMainLooper())
        val listener = object : LocationListener {
            override fun onLocationChanged(location: Location) = finish(location)
            override fun onProviderDisabled(provider: String) = finish(null)

            @Deprecated("Deprecated in Java")
            override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) {}

            fun finish(location: Location?) {
                if (finished) return
                finished = true
                manager.removeUpdates(this)
                onResult(
                    location?.let {
                        CapturedLocation(it.latitude, it.longitude, if (it.hasAccuracy()) it.accuracy else null)
                    },
                )
            }
        }

        try {
            manager.requestLocationUpdates(provider, 0L, 0f, listener, Looper.getMainLooper())
        } catch (e: SecurityException) {
            // Permission denied -- evidence only, never a gate on the
            // verification result, so this fails soft same as a timeout.
            return onResult(null)
        }
        handler.postDelayed({ listener.finish(null) }, 8000)
    }
}
