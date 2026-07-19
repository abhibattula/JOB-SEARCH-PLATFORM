#!/bin/sh
# Wrap the PyInstaller .app into a distributable dmg (runs on the macOS CI runner).
set -e
VERSION="${1:-0.3.0}"
APP="dist/Job Engine.app"
OUT="dist/JobEngine-${VERSION}.dmg"
[ -d "$APP" ] || { echo "missing $APP — run pyinstaller first"; exit 1; }
hdiutil create -volname "Job Engine" -srcfolder "$APP" -ov -format UDZO "$OUT"
echo "built $OUT"
