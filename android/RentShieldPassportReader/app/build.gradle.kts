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
        versionCode = 1
        versionName = "0.1"
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
}
