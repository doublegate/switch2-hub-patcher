"""Synthetic stand-ins for the stock images, for offline tests of the builders.

They contain no vendor code: pseudo-random filler with only the guarded hook bytes
and erased caves the builders check. The builders' SHA-256 guards are pointed at
these images with unittest.mock, so the whole chain (hooks, caves, overlays, CRC,
footprint checks) runs without a real dump.
"""

import hashlib
import random
from contextlib import ExitStack
from unittest import mock

from switch2_hub_patcher import (
    build_target_candidate,
    patch_identity_pd3,
    patch_identity_vid,
    patch_power_15v,
    patch_query02,
    patch_rtd2142_hdr_avi,
    patch_svid,
    patch_versions,
)
from switch2_hub_patcher.vl103_crc import crc16_usb


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _filler(size, seed):
    rng = random.Random(seed)
    return bytearray(rng.randrange(0, 0xFF) for _ in range(size))  # never 0xFF


def vl103_image():
    image = _filler(0x8000, 'vl103')
    image[0x7000:0x7FFE] = b'\xff' * (0x7FFE - 0x7000)
    image[patch_svid.TABLE_OFFSET : patch_svid.TABLE_OFFSET + 8] = patch_svid.OLD_TABLE
    at = patch_svid.NDO_INSTRUCTION
    image[at : at + 5] = patch_svid.OLD_NDO_CALL
    for address, old, _, _ in build_target_candidate.HOOKS:
        image[address : address + len(old)] = old
    image[patch_power_15v.HOOK : patch_power_15v.HOOK + 3] = patch_power_15v.OLD
    for address, old, _ in patch_identity_vid.REDIRECTS:
        image[address : address + 3] = old
    image[patch_identity_pd3.HOOK : patch_identity_pd3.HOOK + 5] = patch_identity_pd3.OLD
    image[-2:] = crc16_usb(bytes(image[:-2])).to_bytes(2, 'little')
    return bytes(image)


def rtd2142_image():
    image = _filler(0x200000, 'rtd2142')
    base = patch_rtd2142_hdr_avi.BANK_BASE
    lo, hi = patch_rtd2142_hdr_avi.REGION
    image[base + lo : base + hi] = b'\xff' * (hi - lo)
    for at, old, _, _ in patch_rtd2142_hdr_avi.HOOKS:
        image[base + at : base + at + 3] = old
    return bytes(image)


VL103_CHAIN = (
    (patch_svid, 'STOCK_SHA256', build_target_candidate.build_candidate),
    (patch_power_15v, 'BASE_SHA', patch_power_15v.build_candidate),
    (patch_identity_vid, 'BASE_SHA', patch_identity_vid.build_candidate),
    (patch_identity_pd3, 'BASE_SHA', patch_identity_pd3.build_candidate),
    (patch_query02, 'BASE_SHA', patch_query02.build_candidate),
    (patch_versions, 'BASE_SHA', patch_versions.build_candidate),
)


def run_vl103_chain(image):
    """Return [(image, manifest), ...] for the six VL103 steps on a synthetic image."""
    results = []
    with ExitStack() as stack:
        for module, attribute, builder in VL103_CHAIN:
            stack.enter_context(mock.patch.object(module, attribute, sha(image)))
            image, manifest = builder(image)
            results.append((image, manifest))
    return results


def run_rtd2142(image):
    with mock.patch.object(patch_rtd2142_hdr_avi, 'BASE_SHA', sha(image)):
        return patch_rtd2142_hdr_avi.build(image)
