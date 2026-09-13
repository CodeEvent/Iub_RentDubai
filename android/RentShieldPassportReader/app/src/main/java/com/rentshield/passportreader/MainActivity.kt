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
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.RadioGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.camera.core.CameraSelector
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.video.FileOutputOptions
import androidx.camera.video.Recorder
import androidx.camera.video.Recording
import androidx.camera.video.VideoCapture
import androidx.camera.video.VideoRecordEvent
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import com.google.mlkit.vision.barcode.common.Barcode
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning
import org.jmrtd.AccessKeySpec
import org.jmrtd.BACKey
import org.jmrtd.PACEKeySpec
import java.io.File
import java.util.Calendar

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

    // VIDEO is deliberately not here anymore -- it's recorded in-app via
    // CameraX (see section_video_record) instead of the plain camera
    // intent this enum still drives for the other two capture kinds,
    // specifically so the confirmation sentence can be shown on screen
    // while recording (the system camera app's own UI can't display it).
    private enum class CaptureKind { CARD_PHOTO, SELFIE, ADDITIONAL_ID }

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
    private lateinit var sectionVideoRecord: View
    private lateinit var videoPreviewView: PreviewView
    private lateinit var videoPromptOverlay: TextView
    private lateinit var buttonRecordToggle: Button
    private lateinit var sectionAdditionalId: View
    private lateinit var inputAdditionalIdType: EditText
    private lateinit var buttonAdditionalId: Button

    // Pending NFC read request, set once "Ready to scan" is tapped and
    // consumed in onNewIntent when the actual tap happens.
    private var pendingPaceKey: AccessKeySpec? = null
    private var pendingBacFallback: BACKey? = null

    private var pendingCaptureFile: File? = null
    private var pendingCaptureKind: CaptureKind? = null

    // Read straight off the NFC chip's own MRZ (onChipReadSuccess) -- the
    // cryptographically signed data, not the (sometimes incomplete, see
    // idswyft-community's own name-matching bug fixed this session)
    // card-photo OCR -- used to build the sentence the user reads aloud
    // on the confirmation video.
    private var verifiedFullName: String = ""
    private var verifiedAgeYears: Int? = null

    private var videoCapture: VideoCapture<Recorder>? = null
    private var activeRecording: Recording? = null
    private val recordingHandler = Handler(Looper.getMainLooper())

    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    private val cameraLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val file = pendingCaptureFile
        val kind = pendingCaptureKind
        if (result.resultCode == RESULT_OK && file != null && file.exists() && kind != null) {
            when (kind) {
                CaptureKind.CARD_PHOTO -> onCardPhotoCaptured(file.readBytes())
                CaptureKind.SELFIE -> onSelfieCaptured(file.readBytes())
                CaptureKind.ADDITIONAL_ID -> onAdditionalIdPhotoCaptured(file.readBytes())
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
        sectionVideoRecord = findViewById(R.id.section_video_record)
        videoPreviewView = findViewById(R.id.video_preview)
        videoPromptOverlay = findViewById(R.id.video_prompt_overlay)
        buttonRecordToggle = findViewById(R.id.button_record_toggle)
        sectionAdditionalId = findViewById(R.id.section_additional_id)
        inputAdditionalIdType = findViewById(R.id.input_additional_id_type)
        buttonAdditionalId = findViewById(R.id.button_additional_id)

        permissionLauncher.launch(
            arrayOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION, Manifest.permission.RECORD_AUDIO),
        )

        findViewById<Button>(R.id.button_scan_pairing_qr).setOnClickListener { onScanPairingQrClicked() }
        findViewById<Button>(R.id.button_biometric).setOnClickListener { runBiometricGate() }
        findViewById<RadioGroup>(R.id.radio_document_type).setOnCheckedChangeListener { _, checkedId ->
            val isCie = checkedId == R.id.radio_cie
            fieldsPassport.visibility = if (isCie) View.GONE else View.VISIBLE
            fieldsCie.visibility = if (isCie) View.VISIBLE else View.GONE
        }
        buttonCardPhoto.setOnClickListener { launchCamera(CaptureKind.CARD_PHOTO) }
        buttonScan.setOnClickListener { onScanClicked() }
        buttonSelfie.setOnClickListener { launchCamera(CaptureKind.SELFIE) }
        buttonVideo.setOnClickListener { showVideoInstructionsThenRecord() }
        buttonRecordToggle.setOnClickListener { onRecordToggleClicked() }
        buttonDone.setOnClickListener { resetToBiometricGate() }
        buttonAdditionalId.setOnClickListener { onAdditionalIdClicked() }

        resumeSessionIfAvailable()
    }

    // MARK: -- Session persistence
    //
    // Real bug, reported live: launching the system camera app for the
    // card photo (launchCamera below) is exactly the kind of foreground
    // activity Android can reclaim memory from by killing this app's
    // whole process while it's backgrounded -- common on real devices,
    // not a hypothetical. `api` was only ever an in-memory lateinit var,
    // so returning from the camera to a freshly recreated MainActivity
    // meant `sectionLogin` (VISIBLE by default in the layout, and never
    // otherwise reset) was the only thing left to show -- the user was
    // sent all the way back to "scan the QR", losing a token a pairing
    // code can't even be reused to get back (it's single-use). Persists
    // just enough (server, token, and what was declared on the web) to
    // resume straight into the biometric gate instead -- a fresh face/
    // fingerprint check plus retaking the card photo is real but minor
    // friction, versus needing an entirely new QR from the website.
    private fun sessionPrefs() = getSharedPreferences("rentshield_session", MODE_PRIVATE)

    private fun persistSession(server: String, token: String, declared: DeclaredDocument) {
        sessionPrefs().edit()
            .putString("server", server)
            .putString("token", token)
            .putString("declared_document_type", declared.documentType)
            .putString("declared_document_number", declared.documentNumber)
            .putString("declared_date_of_birth", declared.dateOfBirth)
            .putString("declared_expiry_date", declared.expiryDate)
            .putString("declared_can", declared.can)
            .apply()
    }

    private fun resumeSessionIfAvailable() {
        val prefs = sessionPrefs()
        val server = prefs.getString("server", null)
        val token = prefs.getString("token", null)
        if (server == null || token == null) return

        api = RentShieldApiClient(server, token)
        prefillDeclaredDocument(
            DeclaredDocument(
                documentType = prefs.getString("declared_document_type", "").orEmpty(),
                documentNumber = prefs.getString("declared_document_number", "").orEmpty(),
                dateOfBirth = prefs.getString("declared_date_of_birth", "").orEmpty(),
                expiryDate = prefs.getString("declared_expiry_date", "").orEmpty(),
                can = prefs.getString("declared_can", "").orEmpty(),
            ),
        )
        sectionLogin.visibility = View.GONE
        sectionBiometric.visibility = View.VISIBLE
        sectionAdditionalId.visibility = View.VISIBLE
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
                    persistSession(server, it.token, it.declared)
                    prefillDeclaredDocument(it.declared)
                    sectionLogin.visibility = View.GONE
                    sectionBiometric.visibility = View.VISIBLE
                    sectionAdditionalId.visibility = View.VISIBLE
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
        // Kept for the confirmation-video sentence -- the chip's own MRZ
        // is the most authoritative name/DOB source on-device (see
        // README's 2026-09-13 note on the OCR name-matching bug fixed
        // in idswyft-community itself), more reliable than re-deriving
        // this from a server round-trip.
        verifiedFullName = fullName
        verifiedAgeYears = ageFromMrzDateOfBirth(result.dateOfBirth)
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

    // MRZ dates of birth are 2-digit years (YYMMDD) -- the standard ICAO
    // century rule: a year greater than the current two-digit year is
    // assumed to be the previous century (nobody's MRZ DOB is in the
    // future), otherwise this century.
    private fun ageFromMrzDateOfBirth(yyMMdd: String): Int? {
        if (yyMMdd.length != 6 || !yyMMdd.all { it.isDigit() }) return null
        val yy = yyMMdd.substring(0, 2).toInt()
        val month = yyMMdd.substring(2, 4).toInt()
        val day = yyMMdd.substring(4, 6).toInt()
        val now = Calendar.getInstance()
        val currentTwoDigitYear = now.get(Calendar.YEAR) % 100
        val century = if (yy > currentTwoDigitYear) 1900 else 2000
        val birthYear = century + yy
        var age = now.get(Calendar.YEAR) - birthYear
        val birthdayAlreadyPassedThisYear =
            (now.get(Calendar.MONTH) + 1 > month) ||
                (now.get(Calendar.MONTH) + 1 == month && now.get(Calendar.DAY_OF_MONTH) >= day)
        if (!birthdayAlreadyPassedThisYear) age -= 1
        return age
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
    //
    // Recorded in-app via CameraX, not the plain video-capture intent the
    // card photo/selfie steps still use: the user must be shown, ON
    // SCREEN, the exact sentence to read aloud while recording -- only a
    // live in-app preview can display an overlay like that; the system
    // camera app's own UI is opaque to this process. Requested
    // explicitly: informed with the sentence BEFORE recording starts
    // (the dialog below), and shown the same sentence again as an
    // overlay WHILE recording (videoPromptOverlay).

    private fun confirmationSentence(): String {
        val age = verifiedAgeYears?.toString() ?: "my age"
        val name = verifiedFullName.ifBlank { "my name" }
        return "Hi, I'm $name and I'm $age years old."
    }

    private fun showVideoInstructionsThenRecord() {
        AlertDialog.Builder(this)
            .setTitle("Before you record")
            .setMessage(
                "You'll record a short video to confirm your identity. Please read the " +
                    "following sentence aloud, clearly, while looking at the camera " +
                    "(it'll stay on screen the whole time):\n\n\"${confirmationSentence()}\"",
            )
            .setCancelable(false)
            .setPositiveButton("I'm ready") { _, _ -> startVideoRecordingUi() }
            .show()
    }

    private fun startVideoRecordingUi() {
        buttonVideo.visibility = View.GONE
        sectionVideoRecord.visibility = View.VISIBLE
        videoPromptOverlay.text = confirmationSentence()
        buttonRecordToggle.visibility = View.VISIBLE
        buttonRecordToggle.text = "Start Recording"

        val cameraProviderFuture = ProcessCameraProvider.getInstance(this)
        cameraProviderFuture.addListener(
            {
                val cameraProvider = cameraProviderFuture.get()
                val preview = Preview.Builder().build().also {
                    it.setSurfaceProvider(videoPreviewView.surfaceProvider)
                }
                val recorder = Recorder.Builder().build()
                videoCapture = VideoCapture.withOutput(recorder)
                try {
                    cameraProvider.unbindAll()
                    cameraProvider.bindToLifecycle(
                        this, CameraSelector.DEFAULT_FRONT_CAMERA, preview, videoCapture,
                    )
                } catch (e: Exception) {
                    toast("Could not start the camera: ${e.message}")
                }
            },
            ContextCompat.getMainExecutor(this),
        )
    }

    private fun onRecordToggleClicked() {
        val capture = videoCapture ?: return
        if (activeRecording != null) {
            activeRecording?.stop()
            activeRecording = null
            return
        }

        val hasAudio = ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            toast("Camera permission is required to record.")
            permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO))
            return
        }

        val dir = File(cacheDir, "videos").apply { mkdirs() }
        val file = File(dir, "confirmation_${System.currentTimeMillis()}.mp4")
        val outputOptions = FileOutputOptions.Builder(file).build()
        var recording = capture.output.prepareRecording(this, outputOptions)
        if (hasAudio) recording = recording.withAudioEnabled()
        activeRecording = recording.start(ContextCompat.getMainExecutor(this)) { event ->
            if (event is VideoRecordEvent.Finalize) {
                runOnUiThread {
                    sectionVideoRecord.visibility = View.GONE
                    buttonRecordToggle.visibility = View.GONE
                    if (!event.hasError()) {
                        onVideoCaptured(file.readBytes())
                    } else {
                        toast("Recording failed: ${event.cause?.message ?: "unknown error"}")
                        buttonVideo.visibility = View.VISIBLE
                    }
                }
            }
        }
        buttonRecordToggle.text = "Stop Recording"
        // A couple of sentences, not a monologue -- same limit the old
        // intent-based capture enforced via EXTRA_DURATION_LIMIT.
        recordingHandler.postDelayed({
            activeRecording?.stop()
            activeRecording = null
        }, 20_000)
    }

    private fun onVideoCaptured(videoBytes: ByteArray) {
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

    // MARK: -- Additional ID (optional, plain photo, no NFC/OCR pipeline)

    private fun onAdditionalIdClicked() {
        val idType = inputAdditionalIdType.text.toString().trim()
        if (idType.isEmpty()) {
            toast("Say what kind of document this is first (e.g. \"Driving licence\").")
            return
        }
        launchCamera(CaptureKind.ADDITIONAL_ID)
    }

    private fun onAdditionalIdPhotoCaptured(photoBytes: ByteArray) {
        val idType = inputAdditionalIdType.text.toString().trim()
        buttonAdditionalId.isEnabled = false
        buttonAdditionalId.text = "Uploading…"
        api.uploadAdditionalId(idType, photoBytes, "image/jpeg") { result ->
            runOnUiThread {
                buttonAdditionalId.isEnabled = true
                result.onSuccess {
                    buttonAdditionalId.text = "Additional ID uploaded"
                }
                result.onFailure {
                    buttonAdditionalId.text = "Take additional ID photo"
                    toast(it.message ?: "Could not upload that document -- try again.")
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
        val dirName = when (kind) {
            CaptureKind.CARD_PHOTO -> "cards"
            CaptureKind.SELFIE -> "selfies"
            CaptureKind.ADDITIONAL_ID -> "additional_ids"
        }
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
        activeRecording?.stop()
        activeRecording = null
        videoCapture = null
        buttonCardPhoto.visibility = View.VISIBLE
        buttonScan.visibility = View.GONE
        buttonSelfie.visibility = View.GONE
        buttonVideo.visibility = View.GONE
        buttonDone.visibility = View.GONE
        sectionVideoRecord.visibility = View.GONE
        buttonRecordToggle.visibility = View.GONE
        photoPreview.setImageDrawable(null)
        statusText.text = ""
        sectionDocument.visibility = View.GONE
        sectionBiometric.visibility = View.VISIBLE
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}
