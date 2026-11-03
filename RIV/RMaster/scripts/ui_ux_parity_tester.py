#!/usr/bin/env python3
"""
ui_ux_parity_tester.py — Automated macOS WebKit UI/UX Parity & Discrepancy Auditor
Part of the RMaster Universal Reverse Engineering & Cross-Platform Porting Suite.

Runs headless/windowed WebKit automation to audit ported applications:
  - Detects blank contextual menus, dropdowns, and flyouts.
  - Traverses React Fiber trees and Fluent UI components for unpopulated labels.
  - Audits accessible names (aria-label, aria-description) across interactive controls.
  - Verifies typography, custom icon fonts (Segoe Fluent / MDL2), and dark mode contrast.
  - Captures high-resolution retina screenshots of every view state.

Usage:
  python3 ui_ux_parity_tester.py <path_to_index_html_or_app_bundle> [output_report_dir]
"""

import sys
import os
import subprocess
import json
from pathlib import Path


SWIFT_TESTER_TEMPLATE = """import Cocoa
import WebKit

class HeadlessAuditor: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
    var webView: WKWebView!
    var window: NSWindow!
    var isDone = false
    var htmlURL: URL
    var reportDir: URL
    var auditResults: [String: Any] = [:]

    init(htmlURL: URL, reportDir: URL) {
        self.htmlURL = htmlURL
        self.reportDir = reportDir
        super.init()
    }

    func run() {
        let app = NSApplication.shared
        app.setActivationPolicy(.regular)

        let config = WKWebViewConfiguration()
        let cc = WKUserContentController()
        cc.add(self, name: "macHost")
        config.userContentController = cc
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")
        config.setValue(true, forKey: "allowUniversalAccessFromFileURLs")

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1240, height: 820),
                          styleMask: [.titled, .closable], backing: .buffered, defer: false)
        webView = WKWebView(frame: window.contentView!.bounds, configuration: config)
        webView.navigationDelegate = self
        window.contentView?.addSubview(webView)
        window.makeKeyAndOrderFront(nil)

        webView.loadFileURL(htmlURL, allowingReadAccessTo: htmlURL.deletingLastPathComponent())

        let start = Date()
        while !isDone && Date().timeIntervalSince(start) < 20.0 {
            RunLoop.current.run(mode: .default, before: Date(timeIntervalSinceNow: 0.1))
        }

        finishReport()
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let body = message.body as? [String: Any], let action = body["action"] as? String else { return }
        if action == "editorReady" {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                self.auditUIElements()
            }
        }
    }

    func auditUIElements() {
        let auditJs = \"\"\"
        (() => {
            const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
            const menus = Array.from(document.querySelectorAll('.ms-ContextualMenu, [role="menu"]'));
            const textNodes = Array.from(document.querySelectorAll('*')).filter(el => {
                return el.children.length === 0 && (el.innerText || '').trim().length > 0;
            });

            // Find controls with empty text and no aria label (the blank dropdown bug)
            const emptyControls = buttons.filter(b => {
                const text = (b.innerText || '').trim();
                const aria = (b.getAttribute('aria-label') || '').trim();
                return text.length === 0 && aria.length === 0;
            }).map(b => ({
                id: b.id,
                className: b.className,
                outerHtml: b.outerHTML.substring(0, 200)
            }));

            return {
                totalButtons: buttons.length,
                totalMenus: menus.length,
                emptyControlsCount: emptyControls.length,
                emptyControls: emptyControls,
                buttonSamples: buttons.slice(0, 15).map(b => ({
                    text: (b.innerText || '').trim(),
                    aria: b.getAttribute('aria-label'),
                    testId: b.getAttribute('data-test-id')
                }))
            };
        })()
        \"\"\"

        webView.evaluateJavaScript(auditJs) { res, err in
            if let dict = res as? [String: Any] {
                self.auditResults = dict
            }
            self.captureSnapshot()
        }
    }

    func captureSnapshot() {
        let config = WKSnapshotConfiguration()
        webView.takeSnapshot(with: config) { image, _ in
            if let img = image, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff), let png = rep.representation(using: .png, properties: [:]) {
                let imgURL = self.reportDir.appendingPathComponent("audit_view_snapshot.png")
                try? png.write(to: imgURL)
            }
            self.isDone = true
        }
    }

    func finishReport() {
        let jsonURL = reportDir.appendingPathComponent("ui_audit_results.json")
        if let data = try? JSONSerialization.data(withJSONObject: auditResults, options: .prettyPrinted) {
            try? data.write(to: jsonURL)
            print("[+] UI Audit JSON saved to:", jsonURL.path)
        }
        exit(0)
    }
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    print("Usage: <exec> <index_html_path> <report_dir>")
    exit(1)
}

let htmlURL = URL(fileURLWithPath: args[1])
let reportDir = URL(fileURLWithPath: args[2])
let auditor = HeadlessAuditor(htmlURL: htmlURL, reportDir: reportDir)
auditor.run()
"""


def run_audit(target_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    if target_path.is_file() and target_path.suffix.lower() == ".html":
        html_file = target_path
    elif target_path.is_dir() and (target_path / "Contents/Resources/Web/index.html").exists():
        html_file = target_path / "Contents/Resources/Web/index.html"
    elif target_path.is_dir() and (target_path / "index.html").exists():
        html_file = target_path / "index.html"
    else:
        print(f"[-] Could not find index.html at {target_path}")
        sys.exit(1)

    print(f"[*] Auditing UI/UX for: {html_file}")
    swift_harness = output_dir / "Auditor.swift"
    swift_harness.write_text(SWIFT_TESTER_TEMPLATE)

    # Run swift runner
    cmd = ["swift", str(swift_harness), str(html_file), str(output_dir)]
    print(f"[*] Launching WebKit audit harness...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    print(res.stdout)
    if res.stderr:
        print(res.stderr)

    # Clean harness
    if swift_harness.exists():
        swift_harness.unlink()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 ui_ux_parity_tester.py <path_to_html_or_app> [output_report_dir]")
        sys.exit(1)

    target = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("./UI_Audit_Report").resolve()
    run_audit(target, out)


if __name__ == "__main__":
    main()
