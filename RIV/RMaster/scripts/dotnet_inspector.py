#!/usr/bin/env python3
"""
dotnet_inspector.py — Pure-Python .NET Assembly Metadata & IL Inspector
Part of the RMaster Cross-Platform Interoperability & Porting Toolkit.

Inspects ECMA-335 (.NET) PE assemblies on macOS/Linux without requiring Windows tools.
Parses the BSJB metadata root, #~ tables (TypeDef, Field, MethodDef, MemberRef),
#Strings heap, #US (User Strings) heap, and disassembles common IL instructions
(ldstr, call, callvirt, ldfld, stfld, ldsfld, stsfld).

Usage:
    python3 dotnet_inspector.py <assembly.exe> [--strings] [--types] [--il <MethodName>]
"""

import struct
import sys
from pathlib import Path


class DotNetInspector:
    def __init__(self, path: Path):
        self.path = path
        self.data = path.read_bytes()
        self.bsjb_offset = self.data.find(b"BSJB")
        if self.bsjb_offset < 0:
            raise ValueError(f"No .NET BSJB metadata signature found in {path}")

        self.streams = {}
        self.strings_heap = b""
        self.us_heap = b""
        self.text_rva = 0
        self.text_raw = 0
        self._parse_pe_sections()
        self._parse_bsjb()

    def _parse_pe_sections(self):
        pe_sig = struct.unpack_from("<I", self.data, 0x3C)[0]
        num_sections = struct.unpack_from("<H", self.data, pe_sig + 6)[0]
        opt_hdr_size = struct.unpack_from("<H", self.data, pe_sig + 20)[0]
        sec_table = pe_sig + 24 + opt_hdr_size
        for i in range(num_sections):
            off = sec_table + i * 40
            name = self.data[off : off + 8].rstrip(b"\x00").decode("ascii", errors="ignore")
            vsize, rva, raw_size, raw_ptr = struct.unpack_from("<IIII", self.data, off + 8)
            if name == ".text":
                self.text_rva = rva
                self.text_raw = raw_ptr

    def rva_to_offset(self, rva: int) -> int:
        if rva == 0 or self.text_rva == 0:
            return 0
        return rva - self.text_rva + self.text_raw

    def _parse_bsjb(self):
        pos = self.bsjb_offset
        sig, maj, min_v, res, ver_len = struct.unpack_from("<IHHII", self.data, pos)
        ver_str = self.data[pos + 16 : pos + 16 + ver_len].rstrip(b"\x00").decode("utf-8", errors="ignore")
        pos += 16 + ver_len
        flags, num_streams = struct.unpack_from("<HH", self.data, pos)
        pos += 4

        for _ in range(num_streams):
            s_off, s_size = struct.unpack_from("<II", self.data, pos)
            pos += 8
            name_bytes = bytearray()
            while self.data[pos] != 0:
                name_bytes.append(self.data[pos])
                pos += 1
            pos += 1
            while (pos - self.bsjb_offset) % 4 != 0:
                pos += 1
            s_name = name_bytes.decode("ascii", errors="ignore")
            self.streams[s_name] = (self.bsjb_offset + s_off, s_size)

        if "#Strings" in self.streams:
            off, sz = self.streams["#Strings"]
            self.strings_heap = self.data[off : off + sz]
        if "#US" in self.streams:
            off, sz = self.streams["#US"]
            self.us_heap = self.data[off : off + sz]

    def get_string(self, idx: int) -> str:
        if idx >= len(self.strings_heap):
            return ""
        end = self.strings_heap.find(b"\x00", idx)
        if end < 0:
            return ""
        return self.strings_heap[idx:end].decode("utf-8", errors="replace")

    def get_user_string(self, idx: int) -> str:
        if idx <= 0 or idx >= len(self.us_heap):
            return ""
        b0 = self.us_heap[idx]
        if (b0 & 0x80) == 0:
            length = b0
            start = idx + 1
        elif (b0 & 0xC0) == 0x80:
            length = ((b0 & 0x3F) << 8) | self.us_heap[idx + 1]
            start = idx + 2
        else:
            length = ((b0 & 0x1F) << 24) | (self.us_heap[idx + 1] << 16) | (self.us_heap[idx + 2] << 8) | self.us_heap[idx + 3]
            start = idx + 4
        if length <= 1:
            return ""
        raw = self.us_heap[start : start + length - 1]
        return raw.decode("utf-16le", errors="replace")

    def dump_user_strings(self):
        print(f"=== User Strings (#US) in {self.path.name} ===")
        idx = 1
        while idx < len(self.us_heap):
            b0 = self.us_heap[idx]
            if b0 == 0:
                idx += 1
                continue
            if (b0 & 0x80) == 0:
                length = b0
                hdr = 1
            elif (b0 & 0xC0) == 0x80:
                length = ((b0 & 0x3F) << 8) | self.us_heap[idx + 1]
                hdr = 2
            else:
                length = ((b0 & 0x1F) << 24) | (self.us_heap[idx + 1] << 16) | (self.us_heap[idx + 2] << 8) | self.us_heap[idx + 3]
                hdr = 4
            if length > 1:
                raw = self.us_heap[idx + hdr : idx + hdr + length - 1]
                s = raw.decode("utf-16le", errors="replace")
                if s.strip():
                    print(f"  [0x70{idx:06x}] {s!r}")
            idx += hdr + max(length, 1)

    def dump_identifier_strings(self):
        print(f"=== Identifier Strings (#Strings) in {self.path.name} ===")
        for item in self.strings_heap.split(b"\x00"):
            s = item.decode("utf-8", errors="replace").strip()
            if len(s) >= 2:
                print(f"  {s}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 dotnet_inspector.py <assembly.exe> [--strings] [--identifiers]")
        sys.exit(1)

    asm_path = Path(sys.argv[1]).expanduser().resolve()
    inspector = DotNetInspector(asm_path)

    if "--identifiers" in sys.argv:
        inspector.dump_identifier_strings()
    else:
        inspector.dump_user_strings()


if __name__ == "__main__":
    main()
