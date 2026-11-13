"""Build an OFFLINE SVID-only VL103 experiment, never flash a device.

Supports only the exact stock dump in this project. Advertises 057E alongside
FF01; DOES NOT implement Nintendo mode entry or proprietary replies. NOT a
Switch 2 compatibility fix. Hardware recovery has not been demonstrated.
"""

import hashlib

from .vl103_crc import IMAGE_SIZE, crc16_usb, stored_and_computed

STOCK_SHA256 = '3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3'
TABLE_OFFSET = 0x6855
OLD_TABLE = bytes.fromhex('00 00 01 ff 00 00 00 00')
NEW_TABLE = bytes.fromhex('7e 05 01 ff 00 00 00 00')
NDO_INSTRUCTION = 0x25A8  # MOV R7,#2; original SVID reply builder call follows
OLD_NDO_CALL = bytes.fromhex('7f 02 12 58 76')
ALLOWED_OFFSETS = frozenset(
    (TABLE_OFFSET, TABLE_OFFSET + 1, NDO_INSTRUCTION + 1, IMAGE_SIZE - 2, IMAGE_SIZE - 1)
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def build_candidate(original):
    """Return (candidate bytes, manifest), or reject anything but the stock dump."""
    if len(original) != IMAGE_SIZE:
        raise ValueError(f'expected {IMAGE_SIZE:#x} bytes, got {len(original):#x}')
    stored, computed = stored_and_computed(original)
    if stored != computed:
        raise ValueError('input checksum is invalid')
    if original[TABLE_OFFSET : TABLE_OFFSET + len(OLD_TABLE)] != OLD_TABLE:
        raise ValueError('original SVID table does not match expected bytes')
    if original[NDO_INSTRUCTION : NDO_INSTRUCTION + len(OLD_NDO_CALL)] != OLD_NDO_CALL:
        raise ValueError('original SVID reply-count instruction does not match')
    if sha256(original) != STOCK_SHA256:
        raise ValueError('input is not the supported stock image (SHA256 mismatch)')

    patched = bytearray(original)
    patched[TABLE_OFFSET : TABLE_OFFSET + len(NEW_TABLE)] = NEW_TABLE
    # Transmit VDM header + SVID pair + zero terminator, like the official dock.
    patched[NDO_INSTRUCTION + 1] = 3
    patched[-2:] = crc16_usb(patched[:-2]).to_bytes(2, 'little')
    patched = bytes(patched)
    changed = [i for i, (old, new) in enumerate(zip(original, patched)) if old != new]
    if not set(changed) <= ALLOWED_OFFSETS or not {
        TABLE_OFFSET,
        TABLE_OFFSET + 1,
        NDO_INSTRUCTION + 1,
    } <= set(changed):
        raise ValueError('unexpected patch footprint')
    stored, computed = stored_and_computed(patched)
    if stored != computed:
        raise ValueError('candidate checksum verification failed')
    manifest = {
        'experiment': 'vl103-svid-only-v1',
        'hardware_validated': False,
        'purpose': 'Advertise Nintendo SVID 057E alongside DisplayPort FF01; no responder',
        'warning': 'Incomplete experiment, not a docking fix; recovery unverified; do not auto-flash',
        'input_sha256': STOCK_SHA256,
        'output_sha256': sha256(patched),
        'size_bytes': IMAGE_SIZE,
        'svid_table_offset': TABLE_OFFSET,
        'original_svid_table': OLD_TABLE.hex(),
        'candidate_svid_table': NEW_TABLE.hex(),
        'svid_reply_ndo': {
            'operand_offset': NDO_INSTRUCTION + 1,
            'old': 2,
            'new': 3,
            'reason': 'Include existing zero terminator VDO as in official captures',
        },
        'original_crc16_usb': f'0x{int.from_bytes(original[-2:], "little"):04X}',
        'candidate_crc16_usb': f'0x{int.from_bytes(patched[-2:], "little"):04X}',
        'changes': [
            {
                'offset': i,
                'offset_hex': f'0x{i:04X}',
                'old': f'{original[i]:02X}',
                'new': f'{patched[i]:02X}',
            }
            for i in changed
        ],
        'unchanged': [
            'control flow',
            'identity',
            'DP capabilities',
            'power profiles',
            'image size',
        ],
    }
    return patched, manifest
