#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="PhotosEditor.app"
OUTPUT_DIR="${SCRIPT_DIR}/${APP_NAME}"
APPLICATIONS_DIR="/Applications/Photos Editor.app"
DMG_NAME="PhotosEditor.dmg"
DMG_OUTPUT="${WORKSPACE_DIR}/${DMG_NAME}"

echo "=========================================="
echo " Building Native macOS Photos Editor App  "
echo "=========================================="

# Kill any existing running instance
pkill -9 -f "PhotosEditor" 2>/dev/null || true

echo "[1/6] Compiling Swift application binary..."
swiftc -O \
       -target arm64-apple-macosx12.0 \
       -framework Cocoa \
       -framework WebKit \
       "${SCRIPT_DIR}/App/AppDelegate.swift" \
       "${SCRIPT_DIR}/App/MainWindowController.swift" \
       "${SCRIPT_DIR}/App/main.swift" \
       -o "${SCRIPT_DIR}/PhotosEditor_bin"

echo "[2/6] Assembling .app bundle directory structure..."
rm -rf "${OUTPUT_DIR}"
mkdir -p "${OUTPUT_DIR}/Contents/MacOS"
mkdir -p "${OUTPUT_DIR}/Contents/Resources"

mv "${SCRIPT_DIR}/PhotosEditor_bin" "${OUTPUT_DIR}/Contents/MacOS/PhotosEditor"
chmod +x "${OUTPUT_DIR}/Contents/MacOS/PhotosEditor"

echo "[3/6] Copying metadata, icon, and Web engine..."
cp "${SCRIPT_DIR}/Info.plist" "${OUTPUT_DIR}/Contents/Info.plist"
cp "${SCRIPT_DIR}/AppIcon.icns" "${OUTPUT_DIR}/Contents/Resources/AppIcon.icns"
cp -R "${SCRIPT_DIR}/Web" "${OUTPUT_DIR}/Contents/Resources/"

echo "[4/6] Ad-hoc codesigning bundle..."
codesign --force --deep --sign - "${OUTPUT_DIR}"

echo "[5/6] Deploying to /Applications and updating LaunchServices..."
rm -rf "${APPLICATIONS_DIR}"
cp -R "${OUTPUT_DIR}" "${APPLICATIONS_DIR}"
codesign --force --deep --sign - "${APPLICATIONS_DIR}"

# Update LaunchServices database so macOS immediately associates file formats & Dock
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "${APPLICATIONS_DIR}"

# Create root folder symlink for quick access
cd "${WORKSPACE_DIR}"
rm -f "Photos Editor.app"
ln -sf "${APPLICATIONS_DIR}" "Photos Editor.app"

echo "[6/6] Generating macOS .dmg Disk Image Distribution Installer..."
DMG_STAGE="${SCRIPT_DIR}/dmg_staging"
rm -rf "${DMG_STAGE}"
mkdir -p "${DMG_STAGE}"
cp -R "${OUTPUT_DIR}" "${DMG_STAGE}/Photos Editor.app"
ln -s /Applications "${DMG_STAGE}/Applications"

rm -f "${DMG_OUTPUT}" "${SCRIPT_DIR}/${DMG_NAME}"
hdiutil create -volname "Photos Editor" \
               -srcfolder "${DMG_STAGE}" \
               -ov -format UDZO \
               "${DMG_OUTPUT}"

cp "${DMG_OUTPUT}" "${SCRIPT_DIR}/${DMG_NAME}"
rm -rf "${DMG_STAGE}"

echo "=========================================="
echo " BUILD SUCCESSFUL!                        "
echo " Installed App: ${APPLICATIONS_DIR}       "
echo " Root App link: ${WORKSPACE_DIR}/Photos Editor.app "
echo " Installer DMG: ${DMG_OUTPUT}             "
echo "=========================================="
