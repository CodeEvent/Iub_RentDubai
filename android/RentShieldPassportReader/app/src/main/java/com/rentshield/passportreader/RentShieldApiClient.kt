package com.rentshield.passportreader

import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

data class VerificationStatus(val status: String?, val step: String?, val detail: String? = null)

// org.json's optString returns the literal string "null" for a JSON null
// value rather than a real null -- the backend genuinely sends step: null
// whenever a session isn't mid-capture, so this isn't a hypothetical.
private fun JSONObject.optNullableString(name: String): String? =
    if (isNull(name) || !has(name)) null else getString(name)

class ApiException(message: String) : Exception(message)

/**
 * Talks to the same Django/DRF endpoints the Angular web app and the iOS
 * build already use (documents/rentshield_identity/views.py) -- no new
 * backend surface, just another native front door. DRF token auth
 * (POST /api/token/, then Authorization: Token ...) rather than session
 * cookies, same reasoning as the iOS client: no shared cookie jar with a
 * browser from a native app.
 */
class RentShieldApiClient(private val baseUrl: String) {
    // OkHttp's default 10s read timeout is shorter than Idswyft's real
    // OCR processing time (typically 15-30s, up to the 60s the Django
    // backend itself allows -- see idswyft_client.py's _upload()) --
    // confirmed exactly this symptom (a real user hit a timeout-then-
    // retake loop on the front-document/card-photo upload) and it
    // matches a documented quirk in Idswyft's own source: "a client
    // retry triggered by a read timeout shorter than our OCR latency
    // (Android okhttp's ~10s default vs typical 15-30s extraction)".
    private val client = OkHttpClient.Builder()
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(90, TimeUnit.SECONDS)
        .writeTimeout(90, TimeUnit.SECONDS)
        .build()
    private var token: String? = null

    private fun url(path: String) = baseUrl.trimEnd('/') + path

    fun login(username: String, password: String, callback: (Result<String>) -> Unit) {
        postForToken("/api/token/", JSONObject().put("username", username).put("password", password), callback)
    }

    // "Scan to sign in" -- called right after the QR scanner returns the
    // code (see MainActivity.onPairingQrScanned), instead of the phone
    // typing a username/password. Deliberately no Authorization header
    // needed for this one call: the phone genuinely has no token yet,
    // that's the whole point (see pairing_views.py's pair_claim_view
    // docstring for why that's safe).
    fun claimPairing(code: String, callback: (Result<String>) -> Unit) {
        postForToken("/api/documents/identity/pair/claim/", JSONObject().put("code", code), callback)
    }

