"""Patch pipelines: stock image in, patched image out, every step hash-checked.

Each step refuses any input other than the exact expected image and the result
must match the hash of the image that was tested on hardware. A mismatch means
a different firmware version or a different assembler output; nothing is
written in that case.
"""

import hashlib
import shutil
import subprocess

from . import (
    build_target_candidate,
    patch_identity_pd3,
    patch_identity_vid,
    patch_power_15v,
    patch_query02,
    patch_rtd2142_hdr_avi,
    patch_versions,
)

VL103_STOCK = '3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3'
RTD2142_STOCK = '17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802'

# (name, builder, expected output SHA-256). Order matters: each step requires
# the exact output of the previous one.
VL103_STEPS = (
    (
        'responder: Nintendo SVID, modes and echo replies',
        build_target_candidate.build_candidate,
        'f1c75dbdf48dd806c003b180fda88813d2256400e46e8e9f9619c0b0047015ee',
    ),
    (
        'power: 15 V / 2.8 A offer (hub reserve 7 W -> 3 W)',
        patch_power_15v.build_candidate,
        '2f59a358e1cd847cbf6aa96a5ba28037cb9287d2d1bef18683ef886b15a79e60',
    ),
    (
        'identity: Nintendo VID',
        patch_identity_vid.build_candidate,
        'c5cff89182e83862b342e63a0adfcecab3213ce141f6b383b8e608f8a9721a2c',
    ),
    (
        'identity: official dock PD3 Discover Identity',
        patch_identity_pd3.build_candidate,
        '6ab038bd2dd0bf008e2ffe73b5d237c46cfee17be8ae701f78096aeea9da3beb',
    ),
    (
        'query 02 reply',
        patch_query02.build_candidate,
        '844d20eb4155e8b5db542d91a6faaa4a00ebebf17b03f8e7bfcacc3bfb8d3d09',
    ),
    (
        'query 04/06 version replies',
        patch_versions.build_candidate,
        '6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e',
    ),
)
RTD2142_STEPS = (
    (
        'HDMI AVI InfoFrame: BT.2020 when PQ/HLG HDR metadata is present',
        patch_rtd2142_hdr_avi.build,
        'f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1',
    ),
)


TOOLCHAIN = ('sdas8051', 'sdld')

# Every assembled overlay, as (module, assemble function name). Their output is
# fingerprinted by overlay_digests() so an SDCC change is caught without dumps.
OVERLAYS = (
    ('target_responder', build_target_candidate),
    ('power_15v', patch_power_15v),
    ('identity_pd3', patch_identity_pd3),
    ('query02', patch_query02),
    ('versions', patch_versions),
    ('rtd2142_hdr_avi', patch_rtd2142_hdr_avi),
)

# overlay_digests() as produced by SDCC 4.6.0 (sdas V05.50.4). All six entries are
# confirmed: real stock VL103 and RTD2142 dumps passed the full hash-locked pipeline with
# this assembler and produced the hardware-tested images.
OVERLAY_DIGESTS_SDCC_4_6_0 = {
    'target_responder': '0c26bd931afa0c52cf506a6ecffa8f9fdf62c9832c0ffbd637b8619c54820c43',
    'power_15v': 'c631c3d58b1f976850cae500a1b2c7af56314bb95a6c9a9ea349f3dec8fec07a',
    'identity_pd3': 'c768c0455460696959c7f80c24c61ddd576d62b082974be450fe92e3a39fd46a',
    'query02': '228747974dbb46faf5f4668d290aa9d53b90c36cf4015e9ea449774f9b173fe0',
    'versions': 'da65a9f8b9ce0866c928871116bee7b71db609eec14fabb99d41da4b702f307b',
    'rtd2142_hdr_avi': '8344a23a15f69a898616bc24017a1c83603bec0d19b5659a73a2173c87a14bdd',
}


class PatchError(Exception):
    pass


def check_toolchain():
    missing = [tool for tool in TOOLCHAIN if shutil.which(tool) is None]
    if missing:
        raise PatchError(
            f'SDCC tools not found on PATH: {", ".join(missing)} '
            '(install SDCC: apt install sdcc / dnf install sdcc / brew install sdcc)'
        )


def toolchain_version():
    try:
        result = subprocess.run(
            ['sdas8051'],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10,
            check=False,
        )
    except OSError:
        return None
    lines = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
    return lines[0] if lines else None


def overlay_digest(memory):
    """SHA-256 over (address, byte) pairs of an assembled overlay."""
    h = hashlib.sha256()
    for address in sorted(memory):
        h.update(address.to_bytes(3, 'big') + bytes([memory[address]]))
    return h.hexdigest()


def overlay_digests():
    """Assemble every patch source (no firmware needed) and fingerprint the output."""
    check_toolchain()
    digests = {}
    for name, module in OVERLAYS:
        try:
            if module is patch_rtd2142_hdr_avi:
                memory = patch_rtd2142_hdr_avi.assemble()[0]
            else:
                memory = module.assemble()
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            raise PatchError(f'assembling {name} failed: {exc}') from exc
        digests[name] = overlay_digest(memory)
    return digests


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def run(image, stock_sha, steps, log=print, manifests=None):
    """Apply steps in order. If manifests is a list, each step's record is appended."""
    if sha256(image) != stock_sha:
        raise PatchError(
            f'input SHA-256 {sha256(image)} is not the supported stock image {stock_sha}'
        )
    check_toolchain()
    for name, builder, expected in steps:
        try:
            result = builder(image)
        except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
            raise PatchError(f'step "{name}" failed: {exc}') from exc
        image, manifest = result if isinstance(result, tuple) else (result, None)
        got = sha256(image)
        if got != expected:
            raise PatchError(
                f'step "{name}" produced {got}, expected {expected} (different SDCC output?)'
            )
        if manifests is not None:
            manifests.append({'step': name, 'output_sha256': got, 'manifest': manifest})
        log(f'  ok  {name}')
    return image


def patch_vl103(image, log=print, manifests=None):
    return run(image, VL103_STOCK, VL103_STEPS, log, manifests)


def patch_rtd2142(image, log=print, manifests=None):
    return run(image, RTD2142_STOCK, RTD2142_STEPS, log, manifests)


def _known_images():
    known = {VL103_STOCK: 'VL103 stock', RTD2142_STOCK: 'RTD2142 stock'}
    for chip, steps in (('VL103', VL103_STEPS), ('RTD2142', RTD2142_STEPS)):
        for number, (name, _, digest) in enumerate(steps, 1):
            if number == len(steps):
                known[digest] = f'{chip} patched'
            else:
                known[digest] = (
                    f'{chip} partly patched (after step {number}/{len(steps)}: '
                    f'{name}); not a final image, do not flash'
                )
    return known


SIZES = {0x8000: 'VL103-sized (32 KiB)', 0x200000: 'RTD2142-sized (2 MiB)'}


def identify(image):
    label = _known_images().get(sha256(image))
    if label:
        return label
    size = SIZES.get(len(image))
    return f'unknown, {size}: different firmware version?' if size else 'unknown'
