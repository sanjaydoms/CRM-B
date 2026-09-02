# Add project specific ProGuard rules here.
# You can control the set of applied configuration files using the
# proguardFiles setting in build.gradle.
#
# For more details, see
#   http://developer.android.com/guide/developing/tools/proguard.html

# If your project uses WebView with JS, uncomment the following
# and specify the fully qualified class name to the JavaScript interface
# class:
#-keepclassmembers class fqcn.of.javascript.interface.for.webview {
#   public *;
#}

# Uncomment this to preserve the line number information for
# debugging stack traces.
#-keepattributes SourceFile,LineNumberTable

# If you keep the line number information, uncomment this to
# hide the original source file name.
#-renamesourcefileattribute SourceFile

# --- Capacitor -----------------------------------------------------------
# Every plugin method the WebView calls is reached by reflection from
# JavaScript, so R8 sees no caller and removes it. The result builds, installs
# and shows a blank screen -- which is why minifyEnabled was left off in the
# template and why these rules exist instead of leaving it off here.
-keep class com.getcapacitor.** { *; }
-keep @com.getcapacitor.annotation.CapacitorPlugin class * { *; }
-keep class * extends com.getcapacitor.Plugin { *; }
-keepclassmembers class * {
    @com.getcapacitor.PluginMethod public <methods>;
}

# The plugins this app actually declares, by their own package names.
-keep class com.capacitorjs.plugins.** { *; }
-keep class com.whitestein.securestorage.** { *; }

# Cordova plugins are bridged the same way (the camera plugin still uses one).
-keep class org.apache.cordova.** { *; }

# Firebase Messaging resolves its service from the manifest by name.
-keep class com.google.firebase.** { *; }

# Crash reports from a shrunk build are unreadable without these, and an
# unreadable crash report is the same as no crash report.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile

# firebase-installations-ktx has a Kotlin extension that references
# com.google.firebase.ktx.Firebase, and firebase-common-ktx -- where that class
# lived -- was folded into firebase-common and removed. Nothing this app calls
# reaches the extension, so the reference is dead code that R8 nonetheless
# refuses to shrink past without being told.
-dontwarn com.google.firebase.ktx.Firebase
