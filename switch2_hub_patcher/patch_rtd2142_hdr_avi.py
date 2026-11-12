#!/usr/bin/env python3
"""OFFLINE candidate: RTD2142 HDMI AVI uses BT.2020 when PQ/HLG metadata is present.

Builds from the hash-guarded original 2 MiB dump; changes bank 2 only. Never
touches hardware. The output is a candidate for review, not an approved image.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ASM = Path(__file__).resolve().parent / 'asm'
BASE_SHA = '17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802'
SOURCE = ASM / 'rtd2142_hdr_avi.asm'
BANK = 2
BANK_BASE = BANK * 0x10000
REGION = (0xff80, 0xfff0)                      # inside the FF padding, above sim trampoline
# (bank-2 address, original bytes, symbol, opcode)
HOOKS = (
    (0xf390, bytes.fromhex('12 b9 f6'), 'avi_wrap', 0x12),   # lcall b9f6
    (0xf31f, bytes.fromhex('12 4a e7'), 'hdr_enable', 0x02),  # lcall 4ae7 (orl;movx;ret)
    (0xf326, bytes.fromhex('12 4a e7'), 'hdr_disable', 0x02),  # lcall 4ae7 (movx;ret)
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    with tempfile.TemporaryDirectory(prefix='rtd-hdr-avi-') as tmp:
        tmp = Path(tmp)
        shutil.copyfile(SOURCE, tmp / 'p.asm')
        for cmd in (['sdas8051', '-losg', 'p.asm'], ['sdld', '-n', '-i', 'p.rel']):
            r = subprocess.run(cmd, cwd=tmp, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=30)
            if r.returncode:
                raise RuntimeError(r.stdout)
        memory = {}
        for line in (tmp / 'p.ihx').read_text().split():
            rec = bytes.fromhex(line[1:])
            if sum(rec) & 255:
                raise ValueError('bad HEX checksum')
            n, addr, kind = rec[0], int.from_bytes(rec[1:3], 'big'), rec[3]
            if kind == 0:
                for i, b in enumerate(rec[4:4 + n]):
                    if not REGION[0] <= addr + i < REGION[1] or addr + i in memory:
                        raise ValueError(f'overlay outside region at {addr + i:04x}')
                    memory[addr + i] = b
        symbols = {}
        text = (tmp / 'p.sym').read_text()
        for m in re.finditer(r'(\w+)\s+([0-9A-Fa-f]{6})\s+GR\b', text):
            symbols[m[1]] = int(m[2], 16)   # sdas truncates names to 8 chars
        return memory, symbols


def build(base):
    if len(base) != 0x200000 or sha(base) != BASE_SHA:
        raise ValueError('requires the exact original RTD2142 dump')
    if base[BANK_BASE + REGION[0]:BANK_BASE + REGION[1]] != b'\xff' * (REGION[1] - REGION[0]):
        raise ValueError('patch region not erased')
    memory, symbols = assemble()
    image = bytearray(base)
    hooks = []
    for at, old, symbol, opcode in HOOKS:
        if base[BANK_BASE + at:BANK_BASE + at + 3] != old:
            raise ValueError(f'hook mismatch at {at:04x}')
        target = symbols[symbol[:8]]
        new = bytes([opcode, target >> 8, target & 255])
        image[BANK_BASE + at:BANK_BASE + at + 3] = new
        hooks.append(dict(bank=BANK, address=f'{at:04x}', old=old.hex(), new=new.hex(),
                          target=symbol))
    for addr, b in memory.items():
        image[BANK_BASE + addr] = b
    image = bytes(image)
    changed = [i for i in range(len(base)) if base[i] != image[i]]
    allowed = {BANK_BASE + a for a in memory}
    for at, *_ in HOOKS:
        allowed |= set(range(BANK_BASE + at, BANK_BASE + at + 3))
    if not set(changed) <= allowed:
        raise ValueError('unexpected footprint')
    manifest = dict(
        experiment='rtd2142-hdr-avi-bt2020-v1', base_sha256=BASE_SHA, output_sha256=sha(image),
        source_sha256=sha(SOURCE.read_bytes()), size_bytes=len(image),
        changed_byte_count=len(changed), banks_changed=sorted({i >> 16 for i in changed}),
        hooks=hooks, overlay=dict(bank=BANK, start=f'{min(memory):04x}',
                                  end=f'{max(memory):04x}', bytes=len(memory)),
        symbols={k: f'{v:04x}' for k, v in symbols.items()},
        behaviour='HDMI port (5Bxx engine): when logical-port-1 HDR metadata (E362 bit1) has '
                  'EOTF PQ/HLG (DD9F&7 in 2,3), every AVI InfoFrame build sets C=3/EC=6 and '
                  'fixes the checksum; AVI is rebuilt when the HDR packet is enabled or disabled.',
        unchanged=['DP transmitter and 56xx engine', 'pixel path / CSC / colour caches',
                   'DPCD, EDID, startup, all other banks'],
        hardware_validated=False, flash_approved=False,
        recovery='external SOIC-8 clip programmer + original dump')
    return image, manifest
