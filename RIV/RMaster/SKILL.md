---
name: rmaster
description: Universal Reverse Engineering & Cross-Platform Software Porting Master Skill (RMaster). Use this skill whenever the user asks to reverse-engineer any Windows (.msi, .cab, .exe, .dll, .NET/CLI, PE32/PE32+, .msix, .msixbundle, .appx, .pri), macOS (Mach-O, .app, .pkg, .dmg), Linux (ELF), or Android (.apk) software, extract embedded data tables/XML/layouts/assets, disassemble bytecode/IL or native instructions, understand internal state machines or OS hooks, audit hybrid web engines (WebView2/Edge), and rebuild a clean, legal, native cross-platform equivalent.
---

# RMaster — Universal Software Reverse Engineering & Cross-Platform Porting Skill

This skill provides an industrial-grade, zero-dependency methodology and automation toolkit (`scripts/`) for dissecting multi-gigabyte closed-source installers, Windows packages (.msixbundle, .appxbundle, .msix, .appx, .msi, .cab, .exe, .dll, .pri), .NET assemblies, Mach-O, and ELF binaries, reverse-engineering hybrid engines and business logic, and re-architecting their core capabilities natively on macOS (Pure AppKit/Swift, WebKit, Metal, CoreGraphics) without Electron overhead.

---

## 1. End-to-End Reverse Engineering & Porting Methodology

```
+---------------------------------------------------------------------------------------+
| Phase 1: Container & Multi-GB Package Carving                                         |
| (msix_appx_carver.py / unpack_installer.py)                                           |
| Streaming extraction of MSIXBundle, Appx, MSI, CAB, and block map validation.         |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 2: Binary, PRI & Resource Decoding                                              |
| (pri_resource_extractor.py / dotnet_inspector.py / extract_pe_resources.py)           |
| Parse Windows .pri schemas, string pools (UTF-8/UTF-16LE), and .NET CLI metadata.     |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 3: Hybrid Engine Analysis & Discrepancy Auditing                                |
| (hybrid_bundle_analyzer.py / webgl_export_auditor.py)                                 |
| Audit WebView2 IPC bridges, detect empty skeleton strings, theme contrast, WebGL      |
| preserveDrawingBuffer clearing hazards, and RAF background throttling.                |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 4: Native macOS AppKit Re-Architecture                                         |
| (mac_native_scaffold_generator.py)                                                    |
| Pure Swift/AppKit, zero-copy buffer bridge, Dock reopen, direct file streaming,      |
| 2D canvas pixel blitting, dynamic format conversion, NSSavePanel, NSPasteboard.       |
+---------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------+
| Phase 5: Verification & UI/UX Parity Testing                                          |
| (ui_ux_parity_tester.py / webgl_export_auditor.py)                                    |
| Automated WebKit auditing, React Fiber inspection, pixel entropy validation,          |
| and high-resolution visual regression checking.                                      |
+---------------------------------------------------------------------------------------+
```

---

## 2. Phase-by-Phase Technical Execution

### Phase 1: Container & Multi-Gigabyte Package Carving
Windows modern apps (.msixbundle, .appxbundle) encapsulate multiple architectures and nested archives.
1. Run `python3 scripts/msix_appx_carver.py <path_to_package> <output_dir>`.
2. The tool streams multi-gigabyte zip streams without RAM exhaustion, prioritizes `x64` and `neutral` packages, extracts `AppxManifest.xml` declarations (entry points, capabilities, file associations), and catalogs all binaries, PRI files, and Web engines into `EXTRACTION_REPORT.md`.
3. For classic Win32 packages (.msi, .cab, .exe), run `python3 scripts/unpack_installer.py <installer_path> <output_dir>`.

### Phase 2: Windows PRI & Resource Decoding
Windows Store apps store UI strings and assets in binary Package Resource Index (.pri) files instead of plain text.
1. Run `python3 scripts/pri_resource_extractor.py <path_to_pri_or_extracted_dir> [output_json_path]`.
2. The parser analyzes the `mrm_pri2` binary headers, extracts schema identifier keys from `[mrm_hschemaex]`, and maps them to UTF-8 and UTF-16LE string pools carved from `[mrm_dataitem]`.
3. Emits complete localized dictionaries (e.g. `localization_en.json`) for drop-in usage on macOS.

### Phase 3: Hybrid Engine Reverse Engineering & Bug Hunting
Modern Windows apps often embed a React/Fluent UI/WebGL engine inside a native WebView2 control.
1. Run `python3 scripts/hybrid_bundle_analyzer.py <web_dir_or_bundle_js>`.
2. Run `python3 scripts/webgl_export_auditor.py --scan <web_dir_or_bundle_js>`.
3. **Empty Skeleton Localization Trap:** Identifies React context state definitions where all values are initialized to `""` (e.g. `Se = { toolbar_imageSave: "" }`). If the native host does not call `setLocalizationJson(...)` on boot, Fluent UI contextual menus and dropdowns render completely blank. The analyzer locates internal fallback translation modules (e.g., module `81927` with 500+ English strings) and generates bridging patches.
4. **Theme Palette Inversion Trap:** Audits dark mode theme stylesheets to ensure semantic palette names (such as `palette.black`) are properly converted to `#ffffff` or `rgba` alpha values on dark backgrounds to prevent invisible text.
5. **WebGL Cleared Drawing Buffer Trap (`preserveDrawingBuffer: false`):** By default in WebGL2, the drawing buffer is cleared to `(0, 0, 0, 0)` immediately after presentation. Calling `canvas.toDataURL()` or `gl.readPixels()` on a live WebGL canvas outside the active render callback yields a 100% transparent blank image. Export pipelines must either render to an offscreen 2D canvas via `createImageData`/`putImageData` or configure `preserveDrawingBuffer: true`.
6. **WebKit Background RAF Throttling:** WebKit aggressively freezes `requestAnimationFrame` when the window is not continuously animating or during modal sheets. Offscreen tile processing loops relying on RAF starve or hang indefinitely; they must be patched to use `setTimeout(..., 0)` or `queueMicrotask`.
7. **External Texture / Filter LUT Dependency Traps:** Windows engines often hang in `waitForRenderingToBeReady` waiting on unbundled DirectX handles or remote LUT lookup textures. Patch them to resolve immediately: `waitForRenderingToBeReady: () => Promise.resolve()`.
8. **TypedArray Length Boundary Mismatches:** Direct calls to `dest.set(src)` throw `RangeError: offset is out of bounds` if tile dimensions exceed destination slice buffers. Always clamp with `dest.set(src.subarray(0, dest.byteLength))` or hand over raw pixel buffers directly.

