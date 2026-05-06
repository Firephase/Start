#!/usr/bin/env bash
# Build Yoda Jump APK
# Requirements: Node.js, Android Studio + SDK, Java 17+
set -e

echo "==> Installing dependencies..."
npm install

echo "==> Adding Android platform (skip if already added)..."
npx cap add android 2>/dev/null || echo "    Android platform already present."

echo "==> Syncing web assets to Android..."
npx cap sync android

echo "==> Building debug APK..."
cd android
chmod +x gradlew
./gradlew assembleDebug

APK="app/build/outputs/apk/debug/app-debug.apk"
if [ -f "$APK" ]; then
  echo ""
  echo "✅  APK ready: android/$APK"
  echo "    Transfer to device with: adb install $APK"
else
  echo "❌  Build failed – check output above."
  exit 1
fi
