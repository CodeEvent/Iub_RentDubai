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
            excludes += listOf("META-INF/LICENSE", "META-INF/NOTICE", "META-INF/DEPENDENCIES")
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")

    // Real ICAO 9303 NFC passport reading -- exact versions proven
    // together in tananaev/passport-reader (452 stars, actively
    // maintained), not picked independently: JMRTD/SCUBA/BouncyCastle
    // version combinations are fragile, and this combo is a known-good
    // one rather than a guess.
    implementation("org.jmrtd:jmrtd:0.7.18")
    implementation("net.sf.scuba:scuba-sc-android:0.0.18")
    implementation("com.madgag.spongycastle:prov:1.58.0.0")
    implementation("org.bouncycastle:bcpkix-jdk15on:1.65") // do not update -- see reference project's own comment
    implementation("commons-io:commons-io:2.22.0")

    // Face/fingerprint gate (confirms phone ownership -- see
    // NfcChipReader.kt's doc comment on why this isn't the identity
    // check itself), backend upload, and JSON responses.
    implementation("androidx.biometric:biometric:1.1.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
}
