#!/usr/bin/env bash
# IPGuard macOS build script: produces dist/IPGuard.app (menu-bar app, no Dock icon)
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[1/5] Creating build virtualenv..."
python3 -m venv .venv-build
# shellcheck disable=SC1091
source .venv-build/bin/activate
pip install -q -U pip
pip install -q -r requirements.txt pyinstaller pillow

echo "[2/5] Generating app icon..."
python packaging/make_icon.py
iconutil -c icns build/icon.iconset -o build/IPGuard.icns

echo "[3/5] PyInstaller bundle..."
pyinstaller --noconfirm --clean --windowed \
  --name IPGuard \
  --icon build/IPGuard.icns \
  --osx-bundle-identifier com.local.ipguard \
  main.py

echo "[4/5] Hide Dock icon (menu-bar-only app)..."
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "dist/IPGuard.app/Contents/Info.plist" 2>/dev/null || true

echo "[5/5] Ad-hoc codesign (personal use)..."
codesign --force --deep -s - "dist/IPGuard.app"

echo ""
echo "Done: dist/IPGuard.app"
echo "  Copy it to /Applications to use."
echo "  If Gatekeeper blocks the first launch: xattr -cr /Applications/IPGuard.app"
echo "  Autostart: System Settings -> General -> Login Items, or use packaging/com.ipguard.plist"
