#!/usr/bin/env python3
"""
mratio_toolkit.py — mRatio Reverse Engineering & Client File Codec Toolkit
Part of the RMaster Cross-Platform Interoperability & Porting Toolkit.

Capabilities:
1. Unpack Confuser v1.9.0.0 protected mRatio.exe into its raw native assembly.
2. Decrypt & parse .mRClient client emulation definition files into structured JSON.
3. Parse and decode .mRLng language localization files.
4. Carve embedded UI PNG assets from extracted resources.

Usage:
    python3 mratio_toolkit.py unpack-exe <mRatio.exe> <output_unpacked.dll>
    python3 mratio_toolkit.py dump-client <client.mRClient> [--json]
    python3 mratio_toolkit.py dump-all-clients <clients_dir> <output_json_dir>
    python3 mratio_toolkit.py dump-lng <lang.mRLng>
"""

import sys
import json
import struct
import hashlib
import zlib
import ctypes
from pathlib import Path


# ---------------------------------------------------------
# 1. Bencode Decoder
# ---------------------------------------------------------
def bdecode(data: bytes):
    """Zero-dependency recursive Bencode decoder."""
    def decode_item(pos: int):
        c = data[pos : pos + 1]
        if c == b'i':
            pos += 1
            end = data.index(b'e', pos)
            return int(data[pos:end]), end + 1
        elif c.isdigit():
            colon = data.index(b':', pos)
            length = int(data[pos:colon])
            start = colon + 1
            return data[start : start + length], start + length
        elif c == b'l':
            pos += 1
            res = []
            while data[pos : pos + 1] != b'e':
                item, pos = decode_item(pos)
                res.append(item)
            return res, pos + 1
        elif c == b'd':
            pos += 1
            res = {}
            while data[pos : pos + 1] != b'e':
                key, pos = decode_item(pos)
                val, pos = decode_item(pos)
                res[key] = val
            return res, pos + 1
        else:
            raise ValueError(f"Unexpected Bencode byte at offset {pos}: {c}")

    val, _ = decode_item(0)
    return val


# ---------------------------------------------------------
# 2. Confuser v1.9.0.0 Binary Assembly Unpacker
# ---------------------------------------------------------
def to_int32(val: int) -> int:
    val = val & 0xFFFFFFFF
    return (val ^ 0x80000000) - 0x80000000


def unpack_mratio_exe(exe_path: Path, out_path: Path) -> Path:
    """Unpacks Confuser v1.9.0.0 outer wrapper from mRatio.exe."""
    data = exe_path.read_bytes()
    res_off = 0x63DC4  # Embedded resource payload in mRatio 5.4.1
    entry_len = struct.unpack_from("<I", data, res_off)[0]
    payload = bytearray(data[res_off + 4 : res_off + 4 + entry_len])

    # Method 2 (.cctor / ResourceResolve) state machine constants
    s1 = to_int32(0xB07588F1)
    s2 = to_int32(0x8AC13692)
    s3 = to_int32(0x885156F9)
    s4 = to_int32(0x574412C3)
    diff1 = to_int32(s3 - s4)
    diff2 = to_int32(s2 - diff1)

    s5 = to_int32(0x985B441F)
    s6 = to_int32(0xB8C5A843)
    s7 = to_int32(0x872D57F7)
    s8 = to_int32(0x1A751354)
    diff3 = to_int32(s7 - s8)
    diff4 = to_int32(s6 - diff3)
    diff5 = to_int32(s5 - diff4)

    s9 = to_int32(0xBB60A2B7)
    s10 = to_int32(0x55118644)
    diff6 = to_int32(s9 - s10)
    x1 = to_int32(diff5 ^ diff6)

    k1 = to_int32(0x356E6703)
    k2 = to_int32(0xDDD3A383)
    k3 = to_int32(0x5B70F43E)
    k4 = to_int32(0x05BB414F)
    k5 = to_int32(0x1618D88C)
    t1 = to_int32(k4 ^ k5)
    t2 = to_int32(k3 ^ t1)
    t3 = to_int32(k2 + t2)
    t4 = to_int32(k1 ^ t3)

    sub1 = to_int32(x1 - t4)
    x2 = to_int32(diff2 ^ sub1)
    loc2 = to_int32(s1 + x2) & 0xFF

    mult_const = 0x000000BD
    mod_const = 0x00000100

    # Execute linear congruential PRNG byte XOR cipher
    for i in range(len(payload)):
        payload[i] ^= loc2
        prod = to_int32(loc2 * mult_const)
        rem = (abs(prod) % mod_const) * (1 if prod >= 0 else -1)
        loc2 = to_int32(rem) & 0xFF

    # Decompress raw Deflate stream
    decomp = zlib.decompress(payload, -15)
    asm_len = struct.unpack_from("<I", decomp, 0)[0]
    asm_bytes = decomp[4 : 4 + asm_len]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(asm_bytes)
    return out_path


