#!/bin/zsh
# Builds Pulse.app.  Usage: ./build.sh            → ~/Applications/Pulse.app (this Mac's architecture)
#                           UNIVERSAL=1 APP=dist/Pulse.app ./build.sh   → Apple Silicon + Intel
set -e
cd "$(dirname "$0")"
APP=${APP:-$HOME/Applications/Pulse.app}
VERSION=${VERSION:-1.0.0}
BIN="$APP/Contents/MacOS/Pulse"
rm -rf "$APP"; mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
FLAGS=(-O -swift-version 5 -parse-as-library)
if [[ -n "$UNIVERSAL" ]]; then
  swiftc "${FLAGS[@]}" -target arm64-apple-macos13.0 Pulse.swift -o "$BIN-arm64"
  swiftc "${FLAGS[@]}" -target x86_64-apple-macos13.0 Pulse.swift -o "$BIN-x86_64"
  lipo -create "$BIN-arm64" "$BIN-x86_64" -output "$BIN" && rm "$BIN-arm64" "$BIN-x86_64"
else
  swiftc "${FLAGS[@]}" Pulse.swift -o "$BIN"
fi
cp Pulse.icns "$APP/Contents/Resources/Pulse.icns"
cat > "$APP/Contents/Info.plist" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>app.pulse.widget</string>
<key>CFBundleName</key><string>Pulse</string>
<key>CFBundleDisplayName</key><string>Pulse</string>
<key>CFBundleExecutable</key><string>Pulse</string>
<key>CFBundleIconFile</key><string>Pulse</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string>
<key>LSMinimumSystemVersion</key><string>13.0</string>
<key>LSUIElement</key><true/>
<key>NSHumanReadableCopyright</key><string>MIT License</string>
</dict></plist>
PL
codesign -s - --force --deep "$APP" >/dev/null 2>&1
echo "built $APP"
