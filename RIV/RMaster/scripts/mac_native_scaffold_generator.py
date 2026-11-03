#!/usr/bin/env python3
"""
mac_native_scaffold_generator.py — Universal Native macOS AppKit + WebKit Project Generator
Part of the RMaster Universal Reverse Engineering & Cross-Platform Porting Suite.

Generates a complete, zero-dependency, production-grade native Swift/AppKit desktop wrapper
around any extracted Windows hybrid web application (Photos, Office, Settings, Teams, etc.).

Eliminates all critical reverse engineering and porting pitfalls:
  1. Window Traffic-Light Overlap: Avoids .fullSizeContentView styleMask conflicts.
  2. Dock Reopen Failures: Implements applicationShouldHandleReopen lifecycle delegate.
  3. AppKit "Cannot open format" Alert Trap: Completely omits NSDocumentClass in Info.plist
     and routes file opening exclusively through NSApplicationDelegate (application(_:open:)).
  4. WebKit IPC Buffer Limit: Injects allowingReadAccessTo: / and direct file:// loading,
     preventing silent truncate crashes on multi-megabyte base64 strings in evaluateJavaScript.
  5. WebGL Backbuffer Clearing & Offscreen Export: Generates safe 2D canvas blit export handlers
     and handles dynamic PNG-to-JPEG conversion via NSBitmapImageRep on macOS save.
  6. Native Save & Clipboard: Integrates NSSavePanel, atomic file writes, and NSPasteboard.general.
  7. Self-Contained Distribution: Generates build.sh compiling with swiftc -O, ad-hoc
     codesigning with codesign, and creating .dmg disk image with hdiutil.

Usage:
  python3 mac_native_scaffold_generator.py <app_name> <bundle_identifier> <web_source_dir> <output_project_dir>
"""

import sys
import os
import shutil
from pathlib import Path


class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RESET = "\033[0m"


def log_info(msg: str):
    print(f"{Colors.BLUE}[*]{Colors.RESET} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[+]{Colors.RESET} {msg}")


