package com.rentshield.passportreader

import android.Manifest
import android.app.PendingIntent
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
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
import org.jmrtd.AccessKeySpec
import org.jmrtd.BACKey
import org.jmrtd.PACEKeySpec
import java.io.File

/**
 * Full flow: sign in -> Face ID/fingerprint gate (confirms phone
 * ownership only, see NfcChipReader.kt) -> pick Passport or Italian CIE
 * and enter its access key -> tap the chip -> take a selfie -> upload
 * both to RentShield's existing identity-verification endpoints, which
 * run the actual identity check (selfie vs. chip photo face match).
 */
class MainActivity : AppCompatActivity() {

    private lateinit var api: RentShieldApiClient

    // Views
    private lateinit var sectionLogin: View
    private lateinit var sectionBiometric: View
    private lateinit var sectionDocument: View
    private lateinit var fieldsPassport: View
    private lateinit var fieldsCie: View
    private lateinit var statusText: TextView
    private lateinit var photoPreview: ImageView
    private lateinit var buttonSelfie: Button
    private lateinit var buttonDone: Button

    // Pending NFC read request, set once "Ready to scan" is tapped and
    // consumed in onNewIntent when the actual tap happens.
    private var pendingPaceKey: AccessKeySpec? = null
    private var pendingBacFallback: BACKey? = null

    private var chipPhotoBytes: ByteArray? = null
    private var chipPhotoMimeType: String? = null
    private var selfieFile: File? = null

    private val permissionLauncher = registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    private val cameraLauncher = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
        val file = selfieFile
        if (result.resultCode == RESULT_OK && file != null && file.exists()) {
            onSelfieCaptured(file.readBytes())
        } else {
            statusText.text = "Selfie was cancelled -- tap 'Take selfie' to try again."
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
        buttonSelfie = findViewById(R.id.button_selfie)
        buttonDone = findViewById(R.id.button_done)

        permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA, Manifest.permission.ACCESS_FINE_LOCATION))

        findViewById<Button>(R.id.button_login).setOnClickListener { onLoginClicked() }
        findViewById<Button>(R.id.button_biometric).setOnClickListener { runBiometricGate() }
        findViewById<RadioGroup>(R.id.radio_document_type).setOnCheckedChangeListener { _, checkedId ->
            val isCie = checkedId == R.id.radio_cie
            fieldsPassport.visibility = if (isCie) View.GONE else View.VISIBLE
            fieldsCie.visibility = if (isCie) View.VISIBLE else View.GONE
        }
        findViewById<Button>(R.id.button_scan).setOnClickListener { onScanClicked() }
        buttonSelfie.setOnClickListener { launchCamera() }
        buttonDone.setOnClickListener { resetToBiometricGate() }
    }

    // MARK: -- Login

    private fun onLoginClicked() {
        val serverUrl = findViewById<EditText>(R.id.input_server_url).text.toString().trim()
        val username = findViewById<EditText>(R.id.input_username).text.toString().trim()
        // Trimmed same as username -- this is a dev-credential typically
        // copy-pasted from chat, where a stray leading/trailing space is
        // an accident, not an intentional part of the password.
        val password = findViewById<EditText>(R.id.input_password).text.toString().trim()
        if (serverUrl.isEmpty() || username.isEmpty() || password.isEmpty()) {
            toast("Fill in server address, username, and password.")
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

    // MARK: -- Document entry + NFC

    private fun onScanClicked() {
        val isCie = findViewById<RadioGroup>(R.id.radio_document_type).checkedRadioButtonId == R.id.radio_cie
        if (isCie) {
            val can = findViewById<EditText>(R.id.input_can).text.toString().trim()
            if (can.length != 6) {
                toast("The CAN is the 6-digit number printed on the front of the card.")
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
                chipPhotoBytes = result.photoBytes
                chipPhotoMimeType = result.photoMimeType
                runOnUiThread { onChipReadSuccess(result) }
            } catch (e: Exception) {
                runOnUiThread { statusText.text = "Could not read the chip: ${e.message}" }
            }
        }.start()
    }

    private fun onChipReadSuccess(result: PassportReadResult) {
        pendingPaceKey = null
        sectionDocument.visibility = View.GONE
        statusText.text = "Read ${result.firstName} ${result.lastName} (${result.nationality})." +
            if (result.photoBitmap == null && result.photoBytes != null) {
                " Photo is JPEG2000 -- no on-device preview, but it's still sent for face-matching."
            } else {
                " Now take a selfie to match against it."
            }
        result.photoBitmap?.let { photoPreview.setImageBitmap(it) }
        buttonSelfie.visibility = View.VISIBLE
    }

    // MARK: -- Selfie

    private fun launchCamera() {
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            toast("Camera permission is required for the selfie step.")
            permissionLauncher.launch(arrayOf(Manifest.permission.CAMERA))
            return
        }
        val dir = File(cacheDir, "selfies").apply { mkdirs() }
        val file = File(dir, "selfie_${System.currentTimeMillis()}.jpg")
        selfieFile = file
        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", file)
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
            putExtra(MediaStore.EXTRA_OUTPUT, uri)
            addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
        }
        cameraLauncher.launch(intent)
    }

    private fun onSelfieCaptured(selfieBytes: ByteArray) {
        buttonSelfie.visibility = View.GONE
        statusText.text = "Verifying…"
        BitmapFactory.decodeByteArray(selfieBytes, 0, selfieBytes.size)?.let { photoPreview.setImageBitmap(it) }

        LocationHelper.requestOnce(this) { location ->
            val chipBytes = chipPhotoBytes
            if (chipBytes == null) {
                runOnUiThread { statusText.text = "Missing chip photo -- restart the scan." }
                return@requestOnce
            }
            api.startVerification { startResult ->
                startResult.onFailure { runOnUiThread { statusText.text = it.message } }
                startResult.onSuccess {
                    api.uploadFrontDocument(chipBytes, chipPhotoMimeType, location) { frontResult ->
                        frontResult.onFailure { runOnUiThread { statusText.text = it.message } }
                        frontResult.onSuccess {
                            api.uploadLiveCapture(selfieBytes, location) { finalResult ->
                                runOnUiThread {
                                    finalResult.onSuccess { onVerificationComplete(it) }
                                    finalResult.onFailure { statusText.text = it.message }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    private fun onVerificationComplete(status: VerificationStatus) {
        statusText.text = when (status.status) {
            "verified" -> "Verified."
            "failed" -> "Verification failed."
            "manual_review" -> "Submitted -- under manual review."
            else -> "Submitted -- processing."
        }
        buttonDone.visibility = View.VISIBLE
    }

    private fun resetToBiometricGate() {
        chipPhotoBytes = null
        chipPhotoMimeType = null
        selfieFile = null
        pendingPaceKey = null
        pendingBacFallback = null
        buttonDone.visibility = View.GONE
        buttonSelfie.visibility = View.GONE
        photoPreview.setImageDrawable(null)
        statusText.text = ""
        sectionDocument.visibility = View.GONE
        sectionBiometric.visibility = View.VISIBLE
    }

    private fun toast(message: String) = Toast.makeText(this, message, Toast.LENGTH_LONG).show()
}
