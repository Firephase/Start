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
APK_NAME=emrilab-debug.apk

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
echo "[4/6] Packaging resources…"
aapt package -f \
    -M AndroidManifest.xml \
    -S res \
    -I $PLATFORM \
    -F $OUT/apk_unsigned/emrilab.ap_ \
    --min-sdk-version 21 \
    --target-sdk-version 33

# 6. Add DEX to the APK
echo "[5/6] Adding DEX…"
cp $OUT/apk_unsigned/emrilab.ap_ $OUT/apk_unsigned/emrilab.apk
cd $OUT/dex
zip -qj ../apk_unsigned/emrilab.apk classes.dex
cd - > /dev/null

# 7. Sign with a debug key
echo "[6/6] Signing APK…"
KEYSTORE=$OUT/debug.keystore
if [ ! -f "$KEYSTORE" ]; then
    keytool -genkeypair -v \
        -keystore $KEYSTORE \
        -alias androiddebugkey \
        -keyalg RSA -keysize 2048 \
        -validity 10000 \
        -dname "CN=Android Debug,O=Android,C=US" \
        -storepass android \
        -keypass android 2>/dev/null
fi

$JAVA_HOME/bin/jarsigner \
    -verbose \
    -keystore $KEYSTORE \
    -storepass android \
    -keypass android \
    -signedjar $OUT/$APK_NAME \
    $OUT/apk_unsigned/emrilab.apk \
    androiddebugkey 2>&1 | grep -E "jar signed|Warning|error" || true

# 8. Align (optional but recommended)
if command -v zipalign &>/dev/null; then
    mv $OUT/$APK_NAME $OUT/${APK_NAME}.unaligned
    zipalign -v 4 $OUT/${APK_NAME}.unaligned $OUT/$APK_NAME > /dev/null
    rm $OUT/${APK_NAME}.unaligned
    echo "zipalign done"
fi

echo ""
echo "=== Build successful ==="
echo "APK: $OUT/$APK_NAME"
ls -lh $OUT/$APK_NAME
