"""Decode a Realtek RTDTool register database (DB.bin) into register and field lines.

Usage: python3 -I research/rtd_db_dump.py DB.bin > fields.txt

Output: "ADDR NAME" per register, then "    [hi:lo] field -- description" per field.
Layout (reverse engineered from the RTD2172 DB in roufsweb/portable-display):
  string pool base 0xf499c; register record = u32 kind, u32 name_ptr, u32 addr, u32 addr;
  field marker word 0x052aHHLL (bits HH:LL), name_ptr 12 bytes before it, description
  pointer 16 bytes after. Other chips' databases may use a different pool base.
"""
import re
import struct
import sys
from pathlib import Path

BASE = 0xF499C


def main(path):
    data = Path(path).read_bytes()

    def string(offset):
        at = BASE + offset
        if offset >= len(data) or at >= len(data):
            return b''
        return data[at:data.find(b'\0', at)]

    registers = []
    for at in range(0x24C, BASE - 16, 4):
        _, name_ptr, a1, a2 = struct.unpack_from('<IIII', data, at)
        if a1 == a2 and 0x100 <= a1 <= 0xFFFF and name_ptr < len(data):
            name = string(name_ptr)
            if name and re.fullmatch(rb'[A-Za-z][A-Za-z0-9_]{2,48}', name):
                registers.append((at, a1, name))
    for i, (at, address, name) in enumerate(registers):
        end = registers[i + 1][0] if i + 1 < len(registers) else at + 600
        print(f'{address:04X} {name.decode()}')
        for f in range(at + 8, end - 20, 4):
            (word,) = struct.unpack_from('<I', data, f)
            if word >> 16 == 0x052A:
                field = string(struct.unpack_from('<I', data, f - 12)[0])
                desc = string(struct.unpack_from('<I', data, f + 16)[0])
                text = desc.decode(errors='replace').replace('\r', ' | ')[:160]
                print(f'    [{(word >> 8) & 0xFF}:{word & 0xFF}] '
                      f'{field.decode(errors="replace")} -- {text}')


if __name__ == '__main__':
    main(sys.argv[1])
