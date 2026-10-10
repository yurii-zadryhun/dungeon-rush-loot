plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

android {
    namespace = "com.yurii.dungeonrushloot"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.yurii.dungeonrushloot.dev"
        minSdk = 30
        targetSdk = 35
        versionCode = System.getenv("ANDROID_VERSION_CODE")?.toIntOrNull() ?: 1
        versionName = System.getenv("ANDROID_VERSION_NAME") ?: "0.1.0-dev"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        create("release") {
            storeFile = file("signing/dungeon-rush-dev.jks")
            storePassword = providers.gradleProperty("DUNGEON_RUSH_KEYSTORE_PASSWORD")
                .orElse("dungeonrush-dev-2026").get()
            keyAlias = providers.gradleProperty("DUNGEON_RUSH_KEY_ALIAS")
                .orElse("dungeonrush").get()
            keyPassword = providers.gradleProperty("DUNGEON_RUSH_KEY_PASSWORD")
                .orElse("dungeonrush-dev-2026").get()
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources {
            excludes += setOf(
                "/META-INF/{AL2.0,LGPL2.1}",
                "META-INF/LICENSE*",
                "META-INF/NOTICE*",
            )
        }
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"
        pyc {
            src = true
        }
    }
    // Python sources live at androidApp/src/main/python. That directory contains a
    // symlink to the repository's shared src package, so Android packages the exact
    // same Python domain without making the repository root a Gradle task input.
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.10.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")

    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    debugImplementation("androidx.compose.ui:ui-tooling")

    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.9.0")

    // Bundled model: works immediately and does not depend on a first-run model download.
    implementation("com.google.mlkit:text-recognition:16.0.1")

    testImplementation("junit:junit:4.13.2")
    // Android's org.json classes have no working implementations in JVM unit tests.
    testImplementation("org.json:json:20240303")
}
