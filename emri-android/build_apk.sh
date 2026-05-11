#!/usr/bin/env bash
# Build EMRI Lab APK with Buildozer.
# Run this script from the emri-android/ directory on Linux/macOS.
set -e

echo "=== EMRI Lab APK Builder ==="

# 1. Check for buildozer
if ! command -v buildozer &> /dev/null; then
    echo "[INFO] buildozer not found — installing..."
    pip install buildozer cython
fi

# 2. On Debian/Ubuntu: install system deps
if command -v apt-get &> /dev/null; then
    echo "[INFO] Installing system dependencies..."
    sudo apt-get install -y \
        git zip unzip openjdk-17-jdk \
        python3-pip autoconf libtool pkg-config \
        zlib1g-dev libncurses5-dev libncursesw5-dev libtinfo5 \
        cmake libffi-dev libssl-dev
fi

# 3. Set JAVA_HOME if needed
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}

# 4. Build
echo "[INFO] Starting Buildozer APK build (this takes 10–30 min on first run)..."
buildozer android debug

echo ""
echo "=== Build complete ==="
echo "APK location: bin/emrilab-0.1.0-arm64-v8a_armeabi-v7a-debug.apk"
echo ""
echo "To install on connected Android device:"
echo "  adb install bin/emrilab-*.apk"
