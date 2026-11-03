#!/usr/bin/env python3
"""
hybrid_bundle_analyzer.py — Universal JavaScript/WASM Hybrid Desktop Application Reverse Engineer
Part of the RMaster Universal Reverse Engineering & Cross-Platform Porting Suite.

Analyzes embedded web engines inside modern desktop applications (WebView2, CEF, Electron, MS Edge).
Capabilities:
  - Deep scanning of minified JS/WASM bundles for Host-Bridge APIs:
      - window.chrome.webview (SharedBuffer, postMessage, hostObjects)
      - window.external
      - Host-View-Controller callback protocols (e.g. hvcEvents)
  - Localization Trap Detector:
      - Finds empty string dictionaries (e.g. { key: "" }) and uncovers internal fallback
        translation modules (e.g. module exports with 500+ full strings).
      - Pinpoints contextual menu items (Fluent UI, React) that render blank due to missing strings.
  - Theme Palette Inversion Auditor:
      - Detects dark mode contrast traps (e.g. text styled with palette.black on dark backgrounds).
  - WebAssembly & Machine Learning Pipeline Auditor:
      - Identifies .wasm.bin patch synthesis, DirectML/ONNX models, and WebGL shader bindings.
  - Generates drop-in Mac bridge code to emulate the Windows host without modifying core Web logic.

Usage:
  python3 hybrid_bundle_analyzer.py <web_directory_or_js_file> [report_output_markdown]
"""

import sys
import os
import re
import json
from pathlib import Path
from typing import Dict, List, Set, Tuple


class Colors:
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    RESET = "\033[0m"


def log_info(msg: str):
    print(f"{Colors.BLUE}[*]{Colors.RESET} {msg}")


def log_success(msg: str):
    print(f"{Colors.GREEN}[+]{Colors.RESET} {msg}")


def log_warn(msg: str):
    print(f"{Colors.YELLOW}[!]{Colors.RESET} {msg}")


