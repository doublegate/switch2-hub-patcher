"""OFFLINE coherent PD3 identity-reply experiment. No device access/flashing.

Returns the observed official PD3 reply, not USB identity or hardware capability
certification. Legacy PD2 uses the unchanged v4 path. Other behavior stays v4.
"""

import hashlib

from . import hexfile
from .vl103_crc import crc16_usb, stored_and_computed

BASE_SHA = 'c5cff89182e83862b342e63a0adfcecab3213ce141f6b383b8e608f8a9721a2c'
HOOK = 0x251F
OLD = bytes.fromhex('7f 05 12 58 76')
NEW = bytes.fromhex('02 7c 40 00 00')
REGIONS = ((0x7C40, 0x7C80), (0x7D00, 0x7D20))
BODY = bytes.fromhex('7e 05 60 54 00 00 00 00 00 00 62 20 31 00 00 65 00 00 00 00')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    memory = hexfile.assemble('identity_pd3', REGIONS, required=(0x7C40,))
    if bytes(memory.get(a, 255) for a in range(0x7D00, 0x7D14)) != BODY:
        raise ValueError('unexpected captured identity body')
    return memory


def build_candidate(base):
    if len(base) != 0x8000 or sha(base) != BASE_SHA:
        raise ValueError('requires exact v4 VID-only image')
    if stored_and_computed(base)[0] != stored_and_computed(base)[1]:
        raise ValueError('invalid base CRC')
    if base[HOOK : HOOK + 5] != OLD:
        raise ValueError('identity header-builder hook mismatch')
    for lo, hi in REGIONS:
        if base[lo:hi] != b'\xff' * (hi - lo):
            raise ValueError('identity CODE region not erased')
    overlay = assemble()
    image = bytearray(base)
    image[HOOK : HOOK + 5] = NEW
    for at, byte in overlay.items():
        image[at] = byte
    image[-2:] = crc16_usb(image[:-2]).to_bytes(2, 'little')
    image = bytes(image)
    changed = [i for i, (a, b) in enumerate(zip(base, image)) if a != b]
    allowed = set(overlay) | set(range(HOOK, HOOK + 5)) | {0x7FFE, 0x7FFF}
    if len(image) != 0x8000 or not set(changed) <= allowed:
        raise ValueError('unexpected identity footprint')
    stored, computed = stored_and_computed(image)
    if stored != computed:
        raise ValueError('candidate CRC mismatch')
    return image, {
        'experiment': 'vl103-native-responder-v5-pd3-identity',
        'base_sha256': BASE_SHA,
        'output_sha256': sha(image),
        'size_bytes': len(image),
        'source_sha256': sha((hexfile.ASM / 'identity_pd3.asm').read_bytes()),
        'crc16_usb': f'0x{stored:04X}',
        'hook': {'offset': HOOK, 'old': OLD.hex(), 'new': NEW.hex()},
        'overlay_bytes': len(overlay),
        'pd3_identity_ndo': 6,
        'pd3_identity_vdos': [
            'FF00A041',
            '5460057E',
            '00000000',
            '20620000',
            '65000031',
            '00000000',
        ],
        'pd2_identity': 'unchanged v4 AMA/VID057E reply',
        'native_resume_pd3': 0x2579,
        'native_resume_pd2': 0x2524,
        'new_xdata_bytes': 0,
        'additional_call_frame_bytes': 0,
        'hardware_validated': False,
        'flashed': False,
        'recovery_verified': False,
        'unchanged': [
            'USB/updater CODE1000..100F metadata and descriptors',
            'DP capabilities/status/configuration and native GPIO/power paths',
            'v3 power reservation and Nintendo responder/control hooks',
        ],
        'limits': [
            'PD identity diagnostic, NOT USB identity change or hardware certification.',
            'Copies the observed PD3 identity tuple together; does not isolate its individual fields.',
            'Reuses stock builders and inherits shared-scratch/IRQ and native arbitration limits.',
            'Retains unmeasured3W hub headroom; USB ports must stay empty.',
            'Recovery and full physical SPI coverage remain unverified; no automatic flash.',
        ],
        'changes': [{'offset': i, 'old': base[i], 'new': image[i]} for i in changed],
    }
