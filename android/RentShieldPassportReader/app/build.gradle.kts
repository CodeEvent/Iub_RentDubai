plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.rentshield.passportreader"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.rentshield.passportreader"
        minSdk = 24
        targetSdk = 34
        // Real bug found live (2026-09-14): this never got bumped across
        // any rebuild this session, including several that changed the
        // login flow entirely (removing the manual server/username/
        // password fields). Android's installer treats an APK with an
        // unchanged versionCode as "not a new version" -- reinstalling
        // over an already-installed copy can silently no-op instead of
        // actually replacing it, which is exactly what made an old build
        // look like it was still running the removed login screen.
        // Bump this on every rebuild meant for someone to actually
        // install, not just the debug-cycle "same device, same session"
        // ones adb install -r already forces through regardless.
        versionCode = 2
        versionName = "0.2"
    }

    // Real bug found live: without this, the Android Gradle Plugin
    // auto-generates ~/.android/debug.keystore on first use -- fine on
    // a single dev machine, but .github/workflows/build-android.yml
    // runs on a fresh, throwaway GitHub Actions VM every time, so every
    // single CI-built APK was signed with a brand-new, different random
    // key. Android refuses to install an update whose signature doesn't
    // match what's already on the device (silently, or with a bare "App
    // not installed" toast easy to miss) -- so a user installing a new
    // CI artifact over an old one saw no change at all, because the
    // install itself was being silently rejected. A committed debug
    // keystore (debug keystores are meant to be shared -- this is not a
    // release signing key) makes every CI build share one stable
    // signature, so updates after this one install cleanly.
    signingConfigs {
        getByName("debug") {
            storeFile = file("debug.keystore")
            storePassword = "android"
            keyAlias = "androiddebugkey"
            keyPassword = "android"
        }
    }
    buildTypes {
        getByName("debug") {
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    packaging {
        resources {
            excludes += listOf(
                "META-INF/LICENSE",
                "META-INF/NOTICE",
                "META-INF/DEPENDENCIES",
                // BouncyCastle's jdk18on jars are multi-release JARs;
                // bcprov and bcutil both ship an identical OSGi manifest
                // under META-INF/versions/9/, which collides when both
                // are on the classpath (real error from this build).
                "META-INF/versions/9/OSGI-INF/MANIFEST.MF",
            )
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")

    // Real ICAO 9303 NFC passport reading. Originally pinned to the
    // exact old versions tananaev/passport-reader proved together
    // (jmrtd 0.7.18 + SpongyCastle) -- but that combo predates JMRTD's
    // PACE-IM support being spec-validated (the JMRTD maintainer's own
    // commit log has "Icart point encoding is likely not correct yet"
    // for PACE-IM ECDH around that era, and a later commit adding tests
    // "with worked examples from Doc 9303"). Bumped to the current
    // release (0.8.1) specifically for Italian CIE cards, which use
    // PACE-IM, not the Generic Mapping passports use -- this pulls in
    // JMRTD's now-required modern BouncyCastle (jdk18on) in place of
    // SpongyCastle, per JMRTD 0.8.1's own declared POM dependencies
    // (checked directly on Maven Central, not guessed).
    implementation("org.jmrtd:jmrtd:0.8.1")
    implementation("net.sf.scuba:scuba-sc-android:0.0.20")
    implementation("org.bouncycastle:bcprov-jdk18on:1.80")
    implementation("org.bouncycastle:bcutil-jdk18on:1.80")
    implementation("commons-io:commons-io:2.22.0")

    // Face/fingerprint gate (confirms phone ownership -- see
    // NfcChipReader.kt's doc comment on why this isn't the identity
    // check itself), backend upload, and JSON responses.
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // "Scan to sign in" -- Google Play Services' own full-screen QR
    // scanner module (GmsBarcodeScanning), not CameraX + ML Kit's
    // barcode detector: this one needs no camera permission of our own
    // (Google's module handles it), no preview UI to build, just
    // .startScan() and a callback with the decoded string. Confirmed
    // real/latest against Google's Maven repo directly (dl.google.com),
    // not guessed.
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")

    // In-app camera for the confirmation video specifically (the card
    // photo/selfie steps still use the plain MediaStore.ACTION_*_CAPTURE
    // intents above -- no reason to change those). The video step needs
    // to show the sentence the user must read ON SCREEN while recording,
    // which the system camera app's own UI can't be made to display --
    // CameraX's Recorder/VideoCapture is the real, supported way to get
    // a live preview with our own overlay drawn on top. 1.4.2, not the
    // newer 1.6.x line -- 1.6.2 pulls in a media3 dependency that
    // requires compileSdk 35 + AGP 8.6.0, and this project is pinned to
    // compileSdk 34 / AGP 8.5.2 (real build failure hit trying 1.6.2).
    // All CameraX artifacts must share one version regardless.
    implementation("androidx.camera:camera-core:1.4.2")
    implementation("androidx.camera:camera-camera2:1.4.2")
    implementation("androidx.camera:camera-lifecycle:1.4.2")
    implementation("androidx.camera:camera-video:1.4.2")
    implementation("androidx.camera:camera-view:1.4.2")
}
