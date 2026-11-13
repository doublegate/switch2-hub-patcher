"""Assemble one patch source with SDCC and load its Intel HEX into a guarded map."""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ASM = Path(__file__).resolve().parent / 'asm'


def parse_ihx(text, regions, required=()):
    """Return {address: byte} from Intel HEX text.

    Every data byte must fall in one of the half-open (lo, hi) regions and appear
    once; records must be well formed and end with an EOF record; each address in
    required must be present.
    """
    memory = {}
    ended = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if ended or not line.startswith(':'):
            raise ValueError('bad Intel HEX ordering')
        record = bytes.fromhex(line[1:])
        if len(record) < 5 or len(record) != record[0] + 5 or sum(record) & 255:
            raise ValueError('bad Intel HEX checksum/length')
        count, address, kind = record[0], int.from_bytes(record[1:3], 'big'), record[3]
        if kind == 1 and count == 0 and address == 0:
            ended = True
        elif kind == 0:
            for offset, byte in enumerate(record[4:-1]):
                at = address + offset
                if at in memory or not any(lo <= at < hi for lo, hi in regions):
                    raise ValueError(
                        f'overlay byte at {at:#06x} outside guarded regions or duplicate'
                    )
                memory[at] = byte
        else:
            raise ValueError('unsupported Intel HEX record')
    if not ended:
        raise ValueError('missing Intel HEX EOF record')
    missing = [at for at in required if at not in memory]
    if missing:
        raise ValueError('missing overlay entry ' + ', '.join(f'{at:#06x}' for at in missing))
    return memory


def parse_symbols(text):
    """Global label addresses from an sdas .sym file (names truncated to 8 chars)."""
    return {m[1]: int(m[2], 16) for m in re.finditer(r'(\w+)\s+([0-9A-Fa-f]{6})\s+GR\b', text)}


def assemble(name, regions, required=(), flags='-los'):
    """Assemble asm/<name>.asm with sdas8051 + sdld; return the guarded memory map."""
    return _build(name, regions, required, flags)[0]


def assemble_with_symbols(name, regions, required=(), flags='-losg'):
    """Like assemble(), also returning the global labels of the .sym file."""
    memory, sym_text = _build(name, regions, required, flags)
    return memory, parse_symbols(sym_text)


def _build(name, regions, required, flags):
    with tempfile.TemporaryDirectory(prefix=f's2hub-{name}-') as tmp:
        directory = Path(tmp)
        shutil.copyfile(ASM / f'{name}.asm', directory / f'{name}.asm')
        for command in (['sdas8051', flags, f'{name}.asm'], ['sdld', '-n', '-i', f'{name}.rel']):
            result = subprocess.run(
                command,
                cwd=directory,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
            if result.returncode:
                raise RuntimeError(f'{name}: {command[0]} failed:\n{result.stdout}')
        memory = parse_ihx((directory / f'{name}.ihx').read_text(), regions, required)
        sym = directory / f'{name}.sym'
        return memory, (sym.read_text() if sym.is_file() else '')