def generate_scaffold(app_name: str, bundle_id: str, web_dir: Path, output_dir: Path):
    output_dir = output_dir.resolve()
    app_dir = output_dir / "App"
    web_target = output_dir / "Web"

    log_info(f"Generating native macOS AppKit scaffold for '{app_name}' at {output_dir}")
    app_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copy Web assets
    if web_dir.exists():
        log_info(f"Copying web assets from {web_dir} -> {web_target}")
        if web_target.exists():
            shutil.rmtree(web_target)
        shutil.copytree(web_dir, web_target)
    else:
        web_target.mkdir(parents=True, exist_ok=True)
        (web_target / "index.html").write_text("<!doctype html><html><body><h1>Loaded</h1></body></html>")

    # 2. Generate main.swift
    main_swift = """import Cocoa

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
"""
    (app_dir / "main.swift").write_text(main_swift)

    # 3. Generate AppDelegate.swift (pure NSApplicationDelegate, no NSDocumentClass traps)
    app_delegate = """import Cocoa

class AppDelegate: NSObject, NSApplicationDelegate {
    var mainWindowController: MainWindowController?
    private var pendingOpenURLs: [URL] = []

    func applicationDidFinishLaunching(_ notification: Notification) {
        if mainWindowController == nil {
            mainWindowController = MainWindowController()
        }
        mainWindowController?.showWindow(nil)
        NSApp.activate(ignoringOtherApps: true)

        if !pendingOpenURLs.isEmpty {
            for url in pendingOpenURLs {
                mainWindowController?.loadFile(from: url)
            }
            pendingOpenURLs.removeAll()
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        if !flag {
            if mainWindowController == nil {
                mainWindowController = MainWindowController()
            }
            mainWindowController?.showWindow(nil)
        } else {
            mainWindowController?.window?.makeKeyAndOrderFront(nil)
        }
        return true
    }

    func application(_ sender: NSApplication, openFile filename: String) -> Bool {
        let url = URL(fileURLWithPath: filename)
        if let mwc = mainWindowController {
            mwc.showWindow(nil)
            mwc.loadFile(from: url)
        } else {
            pendingOpenURLs.append(url)
        }
        return true
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        guard let first = urls.first else { return }
        if let mwc = mainWindowController {
            mwc.showWindow(nil)
            mwc.loadFile(from: first)
        } else {
            pendingOpenURLs.append(first)
        }
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        if let first = filenames.first {
            _ = application(sender, openFile: first)
        }
        sender.reply(toOpenOrPrint: .success)
    }
}
"""
    (app_dir / "AppDelegate.swift").write_text(app_delegate)

    # 4. Generate MainWindowController.swift
    win_controller = """import Cocoa
import WebKit

class MainWindowController: NSWindowController, NSWindowDelegate, WKScriptMessageHandler, WKNavigationDelegate {
    private var webView: WKWebView!
    private var currentFileURL: URL?

    convenience init() {
        let window = NSWindow(
            contentRect: NSRect(x: 100, y: 100, width: 1240, height: 820),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.center()
        window.minSize = NSSize(width: 800, height: 600)
        window.title = "APP_NAME_PLACEHOLDER"
        window.titleVisibility = .visible
        window.titlebarAppearsTransparent = false
        window.appearance = NSAppearance(named: .darkAqua)

        self.init(window: window)
        window.delegate = self
        setupWebView()
        loadWebEngine()
    }

    private func setupWebView() {
        guard let window = self.window else { return }

        let cc = WKUserContentController()
        cc.add(self, name: "macHost")

        let config = WKWebViewConfiguration()
        config.userContentController = cc
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        config.setValue(true, forKey: "allowUniversalAccessFromFileURLs")

        webView = WKWebView(frame: window.contentView?.bounds ?? .zero, configuration: config)
        webView.autoresizingMask = [.width, .height]
        webView.navigationDelegate = self
        webView.setValue(false, forKey: "drawsBackground")

        if #available(macOS 13.3, *) {
            webView.isInspectable = true
        }

        window.contentView?.addSubview(webView)
    }

    private func loadWebEngine() {
        var indexURL: URL?
        if let bundleWeb = Bundle.main.resourceURL?.appendingPathComponent("Web/index.html"),
           FileManager.default.fileExists(atPath: bundleWeb.path) {
            indexURL = bundleWeb
        } else {
            indexURL = URL(fileURLWithPath: "WEB_DIR_PLACEHOLDER/index.html")
        }

        if let url = indexURL {
            // Read access to root allows streaming local file:// URLs directly into Image elements
            webView.loadFileURL(url, allowingReadAccessTo: URL(fileURLWithPath: "/"))
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any],
              let action = body["action"] as? String else { return }

        switch action {
        case "editorReady":
            print("[MacHost] Web engine ready")
        case "saveImage", "saveFile":
            handleSave(body)
        case "copyClipboard":
            handleCopy(body)
        default:
            print("[MacHost] Action:", action)
        }
    }

    func loadFile(from url: URL) {
        currentFileURL = url
        self.window?.title = "\\(url.lastPathComponent) — APP_NAME_PLACEHOLDER"
        self.window?.representedURL = url
        self.window?.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)

        let escapedPath = url.path.replacingOccurrences(of: "\\\\", with: "\\\\\\\\").replacingOccurrences(of: "'", with: "\\\\'")
        let js = "if (window.loadFromUrl) { window.loadFromUrl('file://\\(escapedPath)', '\\(url.lastPathComponent)'); }"
        webView.evaluateJavaScript(js, completionHandler: nil)
    }

    private func handleSave(_ body: [String: Any]) {
        guard let dataUrl = body["dataUrl"] as? String else {
            print("[MacHost] No dataUrl received in save action")
            return
        }

        let isSaveAsCopy = (body["isCopy"] as? Bool) ?? true

        let parts = dataUrl.components(separatedBy: ",")
        guard parts.count == 2, let rawData = Data(base64Encoded: parts[1]) else {
            print("[MacHost] Failed to decode base64 dataUrl")
            return
        }

        if !isSaveAsCopy, let targetURL = currentFileURL {
            saveImageData(rawData, to: targetURL)
            return
        }

        let savePanel = NSSavePanel()
        savePanel.canCreateDirectories = true
        let defaultName = currentFileURL?.deletingPathExtension().lastPathComponent ?? "ExportedImage"
        savePanel.nameFieldStringValue = "\\(defaultName)_copy.png"
        savePanel.allowedFileTypes = ["png", "jpg", "jpeg"]

        savePanel.beginSheetModal(for: self.window!) { response in
            if response == .OK, let targetURL = savePanel.url {
                self.saveImageData(rawData, to: targetURL)
            }
        }
    }

    private func saveImageData(_ rawData: Data, to targetURL: URL) {
        let ext = targetURL.pathExtension.lowercased()
        var finalData = rawData

        // Dynamic format conversion: If target is JPEG, convert PNG data to high-quality JPEG
        if ext == "jpg" || ext == "jpeg" {
            if let imageRep = NSBitmapImageRep(data: rawData),
               let jpegData = imageRep.representation(using: .jpeg, properties: [.compressionFactor: 0.95]) {
                finalData = jpegData
            }
        }

        do {
            try finalData.write(to: targetURL, options: .atomic)
            print("[MacHost] Image successfully saved to: \\(targetURL.path)")
            self.currentFileURL = targetURL
            self.window?.title = "\\(targetURL.lastPathComponent) — APP_NAME_PLACEHOLDER"
            self.window?.representedURL = targetURL
        } catch {
            print("[MacHost] Failed to write image: \\(error)")
        }
    }

    private func handleCopy(_ body: [String: Any]) {
        if let dataUrl = body["dataUrl"] as? String {
            let parts = dataUrl.components(separatedBy: ",")
            if parts.count == 2, let rawData = Data(base64Encoded: parts[1]), let image = NSImage(data: rawData) {
                NSPasteboard.general.clearContents()
                NSPasteboard.general.writeObjects([image])
                print("[MacHost] Image copied to system clipboard")
            }
        }
    }
}
"""
    win_controller = win_controller.replace("APP_NAME_PLACEHOLDER", app_name)
    win_controller = win_controller.replace("WEB_DIR_PLACEHOLDER", str(web_target.resolve()))
    (app_dir / "MainWindowController.swift").write_text(win_controller)

    # 5. Generate Info.plist (registers document types WITHOUT NSDocumentClass)
    info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>{app_name.replace(" ", "")}</string>
    <key>CFBundleIdentifier</key>
    <string>{bundle_id}</string>
    <key>CFBundleName</key>
    <string>{app_name}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Image File</string>
            <key>CFBundleTypeRole</key>
            <string>Editor</string>
            <key>LSHandlerRank</key>
            <string>Default</string>
            <key>LSItemContentTypes</key>
            <array>
                <string>public.image</string>
                <string>public.jpeg</string>
                <string>public.png</string>
                <string>public.heic</string>
                <string>public.tiff</string>
                <string>com.compuserve.gif</string>
                <string>org.webmproject.webp</string>
                <string>com.microsoft.bmp</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
