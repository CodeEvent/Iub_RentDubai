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

## This was written without a Mac or Xcode available

Everything in `Sources/` is real Swift written against the documented
CoreNFC, LocalAuthentication, CoreLocation, and URLSession APIs (stable,
unlikely to have shifted), plus the third-party `NFCPassportReader`
package. **None of it has been compiled or run** -- this sandbox has no
Swift toolchain at all. Before trusting it:

1. Open the project in Xcode (steps below) and fix any build errors --
   most likely spot: `PassportNFCService.swift`'s call to
   `reader.readPassport(mrzKey:tags:completed:)`, which was written from
   memory of `NFCPassportReader`'s API and should be checked against
   whatever version SPM actually resolves. The MRZ check-digit math above
   it is the standardized ICAO 9303 algorithm and doesn't depend on the
   library.
2. Test on a real iPhone 7 or later running iOS 15+. NFC reading does not
   work in the iOS Simulator at all -- this needs physical hardware.

## What you need to actually build and run this

1. **A Mac with Xcode installed** (or a cloud Mac CI, e.g. a GitHub
   Actions macOS runner or Codemagic -- ask if you want that set up
   instead; it still needs everything below).
2. **[XcodeGen](https://github.com/yonaskolb/XcodeGen)** (`brew install
   xcodegen`) -- this repo ships a `project.yml`, not a hand-authored
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
