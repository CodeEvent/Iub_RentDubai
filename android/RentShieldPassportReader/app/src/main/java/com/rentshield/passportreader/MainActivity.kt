package com.rentshield.passportreader

import android.Manifest
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.net.Uri
import android.nfc.NfcAdapter
import android.nfc.Tag
import android.nfc.tech.IsoDep
import android.os.Bundle
import android.provider.MediaStore
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.jmrtd.AccessKeySpec
import org.jmrtd.BACKey
import org.jmrtd.PACEKeySpec
import java.io.File

/**
 * Full flow: sign in -> Face ID/fingerprint gate (confirms phone
 * ownership only, see NfcChipReader.kt) -> pick Passport or Italian CIE
 * and enter its access key -> photograph the physical card (Idswyft
 * OCRs it, RentShield auto-updates the account's name) -> tap the chip
 * (cross-checked against the card photo's OCR, never a hard gate) ->
 * selfie (matched against the card photo) -> a short recorded video ->
 * a human (Notary Public) reviews everything within 24h before the
 * account is actually marked verified.
 */
class MainActivity : AppCompatActivity() {

    private enum class CaptureKind { CARD_PHOTO, SELFIE, VIDEO }

    private lateinit var api: RentShieldApiClient

    // Views
    private lateinit var sectionLogin: View
    private lateinit var sectionBiometric: View
    private lateinit var sectionDocument: View
    private lateinit var fieldsPassport: View
    private lateinit var fieldsCie: View
    private lateinit var statusText: TextView
    private lateinit var photoPreview: ImageView
    private lateinit var buttonCardPhoto: Button
    private lateinit var buttonScan: Button
    private lateinit var buttonSelfie: Button
    private lateinit var buttonVideo: Button
    private lateinit var buttonDone: Button

    // Pending NFC read request, set once "Ready to scan" is tapped and
    // consumed in onNewIntent when the actual tap happens.
    private var pendingPaceKey: AccessKeySpec? = null
    private var pendingBacFallback: BACKey? = null