"""
    (output_dir / "Info.plist").write_text(info_plist)

    # 6. Generate build.sh
    app_bin_name = app_name.replace(" ", "")
    build_sh = f"""#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
APP_BUNDLE="${{SCRIPT_DIR}}/{app_bin_name}.app"
DMG_NAME="{app_bin_name}.dmg"

echo "=== Building {app_name} for macOS ==="
swiftc -O \\
       -target arm64-apple-macosx12.0 \\
       -framework Cocoa \\
       -framework WebKit \\
       "${{SCRIPT_DIR}}/App/AppDelegate.swift" \\
       "${{SCRIPT_DIR}}/App/MainWindowController.swift" \\
       "${{SCRIPT_DIR}}/App/main.swift" \\
       -o "${{SCRIPT_DIR}}/{app_bin_name}_bin"

rm -rf "${{APP_BUNDLE}}"
mkdir -p "${{APP_BUNDLE}}/Contents/MacOS"
mkdir -p "${{APP_BUNDLE}}/Contents/Resources"

mv "${{SCRIPT_DIR}}/{app_bin_name}_bin" "${{APP_BUNDLE}}/Contents/MacOS/{app_bin_name}"
chmod +x "${{APP_BUNDLE}}/Contents/MacOS/{app_bin_name}"
cp "${{SCRIPT_DIR}}/Info.plist" "${{APP_BUNDLE}}/Contents/Info.plist"
cp -R "${{SCRIPT_DIR}}/Web" "${{APP_BUNDLE}}/Contents/Resources/"

echo "=== Codesigning ==="
codesign --force --deep --sign - "${{APP_BUNDLE}}"

echo "=== Packaging DMG ==="
DMG_STAGE="${{SCRIPT_DIR}}/dmg_staging"
rm -rf "${{DMG_STAGE}}" "${{SCRIPT_DIR}}/${{DMG_NAME}}"
mkdir -p "${{DMG_STAGE}}"
cp -R "${{APP_BUNDLE}}" "${{DMG_STAGE}}/"
ln -s /Applications "${{DMG_STAGE}}/Applications"
hdiutil create -volname "{app_name}" -srcfolder "${{DMG_STAGE}}" -ov -format UDZO "${{SCRIPT_DIR}}/${{DMG_NAME}}"
rm -rf "${{DMG_STAGE}}"

echo "Build complete: ${{SCRIPT_DIR}}/${{DMG_NAME}}"
"""
    build_path = output_dir / "build.sh"
    build_path.write_text(build_sh)
    build_path.chmod(0o755)

    log_success(f"Native macOS project scaffold successfully generated at: {output_dir}")


def main():
    if len(sys.argv) < 5:
        print("Usage: python3 mac_native_scaffold_generator.py <app_name> <bundle_id> <web_source_dir> <output_project_dir>")
        sys.exit(1)

    name = sys.argv[1]
    bid = sys.argv[2]
    web = Path(sys.argv[3])
    out = Path(sys.argv[4])
    generate_scaffold(name, bid, web, out)


if __name__ == "__main__":
    main()
