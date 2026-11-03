#!/usr/bin/env python3
"""
unpack_installer.py — Universal Multi-Stage Installer Unpacker & Classifier
Part of the RMaster Cross-Platform Interoperability & Porting Toolkit.

Unpacks Windows (.msi, .cab, .zip), macOS (.pkg, .dmg), or archive packages
and classifies extracted files (executables, XML layouts, SQLite DBs, fonts, resources).

Usage:
    python3 unpack_installer.py <installer_path> <output_dir>
"""

import os
import sys
import subprocess
from pathlib import Path


def run_cmd(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def unpack_file(installer_path: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = installer_path.suffix.lower()

    print(f"[*] Unpacking {installer_path.name} -> {output_dir}")
    if ext in (".msi", ".cab", ".zip", ".7z", ".exe"):
        res = run_cmd(["7z", "x", "-y", str(installer_path), f"-o{output_dir}"])
        if res.returncode != 0:
            print(f"[!] 7z warning/error: {res.stderr.strip()}")
    elif ext == ".pkg":
        res = run_cmd(["pkgutil", "--expand-full", str(installer_path), str(output_dir / "expanded_pkg")])
        if res.returncode != 0:
            print(f"[!] pkgutil error: {res.stderr.strip()}")

    # Second pass: unpack any nested .cab archives extracted from .msi
    for item in list(output_dir.rglob("*")):
        if item.is_file() and (item.suffix.lower() == ".cab" or "cab" in item.name.lower()):
            cab_out = output_dir / f"{item.name}_unpacked"
            if not cab_out.exists():
                print(f"[*] Unpacking nested archive: {item.name} -> {cab_out}")
                run_cmd(["7z", "x", "-y", str(item), f"-o{cab_out}"])


def classify_directory(output_dir: Path):
    print("\n=== Extracted Artifact Classification ===")
    categories = {
        "PE / Executables / Libraries": [],
        "XML / JSON / Configs": [],
        "Fonts (TTF / OTF)": [],
        "Databases / Binary Blobs": [],
        "Other Files": [],
    }

    for f in sorted(output_dir.rglob("*")):
        if not f.is_file():
            continue
        res = run_cmd(["file", "-b", str(f)])
        desc = res.stdout.strip()
        rel = f.relative_to(output_dir)

        if any(k in desc for k in ("PE32", "Mach-O", "ELF", "executable", "DLL")):
            categories["PE / Executables / Libraries"].append((rel, desc))
        elif any(k in desc for k in ("XML", "JSON", "ASCII text", "UTF-8 text")):
            categories["XML / JSON / Configs"].append((rel, desc))
        elif any(k in desc for k in ("TrueType", "OpenType", "font")):
            categories["Fonts (TTF / OTF)"].append((rel, desc))
        elif any(k in desc for k in ("SQLite", "database", "Cabinet")):
            categories["Databases / Binary Blobs"].append((rel, desc))
        else:
            categories["Other Files"].append((rel, desc))

    for cat, items in categories.items():
        if items:
            print(f"\n[{cat}] ({len(items)} files)")
            for rel, desc in items[:40]:
                print(f"  - {rel}: {desc}")
            if len(items) > 40:
                print(f"  ... and {len(items) - 40} more")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 unpack_installer.py <installer_path> <output_dir>")
        sys.exit(1)

    installer_path = Path(sys.argv[1]).expanduser().resolve()
    output_dir = Path(sys.argv[2]).expanduser().resolve()

    if not installer_path.exists():
        print(f"Error: {installer_path} does not exist.")
        sys.exit(1)

    unpack_file(installer_path, output_dir)
    classify_directory(output_dir)


if __name__ == "__main__":
    main()
