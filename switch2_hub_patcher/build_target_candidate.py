"""Build a guarded EXPERIMENTAL 32KiB candidate. NEVER opens/flashes a device.

Unlike the simulator overlay, CODE stays inside the real image and no new XDATA
is allocated. This uses optimistic/native-style mode state, NOT the strict host
lifecycle's delivery-confirmed commit. Read the manifest before any experiment.
"""
import hashlib

from . import hexfile
from .patch_svid import STOCK_SHA256
from .patch_svid import build_candidate as build_svid
from .vl103_crc import crc16_usb, stored_and_computed

HOOKS = (
    (0x5d3f, bytes.fromhex('e5 2c 24 de'), bytes.fromhex('02 70 00 00'), 'source data router'),
    (0x591c, bytes.fromhex('e4 90 2a 29'), bytes.fromhex('02 7a 00 00'), 'common PD reset'),
    (0x5cbf, bytes.fromhex('02 1a e7'), bytes.fromhex('02 7a 10'), 'post-initializer boot'),
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    return hexfile.assemble('target_responder', ((0x7000, 0x7ffe),),
                            required=(0x7000, 0x7100, 0x7180, 0x7200, 0x7280, 0x7400,
                                      0x7500, 0x7580, 0x7600, 0x7a00, 0x7a10))


def build_candidate(original):
    candidate, _ = build_svid(original)  # exact SHA/CRC/SVID-layout guards
    if original[0x7000:0x7ffe] != b'\xff' * (0x7ffe - 0x7000):
        raise ValueError('CODE cave is not completely erased')
    for address, old, new, _ in HOOKS:
        if len(old) != len(new) or original[address:address + len(old)] != old:
            raise ValueError(f'hook guard failed at {address:#x}')
    overlay = assemble()
    image = bytearray(candidate)
    allowed = set(overlay) | {0x25a9, 0x6855, 0x6856, 0x7ffe, 0x7fff}
    for address, old, new, _ in HOOKS:
        image[address:address + len(new)] = new
        allowed.update(range(address, address + len(old)))
    for address, byte in overlay.items():
        image[address] = byte
    image[-2:] = crc16_usb(image[:-2]).to_bytes(2, 'little')
    image = bytes(image)
    changed = [i for i, (old, new) in enumerate(zip(original, image)) if old != new]
    if len(image) != 0x8000 or not set(changed) <= allowed:
        raise ValueError('unexpected candidate footprint')
    stored, computed = stored_and_computed(image)
    if stored != computed:
        raise ValueError('candidate CRC mismatch')
    manifest = {
        'experiment': 'vl103-native-responder-v2',
        'hardware_validated': False,
        'flash_approved': False,
        'recovery_verified': False,
        'size_bytes': len(image),
        'input_sha256': STOCK_SHA256,
        'output_sha256': sha(image),
        'source_sha256': sha((hexfile.ASM / 'target_responder.asm').read_bytes()),
        'crc16_usb': f'0x{stored:04X}',
        'overlay_bytes': len(overlay),
        'overlay_first': min(overlay),
        'overlay_last': max(overlay),
        'hooks': [{'offset': address, 'old': old.hex(), 'new': new.hex(), 'purpose': purpose}
                  for address, old, new, purpose in HOOKS],
        'scope': 'Source/UFP source-ready path; normal-SOP routing assumed from stock, not independently decoded',
        'persistent_state': {'bit_address': 0x45, 'iram_byte': 0x28, 'mask': 0x20,
                             'boot_and_common_reset_clear': True, 'target_allocation_proven': False},
        'new_xdata_bytes': 0,
        'extra_saved_context_stack_bytes': 11,
        'stock_tx_trigger': 0x65d5,
        'stock_wait_state': 0x78,
        'mode_commit': 'optimistic at TX START, not peer-ACK-confirmed; native-style experimental policy',
        'fresh_rx_before_trigger': 'abort old draft, retain new pending event; no private retry queue',
        'native_priority_guard': 'primary4B mask86 or secondary4C bit1 defer/abort; no status names assigned',
        'tx_busy': 'leave pending RX untouched and return, no blocking wait',
        'assumptions_and_limits': [
            'Bit45 allocation and erased CODE cave are experimental, not fully proven against indirect references.',
            'Full ISR nesting/stack bounds and physical IRQ admission remain unverified.',
            'No independently verified SOP/SOP-prime discriminator; relies on native/hardware source-ready routing.',
            'No generic hardware delivery/cancel/error meanings are assigned.',
            'Identity, power and DP code/data remain stock except expanded SVID advertisement.',
            'No promise of video compatibility or complete proprietary command side effects.',
            'Not the strict host lifecycle implementation: no delivery-confirmed state commit or pending queue.',
            'No erase/program, USB access or automatic flashing performed by this builder.',
        ],
        'changed_byte_count': len(changed),
        'changes': [{'offset': i, 'old': original[i], 'new': image[i]} for i in changed],
    }
    return image, manifest
