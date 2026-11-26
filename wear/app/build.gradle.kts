import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.google.devtools.ksp")
}

android {
    namespace = "se.konsiliet.wear"
    compileSdk = 36

    defaultConfig {
        // Samma applicationId som mobilappen. Wearable Data Layer levererar bara mellan appar
        // med samma paketnamn och samma signeringsnyckel.
        applicationId = "se.konsiliet"
        minSdk = 30
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("debug")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation("androidx.health:health-services-client:1.1.0")
    implementation("com.google.android.gms:play-services-wearable:19.0.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.10.2")
    implementation("androidx.concurrent:concurrent-futures-ktx:1.2.0")
    implementation("com.google.guava:guava:33.3.1-android")

    implementation("androidx.room:room-runtime:2.8.3")
    implementation("androidx.room:room-ktx:2.8.3")
    ksp("androidx.room:room-compiler:2.8.3")

    implementation("androidx.work:work-runtime-ktx:2.10.5")
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.lifecycle:lifecycle-service:2.9.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.9.4")

    implementation(platform("androidx.compose:compose-bom:2025.10.01"))
    implementation("androidx.activity:activity-compose:1.11.0")
    implementation("androidx.fragment:fragment-ktx:1.8.9") // ActivityResult-API:t kräver Fragment 1.3+ (lint i release)
    implementation("androidx.wear.compose:compose-material3:1.5.3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.wear.compose:compose-foundation:1.5.3")
    implementation("androidx.compose.ui:ui-tooling-preview")

    // Tile och komplikationer.
    implementation("androidx.wear.tiles:tiles:1.6.2")
    implementation("androidx.wear.protolayout:protolayout:1.4.2")
    implementation("androidx.wear.watchface:watchface-complications-data-source-ktx:1.2.1")
}
