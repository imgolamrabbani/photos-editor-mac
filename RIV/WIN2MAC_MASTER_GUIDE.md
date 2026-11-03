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

### 3.3 The WebGL Cleared Drawing Buffer Trap (`preserveDrawingBuffer: false`)
By default in WebGL/WebGL2 specifications, `preserveDrawingBuffer` defaults to `false`. This allows the GPU compositor to discard or clear the backbuffer to transparent black `(0, 0, 0, 0)` immediately after each frame is swapped to the display surface.

When an application calls `canvas.toDataURL()` or `gl.readPixels()` outside of the active draw callback, WebKit returns a completely transparent black image. This manifests as the classic "Blank Saved Copy" bug: the on-screen preview looks vibrant, but any saved image or clipboard copy contains 0 bytes of visual content.

**Remediation Pattern:**
1. Intercept offscreen tile render loops (e.g. Babylon `getEditedImageBytes` or `readPixels`).
2. Hand over raw pixel buffers directly via a dedicated bridge variable (e.g. `window._lastEditedPixels`).
3. Blit the pixel buffer onto an offscreen **2D Canvas** using `createImageData` and `putImageData`:
   ```javascript
   const offscreenCanvas = document.createElement('canvas');
   offscreenCanvas.width = width;
   offscreenCanvas.height = height;
   const ctx = offscreenCanvas.getContext('2d');
   const imgData = ctx.createImageData(width, height);
   imgData.data.set(renderedPixelBuffer);
   ctx.putImageData(imgData, 0, 0);
   const exportDataUrl = offscreenCanvas.toDataURL('image/png');
   ```
   Unlike WebGL canvases, 2D HTML5 canvas buffers retain their raster data indefinitely and never auto-clear.

### 3.4 WebKit Background RAF Throttling in Offscreen Export Pipelines
Chromium and WebKit handle `requestAnimationFrame` differently when processing tasks offscreen or in background tabs.
In WebKit (macOS Safari and `WKWebView`):
- `requestAnimationFrame` is aggressively throttled or frozen when windows are not animating continuously, when minimized, or while native modal sheets (such as `NSSavePanel`) are displayed.
- If an offscreen tile loop uses `requestAnimationFrame` to iterate through image tiles, the entire export pipeline deadlocks or hangs at 0% progress.

**Remediation:**
In offscreen tile renderers (e.g. Webpack module `94271`), replace recursive `requestAnimationFrame(cb)` calls with:
```javascript
setTimeout(cb, 0);
```
or `queueMicrotask(cb)`. This ensures tile rendering executes cooperatively on the event loop without being suspended by WebKit's display link throttler.

### 3.5 External Texture / Filter LUT Dependency Traps
Windows photo engines frequently rely on unbundled native Look-Up Tables (LUTs) or DirectX surface handles. Before exporting, they invoke:
```javascript
editor.waitForRenderingToBeReady();
```
On macOS, if external LUT asset URLs fail to load or DirectX handles are missing, this Promise never resolves, causing saving to hang indefinitely.

**Remediation:**
Short-circuit the readiness check in the JavaScript bundle:
```javascript
waitForRenderingToBeReady: function() {
    return Promise.resolve();
}
```

### 3.6 TypedArray Length Boundary and RangeError Handover
When assembling composite tiles in JavaScript (e.g. `Uint8ClampedArray.set(src, offset)`), if the calculated source tile byte length exceeds the destination subarray bounds, JavaScript immediately throws:
```
RangeError: offset is out of bounds
```
**Remediation:**
Always clamp source slice operations before invoking `.set()`:
```javascript
dest.set(src.subarray(0, Math.min(src.byteLength, dest.byteLength - offset)), offset);
```
Or bypass intermediate tile stitching by having the rendering engine hand over the completed frame buffer directly to the host container.

