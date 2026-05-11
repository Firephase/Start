[app]
title = EMRI Lab
package.name = emrilab
package.domain = org.emrilab

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,yaml

version = 0.1.0

requirements = python3==3.11.0,kivy==2.3.0,kivymd==1.2.0,numpy,matplotlib

# Pre-built numpy wheel path (p4a has a numpy recipe — leave empty to use it)
# If build fails for numpy, uncomment and use:
# p4a.local_recipes = ./p4a_recipes

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,WRITE_EXTERNAL_STORAGE,READ_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.sdk = 33
android.archs = arm64-v8a, armeabi-v7a

android.allow_backup = True
android.logcat_filters = *:S python:D

# Icon and splash (place 512×512 PNG in assets/)
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/presplash.png

[buildozer]
log_level = 2
warn_on_root = 0

# Build directory
# buildozer_dir = .buildozer