    private var pendingCaptureFile: File? = null
    private var pendingCaptureKind: CaptureKind? = null

    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    private val cameraLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val file = pendingCaptureFile
        val kind = pendingCaptureKind
        if (result.resultCode == RESULT_OK && file != null && file.exists() && kind != null) {
            when (kind) {
                CaptureKind.CARD_PHOTO -> onCardPhotoCaptured(file.readBytes())
                CaptureKind.SELFIE -> onSelfieCaptured(file.readBytes())
                CaptureKind.VIDEO -> onVideoCaptured(file.readBytes())
            }
        } else {
            statusText.text = "Capture was cancelled -- try again."
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        sectionLogin = findViewById(R.id.section_login)
        sectionBiometric = findViewById(R.id.section_biometric)
        sectionDocument = findViewById(R.id.section_document)
        fieldsPassport = findViewById(R.id.fields_passport)
        fieldsCie = findViewById(R.id.fields_cie)
        statusText = findViewById(R.id.status_text)
        photoPreview = findViewById(R.id.photo_preview)
        buttonCardPhoto = findViewById(R.id.button_card_photo)
        buttonScan = findViewById(R.id.button_scan)
        buttonSelfie = findViewById(R.id.button_selfie)
        buttonVideo = findViewById(R.id.button_video)
        buttonDone = findViewById(R.id.button_done)

        permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION))

        findViewById<Button>(R.id.button_scan_pairing_qr).setOnClickListener { onScanPairingQrClicked() }
        findViewById<Button>(R.id.button_login).setOnClickListener { onLoginClicked() }
        findViewById<Button>(R.id.button_biometric).setOnClickListener { runBiometricGate() }
        findViewById<RadioGroup>(R.id.radio_document_type).setOnCheckedChangeListener { _, checkedId ->
            val isCie = checkedId == R.id.radio_cie
            fieldsPassport.visibility = if (isCie) View.GONE else View.VISIBLE
            fieldsCie.visibility = if (isCie) View.VISIBLE else View.GONE
        }
        buttonCardPhoto.setOnClickListener { launchCamera(CaptureKind.CARD_PHOTO) }
        buttonScan.setOnClickListener { onScanClicked() }
        buttonSelfie.setOnClickListener { launchCamera(CaptureKind.SELFIE) }
        buttonVideo.setOnClickListener { launchVideoCamera() }
        buttonDone.setOnClickListener { resetToBiometricGate() }
    }

    // MARK: -- Scan to sign in (documents/rentshield_identity/pairing_views.py)

    private fun onScanPairingQrClicked() {
        val scanner = GmsBarcodeScanning.getClient(
            this,
            GmsBarcodeScannerOptions.Builder().setBarcodeFormats(Barcode.FORMAT_QR_CODE).build(),
        )
        scanner.startScan()
            .addOnSuccessListener { barcode -> onPairingQrScanned(barcode.rawValue) }
            .addOnFailureListener { toast(it.message ?: "Could not scan that code -- try again.") }
        // No addOnCanceledListener: the user backing out of the scanner
        // (no QR found, changed their mind) just returns them to this
        // same login screen, nothing to handle.
    }

    private fun onPairingQrScanned(rawValue: String?) {
        // rentshieldpair://pair?server=<url-encoded>&code=<code> -- see
        // pairing_views.py's pair_start_view for why this is a real URI
        // (survives a server address that itself contains a colon)
        // instead of a hand-split string.
        val uri = rawValue?.let { runCatching { Uri.parse(it) }.getOrNull() }
        val server = uri?.getQueryParameter("server")
        val code = uri?.getQueryParameter("code")
        if (uri?.scheme != "rentshieldpair" || server.isNullOrEmpty() || code.isNullOrEmpty()) {
            toast("That doesn't look like a RentShield sign-in code -- try again.")
            return
        }

        api = RentShieldApiClient(server)
        api.claimPairing(code) { result ->
            runOnUiThread {
                result.onSuccess {
                    prefillDeclaredDocument(it.declared)
                    sectionLogin.visibility = View.GONE
                    sectionBiometric.visibility = View.VISIBLE
                }.onFailure { toast(it.message ?: "That code is invalid or expired -- get a new one on the website.") }
            }
        }
    }

    // Pre-fills (still editable, never locked) the same fields
    // section_document already had -- typed once on the web's real
    // keyboard instead of asking for them again from scratch here. The
    // web's date inputs are ISO (YYYY-MM-DD); BACKey needs yyMMdd.
    private fun prefillDeclaredDocument(declared: DeclaredDocument) {
        if (declared.documentType == "cie") {
            findViewById<RadioGroup>(R.id.radio_document_type).check(R.id.radio_cie)
            findViewById<EditText>(R.id.input_can).setText(declared.can)
        } else {
            findViewById<RadioGroup>(R.id.radio_document_type).check(R.id.radio_passport)
            findViewById<EditText>(R.id.input_passport_number).setText(declared.documentNumber)
            findViewById<EditText>(R.id.input_date_of_birth).setText(isoDateToYyMMdd(declared.dateOfBirth))
            findViewById<EditText>(R.id.input_expiration_date).setText(isoDateToYyMMdd(declared.expiryDate))
        }
    }

    private fun isoDateToYyMMdd(iso: String): String {
        val parts = iso.split("-")
        if (parts.size != 3 || parts[0].length < 2) return ""
        return parts[0].takeLast(2) + parts[1] + parts[2]
    }

    // MARK: -- Login

    private fun onLoginClicked() {
        val serverUrl = findViewById<EditText>(R.id.input_server_url).text.toString().trim()
        val username = findViewById<EditText>(R.id.input_username).text.toString().trim()
        val password = findViewById<EditText>(R.id.input_password).text.toString().trim()
        if (serverUrl.isEmpty() || username.isEmpty() || password.isEmpty()) {
            toast("Fill in server address, username, and password.")
            return
        }
        // Real crash reported here: a typo ("gttp://" for "http://")
        // reached OkHttp's URL parser as-is and threw an uncaught
        // IllegalArgumentException, crashing the whole app over a single
        // mistyped character. Validated up front now so a bad address
        // is just a message, not a crash.
        if (!serverUrl.startsWith("http://") && !serverUrl.startsWith("https://")) {
            toast("Server address must start with http:// or https:// -- check for typos.")
            return
        }
        // Deliberately not defaulted to localhost -- this device is
        // separate hardware on the network, the exact bug already hit
        // once with Idswyft's QR code pointing at a laptop-only address.
        api = RentShieldApiClient(serverUrl)
        api.login(username, password) { result ->
            runOnUiThread {
                result.onSuccess {
                    sectionLogin.visibility = View.GONE
                    sectionBiometric.visibility = View.VISIBLE
                }.onFailure { toast(it.message ?: "Login failed.") }
            }
        }
    }

    // MARK: -- Biometric gate

    private fun runBiometricGate() {
        val canAuth = BiometricManager.from(this)
            .canAuthenticate(BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL)
        if (canAuth != BiometricManager.BIOMETRIC_SUCCESS) {
            toast("No Face ID/fingerprint/PIN set up on this device.")
            return
        }
        val prompt = BiometricPrompt(
            this,
            ContextCompat.getMainExecutor(this),
            object : BiometricPrompt.AuthenticationCallback() {
                override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                    sectionBiometric.visibility = View.GONE
                    sectionDocument.visibility = View.VISIBLE
                }

                override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                    toast("Confirmation required to continue: $errString")
                }
            },
        )
        // Combining BIOMETRIC_WEAK + DEVICE_CREDENTIAL: the system supplies
        // its own PIN fallback UI, and setNegativeButtonText must NOT be
        // called alongside it (androidx.biometric throws if both are set).
        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Confirm it's you")
            .setSubtitle("This only confirms you unlocked this phone -- it isn't compared against your document.")
            .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_WEAK or BiometricManager.Authenticators.DEVICE_CREDENTIAL)
            .build()
        prompt.authenticate(promptInfo)
    }

    // MARK: -- Card photo (Idswyft OCR + face-match reference)

    private fun onCardPhotoCaptured(cardPhotoBytes: ByteArray) {
        buttonCardPhoto.visibility = View.GONE
        statusText.text = "Reading your card…"
        BitmapFactory.decodeByteArray(cardPhotoBytes, 0, cardPhotoBytes.size)?.let { photoPreview.setImageBitmap(it) }

        LocationHelper.requestOnce(this) { location ->
            api.startVerification { startResult ->
                startResult.onFailure { runOnUiThread { statusText.text = it.message; buttonCardPhoto.visibility = View.VISIBLE } }
                startResult.onSuccess {
                    api.uploadFrontDocument(cardPhotoBytes, "image/jpeg", location) { result ->
                        runOnUiThread {
                            result.onSuccess {
                                // Real bug, reported: a card photo that fails
                                // Idswyft's own quality check (e.g. OCR
                                // confidence too low) still comes back as an
                                // HTTP 200 with status="failed" in the body --
                                // onSuccess only means "the network call
                                // worked", not "verification passed". Without
                                // this check the app let you proceed to NFC/
                                // selfie on an already-dead session, and the
                                // real failure only surfaced several steps
                                // later as a confusing, unrelated-looking
                                // selfie error.
                                if (it.status == "failed") {
                                    onVerificationComplete(it)
                                } else {
                                    statusText.text = "Card read. Now tap the chip: hold it flat against the back of your phone."
                                    buttonScan.visibility = View.VISIBLE
                                }
                            }
                            result.onFailure {
                                statusText.text = it.message
                                buttonCardPhoto.visibility = View.VISIBLE
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: -- NFC scan (cross-checked against the card photo's OCR, server-side)

    // The CAN here is mandatory and cannot be swapped for the card's
    // printed ID/serial number ("CA00000AA"-style) -- the chip's own
    // firmware only recognizes CAN, MRZ, PIN, or PUK as valid PACE key
    // material, full stop, the same way a bike lock only opens for its
    // actual combination. The serial number IS still checked, just not
    // here: once the chip is unlocked with the real CAN, its own copy of
    // the document number (PassportReadResult.documentNumber) is sent to
    // the backend and cross-checked against the card photo's OCR read
    // (see views.py's _check_identity_mismatch) -- that's the "does the
    // card number match the chip" check, just done after unlocking, not
    // used to unlock.
    private fun onScanClicked() {
        val isCie = findViewById<RadioGroup>(R.id.radio_document_type).checkedRadioButtonId == R.id.radio_cie
        if (isCie) {
            val can = findViewById<EditText>(R.id.input_can).text.toString().trim()
            if (can.length != 6) {
                toast("The CAN is exactly 6 digits -- it's a different number from the card's longer alphanumeric ID/serial number.")
                return
            }
            pendingPaceKey = PACEKeySpec.createCANKey(can)
            pendingBacFallback = null
        } else {
            val passportNumber = findViewById<EditText>(R.id.input_passport_number).text.toString().trim()
            val birthDate = findViewById<EditText>(R.id.input_date_of_birth).text.toString().trim()
            val expirationDate = findViewById<EditText>(R.id.input_expiration_date).text.toString().trim()
            if (passportNumber.isEmpty() || birthDate.isEmpty() || expirationDate.isEmpty()) {
                toast("Fill in passport number, date of birth, and expiry date first.")
                return
            }
            val bacKey = BACKey(passportNumber, birthDate, expirationDate)
            pendingPaceKey = bacKey
            pendingBacFallback = bacKey
        }
        statusText.text = "Hold the document flat against the back of your phone…"
    }

    override fun onResume() {
        super.onResume()
        val adapter = NfcAdapter.getDefaultAdapter(this) ?: return
        val intent = Intent(applicationContext, javaClass).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP
        }
        val pendingIntent = PendingIntent.getActivity(this, 0, intent, PendingIntent.FLAG_MUTABLE)
        val filter = arrayOf(arrayOf(IsoDep::class.java.name))
        adapter.enableForegroundDispatch(this, pendingIntent, null, filter)
    }

    override fun onPause() {
        super.onPause()
        NfcAdapter.getDefaultAdapter(this)?.disableForegroundDispatch(this)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val paceKey = pendingPaceKey ?: return
        val tag: Tag = intent.getParcelableExtra(NfcAdapter.EXTRA_TAG) ?: return
        val isoDep = IsoDep.get(tag) ?: run {
            statusText.text = "That isn't a passport/ID chip -- try again."
            return
        }

        statusText.text = "Reading chip…"
        Thread {
            try {
                val result = NfcChipReader.read(isoDep, paceKey, pendingBacFallback)
                runOnUiThread { onChipReadSuccess(result) }
            } catch (t: Throwable) {
                // Throwable, not Exception -- a real crash was reported
                // here (app crash + logout) that this didn't catch.
                // PACE-IM's cryptography (needed for CIE, added when
                // JMRTD was upgraded from 0.7.18 to 0.8.1) is heavier
                // than passports' Generic Mapping and pulls in a much
                // newer BouncyCastle (jdk18on) that has never been
                // exercised on real Android hardware before now -- an
                // Error subtype (NoSuchMethodError, OutOfMemoryError,
                // ...) from that combination wouldn't have been caught
                // by `catch (e: Exception)` and would kill the whole
                // process, which also explains the reported "logs me
                // out" (the in-memory login token doesn't survive a
                // process restart). Whatever this actually is will now
                // show on screen instead of crashing blind.
                runOnUiThread { statusText.text = "Could not read the chip: ${t::class.simpleName}: ${t.message}" }
            }
        }.start()
    }

    private fun onChipReadSuccess(result: PassportReadResult) {
        pendingPaceKey = null
        sectionDocument.visibility = View.GONE
        statusText.text = "Checking chip details against your card photo…"
        val fullName = "${result.firstName} ${result.lastName}".trim()
        api.submitChipData(fullName, result.dateOfBirth, result.documentNumber, result.photoBytes, result.photoMimeType) { chipResult ->
            runOnUiThread {
                chipResult.onSuccess {
                    statusText.text = "Chip read: $fullName. Now take a selfie."
                    buttonSelfie.visibility = View.VISIBLE
                }
                chipResult.onFailure {
                    statusText.text = it.message
                    sectionDocument.visibility = View.VISIBLE
                }
            }
        }
    }

    // MARK: -- Selfie (Idswyft matches this against the card photo)

    private fun onSelfieCaptured(selfieBytes: ByteArray) {
        buttonSelfie.visibility = View.GONE
        statusText.text = "Verifying selfie…"
        BitmapFactory.decodeByteArray(selfieBytes, 0, selfieBytes.size)?.let { photoPreview.setImageBitmap(it) }

        LocationHelper.requestOnce(this) { location ->
            api.uploadLiveCapture(selfieBytes, location) { result ->
                runOnUiThread {
                    result.onSuccess {
                        if (it.status == "failed") {
                            onVerificationComplete(it)
                        } else {
                            statusText.text = "Selfie submitted. Last step: record a short confirmation video."
                            buttonVideo.visibility = View.VISIBLE
                        }
                    }
                    result.onFailure { statusText.text = it.message }
                }
            }
        }
    }

    // MARK: -- Confirmation video (reviewed by a Notary Public within 24h)

    private fun launchVideoCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            toast("Camera permission is required to record the confirmation video.")
            permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
            return
        }
        val dir = File(cacheDir, "videos").apply { mkdirs() }
        val file = File(dir, "confirmation_${System.currentTimeMillis()}.mp4")
        pendingCaptureFile = file
        pendingCaptureKind = CaptureKind.VIDEO
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val intent = Intent(MediaStore.ACTION_VIDEO_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            putExtra(MediaStore.EXTRA_DURATION_LIMIT, 20) // a couple of sentences, not a monologue
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
        cameraLauncher.launch(intent)
    }

    private fun onVideoCaptured(videoBytes: ByteArray) {
        buttonVideo.visibility = View.GONE
        statusText.text = "Uploading video…"
        api.uploadVideo(videoBytes) { result ->
            runOnUiThread {
                result.onSuccess { onVerificationComplete(it) }
                result.onFailure {
                    statusText.text = it.message
                    buttonVideo.visibility = View.VISIBLE
                }
            }
        }
    }

    // MARK: -- Shared camera helper (card photo + selfie both take a still photo)

    private fun launchCamera(kind: CaptureKind) {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            toast("Camera permission is required for this step.")
            permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
            return
        }
        val dirName = if (kind == CaptureKind.CARD_PHOTO) "cards" else "selfies"
        val dir = File(cacheDir, dirName).apply { mkdirs() }
        val file = File(dir, "${dirName}_${System.currentTimeMillis()}.jpg")
        pendingCaptureFile = file
        pendingCaptureKind = kind
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
        cameraLauncher.launch(intent)
    }

    // MARK: -- Result

    private fun onVerificationComplete(status: VerificationStatus) {
        val summary = when (status.status) {
            "verified" -> "Verified."
            "failed" -> "Verification failed."
            "awaiting_notary_review" -> "Submitted -- a Notary Public will review your video within 24 hours."
            "manual_review" -> "Submitted -- under manual review."
            else -> "Submitted -- processing."
        }
        // Idswyft's own rejection detail (e.g. "OCR confidence 0.23 is
        // below minimum 0.6") is real, specific, and actionable -- a
        // bare "Verification failed." left a real failure looking like
        // an unexplained dead end.
        statusText.text = if (status.detail != null) "$summary ${status.detail}" else summary
        buttonDone.visibility = View.VISIBLE
    }

    private fun resetToBiometricGate() {
        pendingCaptureFile = null
        pendingCaptureKind = null
        pendingPaceKey = null
        pendingBacFallback = null
        buttonCardPhoto.visibility = View.VISIBLE
        buttonScan.visibility = View.GONE
        buttonSelfie.visibility = View.GONE
        buttonVideo.visibility = View.GONE
        buttonDone.visibility = View.GONE
        photoPreview.setImageDrawable(null)
        statusText.text = ""
        sectionDocument.visibility = View.GONE
        sectionBiometric.visibility = View.VISIBLE
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}
