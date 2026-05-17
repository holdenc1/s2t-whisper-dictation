# HelloWorld Android App

A minimal first Android app built with **Kotlin** and **Jetpack Compose**.

The app shows a greeting and a button. Tapping the button toggles the greeting
text and increments a tap counter. The whole UI is in
[`MainActivity.kt`](app/src/main/java/com/example/helloworld/MainActivity.kt).

## How to get the APK onto your tablet

You don't need Android Studio. GitHub Actions builds the APK in the cloud
whenever you push changes to the `claude/android-beginner-app-ZBcwS` branch.

1. Push code to GitHub (Claude Code does this for you).
2. Open the repo on GitHub in your tablet's browser.
3. Click the **Actions** tab.
4. Click the most recent **Build Android APK** run.
5. Scroll to **Artifacts** at the bottom and download
   `HelloWorld-debug-apk`. It downloads as a zip — extract it to get
   `app-debug.apk`.
6. On your tablet, open the APK file. Android will ask you to allow
   installs from your browser/file manager the first time — say yes,
   then tap **Install**.

## What's in this project

```
android-app/
├── settings.gradle.kts        # Lists which modules belong to this project
├── build.gradle.kts           # Top-level build config (plugin versions)
├── gradle.properties          # Global Gradle settings (memory, AndroidX)
└── app/                       # The actual app module
    ├── build.gradle.kts       # App-level build config (SDK, dependencies)
    └── src/main/
        ├── AndroidManifest.xml          # Declares the app to Android
        ├── java/.../MainActivity.kt     # The Kotlin code for the screen
        └── res/values/                  # Resources: strings, theme colors
```

## Key concepts for beginners

- **Activity** = a screen in your app. `MainActivity` is the launch screen.
- **Compose** = the modern way to build UI. You describe what the screen
  should look like (Text, Button, Column) rather than imperatively
  creating views.
- **`@Composable`** = a function that produces UI. `HelloScreen()` is one.
- **`remember { mutableStateOf(...) }`** = how Compose tracks values that
  change over time and need to redraw the UI when they change.
- **Gradle** = the build tool. It downloads dependencies, compiles Kotlin
  to bytecode, packages the APK.

## Making changes

Edit `MainActivity.kt`, commit, and push. The GitHub Actions workflow will
rebuild the APK automatically. Download the new one and reinstall.
