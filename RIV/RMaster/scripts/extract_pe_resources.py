#!/usr/bin/env python3
"""
extract_pe_resources.py — Embedded Image & XML Resource Carver
Part of the RMaster Cross-Platform Interoperability & Porting Toolkit.

Scans binary files (PE .exe/.dll, Mach-O, or resource blobs) for embedded PNG,
JPEG, and XML payloads and extracts them for reference inspection.

Usage:
    python3 extract_pe_resources.py <binary_path> <output_dir>
"""

import struct
import sys
from pathlib import Path


PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


def extract_pngs(data: bytes, out_dir: Path, prefix: str):
    pos = 0
    count = 0
    while True:
        idx = data.find(PNG_MAGIC, pos)
        if idx < 0:
            break
        end_idx = data.find(PNG_IEND, idx)
        if end_idx < 0:
            break
        end_idx += len(PNG_IEND)
        png_bytes = data[idx:end_idx]

        # Read IHDR width x height
        if len(png_bytes) >= 24:
            w, h = struct.unpack(">II", png_bytes[16:24])
            out_file = out_dir / f"{prefix}_png_{count:03d}_{w}x{h}.png"
        else:
            out_file = out_dir / f"{prefix}_png_{count:03d}.png"

        out_file.write_bytes(png_bytes)
        print(f"  [+] Extracted PNG: {out_file.name} ({len(png_bytes)} bytes)")
        count += 1
        pos = end_idx
    return count


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 extract_pe_resources.py <binary_path> <output_dir>")
        sys.exit(1)

    bin_path = Path(sys.argv[1]).expanduser().resolve()
    out_dir = Path(sys.argv[2]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    data = bin_path.read_bytes()
    print(f"[*] Scanning {bin_path.name} ({len(data)} bytes) for embedded resources...")
    total_pngs = extract_pngs(data, out_dir, bin_path.stem)
    print(f"[*] Done. Extracted {total_pngs} PNG image(s) to {out_dir}")


if __name__ == "__main__":
    main()
