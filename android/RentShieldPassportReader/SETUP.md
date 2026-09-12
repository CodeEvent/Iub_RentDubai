# RentShield Passport/CIE Reader (Android) -- setup

## What this actually is

The free, working path to real NFC document reading (see the repo's
`ios/RentShieldPassportReader/SETUP.md` for why iOS categorically can't
do this without a paid $99/year Apple Developer account -- Android has
no equivalent paywall for NFC).

Reads either a passport or an Italian CIE (digital ID card) over NFC --
`NfcChipReader.kt` handles both with the same ICAO 9303 DG1/DG2 call
sequence (JMRTD), keyed differently: a passport derives its access key
from the printed number/DOB/expiry (BAC, with PACE tried first), a CIE
from its printed 6-digit CAN (`PACEKeySpec.createCANKey`, verified against
JMRTD's actual tagged source, not guessed -- CIE has no BAC fallback,
confirmed against Italy's own CIE documentation). Then: a Face ID/
fingerprint gate (`androidx.biometric`, confirms phone ownership only --
see `NfcChipReader.kt`'s doc comment on why chip-stored fingerprints
can't be read or matched by any commercial app), a live selfie via the
stock camera app, best-effort geolocation, and upload to RentShield's
existing, already-verified Django backend -- no new backend endpoints.

## Actually compiled, twice

Unlike the iOS build (written blind, fixed via CI trial and error), this
was built and verified locally in the same sandbox that wrote it, using
a real Android SDK + Gradle install -- `./gradlew assembleDebug` produces
a real, `aapt`-verified, installable APK. `.github/workflows/
build-android.yml` now also builds it on every push (plain `ubuntu-latest`,
no special runner needed) and uploads the APK as a workflow artifact.

## Not yet verified

- Never run on a real device -- NFC chip reading itself (for either
  document type), the biometric prompt, and the upload flow are
  untested beyond compiling. The original passport-only version's NFC
  read was written from a proven reference app's call sequence, but this
  session has no phone or physical passport/CIE to tap.
- No retry affordance if a scan fails partway -- returns to the
  document-entry screen to start over.
- Passive Authentication (verifying the chip's data wasn't tampered
  with via its signed SOD against a CSCA master list) isn't implemented
  -- same known gap as the original version.
