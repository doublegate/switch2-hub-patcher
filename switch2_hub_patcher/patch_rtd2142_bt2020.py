"""CANDIDATE: RTD2142 HDMI AVI says BT.2020 for HDR, stacked on SDR-fix v7b.

Reworks the upstream BT.2020 patch (patch_rtd2142_hdr_avi) so it can be applied on top of
SDR-fix v7b and only claims what the TV accepts:

- an AVI InfoFrame the stock builder already marked extended colorimetry (C = 3, any EC,
  including the version-4 EC = 7 form) is left exactly as built;
- C = 3 / EC = 6 is written only while the source sends HDR metadata with a PQ or HLG
  EOTF, and only when the sink's EDID Colorimetry Data Block lists BT.2020 for the pixel
  encoding being sent (BT2020_RGB for RGB, BT2020_YCC for YCbCr);
- the decision is re-made on every HDR metadata update and the AVI is rebuilt when it
  changes, so an output restart that built the AVI before the new metadata was current is
  corrected.

Builds from the hash-guarded SDR-fix v7b image; changes bank 2 only. Never touches
hardware. The output is a candidate until it is tested on a hub.
"""

import hashlib

from . import hexfile

BASE_SHA = '4a39d09511603c6c2947003b9fbf3dd58612622c5932f1b22e8af4f2e69bfd24'  # SDR-fix v7b
SOURCE = hexfile.ASM / 'rtd2142_bt2020_avi.asm'
MODULE = 'rtd2142_bt2020_avi'
BANK = 2
BANK_BASE = BANK * 0x10000
REGION = (0xFF36, 0x10000)  # above v7b's hdmi_drm_enable_guard (FF20..FF34)
LCALL, LJMP = 0x12, 0x02
# (bank-2 address, bytes in the v7b image, symbol, opcode)
HOOKS = (
    (0xF390, bytes.fromhex('12 b9 f6'), 'avi_wrap', LCALL),  # lcall hdmi_build_avi
    (0xF31F, bytes.fromhex('02 ff 20'), 'drm_on', LJMP),  # v7b: ljmp hdmi_drm_enable_guard
    (0xF326, bytes.fromhex('12 4a e7'), 'drm_off', LJMP),  # lcall 4ae7 (movx; ret)
)
FLAG = 0xE9F1  # XDATA state byte; unreferenced by the stock firmware


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    return hexfile.assemble_with_symbols(MODULE, (REGION,))


def build(base):
    if len(base) != 0x200000 or sha(base) != BASE_SHA:
        raise ValueError('requires the exact RTD2142 SDR-fix v7b image')
    lo, hi = REGION
    if base[BANK_BASE + lo : BANK_BASE + hi] != b'\xff' * (hi - lo):
        raise ValueError(f'patch region {BANK}:{lo:04x} not erased')
    memory, symbols = assemble()
    image = bytearray(base)
    hooks = []
    allowed = {BANK_BASE + a for a in memory}
    for at, old, symbol, opcode in HOOKS:
        if base[BANK_BASE + at : BANK_BASE + at + 3] != old:
            raise ValueError(f'hook mismatch at {BANK}:{at:04x}')
        target = symbols[symbol[:8]]
        new = bytes([opcode, target >> 8, target & 0xFF])
        image[BANK_BASE + at : BANK_BASE + at + 3] = new
        allowed |= set(range(BANK_BASE + at, BANK_BASE + at + 3))
        hooks.append(
            {
                'bank': BANK,
                'address': f'{at:04x}',
                'old': old.hex(),
                'new': new.hex(),
                'target': symbol,
                'module': MODULE,
            }
        )
    for at, b in memory.items():
        image[BANK_BASE + at] = b
    image = bytes(image)
    changed = [i for i in range(len(base)) if base[i] != image[i]]
    if not set(changed) <= allowed:
        raise ValueError('unexpected footprint')
    manifest = {
        'experiment': 'rtd2142-sdr-fix-v7b-bt2020-v1',
        'base_sha256': BASE_SHA,
        'output_sha256': sha(image),
        'source_sha256': sha(SOURCE.read_bytes()),
        'size_bytes': len(image),
        'changed_byte_count': len(changed),
        'banks_changed': sorted({i >> 16 for i in changed}),
        'hooks': hooks,
        'overlay': {
            'bank': BANK,
            'start': f'{min(memory):04x}',
            'end': f'{max(memory):04x}',
            'bytes': len(memory),
        },
        'symbols': {k: f'{BANK}:{v:04x}' for k, v in symbols.items()},
        'state': {'xdata': f'{FLAG:04x}', 'bit0': 'AVI marked BT.2020', 'bit1': 'built extended'},
        'behaviour': 'HDMI AVI InfoFrame: when logical-port-1 HDR metadata (E362 bit 1) has a PQ '
        'or HLG EOTF (DD9F[2:0] = 2 or 3), the AVI as built is not already extended colorimetry '
        '(PB2 C != 3), and the sink EDID cached at C600 has a CTA-861 Colorimetry Data Block '
        'listing BT.2020 for the output encoding (E0E6[2:0]: RGB -> BT2020_RGB, YCbCr '
        '4:2:2/4:4:4/4:2:0 -> BT2020_YCC), PB2 C = 3 and PB3 EC = 6 are written and the '
        'checksum is corrected. Re-decided on every hdmi_drm_update pass (HDR packet on or off '
        'path); the AVI is rebuilt (hdmi_pkt_build, builder 0) only when the decision changes.',
        'unchanged': [
            'AVI fields other than C and EC (Y, Q, VIC, ...), and any AVI built extended',
            'SDR-fix v7b (banks 2, 4, 5), HDR packet guard, pixel path, CSC, quantization',
            'DP transmitter, DPCD, EDID content, startup, all other banks',
        ],
        'hardware_validated': False,
        'flash_approved': False,
        'recovery': 'rtd-flash back to SDR-fix v7b or stock; SOIC-8 clip + stock dump',
    }
    return image, manifest
