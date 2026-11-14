"""CANDIDATE: fix the RTD2142 HDR -> SDR picture-format bugs (stock firmware).

After an HDR -> SDR switch the stock firmware keeps describing the picture with the HDR
format: the DP side's format check never notices that the source moved its colorimetry
from the VSC SDP back to MSA MISC0, so the HDMI AVI InfoFrame keeps saying BT.2020; and
the HDMI side leaves the 12-bit colour depth in 5B07. Both were read on a live chip
while the TV kept re-detecting (research/DP_HDR_AND_VRR.md).

Builds from the hash-guarded stock dump; changes banks 2 and 5 only. Never touches
hardware. The output is a candidate until it is tested on a hub.
"""

import hashlib

from . import hexfile

BASE_SHA = '17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802'
BANK_SIZE = 0x10000
# (asm module, bank, overlay region, hooks: (address, original bytes, symbol))
PARTS = (
    (
        'rtd2142_rx2_colorimetry',
        5,
        (0xFD80, 0xFDC0),
        ((0xC476, bytes.fromhex('90 b4 03'), 'rx2_fmt_check'),),
    ),
    (
        'rtd2142_hdmi_deep_color',
        2,
        (0xFF00, 0xFF40),
        ((0xE952, bytes.fromhex('90 5b 06'), 'hdmi_deep_color_off'),),
    ),
)
LJMP = 0x02


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    """{(bank, address): byte} for every overlay, plus {symbol: (bank, address)}."""
    memory, symbols = {}, {}
    for name, bank, region, _ in PARTS:
        part, syms = hexfile.assemble_with_symbols(name, (region,))
        memory.update({(bank, at): b for at, b in part.items()})
        symbols.update({s: (bank, at) for s, at in syms.items()})
    return memory, symbols


def build(base):
    if len(base) != 0x200000 or sha(base) != BASE_SHA:
        raise ValueError('requires the exact original RTD2142 dump')
    memory, symbols = assemble()
    image = bytearray(base)
    hooks = []
    allowed = set()
    for name, bank, (lo, hi), part_hooks in PARTS:
        start = bank * BANK_SIZE
        if base[start + lo : start + hi] != b'\xff' * (hi - lo):
            raise ValueError(f'patch region {bank}:{lo:04x} not erased')
        for at, old, symbol in part_hooks:
            if base[start + at : start + at + 3] != old:
                raise ValueError(f'hook mismatch at {bank}:{at:04x}')
            target_bank, target = symbols[symbol[:8]]
            if target_bank != bank:
                raise ValueError(f'{symbol} is not in bank {bank}')
            new = bytes([LJMP, target >> 8, target & 0xFF])
            image[start + at : start + at + 3] = new
            allowed |= set(range(start + at, start + at + 3))
            hooks.append(
                {
                    'bank': bank,
                    'address': f'{at:04x}',
                    'old': old.hex(),
                    'new': new.hex(),
                    'target': symbol,
                    'module': name,
                }
            )
    for (bank, at), b in memory.items():
        image[bank * BANK_SIZE + at] = b
        allowed.add(bank * BANK_SIZE + at)
    image = bytes(image)
    changed = [i for i in range(len(base)) if base[i] != image[i]]
    if not set(changed) <= allowed:
        raise ValueError('unexpected footprint')
    manifest = {
        'experiment': 'rtd2142-sdr-fix-v1',
        'base_sha256': BASE_SHA,
        'output_sha256': sha(image),
        'source_sha256': {
            name: sha((hexfile.ASM / f'{name}.asm').read_bytes()) for name, *_ in PARTS
        },
        'size_bytes': len(image),
        'changed_byte_count': len(changed),
        'banks_changed': sorted({i // BANK_SIZE for i in changed}),
        'hooks': hooks,
        'symbols': {s: f'{bank}:{at:04x}' for s, (bank, at) in symbols.items()},
        'behaviour': 'DP RX stream 2: when MSA MISC1 bit 6 is clear but the cached format came '
        'from the VSC SDP (flag 0x2E), the format check reports a change so the firmware '
        're-captures from MISC0 (AVI colorimetry follows); HDMI TX: the 8-bit branch of '
        'hdmi_set_deep_color also clears 5B07[7:4] (dp_color_depth).',
        'unchanged': [
            'HDR packet forwarding, AVI builder, DP transmitter',
            'streams 1, 3 and 4, DPCD, EDID, startup, all other banks',
        ],
        'hardware_validated': False,
        'recovery': 'rtd-flash back to the stock dump, or an external SOIC-8 clip programmer',
    }
    return image, manifest