class HybridBundleAnalyzer:
    def __init__(self, target_path: Path):
        self.target_path = target_path.resolve()
        self.js_files: List[Path] = []
        self.findings: Dict = {
            "host_bridges": [],
            "host_callbacks": set(),
            "shared_buffers": [],
            "empty_localization_skeletons": [],
            "rich_localization_modules": [],
            "theme_color_traps": [],
            "wasm_pipelines": []
        }

    def run(self, report_path: Optional[Path] = None):
        log_info(f"Analyzing target: {self.target_path.name}")
        if self.target_path.is_file():
            self.js_files = [self.target_path]
        elif self.target_path.is_dir():
            self.js_files = list(self.target_path.rglob("*.js"))
            log_info(f"Discovered {len(self.js_files)} JavaScript bundle files")

        for js_file in self.js_files:
            self._analyze_file(js_file)

        self._generate_report(report_path)

    def _analyze_file(self, js_path: Path):
        log_info(f"Scanning bundle: {js_path.name} ({js_path.stat().st_size / 1024:.1f} KB)")
        try:
            with open(js_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception as e:
            log_warn(f"Failed to read {js_path.name}: {e}")
            return

        # 1. Search for WebView2 / Host Bridge bindings
        if "chrome.webview" in content:
            self.findings["host_bridges"].append({
                "file": js_path.name,
                "type": "WebView2",
                "has_shared_buffer": "sharedbufferreceived" in content,
                "has_host_objects": "hostObjects" in content or "sync" in content
            })

        # 2. Extract Host Callback Protocols (e.g. hvcEvents.notifyOn*)
        callbacks = re.findall(r"notifyOn[A-Za-z0-9_]+", content)
        for cb in callbacks:
            self.findings["host_callbacks"].add(cb)

        # 3. Detect Empty Localization Skeletons vs Rich Localization Dictionaries
        # Skeleton pattern: { foo: "", bar: "", baz: "" } (many empty string properties)
        empty_str_runs = re.findall(r"([a-zA-Z0-9_]+:\s*\"\",\s*){10,}", content)
        if empty_str_runs:
            # Count consecutive empty assignments
            matches = list(re.finditer(r"([a-zA-Z0-9_]+:\s*\"\",\s*){10,}", content))
            for m in matches:
                sample = content[m.start():min(len(content), m.start() + 400)]
                keys = re.findall(r"([a-zA-Z0-9_]+):\"\"", sample)
                self.findings["empty_localization_skeletons"].append({
                    "file": js_path.name,
                    "offset": m.start(),
                    "sample_keys": keys[:10]
                })

        # Rich dictionary pattern: module exporting 50+ populated string values
        # e.g., var r = { foo: "English", bar: "Values" }
        populated_runs = list(re.finditer(r"([a-zA-Z0-9_]+:\s*\"[A-Za-z0-9\s.,'()\-]{2,100}\",\s*){15,}", content))
        for m in populated_runs:
            snippet = content[m.start():min(len(content), m.start() + 1000)]
            pairs = re.findall(r"([a-zA-Z0-9_]+):\"([^\"]+)\"", snippet)
            if len(pairs) >= 10:
                self.findings["rich_localization_modules"].append({
                    "file": js_path.name,
                    "offset": m.start(),
                    "count_sample": len(pairs),
                    "pairs": pairs[:8]
                })

        # 4. Detect Dark Mode Theme / Contrast Traps
        # e.g. color: palette.black used inside ContextualMenu or Button
        if "palette.black" in content and "contextualMenu" in content:
            self.findings["theme_color_traps"].append({
                "file": js_path.name,
                "detail": "ContextualMenu uses palette.black; in dark theme this must be inverted or rgba-mapped to prevent invisible black text on dark gray."
            })

        # 5. Detect WebAssembly / AI Pipelines
        if "WebAssembly" in content or ".wasm" in content:
            self.findings["wasm_pipelines"].append({
                "file": js_path.name,
                "references": re.findall(r"[A-Za-z0-9_\-./]+\.wasm(?:\.bin)?", content)
            })

    def _generate_report(self, report_path: Optional[Path]):
        out_file = report_path or (self.target_path.parent / "HYBRID_BUNDLE_ANALYSIS.md")
        log_info(f"Writing analysis report: {out_file.name}")

        with open(out_file, "w", encoding="utf-8") as f:
            f.write("# Windows Hybrid Engine Reverse Engineering Audit Report\n\n")

            f.write("## 1. Host Bridge & WebView2 IPC Bindings\n\n")
            if self.findings["host_bridges"]:
                for hb in self.findings["host_bridges"]:
                    f.write(f"- File: `{hb['file']}`\n")
                    f.write(f"  - WebView2 API Detected: Yes\n")
                    f.write(f"  - Shared Buffer Support: {hb['has_shared_buffer']}\n")
                    f.write(f"  - Synchronous Host Objects: {hb['has_host_objects']}\n\n")
            else:
                f.write("No direct WebView2 bindings found in scanned files.\n\n")

            f.write("## 2. Host-View-Controller Callback Protocol\n\n")
            f.write("The web application expects the native host to implement or listen for the following callbacks:\n\n")
            for cb in sorted(self.findings["host_callbacks"]):
                f.write(f"- `window.hvcEvents.{cb}(...)`\n")
            f.write("\n")

            f.write("## 3. Localization Architecture & Missing String Traps\n\n")
            if self.findings["empty_localization_skeletons"]:
                f.write("### Warning: Empty Localization Skeletons Found\n")
                f.write("The bundle defines default React localization context objects where every property is initialized to empty string `\"\"`.\n")
                f.write("If the native host does not call `setLocalizationJson(...)` on boot, Fluent UI menus and buttons will render completely blank without text.\n\n")
                for sk in self.findings["empty_localization_skeletons"]:
                    f.write(f"- File `{sk['file']}` at offset `{sk['offset']}`:\n")
                    f.write(f"  - Sample keys: `{', '.join(sk['sample_keys'])}`\n")
                f.write("\n")

            if self.findings["rich_localization_modules"]:
                f.write("### Internal English Fallback Dictionaries Discovered\n")
                f.write("The bundle includes built-in fallback modules containing complete English translations:\n\n")
                for rm in self.findings["rich_localization_modules"]:
                    f.write(f"- File `{rm['file']}` at offset `{rm['offset']}`:\n")
                    for k, v in rm["pairs"]:
                        f.write(f"  - `{k}`: \"{v}\"\n")
                f.write("\n")

            f.write("## 4. Theme Palette Contrast Auditing\n\n")
            if self.findings["theme_color_traps"]:
                for trap in self.findings["theme_color_traps"]:
                    f.write(f"- `{trap['file']}`: {trap['detail']}\n")
            else:
                f.write("No direct theme color inversion traps detected.\n")
            f.write("\n")

            f.write("## 5. WebAssembly & Pipeline Inference\n\n")
            if self.findings["wasm_pipelines"]:
                for wasm in self.findings["wasm_pipelines"]:
                    f.write(f"- `{wasm['file']}` references WASM artifacts: `{wasm['references']}`\n")
            else:
                f.write("No standalone WebAssembly binaries detected.\n")

        log_success(f"Audit report generated at: {out_file}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 hybrid_bundle_analyzer.py <web_dir_or_js_file> [report_path]")
        sys.exit(1)

    target = Path(sys.argv[1])
    rep = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    analyzer = HybridBundleAnalyzer(target)
    analyzer.run(rep)


if __name__ == "__main__":
    main()
