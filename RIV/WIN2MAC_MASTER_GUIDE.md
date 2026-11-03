# Windows to macOS Reverse Engineering & Cross-Platform Re-Architecture Master Guide
Part of the RMaster Industrial-Grade Reverse Engineering & Porting Framework.

---

## Abstract

Modern desktop software distributed on Windows frequently incorporates hybrid architectures: WinUI/C++/WinRT or C# outer application shells hosting embedded Chromium/WebView2 or Edge engines, WebAssembly computational filters, and DirectX/HLSL shaders. 

This guide defines a comprehensive, clean-room reverse engineering methodology for unpacking multi-gigabyte Windows packages, extracting indexed resources, analyzing Web/WASM logic, identifying common host-bridge discrepancy bugs, and reconstructing a native, high-performance macOS equivalent using native Cocoa/AppKit, WebKit, and CoreGraphics without Electron overhead.

---

## 1. Package Extraction & Multi-Gigabyte Stream Carving

### 1.1 Architecture Hierarchy in Windows Distribution Containers
Windows Store and enterprise distributions package binaries within nested containers:
1. **AppxBundle / MSIXBundle**: Top-level distribution container holding metadata (`AppxBundleManifest.xml`) and nested architecture-specific packages (`*_x64.msix`, `*_arm64.msix`, `*_neutral.msix`).
2. **Appx / MSIX**: Individual application packages formatted as ZIP archives containing:
   - `AppxManifest.xml`: Entry point declarations, capabilities, file associations, protocol handlers.
   - `AppxBlockMap.xml`: Cryptographic block hashes (SHA256) for streaming verification.
   - `resources.pri`: Windows Package Resource Index storing localized strings, asset paths, and scale factors.
   - Native binaries: `.exe` and `.dll` files (PE32/PE32+).
   - Embedded engines: Web bundles (`Assets/web/`, `Web/`), WebAssembly modules (`.wasm`, `.wasm.bin`), and compiled shaders (`.cso`).

### 1.2 Automated Tool: `msix_appx_carver.py`
To process multi-gigabyte distribution packages without exhausting system memory:
```bash
python3 RIV/RMaster/scripts/msix_appx_carver.py <path_to_msixbundle> <target_output_dir>
```
The script performs:
- Streaming decompression of the bundle.
- Automatic triage of architecture subpackages, prioritizing `x64` and `neutral`.
- Extraction of hybrid assets, native libraries, and configuration manifests.
- Generation of an inventory report (`EXTRACTION_REPORT.md`).

---

## 2. Resource & String Decoding from Windows PRI Files

### 2.1 Understanding the Package Resource Index Format
Windows applications avoid plain-text strings in their user interface code. Strings are compiled into binary `.pri` files (`resources.pri`, `ImageEditorLib.pri`, etc.).
A `.pri` file consists of structured sections:
- `mrm_pri2`: File magic identifier.
- `[mrm_hschemaex]`: Hierarchical Schema Extension containing null-terminated ASCII identifier keys (e.g., `toolbar_imageSave`, `crop_panelLabel`, `filter_listTitle`).
- `[mrm_res_map2_]`: Resource Maps associating schema keys with candidate runtime values.
- `[mrm_dataitem]`: Data Item Streams containing pools of UTF-8 and UTF-16LE localized string values, file references (`ms-appx://`), and binary blobs.

### 2.2 Automated Tool: `pri_resource_extractor.py`
Windows development tools (`makepri.exe`) do not exist natively on macOS. Use `pri_resource_extractor.py` to extract localization dictionaries directly:
```bash
python3 RIV/RMaster/scripts/pri_resource_extractor.py <path_to_pri_or_extracted_dir> [output_localization.json]
```
The parser outputs complete JSON localization tables mapping all resource keys to English and localized strings.

---

## 3. Hybrid Engine Reverse Engineering & Discrepancy Auditing

Modern Windows applications commonly deploy a WebGL/React/Fluent UI frontend hosted inside a native WebView2 control. The native host communicates with the Web view via asynchronous message passing and shared memory buffers.

### 3.1 The Empty Skeleton String Trap (The Blank Dropdown Bug)
In production bundles, the frontend often contains two localization tables:
1. An **empty skeleton object** (e.g., `Se = { toolbar_imageSave: "", toolbar_imageSaveAsCopy: "" }`).
2. An **internal fallback dictionary** (e.g., Webpack module `81927` exporting 500+ full English translations).

When running on Windows, the C++ host calls:
```javascript
window.setLocalizationJson(JSON.stringify(stringsFromPriFile));
```
If the macOS host does not call `setLocalizationJson`, the React context defaults to the empty skeleton object. In Fluent UI's `ContextualMenu`, items with `text: ""` render as empty blocks with zero height or invisible text.