    private fun postForToken(path: String, body: JSONObject, callback: (Result<String>) -> Unit) {
        val request = Request.Builder().url(url(path))
            .post(body.toString().toRequestBody("application/json".toMediaType())).build()
        client.newCall(request).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) = callback(Result.failure(e))
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val bodyString = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        callback(Result.failure(ApiException(errorMessage(bodyString, it.code))))
                        return
                    }
                    val received = JSONObject(bodyString).getString("token")
                    token = received
                    callback(Result.success(received))
                }
            }
        })
    }

    fun startVerification(callback: (Result<VerificationStatus>) -> Unit) {
        authed("/api/documents/identity/verify/start/", "POST", callback = callback)
    }

    fun status(callback: (Result<VerificationStatus>) -> Unit) {
        authed("/api/documents/identity/verify/status/", "GET", callback = callback)
    }

    fun uploadFrontDocument(
        photoBytes: ByteArray,
        mimeType: String?,
        location: CapturedLocation?,
        callback: (Result<VerificationStatus>) -> Unit,
    ) {
        uploadMultipart("/api/documents/identity/verify/front-document/", "document", "chip-photo.jpg", photoBytes, mimeType, location, callback)
    }

    fun uploadLiveCapture(
        selfieBytes: ByteArray,
        location: CapturedLocation?,
        callback: (Result<VerificationStatus>) -> Unit,
    ) {
        uploadMultipart("/api/documents/identity/verify/live-capture/", "selfie", "selfie.jpg", selfieBytes, "image/jpeg", location, callback)
    }

    /** The name/DOB/document number read straight off the NFC chip
     * (DG1/MRZ), cross-checked server-side against the card photo's own
     * OCR read (see views.py's _check_identity_mismatch). [chipPhotoBytes]
     * is the chip's own DG2 photo -- optional (a chip read can succeed
     * on the text data while DG2 parsing fails) -- used server-side for
     * an independent second face match against the selfie
     * (face_match.py), separate from Idswyft's own card-photo-vs-selfie
     * match. Multipart, not JSON, specifically to carry that optional
     * file alongside the text fields. */
    fun submitChipData(
        fullName: String,
        dateOfBirth: String,
        documentNumber: String,
        chipPhotoBytes: ByteArray?,
        chipPhotoMimeType: String?,
        callback: (Result<VerificationStatus>) -> Unit,
    ) {
        uploadMultipartTextOnly(
            path = "/api/documents/identity/verify/chip-data/",
            textFields = mapOf(
                "full_name" to fullName,
                "date_of_birth" to dateOfBirth,
                "document_number" to documentNumber,
            ),
            fileFieldName = if (chipPhotoBytes != null) "chip_photo" else null,
            filename = "chip-photo.jpg",
            fileBytes = chipPhotoBytes,
            mimeType = chipPhotoMimeType,
            callback = callback,
        )
    }

    fun uploadVideo(videoBytes: ByteArray, callback: (Result<VerificationStatus>) -> Unit) {
        uploadMultipart("/api/documents/identity/verify/video/", "video", "confirmation.mp4", videoBytes, "video/mp4", location = null, callback = callback)
    }

    // MARK: internals

    private fun authed(path: String, method: String, callback: (Result<VerificationStatus>) -> Unit) {
        val currentToken = token ?: return callback(Result.failure(ApiException("Not logged in.")))
        val builder = Request.Builder().url(url(path)).header("Authorization", "Token $currentToken")
        if (method == "POST") builder.post("".toRequestBody(null))
        client.newCall(builder.build()).enqueue(jsonCallback(callback) { json ->
            VerificationStatus(json.optNullableString("status"), json.optNullableString("step"), json.optNullableString("detail"))
        })
    }

    private fun uploadMultipart(
        path: String,
        fieldName: String,
        filename: String,
        fileBytes: ByteArray,
        mimeType: String?,
        location: CapturedLocation?,
        callback: (Result<VerificationStatus>) -> Unit,
        extraTextFields: Map<String, String> = emptyMap(),
    ) {
        val currentToken = token ?: return callback(Result.failure(ApiException("Not logged in.")))
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
        location?.let {
            bodyBuilder.addFormDataPart("latitude", it.latitude.toString())
            bodyBuilder.addFormDataPart("longitude", it.longitude.toString())
            it.accuracyMeters?.let { accuracy -> bodyBuilder.addFormDataPart("location_accuracy_m", accuracy.toString()) }
        }
        extraTextFields.forEach { (key, value) -> bodyBuilder.addFormDataPart(key, value) }
        bodyBuilder.addFormDataPart(
            fieldName, filename,
            fileBytes.toRequestBody((mimeType ?: "image/jpeg").toMediaType()),
        )
        val request = Request.Builder()
            .url(url(path))
            .header("Authorization", "Token $currentToken")
            .post(bodyBuilder.build())
            .build()
        client.newCall(request).enqueue(jsonCallback(callback) { json ->
            VerificationStatus(json.optNullableString("status"), json.optNullableString("step"), json.optNullableString("detail"))
        })
    }

    /** Same as uploadMultipart, but the file is optional -- used by
     * submitChipData(), where a chip photo might genuinely be absent
     * (extraction failure, or a document whose DG2 didn't parse) while
     * the text fields (name/DOB/document number) are still required. */
    private fun uploadMultipartTextOnly(
        path: String,
        textFields: Map<String, String>,
        fileFieldName: String? = null,
        filename: String? = null,
        fileBytes: ByteArray? = null,
        mimeType: String? = null,
        callback: (Result<VerificationStatus>) -> Unit,
    ) {
        val currentToken = token ?: return callback(Result.failure(ApiException("Not logged in.")))
        val bodyBuilder = MultipartBody.Builder().setType(MultipartBody.FORM)
        textFields.forEach { (key, value) -> bodyBuilder.addFormDataPart(key, value) }
        if (fileFieldName != null && fileBytes != null) {
            bodyBuilder.addFormDataPart(
                fileFieldName, filename ?: "file.jpg",
                fileBytes.toRequestBody((mimeType ?: "image/jpeg").toMediaType()),
            )
        }
        val request = Request.Builder()
            .url(url(path))
            .header("Authorization", "Token $currentToken")
            .post(bodyBuilder.build())
            .build()
        client.newCall(request).enqueue(jsonCallback(callback) { json ->
            VerificationStatus(json.optNullableString("status"), json.optNullableString("step"), json.optNullableString("detail"))
        })
    }

    private fun <T> jsonCallback(callback: (Result<T>) -> Unit, extract: (JSONObject) -> T): Callback {
        return object : Callback {
            override fun onFailure(call: Call, e: IOException) = callback(Result.failure(e))
            override fun onResponse(call: Call, response: Response) {
                response.use {
                    val bodyString = it.body?.string().orEmpty()
                    if (!it.isSuccessful) {
                        callback(Result.failure(ApiException(errorMessage(bodyString, it.code))))
                        return
                    }
                    callback(Result.success(extract(JSONObject(bodyString))))
                }
            }
        }
    }

    // The identity-verification endpoints return {"error": "..."}, but
    // DRF's own login serializer (used by /api/token/) returns its
    // default validation shape instead -- {"non_field_errors": [...]}
    // for bad credentials, or {"<field>": [...]} for a missing field.
    // Only checking "error" silently swallowed those into a useless
    // "Server returned 400." -- a real bug caught by an actual bad
    // login (autocorrect turned "Ownwer" into "Owner" in the seed
    // username), not a hypothetical.
    private fun errorMessage(body: String, code: Int): String = runCatching {
        val json = JSONObject(body)
        json.optString("error").takeIf { it.isNotEmpty() }
            ?: json.optJSONArray("non_field_errors")?.optString(0)?.takeIf { it.isNotEmpty() }
            ?: json.keys().asSequence().firstNotNullOfOrNull { key -> json.optJSONArray(key)?.optString(0) }
            ?: "Server returned $code."
    }.getOrDefault("Server returned $code.")
}