### 3.7 Automated Tools: `hybrid_bundle_analyzer.py` & `webgl_export_auditor.py`
Audit bundles for IPC hooks, empty localization traps, theme hazards, and WebGL drawing buffer hazards:
```bash
python3 RIV/RMaster/scripts/hybrid_bundle_analyzer.py <web_dir_or_bundle_js>
python3 RIV/RMaster/scripts/webgl_export_auditor.py --scan <web_dir_or_bundle_js>
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

### 4.2 AppKit Single-Window vs NSDocumentClass Alert Traps
A critical Cocoa trap occurs when porting single-window hybrid apps:
- If `<key>NSDocumentClass</key>` is defined in `Info.plist`, Cocoa automatically routes file open requests through `NSDocumentController.openDocument(...)`.
- If the app does not subclass `NSDocument` with a full multi-window document model, or if the controller's completion handler returns `nil`, Cocoa displays a blocking modal alert:
  *"The document could not be opened. Photos Editor cannot open files in the 'Image File' format."*

**The Correct Native Architecture:**
1. Completely remove `<key>NSDocumentClass</key>` from `Info.plist`.
2. Declare `CFBundleDocumentTypes` with all standard image UTIs (`public.image`, `public.jpeg`, `public.png`, `public.heic`, `public.tiff`, etc.).
3. Handle file opening exclusively via `NSApplicationDelegate`:
   ```swift
   func application(_ application: NSApplication, open urls: [URL]) {
       guard let first = urls.first else { return }
       mainWindowController?.loadFile(from: first)
   }

   func application(_ sender: NSApplication, openFile filename: String) -> Bool {
       let url = URL(fileURLWithPath: filename)
       mainWindowController?.loadFile(from: url)
       return true
   }
   ```
4. Implement `applicationShouldHandleReopen(_:hasVisibleWindows:)` to restore the window when clicking the macOS Dock icon.

### 4.3 WebKit IPC Buffer Limits & Direct File Streaming
Passing large base64 image strings (>8-16 MB) across the WebKit IPC bridge via `evaluateJavaScript("loadFromDataUrl('data:...base64...')")` frequently triggers silent IPC serialization limits or process terminations.

**The Solution:**
1. Configure `WKWebView` with root directory access:
   ```swift
   webView.loadFileURL(indexURL, allowingReadAccessTo: URL(fileURLWithPath: "/"))
   ```
2. Pass the raw `file://` URL directly to JavaScript:
   ```javascript
   function loadFromUrl(fileUrl, filename) {
       const img = new Image();
       img.crossOrigin = 'anonymous';
       img.onload = () => { /* feed image directly to WebGL texture */ };
       img.src = fileUrl;
   }
   ```
This provides instant, zero-copy loading of multi-hundred-megabyte images and RAW files.

### 4.4 Dynamic Image Format Conversion on Save
When the user selects "Save as copy" and chooses a `.jpg` or `.jpeg` destination, the exported PNG data URL from the HTML5 canvas must be dynamically transcoded to JPEG with high fidelity:
```swift
let ext = targetURL.pathExtension.lowercased()
var finalData = rawData

if ext == "jpg" || ext == "jpeg" {
    if let imageRep = NSBitmapImageRep(data: rawData),
       let jpegData = imageRep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) {
        finalData = jpegData
    }
}

try finalData.write(to: targetURL, options: .atomic)
```

### 4.5 Save & Clipboard Operations
- **Save as copy:** Display `NSSavePanel` configured with the original filename base and `.png` / `.jpeg` extensions.
- **Save:** Overwrite the original file URL directly using atomic disk writes (`try data.write(to: url, options: .atomic)`).
- **Copy to clipboard:** Decode the image data in Swift and write to `NSPasteboard.general.writeObjects([image])`.

### 4.6 Automated Tool: `mac_native_scaffold_generator.py`
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
- Samples rendered pixel grids to ensure views are not solid blank or transparent.

### 5.2 Automated Tool: `webgl_export_auditor.py`
Verify exported image files to guarantee they contain real rendered pixels:
```bash
python3 RIV/RMaster/scripts/webgl_export_auditor.py --verify-image <path_to_exported_file>
```

---

## 6. Distribution & Release Packaging

A production macOS deployment requires:
1. **Compilation:** `swiftc -O -target arm64-apple-macosx12.0 -framework Cocoa -framework WebKit ...`
2. **Code Signing:** `codesign --force --deep --sign - "AppName.app"` (ad-hoc signing allows local Gatekeeper execution).
3. **LaunchServices Registration:** `/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "AppName.app"`
4. **DMG Disk Image Generation:** `hdiutil create -volname "AppName" -srcfolder staging -ov -format UDZO AppName.dmg`