# ---------------------------------------------------------
# 3. .mRClient Decryptor (TripleDES-CBC + MD5 PBKDF)
# ---------------------------------------------------------
CLIENT_IV_V5 = bytes([0xD2, 0xBC, 0x19, 0x84, 0xA0, 0xD5, 0x99, 0x46])
CLIENT_IV_LEGACY = bytes([0x18, 0x62, 0xD3, 0x3C, 0x29, 0x00, 0x25, 0xFB])


def decrypt_mrclient(client_path: Path) -> dict:
    """Decrypts an .mRClient file into its inner emulation parameter dictionary."""
    outer = bdecode(client_path.read_bytes())
    author = outer[b'a'].decode('latin1')
    emulation = outer[b'e'].decode('latin1')
    key_str = outer[b'key'].decode('latin1')
    zdata = outer[b'zdata']

    # Handle modern v5.4.0 clients vs legacy clients
    if b'v' in outer:
        version_str = outer[b'v'].decode('latin1')
        concat_str = author + emulation + key_str + version_str
        iv = CLIENT_IV_V5
    else:
        concat_str = author + emulation + key_str
        iv = CLIENT_IV_LEGACY

    md5_hex = hashlib.md5(concat_str.encode('cp1252')).hexdigest()
    key24 = md5_hex[:24].encode('ascii')

    # macOS Native CommonCrypto 3DES Decryption
    lib = ctypes.CDLL('/usr/lib/libSystem.B.dylib')
    kCCDecrypt = 1
    kCCAlgorithm3DES = 2
    kCCOptionPKCS7Padding = 1

    data_out = ctypes.create_string_buffer(len(zdata) + 16)
    data_out_moved = ctypes.c_size_t(0)
    st = lib.CCCrypt(
        kCCDecrypt,
        kCCAlgorithm3DES,
        kCCOptionPKCS7Padding,
        key24, len(key24),
        iv,
        zdata, len(zdata),
        data_out, len(data_out),
        ctypes.byref(data_out_moved)
    )
    if st != 0:
        raise ValueError(f"CommonCrypto 3DES decryption failed with code {st}")

    decrypted_bytes = data_out.raw[: data_out_moved.value]
    inner = bdecode(decrypted_bytes)

    # Format result as clean dictionary
    result = {}
    for k, v in inner.items():
        k_str = k.decode('ascii', errors='ignore')
        if isinstance(v, bytes):
            result[k_str] = v.decode('latin1', errors='replace')
        else:
            result[k_str] = v
    return result


# ---------------------------------------------------------
# 4. .mRLng Language Localization Parser
# ---------------------------------------------------------
def parse_mrlng(lng_path: Path) -> dict:
    """Parses an .mRLng Bencoded language file into a string mapping dictionary."""
    raw = bdecode(lng_path.read_bytes())
    result = {}
    for k, v in raw.items():
        k_str = k.decode('utf-8', errors='ignore')
        if k_str == "lngFlagBitmap":
            result[k_str] = f"<{len(v)} bytes base64 flag>"
        elif isinstance(v, bytes):
            result[k_str] = v.decode('utf-8', errors='replace')
        else:
            result[k_str] = v
    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "unpack-exe" and len(sys.argv) >= 4:
        inp = Path(sys.argv[2])
        out = Path(sys.argv[3])
        res = unpack_mratio_exe(inp, out)
        print(f"[+] Successfully unpacked {inp.name} -> {res} ({res.stat().st_size} bytes)")

    elif cmd == "dump-client" and len(sys.argv) >= 3:
        client_file = Path(sys.argv[2])
        dec = decrypt_mrclient(client_file)
        if "--json" in sys.argv:
            print(json.dumps(dec, indent=2))
        else:
            print(f"=== {client_file.name} ===")
            for k, v in sorted(dec.items()):
                print(f"  {k}: {v}")

    elif cmd == "dump-all-clients" and len(sys.argv) >= 4:
        inp_dir = Path(sys.argv[2])
        out_dir = Path(sys.argv[3])
        out_dir.mkdir(parents=True, exist_ok=True)
        count = 0
        for f in sorted(inp_dir.glob("*.mRClient")):
            try:
                dec = decrypt_mrclient(f)
                out_json = out_dir / f"{f.stem}.json"
                out_json.write_text(json.dumps(dec, indent=2), encoding='utf-8')
                print(f"[+] Decrypted: {f.name} -> {out_json.name}")
                count += 1
            except Exception as e:
                print(f"[-] Failed {f.name}: {e}")
        print(f"[+] Finished. Decrypted {count} client profiles to {out_dir}")

    elif cmd == "dump-lng" and len(sys.argv) >= 3:
        lng_file = Path(sys.argv[2])
        strings = parse_mrlng(lng_file)
        print(f"=== {lng_file.name} ({len(strings)} strings) ===")
        for k in sorted(strings.keys(), key=lambda x: int(x) if x.isdigit() else 9999):
            if k in ["lngName", "lngAuthor", "lngEncoding"] or (k.isdigit() and int(k) < 20):
                print(f"  [{k}] {strings[k]}")

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
