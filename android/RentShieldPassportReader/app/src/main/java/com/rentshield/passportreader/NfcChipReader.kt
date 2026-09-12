package com.rentshield.passportreader

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.nfc.tech.IsoDep
import net.sf.scuba.smartcards.CardService
import org.jmrtd.AccessKeySpec
import org.jmrtd.BACKeySpec
import org.jmrtd.PassportService
import org.jmrtd.lds.CardAccessFile
import org.jmrtd.lds.PACEInfo
import org.jmrtd.lds.SecurityInfo
import org.jmrtd.lds.icao.DG1File
import org.jmrtd.lds.icao.DG2File
import org.jmrtd.lds.iso19794.FaceImageInfo
import java.io.ByteArrayInputStream
import java.io.DataInputStream

data class PassportReadResult(
    val firstName: String,
    val lastName: String,
    val nationality: String,
    val dateOfBirth: String, // MRZ's own YYMMDD, per MRZInfo.getDateOfBirth() -- passed through as-is, not reformatted
    val documentNumber: String, // the chip's OWN copy of the card's printed ID/serial number -- cross-checked server-side against the card photo's OCR read, never used as the access key (that's the CAN, a different, mandatory field -- see onScanClicked()'s comment)
    val photoBytes: ByteArray?,
    val photoMimeType: String?,
    val photoBitmap: Bitmap?,
)

/**
 * Real ICAO 9303 chip reading -- PACE (falling back to BAC when a fallback
 * key is given), DG1 (MRZ-equivalent) + DG2 (face photo). Originally
 * written for passports only (ported from tananaev/passport-reader), now
 * generalized so an Italian CIE's CAN-based PACE key can drive the exact
 * same call sequence: [paceKey] is whatever JMRTD [AccessKeySpec] applies
 * (a [org.jmrtd.BACKey] for a passport, [org.jmrtd.PACEKeySpec.createCANKey]
 * for a CIE), and [bacFallbackKey] is only non-null for passports -- a CIE
 * has no BAC to fall back to (PACE with CAN is mandatory), confirmed
 * against Italy's own CIE documentation (cartaidentita.interno.gov.it),
 * not assumed.
 *
 * Deliberately doesn't touch DG3 (fingerprint) -- that data group is
 * behind Extended Access Control, which requires a country-issued
 * Document Verifier certificate only border-control terminals hold. No
 * commercial app can read it; this isn't a missing feature here, it's the
 * standard's own design.
 */
object NfcChipReader {

    fun read(isoDep: IsoDep, paceKey: AccessKeySpec, bacFallbackKey: BACKeySpec?): PassportReadResult {
        isoDep.timeout = 10000
        val cardService = CardService.getInstance(isoDep)
        cardService.open()
        val service = PassportService(
            cardService,
            PassportService.NORMAL_MAX_TRANCEIVE_LENGTH,
            PassportService.DEFAULT_MAX_BLOCKSIZE,
            false,
            false,
        )
        service.open()

        var paceSucceeded = false
        var paceFailure: Exception? = null
        try {
            val cardAccessFile = CardAccessFile(service.getInputStream(PassportService.EF_CARD_ACCESS))
            for (securityInfo: SecurityInfo in cardAccessFile.securityInfos) {
                if (securityInfo is PACEInfo && !paceSucceeded) {
                    service.doPACE(
                        paceKey,
                        securityInfo.objectIdentifier,
                        PACEInfo.toParameterSpec(securityInfo.parameterId),
                        null,
                    )
                    paceSucceeded = true
                }
            }
        } catch (e: Exception) {
            // Could be a genuinely wrong key (bad CAN/passport details), a
            // dropped connection (card moved mid-read), or a chip that
            // really has no PACE support -- surfaced below rather than
            // swallowed, so the actual cause is visible instead of a
            // generic message that looks the same for all three.
            paceFailure = e
        }

        service.sendSelectApplet(paceSucceeded)
        if (!paceSucceeded) {
            if (bacFallbackKey == null) {
                val reason = paceFailure?.message?.let { ": $it" } ?: " (no further detail from the chip)"
                throw IllegalStateException(
                    "Could not establish PACE with this card$reason. Double-check the CAN, and hold the card flat against the phone without moving it.",
                    paceFailure,
                )
            }
            try {
                service.getInputStream(PassportService.EF_COM).read()
            } catch (e: Exception) {
                service.doBAC(bacFallbackKey)
            }
        }

        val dg1File = DG1File(service.getInputStream(PassportService.EF_DG1))
        val dg2File = DG2File(service.getInputStream(PassportService.EF_DG2))

        val mrzInfo = dg1File.mrzInfo
        val faceImageInfos = mutableListOf<FaceImageInfo>()
        dg2File.faceInfos.forEach { faceImageInfos.addAll(it.faceImageInfos) }

        var bitmap: Bitmap? = null
        var photoBytes: ByteArray? = null
        var mimeType: String? = null
        if (faceImageInfos.isNotEmpty()) {
            val faceImageInfo = faceImageInfos.first()
            mimeType = faceImageInfo.mimeType
            val buffer = ByteArray(faceImageInfo.imageLength)
            DataInputStream(faceImageInfo.imageInputStream).readFully(buffer)
            photoBytes = buffer
            // ponytail: JPEG2000 (common on-chip format) isn't decoded to a
            // Bitmap here for on-screen preview -- Android's stock
            // BitmapFactory can't read it, same limitation tananaev's own
            // mature app has. Raw bytes still go to the backend, where a
            // real image library can convert it before face-matching.
            if (!mimeType.contains("jp2", ignoreCase = true) &&
                !mimeType.contains("jpeg2000", ignoreCase = true)
            ) {
                bitmap = BitmapFactory.decodeStream(ByteArrayInputStream(buffer))
            }
        }

        return PassportReadResult(
            firstName = mrzInfo.secondaryIdentifier.replace("<", " ").trim(),
            lastName = mrzInfo.primaryIdentifier.replace("<", " ").trim(),
            nationality = mrzInfo.nationality,
            dateOfBirth = mrzInfo.dateOfBirth,
            documentNumber = mrzInfo.documentNumber,
            photoBytes = photoBytes,
            photoMimeType = mimeType,
            photoBitmap = bitmap,
        )
    }
}