### Phase 4: Native macOS AppKit Architecture
Never port desktop hybrid applications to Electron. Electron wastes hundreds of megabytes of memory and battery. Rebuild with pure Swift + Cocoa + WebKit.
1. Run `python3 scripts/mac_native_scaffold_generator.py <app_name> <bundle_id> <web_source_dir> <output_project_dir>`.
2. **Window Ergonomics:** Avoid `.fullSizeContentView` unless custom titlebar drag regions are completely managed. Standard `.titled, .closable, .miniaturizable, .resizable` styling prevents traffic light overlap bugs.
3. **AppKit Single-Window vs NSDocumentClass Alert Trap:** Never declare `<key>NSDocumentClass</key>` in `Info.plist` for single-window apps without a true multi-document Cocoa model. Declaring it forces Cocoa's `NSDocumentController` to intercept opens and display modal errors: *"App cannot open files in 'Image File' format"*. Instead, declare `CFBundleDocumentTypes` with system UTIs (`public.image`, etc.) and route open events exclusively through `NSApplicationDelegate` (`application(_:open:)` and `application(_:openFile:) -> true`).
4. **WebKit IPC Limits & Direct File Streaming:** Calling `evaluateJavaScript` with large base64 strings (>8-16 MB) silently fails or truncates. Initialize the web view with `webView.loadFileURL(url, allowingReadAccessTo: URL(fileURLWithPath: "/"))` and stream local files directly via `file://` URLs in `Image.src`.
5. **Dynamic Format Conversion on Save:** When the user saves an exported canvas as `.jpg` or `.jpeg`, decode the PNG data in Swift and convert it using `NSBitmapImageRep(data: rawData)?.representation(using: .jpeg, properties: [.compressionFactor: 0.95])` before atomic disk write.
6. **WebView2 Shared Buffer Emulation:** Emulate `window.chrome.webview` and dispatch raw pixel buffers via `sharedbufferreceived` listeners.
7. **Native Save & Clipboard:** Wire `NSSavePanel` for "Save as copy", atomic file overwrites for "Save", and `NSPasteboard.general` for "Copy to clipboard".

### Phase 5: Automated Verification & Packaging
1. Run `python3 scripts/ui_ux_parity_tester.py <path_to_app_or_html>` to launch a headless WebKit auditor that verifies all buttons, menus, and dropdowns have non-empty text, aria-labels, and valid icons.
2. Run `python3 scripts/webgl_export_auditor.py --verify-image <path_to_saved_image>` to audit exported files for non-blank pixel distributions and valid entropy.
3. Build, ad-hoc codesign, and package into a standalone distribution disk image (.dmg):
   - `swiftc -O -target arm64-apple-macosx12.0 -framework Cocoa -framework WebKit ...`
   - `codesign --force --deep --sign - "AppName.app"`
   - `hdiutil create -volname "AppName" -srcfolder staging -ov -format UDZO AppName.dmg`

---

## 3. Toolkit Inventory (`scripts/`)

| Script | Purpose & Capabilities |
| :--- | :--- |
| `scripts/msix_appx_carver.py` | Multi-GB streaming unpacker for .msixbundle, .appxbundle, .msix, .appx, and .msi packages. Catalogs PE, WinRT, Web, and shader assets. |
| `scripts/pri_resource_extractor.py` | Pure-Python Windows PRI (`resources.pri`) binary parser. Decodes schemas, UTF-8/UTF-16LE pools, and generates JSON localization tables. |
| `scripts/hybrid_bundle_analyzer.py` | Reverse-engineers Web/WASM engines. Pinpoints WebView2 IPC hooks, empty localization traps, and theme palette contrast bugs. |
| `scripts/webgl_export_auditor.py` | Static code auditor and runtime pixel validator detecting cleared drawing buffers (`preserveDrawingBuffer: false`), WebKit RAF throttling, LUT starvation, and blank exported images. |
| `scripts/mac_native_scaffold_generator.py` | Generates a complete Swift AppKit + WebKit desktop wrapper with Dock reopen, pure NSApplicationDelegate document routing, direct file streaming, 2D canvas blit export, and build script. |
| `scripts/ui_ux_parity_tester.py` | Automated WebKit test runner auditing buttons, menus, aria labels, dark contrast, and capturing retina snapshots with pixel entropy validation. |
| `scripts/dotnet_inspector.py` | Pure-Python .NET metadata and IL disassembler. Dumps classes, fields, methods (RVAs), and traces P/Invoke calls. |
| `scripts/extract_pe_resources.py` | Carves embedded PNG, JPEG, BMP, and XML resources from any PE or Mach-O binary. |
| `scripts/unpack_installer.py` | General-purpose multi-format archive extractor (.msi, .cab, .pkg, .zip). |
| `scripts/vk_to_mackeycode.py` | Keymap converter translating Windows `VK_*` codes to macOS `CGKeyCode` values. |
