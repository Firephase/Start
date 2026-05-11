#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

SDK=/usr/lib/android-sdk
export PATH="$SDK/build-tools/debian:$PATH"
PLATFORM=$SDK/platforms/android-23/android.jar
BUILD_TOOLS=$SDK/build-tools/debian
JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
JAVAC=$JAVA_HOME/bin/javac
OUT=build
APK_NAME=emrilab.apk

echo "=== EMRI Lab APK build (pure Java / WebView) ==="

# 1. Prepare output dirs
rm -rf $OUT
mkdir -p $OUT/{gen,obj,dex,apk_unsigned}

# 2. aapt: generate R.java from resources
echo "[1/6] Generating R.java…"
aapt package -f -m \
    -J $OUT/gen \
    -M AndroidManifest.xml \
    -S res \
    -I $PLATFORM

# 3. Compile Java sources
echo "[2/6] Compiling Java sources…"
find src $OUT/gen -name "*.java" > $OUT/sources.list
$JAVAC \
    -source 1.8 -target 1.8 \
    -cp $PLATFORM \
    -d $OUT/obj \
    @$OUT/sources.list

# 4. Convert .class → .dex
echo "[3/6] Converting to DEX…"
dx --dex --output=$OUT/dex/classes.dex $OUT/obj

# 5. Package APK (resources + manifest)
# -0 arsc: store resources.arsc uncompressed (required for Android 11+, API 30+)
echo "[4/6] Packaging resources…"
aapt package -f \
    -M AndroidManifest.xml \
    -S res \
    -I $PLATFORM \
    -F $OUT/apk_unsigned/emrilab.ap_ \
    --min-sdk-version 21 \
    --target-sdk-version 33 \
    -0 arsc

# 6. Add DEX to the APK (store uncompressed with -0 so zipalign can align it)
echo "[5/6] Adding DEX…"
cp $OUT/apk_unsigned/emrilab.ap_ $OUT/apk_unsigned/emrilab.apk
cd $OUT/dex
zip -qj0 ../apk_unsigned/emrilab.apk classes.dex
cd - > /dev/null

# 7. zipalign BEFORE signing (required for correct 4-byte alignment)
echo "[6/7] Aligning APK (4-byte)…"
zipalign -f 4 $OUT/apk_unsigned/emrilab.apk $OUT/apk_aligned.apk

# 8. Sign with a release key
echo "[7/7] Signing APK…"
KEYSTORE=$OUT/emrilab.keystore
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair -v \
        -keystore $KEYSTORE \
        -alias emrilab \
        -keyalg RSA -keysize 2048 \
        -validity 36500 \
        -dname "CN=EMRI Lab,O=EMRILab,C=US" \
        -storepass emrilab2024 \
        -keypass emrilab2024 2>/dev/null
fi

$JAVA_HOME/bin/jarsigner \
    -verbose \
    -keystore $KEYSTORE \
    -storepass emrilab2024 \
    -keypass emrilab2024 \
    -signedjar $OUT/$APK_NAME \
    $OUT/apk_aligned.apk \
    emrilab 2>&1 | grep -E "jar signed|Warning|error" || true

echo ""
echo "=== Build successful ==="
echo "APK: $OUT/$APK_NAME"
ls -lh $OUT/$APK_NAME
