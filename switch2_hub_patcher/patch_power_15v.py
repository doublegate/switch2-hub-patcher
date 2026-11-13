"""Build an OFFLINE 15V-only reservation experiment on the exact v2 candidate.

No USB/device access or flashing. Reallocates budget, not measured hardware
headroom: fixed15V EXACT3A inputs reserve3W, all other profiles stay stock.
"""

import hashlib

from . import hexfile
from .vl103_crc import crc16_usb, stored_and_computed

BASE_SHA = 'f1c75dbdf48dd806c003b180fda88813d2256400e46e8e9f9619c0b0047015ee'
HOOK = 0x339D
OLD = bytes.fromhex('75 14 46')
NEW = bytes.fromhex('12 7b 40')
ENTRY = 0x7B40
END = 0x7C00


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    return hexfile.assemble('power_15v', ((ENTRY, END),), required=(ENTRY,))


def build_candidate(base):
    if len(base) != 0x8000 or sha(base) != BASE_SHA:
        raise ValueError('requires exact native responder v2 image')
    if stored_and_computed(base)[0] != stored_and_computed(base)[1]:
        raise ValueError('base CRC invalid')
    if base[HOOK : HOOK + 3] != OLD:
        raise ValueError('reservation instruction guard failed')
    if base[ENTRY:END] != b'\xff' * (END - ENTRY):
        raise ValueError('power code cave not erased')
    overlay = assemble()
    image = bytearray(base)
    image[HOOK : HOOK + 3] = NEW
    for at, byte in overlay.items():
        image[at] = byte
    image[-2:] = crc16_usb(image[:-2]).to_bytes(2, 'little')
    image = bytes(image)
    changed = [i for i, (old, new) in enumerate(zip(base, image)) if old != new]
    allowed = set(overlay) | set(range(HOOK, HOOK + 3)) | {0x7FFE, 0x7FFF}
    if len(image) != 0x8000 or not set(changed) <= allowed:
        raise ValueError('unexpected power experiment footprint')
    stored, computed = stored_and_computed(image)
    if stored != computed:
        raise ValueError('power experiment CRC failed')
    return image, {
        'experiment': 'vl103-native-responder-v3-15v',
        'base_sha256': BASE_SHA,
        'output_sha256': sha(image),
        'source_sha256': sha((hexfile.ASM / 'power_15v.asm').read_bytes()),
        'size_bytes': len(image),
        'crc16_usb': f'0x{stored:04X}',
        'power_hook': {'offset': HOOK, 'old': OLD.hex(), 'new': NEW.hex()},
        'stub_entry': ENTRY,
        'stub_last': max(overlay),
        'stub_bytes': len(overlay),
        'selector_units_mw': 100,
        'condition': 'fixed PDO, voltage code300 (15V), original current code300 (3A)',
        'eligible_reservation_mw': 3000,
        'original_default_reservation_mw': 7000,
        'eligible_advertised_current_ma': 2800,
        'other_profiles': 'unchanged, including existing 5V cap and 20V <=60W exception',
        'upstream_pdo_rdo': 'unchanged; existing full input-current request retained',
        'analog_protection_registers': 'no direct edits; later native configuration and physical behavior unmeasured',
        'new_xdata_bytes': 0,
        'extra_saved_context_stack_bytes': 6,
        'hardware_validated': False,
        'flashed': False,
        'recovery_verified': False,
        'limits': [
            'Reducing reserve does NOT establish sufficient physical hub self-power headroom.',
            'Keep USB peripherals absent; stop on resets, current limiting, voltage sag or overheating.',
            'Adds a bounded IE-preserving stub; does not fix existing shared-scratch races in native budgeting.',
            'Inherits v2 mode-bit/CODE-cave/native-policy assumptions and unverified recovery.',
            'Does not change identity, DP capabilities, output voltage, upstream current request or other PDOs.',
            'No automatic flash; validate and perform a separately controlled hardware experiment.',
        ],
        'changes': [{'offset': i, 'old': base[i], 'new': image[i]} for i in changed],
    }
