#!/usr/bin/env python3
"""OFFLINE VID-only diagnostic on the exact v3-15V image. Never flashes a device.

Redirect ONLY the PD Discover Identity builder's two VID CODE reads. Do not edit
USB/update metadata, product type, other identity VDOs, DP, power or responders.
This tests a hypothesis, not a full official-dock identity or compatibility fix.
"""
import argparse
import hashlib
import json
from pathlib import Path
from .vl103_crc import crc16_usb, stored_and_computed

ASM = Path(__file__).resolve().parent / 'asm'
BASE_SHA = '2f59a358e1cd847cbf6aa96a5ba28037cb9287d2d1bef18683ef886b15a79e60'
CONSTANT = 0x7c00
VID = bytes.fromhex('7e 05')
REDIRECTS = (
    (0x2539, bytes.fromhex('90 10 07'), bytes.fromhex('90 7c 00')),
    (0x2542, bytes.fromhex('90 10 08'), bytes.fromhex('90 7c 01')),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build_candidate(base):
    if len(base) != 0x8000 or sha(base) != BASE_SHA:
        raise ValueError('requires exact native responder v3-15v image')
    if stored_and_computed(base)[0] != stored_and_computed(base)[1]:
        raise ValueError('base CRC invalid')
    if base[CONSTANT:CONSTANT+2] != b'\xff\xff':
        raise ValueError('VID constant cave not erased')
    for address, old, _ in REDIRECTS:
        if base[address:address+3] != old:
            raise ValueError(f'identity instruction mismatch at {address:#x}')
    image = bytearray(base)
    for address, _, new in REDIRECTS:
        image[address:address+3] = new
    image[CONSTANT:CONSTANT+2] = VID
    image[-2:] = crc16_usb(image[:-2]).to_bytes(2, 'little')
    image = bytes(image)
    changed = [i for i, (old, new) in enumerate(zip(base, image)) if old != new]
    allowed = {CONSTANT, CONSTANT+1, 0x7ffe, 0x7fff}
    for address, _, _ in REDIRECTS:
        allowed.update((address+1, address+2))
    if len(image) != 0x8000 or not set(changed) <= allowed:
        raise ValueError('unexpected VID-only footprint')
    stored, computed = stored_and_computed(image)
    if stored != computed:
        raise ValueError('VID-only CRC mismatch')
    return image, {
        'experiment': 'vl103-native-responder-v4-vid',
        'base_sha256': BASE_SHA,
        'output_sha256': sha(image),
        'size_bytes': len(image),
        'crc16_usb': f'0x{stored:04X}',
        'constant_offset': CONSTANT,
        'constant_bytes': VID.hex(),
        'redirects': [{'offset': at, 'old': old.hex(), 'new': new.hex()}
                      for at, old, new in REDIRECTS],
        'expected_rev3_id_header_before': '0x6C602109',
        'expected_rev3_id_header_after': '0x6C60057E',
        'changed_semantic_field': 'USB VID in PD Discover Identity ACK only',
        'hardware_validated': False, 'flashed': False, 'recovery_verified': False,
        'new_executable_bytes': 0, 'new_xdata_bytes': 0, 'extra_stack_bytes': 0,
        'unchanged': [
            'Original CODE1000..100F USB/update metadata and version',
            'PD identity product type AMA, Cert Stat, PID/bcdDevice and AMA VDO',
            'Identity reply NDO and high ID-header bits',
            'USB controller/hub descriptors and VID/PID metadata',
            'SVIDs, DP capability/status/configuration, v3 power policy and all PDOs',
            'Nintendo responder, source/reset/boot hooks and error/ready handling',
        ],
        'limits': [
            'VID causality is unproven; this is NOT the full official-dock identity.',
            'Normal-SOP routing, mode-bit/CODE-cave, stack/IRQ and recovery assumptions are inherited.',
            'Retains unmeasured v3 3W hub reservation at eligible15V; keep USB ports empty.',
            'Existing VID table at685D is overwritten at runtime; metadata1007/1008 is deliberately NOT edited.',
            'No automatic installation or live USB/device operations in this builder.',
        ],
        'changes': [{'offset': i, 'old': base[i], 'new': image[i]} for i in changed],
    }
