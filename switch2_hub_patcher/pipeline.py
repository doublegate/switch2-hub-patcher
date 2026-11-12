"""Patch pipelines: stock image in, patched image out, every step hash-checked.

Each step refuses any input other than the exact expected image and the result
must match the hash of the image that was tested on hardware. A mismatch means
a different firmware version or a different assembler output; nothing is
written in that case.
"""
import hashlib

from . import (build_target_candidate, patch_identity_pd3, patch_identity_vid,
               patch_power_15v, patch_query02, patch_rtd2142_hdr_avi, patch_versions)

VL103_STOCK = '3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3'
RTD2142_STOCK = '17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802'

# (name, builder, expected output SHA-256). Order matters: each step requires
# the exact output of the previous one.
VL103_STEPS = (
    ('responder: Nintendo SVID, modes and echo replies', build_target_candidate.build_candidate,
     'f1c75dbdf48dd806c003b180fda88813d2256400e46e8e9f9619c0b0047015ee'),
    ('power: 15 V / 2.8 A offer (hub reserve 7 W -> 3 W)', patch_power_15v.build_candidate,
     '2f59a358e1cd847cbf6aa96a5ba28037cb9287d2d1bef18683ef886b15a79e60'),
    ('identity: Nintendo VID', patch_identity_vid.build_candidate,
     'c5cff89182e83862b342e63a0adfcecab3213ce141f6b383b8e608f8a9721a2c'),
    ('identity: official dock PD3 Discover Identity', patch_identity_pd3.build_candidate,
     '6ab038bd2dd0bf008e2ffe73b5d237c46cfee17be8ae701f78096aeea9da3beb'),
    ('query 02 reply', patch_query02.build_candidate,
     '844d20eb4155e8b5db542d91a6faaa4a00ebebf17b03f8e7bfcacc3bfb8d3d09'),
    ('query 04/06 version replies', patch_versions.build_candidate,
     '6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e'),
)
RTD2142_STEPS = (
    ('HDMI AVI InfoFrame: BT.2020 when PQ/HLG HDR metadata is present',
     lambda image: patch_rtd2142_hdr_avi.build(image),
     'f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1'),
)


class PatchError(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(image, stock_sha, steps, log=print):
    if sha256(image) != stock_sha:
        raise PatchError(f'input SHA-256 {sha256(image)} is not the supported stock image '
                         f'{stock_sha}')
    for name, builder, expected in steps:
        result = builder(image)
        image = result[0] if isinstance(result, tuple) else result
        got = sha256(image)
        if got != expected:
            raise PatchError(f'step "{name}" produced {got}, expected {expected} '
                             '(different SDCC output?)')
        log(f'  ok  {name}')
    return image


def patch_vl103(image, log=print):
    return run(image, VL103_STOCK, VL103_STEPS, log)


def patch_rtd2142(image, log=print):
    return run(image, RTD2142_STOCK, RTD2142_STEPS, log)


def identify(image):
    known = {VL103_STOCK: 'VL103 stock', VL103_STEPS[-1][2]: 'VL103 patched',
             RTD2142_STOCK: 'RTD2142 stock', RTD2142_STEPS[-1][2]: 'RTD2142 patched'}
    return known.get(sha256(image), 'unknown')
