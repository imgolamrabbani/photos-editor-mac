# Photos Editor for macOS

A native macOS port and standalone desktop replica of the Windows 11 Photos application image editor.

Extracted, reverse-engineered, and rebuilt from the Microsoft Photos MSIX package into a high-performance native macOS desktop application powered by Swift, AppKit, WebKit, WebGL, and WebAssembly.

---

## Overview

The Windows 11 Photos application contains a sophisticated image editing pipeline featuring WebGL-accelerated color grading, canvas transformations, vector markup, and WebAssembly-based patch inpainting.

This project reconstructs that editing experience as a native macOS application (`Photos Editor.app`) packaged with an installer disk image (`PhotosEditor.dmg`). It eliminates all Windows-only dependencies (.NET WinUI 3, DirectX, DirectML, and Microsoft Graph) while preserving the complete image editing toolchain.

---

## Size Comparison: 1 GB+ Windows MSIX vs 11 MB Mac App

The original Windows package was 1.1 GB uncompressed. The macOS distribution is approximately 11 MB (3.1 MB compressed as DMG). The size difference is explained by inspecting the contents of the Windows MSIX:

| Windows MSIX Component | Size | Functionality | Status on macOS |
| :--- | :--- | :--- | :--- |
| `mager.onnxe` | 288 MB | Windows NPU Generative Erase ONNX weights | Windows DirectML proprietary |
| `Microsoft.Graph.Beta.dll` | 140 MB | Microsoft 365 Cloud & OneDrive sync assemblies | Omitted (local-first editor) |
| `oneocr.dll` + `oneocr.onemodel` | 95 MB | Windows OCR text scanner engine | Replaced by native macOS Vision |
| `DirectML.dll` + `onnxruntime.dll` | 39 MB | DirectX Machine Learning Windows runtime | Replaced by Apple Silicon Metal |
| .NET 8 + WinUI 3 Assemblies | ~110 MB | C# WinUI desktop runtime (`System.Private.CoreLib`, etc.) | Replaced by native Swift / AppKit |
| `seg.onnxe` | 22 MB | Windows background segmentation model | Windows DirectML proprietary |
| `resources.pri` | 16 MB | Windows MUI localization string database | Replaced by lightweight JSON tables |
| WebGL Editor Engine | 4.8 MB | React canvas, shaders, WASM inpainting | Preserved and ported directly |

The core image processing engine, WebAssembly inpainting runtime (`completion.wasm.bin`), shaders, and assets require only ~5 MB. macOS provides native graphics and system frameworks (CoreGraphics, ImageIO, Metal) out of the box, eliminating the need to bundle redundant runtimes.

---

## Features

### Native macOS Integration
* Built using native AppKit and Swift without Electron or third-party wrappers.
* macOS Dark Aqua appearance conforming to Apple Human Interface Guidelines.
* Native window title bar with document proxy icon (drag the icon or Command-click the title to view file paths).
* Full Finder integration: Double-click to open, Right-Click -> "Open With", and Drag-and-Drop from Finder.
* Native macOS Dock lifecycle support (`applicationShouldHandleReopen`) restoring windows immediately upon click.
* Native menu bar with standard keyboard shortcuts:
  * Open Photo: Command + O
  * Save Changes: Command + S
  * Save As Copy: Shift + Command + S
  * Undo: Command + Z
  * Redo: Shift + Command + Z
  * Zoom In / Out: Command + Plus / Command + Minus
  * Actual Size (100%): Command + 1
  * Fit to Window: Command + 0
  * Toggle Full Screen: Command + F

### High-Fidelity Image Format Support
Image decoding is handled by Apple ImageIO and `CGImageSource`, enabling hardware-accelerated decoding of:
* JPEG / JPG
* PNG (with transparency preservation)
* HEIC / HEIF (Apple iPhone High Efficiency Image Container)
* WebP
* TIFF / TIF
* BMP
* GIF
* Camera RAW formats (CR2, CR3, NEF, ARW, DNG)

### Comprehensive Editing Suite
* Crop & Rotate: Freeform cropping, standard aspect ratios (Original, 1:1, 4:3, 16:9, etc.), arbitrary angle rotation, 90-degree step rotation, horizontal flip, and vertical flip.
* Adjustments: Exposure, Brightness, Contrast, Highlights, Shadows, Vignette, Saturation, Warmth, and Tint controls.
* Filter Profiles: Photographic color presets with adjustable intensity sliders.
* Precision Markup: Ballpoint pen, highlighter, pencil, and calligraphy brush tools with customizable thickness and color pickers.
* Spot Fix / Erase: Client-side patch synthesis running via WebAssembly background workers (`completion.wasm.bin`).

---