**Fix Strategy:**
1. Populate default React context values with the internal fallback module (`n(81927).b`).
2. Supply default string guards in menu components (`g.toolbar_imageSaveAsCopy || "Save as copy"`).
3. Call `window.setLocalizationJson(...)` on boot from both `index.html` and the native macOS Swift host.

### 3.2 Theme Palette Inversion Traps
In dark mode, Fluent UI themes invert semantic color names:
- `palette.black` is defined as `#ffffff`.
- `palette.white` is defined as `#000000`.

If a component applies `color: palette.black` directly without checking whether dark mode is active or converting through rgba alpha utilities (`Zy(e.palette.black, ...)`), text becomes pure black on dark gray backgrounds.

### 3.3 Automated Tool: `hybrid_bundle_analyzer.py`
Audit minified JavaScript bundles for host hooks, localization traps, and theme contrast hazards:
```bash
python3 RIV/RMaster/scripts/hybrid_bundle_analyzer.py <web_directory_or_js_file>
```

---

## 4. Native macOS AppKit Architecture Engine

Do not wrap hybrid Windows applications in Electron. Electron adds 200 MB+ of overhead, drains battery, and lacks macOS windowing ergonomics. Use a pure native Swift/AppKit container embedding `WKWebView`.

### 4.1 Windowing & Traffic Light Styling
To eliminate title bar overlaps:
- Avoid `.fullSizeContentView` styleMask unless building a completely custom glass title bar.
- Use standard AppKit window masks: `[.titled, .closable, .miniaturizable, .resizable]`.
- Set `window.appearance = NSAppearance(named: .darkAqua)` to match native system dark themes.
- Set `window.representedURL = fileURL` to enable the native macOS document proxy icon in the window title bar.

### 4.2 Dock Reopen & File Opening Lifecycle
1. **Dock Click:** Implement `applicationShouldHandleReopen(_:hasVisibleWindows:)` in `AppDelegate.swift` so clicking the Dock icon restores or recreates the main window if closed.
2. **Document Controller:** Subclass `NSDocumentController` (`UniversalDocumentController.shared`) to intercept `openDocument(...)`. This prevents macOS from displaying the modal alert:
   *"The document could not be opened. App cannot open files in 'Image File' format."*

### 4.3 Zero-Copy / Shared Buffer Emulation
Windows WebView2 dispatches image data via `sharedbufferreceived`. Emulate this in `index.html`:
```javascript
window.chrome = {
  webview: {
    addEventListener: function(event, callback) {
      if (event === 'sharedbufferreceived') {
        window._sharedBufferListeners.push(callback);
      }
    },
    removeEventListener: function(event, callback) {
      window._sharedBufferListeners = window._sharedBufferListeners.filter(cb => cb !== callback);
    },
    hostObjects: { sync: {} }
  }
};
```
Dispatch ArrayBuffers directly to listeners with `additionalData: { type: 'fullImage', payload: { ... } }`.

### 4.4 Save & Clipboard Operations
- **Save as copy:** Display `NSSavePanel` configured with the original filename base and `.png` / `.jpeg` extensions.
- **Save:** Overwrite the original file URL directly using atomic disk writes (`try data.write(to: url, options: .atomic)`).
- **Copy to clipboard:** Decode the image data in Swift and write to `NSPasteboard.general.writeObjects([image])`.

### 4.5 Automated Tool: `mac_native_scaffold_generator.py`
Generate a complete, compile-ready Swift project:
```bash
python3 RIV/RMaster/scripts/mac_native_scaffold_generator.py "Photos Editor" "com.company.photos" <web_dir> <output_dir>
```

---

## 5. UI/UX Parity & Verification Harness

### 5.1 Automated Tool: `ui_ux_parity_tester.py`
Runs a headless/live WebKit instance to audit the ported user interface:
```bash
python3 RIV/RMaster/scripts/ui_ux_parity_tester.py <path_to_app_or_index_html>
```
The test verifies:
- That all buttons have non-empty `innerText` or `aria-label`.
- That contextual menus open with valid item labels.
- That icon glyphs resolve properly against custom Segoe Fluent / MDL2 font files.
- Generates high-resolution screenshots for visual regression auditing.

---

## 6. Distribution & Release Packaging

A production macOS deployment requires:
1. **Compilation:** `swiftc -O -target arm64-apple-macosx12.0 -framework Cocoa -framework WebKit ...`
2. **Code Signing:** `codesign --force --deep --sign - "AppName.app"` (ad-hoc signing allows local Gatekeeper execution).
3. **LaunchServices Registration:** `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "AppName.app"`
4. **DMG Disk Image Generation:** `hdiutil create -volname "AppName" -srcfolder staging -ov -format UDZO AppName.dmg`
