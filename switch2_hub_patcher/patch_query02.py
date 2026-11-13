"""Build an OFFLINE UNVERIFIED query02-only diagnostic from exact v5.

Advertises captured official0003006E, not the actual RTD2142 firmware version.
No device access/flashing, GPIO, converter, DP, identity or power changes.
"""
import hashlib

from . import hexfile
from .vl103_crc import crc16_usb, stored_and_computed

BASE_SHA = '6ab038bd2dd0bf008e2ffe73b5d237c46cfee17be8ae701f78096aeea9da3beb'
HOOKS = (
    (0x7280, bytes.fromhex('e9 60 09'), bytes.fromhex('02 7e 00')),
    (0x743a, bytes.fromhex('e8 b4 01 15'), bytes.fromhex('02 7e 40 00')),
)
REGIONS = ((0x7e00,0x7e20),(0x7e40,0x7e80))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def assemble():
    return hexfile.assemble('query02', REGIONS, required=(0x7e00, 0x7e40))


def build_candidate(base):
    if len(base) != 0x8000 or sha(base) != BASE_SHA:
        raise ValueError('requires exact working v5 image')
    stored,computed = stored_and_computed(base)
    if stored != computed:
        raise ValueError('invalid base CRC')
    for at,old,new in HOOKS:
        if len(old) != len(new) or base[at:at+len(old)] != old:
            raise ValueError(f'hook mismatch at{at:04X}')
    for lo,hi in REGIONS:
        if base[lo:hi] != b'\xff'*(hi-lo):
            raise ValueError('query02 CODE region not erased')
    overlay = assemble()
    image = bytearray(base)
    for at,old,new in HOOKS:
        image[at:at+len(new)] = new
    for at,byte in overlay.items():
        image[at] = byte
    image[-2:] = crc16_usb(image[:-2]).to_bytes(2,'little')
    image = bytes(image)
    changed = [i for i,(old,new) in enumerate(zip(base,image)) if old != new]
    allowed = set(overlay)|{0x7ffe,0x7fff}
    for at,old,new in HOOKS:
        allowed.update(range(at,at+len(old)))
    if len(image) != 0x8000 or not set(changed) <= allowed:
        raise ValueError('unexpected query02 footprint')
    stored,computed = stored_and_computed(image)
    if stored != computed:
        raise ValueError('candidate CRC mismatch')
    return image,{
        'experiment':'vl103-native-responder-v6-query02',
        'base_sha256':BASE_SHA,'output_sha256':sha(image),'size_bytes':len(image),
        'source_sha256':sha((hexfile.ASM / 'query02.asm').read_bytes()),
        'crc16_usb':f'0x{stored:04X}','overlay_bytes':len(overlay),
        'hooks':[{'offset':at,'old':old.hex(),'new':new.hex()} for at,old,new in HOOKS],
        'request_vdos':['057E0001','00000002'],
        'reply_vdos':['057E0041','00000002','0003006E'],
        'scope':'Exact NDO2 query02 only, after existing source-ready/entered/header/role guards.',
        'additional_stack_bytes':0,'new_xdata_bytes':0,'new_persistent_state':False,
        'hardware_validated':False,'flash_approved':False,'recovery_verified':False,
        'unchanged':['All other admitted commands and rejection forms, including04/06 unhandled.',
                     'Full PD3 identity, legacy PD2 identity and USB/updater metadata.',
                     'v3 power policy, DP/GPIO/converter code and all existing arbitration.'],
        'limits':['UNVERIFIED compatibility probe, not a confirmed HDR fix.',
                  '0003006E is captured official data, NOT the actual RTD2142 firmware version.',
                  'Opcode02 formal meaning/component mapping remains unproven; version-like evidence only.',
                  'May expose later unsupported queries or different console behavior; do not auto-ACK them.',
                  'Inherited IRQ/stack/cave/recovery and unmeasured3W hub reserve limits; USB ports empty.',
                  'No device access or automatic flashing; preserve exact v5 as baseline.'],
        'changed_byte_count':len(changed),
        'changes':[{'offset':at,'old':base[at],'new':image[at]} for at in changed],
    }