## Project Structure

```
photos-editor-mac/
├── App/
│   ├── main.swift                 # Application entry point
│   ├── AppDelegate.swift          # Lifecycle delegate, Dock click, and native menu bar
│   └── MainWindowController.swift # NSWindowController, WKWebView host, image loader/saver
├── Web/
│   ├── index.html                 # Host bridge, theme adapter, and WebGL container
│   ├── static/                    # React bundles, WebAssembly inpainting, workers, css
│   ├── fonts/                     # Fluent and UI symbol web fonts
│   └── cursors/                   # Pen and eraser cursor assets
├── AppIcon.icns                   # High-resolution multi-size macOS application icon
├── Info.plist                     # Document type associations and bundle configuration
├── build.sh                       # Automated compile and DMG distribution build script
├── .gitignore                     # Git ignore rules
└── README.md                      # Project documentation
```

---

## Installation

### Method 1: Pre-built DMG Installer (Recommended)
1. Download `PhotosEditor.dmg` from the [Releases](https://github.com/imgolamrabbani/photos-editor-mac/releases) page.
2. Double-click `PhotosEditor.dmg` to mount the disk image.
3. Drag `Photos Editor.app` into the `Applications` shortcut folder.
4. Launch `Photos Editor` from Launchpad, Spotlight, or the Applications folder.

### Method 2: Command Line Installation
```bash
# Mount and copy to /Applications
hdiutil attach PhotosEditor.dmg
cp -R "/Volumes/Photos Editor/Photos Editor.app" /Applications/
hdiutil detach "/Volumes/Photos Editor"

# Register file associations with macOS LaunchServices
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "/Applications/Photos Editor.app"
```

---

## Building from Source

### Prerequisites
* macOS 12.0 (Monterey) or later
* Apple Silicon (arm64) or Intel (x86_64) Mac
* Xcode Command Line Tools (`xcode-select --install`)

### Build Steps
```bash
# Clone the repository
git clone https://github.com/imgolamrabbani/photos-editor-mac.git
cd photos-editor-mac

# Compile application and assemble DMG
./build.sh
```

The build script performs the following tasks:
1. Compiles the Swift source files (`main.swift`, `AppDelegate.swift`, `MainWindowController.swift`) into an optimized binary.
2. Packages the `.app` bundle structure with `Info.plist`, `AppIcon.icns`, and the Web engine assets.
3. Ad-hoc codesigns the application bundle.
4. Installs the application to `/Applications/Photos Editor.app` and updates LaunchServices.
5. Generates the distribution installer `PhotosEditor.dmg`.

---

## Technical Architecture & Porting Solutions

### 1. Document Routing without NSDocumentClass
In single-window hybrid macOS apps, declaring `<key>NSDocumentClass</key>` in `Info.plist` without a true Cocoa multi-document model causes `NSDocumentController` to intercept opens and generate modal errors: *"Photos Editor cannot open files in the 'Image File' format"*.
This project eliminates `NSDocumentClass` entirely, registers system UTIs (`public.image`, `public.jpeg`, `public.png`, `public.heic`, etc.) in `CFBundleDocumentTypes`, and handles file opening directly through `NSApplicationDelegate`:
```swift
func application(_ application: NSApplication, open urls: [URL]) {
    guard let first = urls.first else { return }
    mainWindowController?.loadFile(from: first)
}
```

### 2. WebGL Drawing Buffer Invalidation & 2D Canvas Handover
In WebGL2, `preserveDrawingBuffer: false` clears the canvas backbuffer to `(0, 0, 0, 0)` immediately after each display swap. Calling `canvas.toDataURL()` on the live canvas results in a completely blank image.
The port resolves this by extracting rendered pixel buffers from the Babylon tile renderer and blitting them to an offscreen 2D canvas via `createImageData`/`putImageData`, which preserves pixel data for lossless export.

### 3. WebKit Background RAF Throttling
WebKit aggressively throttles `requestAnimationFrame` when the window is not continuously animating or during modal sheet presentations (such as `NSSavePanel`). Offscreen tile rendering loops are patched to use `setTimeout(..., 0)`, guaranteeing unthrottled execution.

### 4. Direct Local File Streaming
`evaluateJavaScript` has strict IPC buffer limits (~8-16 MB) that silently drop or truncate large base64 image strings. The host allows root directory access (`allowingReadAccessTo: URL(fileURLWithPath: "/")`) and streams local files directly into WebGL textures via `file://` URLs, supporting multi-hundred-megabyte high-resolution images.

---

## License & Disclaimers

This repository is created for cross-platform research, system interoperability, and educational purposes. Original Microsoft Photos assets and WebGL code remain the intellectual property of Microsoft Corporation.
