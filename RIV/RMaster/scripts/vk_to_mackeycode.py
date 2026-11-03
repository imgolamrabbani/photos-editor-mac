#!/usr/bin/env python3
"""
vk_to_mackeycode.py — Windows Virtual-Key (VK_*) to macOS CGKeyCode Translator
Part of the RMaster Cross-Platform Interoperability & Porting Toolkit.

Converts Windows VK_* integer codes (e.g. from XML keyboard layout definitions)
into native macOS Carbon/Quartz CGKeyCode constants and generates ready-to-compile
Swift dictionary definitions.

Usage:
    python3 vk_to_mackeycode.py [optional_layout.xml]
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Complete Windows VK_* to macOS CGKeyCode hardware mapping table
VK_TO_CGKEYCODE = {
    # Digits 0-9
    48: (29, "0"),
    49: (18, "1"),
    50: (19, "2"),
    51: (20, "3"),
    52: (21, "4"),
    53: (23, "5"),
    54: (22, "6"),
    55: (26, "7"),
    56: (28, "8"),
    57: (25, "9"),
    # Letters A-Z
    65: (0, "A"),
    66: (11, "B"),
    67: (8, "C"),
    68: (2, "D"),
    69: (14, "E"),
    70: (3, "F"),
    71: (5, "G"),
    72: (4, "H"),
    73: (34, "I"),
    74: (38, "J"),
    75: (40, "K"),
    76: (37, "L"),
    77: (46, "M"),
    78: (45, "N"),
    79: (31, "O"),
    80: (35, "P"),
    81: (12, "Q"),
    82: (15, "R"),
    83: (1, "S"),
    84: (17, "T"),
    85: (32, "U"),
    86: (9, "V"),
    87: (13, "W"),
    88: (7, "X"),
    89: (16, "Y"),
    90: (6, "Z"),
    # OEM Punctuation Keys
    186: (41, "Semicolon (;)"),
    187: (24, "Equals (=)"),
    188: (43, "Comma (,)"),
    189: (27, "Minus (-)"),
    190: (47, "Period (.)"),
    191: (44, "Slash (/)"),
    192: (50, "Grave (`)"),
    219: (33, "LeftBracket ([)"),
    220: (42, "Backslash (\\)"),
    221: (30, "RightBracket (])"),
    222: (39, "Quote (')"),
}


def print_table():
    print("// Windows VK_* -> macOS CGKeyCode Mapping Table")
    for vk, (cg, label) in sorted(VK_TO_CGKEYCODE.items()):
        print(f"// VK {vk:3d} ({label:16s}) -> CGKeyCode {cg:2d}")


def convert_xml_layout(xml_path: Path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    print(f"// Converted from {xml_path.name}")
    print("let keyMap: [UInt16: (normal: String, shift: String)] = [")
    for detail in root.findall(".//Detail"):
        vk_text = detail.findtext("KeyCode", "0").strip()
        n_text = detail.findtext("Normal", "") or ""
        s_text = detail.findtext("Shift", "") or ""
        vk = int(vk_text)
        if vk in VK_TO_CGKEYCODE:
            cg, label = VK_TO_CGKEYCODE[vk]
            print(f'    {cg:2d}: ({n_text!r}, {s_text!r}), // VK {vk} ({label})')
    print("]")


def main():
    if len(sys.argv) > 1:
        convert_xml_layout(Path(sys.argv[1]).expanduser().resolve())
    else:
        print_table()


if __name__ == "__main__":
    main()
