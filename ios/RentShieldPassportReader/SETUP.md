# RentShield Passport Reader (iOS) -- setup

## What this actually is

A native iPhone app that reads a passport's NFC chip (the real BAC
handshake per ICAO 9303, via the open-source `NFCPassportReader` library),
takes a live selfie with the front camera, and uploads both to
RentShield's existing, already-verified Django backend -- the exact same
`start` / `front-document` / `live-capture` / `status` endpoints the
Angular web app already uses. It doesn't add any new backend surface.

Face ID gates opening the app (confirms the phone owner authorized this
attempt) but does **not** verify identity by itself -- see
`FaceIDAuthenticator.swift`'s comment for why that's a hard platform limit,
not a missing feature. The actual identity check is Idswyft's face match
between the live selfie and the passport photo -- here, that photo comes
straight off the chip (DG2), which is cleaner data than a phone photo of
the printed page.

## Compile-verified in CI, not device-verified

This sandbox has no Mac and no Swift toolchain, so nothing here was ever
built locally. Instead, `.github/workflows/build-ios.yml` builds this
project for real on a macOS GitHub Actions runner (free -- this repo is
public) on every push, targeting the iOS Simulator with no code signing
-- **currently green**: https://github.com/CodeEvent/Iub_RentDubai/actions/workflows/build-ios.yml.
Getting there took three real, CI-caught fixes, not guesswork left
uncorrected: `NFCPassportReader`'s version pin was wrong (4.0.0 doesn't
exist; fixed to the real latest, 2.3.3) and its actual API is
`async throws`, not completion-handler based -- both found by cloning
the tagged 2.3.3 source directly and reading it, not by re-guessing; and
the deployment target had to move from iOS 15 to 16 for
`NavigationStack`.

What CI *can't* verify: NFC doesn't work in the Simulator at all -- it
needs a real iPhone 7 or later on iOS 16+, which also needs real code
signing (see below).

## What you need to actually run this on your phone

The CI build above proves the code compiles -- getting it onto a real
iPhone with working NFC/Face ID/camera additionally needs:

1. **A Mac with Xcode**, OR extending the existing CI workflow to
   produce a signed, installable build (e.g. via TestFlight) instead of
   just a Simulator build -- ask if you want that set up; it still needs
   everything below.
2. **[XcodeGen](https://github.com/yonaskolb/XcodeGen)** (`brew install
   xcodegen`) if building locally on a Mac -- CI already installs it
   itself. This repo ships a `project.yml`, not a hand-authored
   `.xcodeproj` (those are fragile to write by hand without Xcode itself
   generating them; XcodeGen is the standard tool for this).
3. **An Apple Developer account enrolled in the Apple Developer Program
   ($99/year)**. This is unavoidable regardless of build method: the NFC
   entitlement (`com.apple.developer.nfc.readersession.formats`) and
   installing on your own device for longer than Xcode's 7-day free
   "Personal Team" window both need it.
4. **A real iPhone 7 or later**, connected by cable or over the network to
   Xcode, or enrolled in TestFlight if built via CI.

## Build steps (on a Mac)

```bash
cd RentShieldPassportReaderIOS
xcodegen generate
open RentShieldPassportReader.xcodeproj
```

In Xcode: Signing & Capabilities tab -> set your Team -> Xcode fills in
the NFC/Camera/Location entitlements from `project.yml` automatically.
Plug in your iPhone, select it as the run destination, hit Run.

On first launch, enter your RentShield server's real network address
(e.g. `http://192.168.0.120:8000`) -- **not** `localhost`, since the
phone is a separate device on the network. This project already hit this
exact bug once with Idswyft's QR code; the login screen forces you to
type a real address instead of defaulting to one.

## Not done yet (named, not silently skipped)

- MRZ auto-scan via the camera (Vision framework OCR) -- passport number/
  DOB/expiry are typed in manually for now.
- The front-document hard-reject path isn't specially handled for a
  chip photo specifically -- it reuses the same check the web app's
  photographed-passport flow already has, untested against a real chip
  photo.
- No retry/back button if the NFC read itself fails partway through --
  currently returns you to the entry screen to start the tap again.
