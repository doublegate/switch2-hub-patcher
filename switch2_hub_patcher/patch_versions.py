#!/usr/bin/env python3
"""OFFLINE v7 diagnostic: exact captured04/06 version replies on exact v6.

Virtual records are NOT actual VIA/RTD2142 versions or an HDR feature claim.
No device access, update handlers, power/DP/identity or converter/GPIO changes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
from .vl103_crc import crc16_usb, stored_and_computed

ASM = Path(__file__).resolve().parent / 'asm'
BASE_SHA = '844d20eb4155e8b5db542d91a6faaa4a00ebebf17b03f8e7bfcacc3bfb8d3d09'
HOOKS = (
    (0x7280,bytes.fromhex('02 7e 00'),bytes.fromhex('02 7f 00')),
    (0x743a,bytes.fromhex('02 7e 40 00'),bytes.fromhex('02 7f 40 00')),
)
REGIONS = ((0x7f00,0x7f20),(0x7f40,0x7f80),(0x7fa0,0x7fc0))
BODIES = {4:struct.pack('<II',0x330107da,0x06016d61)*2,
          6:struct.pack('<II',0x330107da,0x06016d68)*2}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def parse_hex(text):
    memory = {}
    ended = False
    for line in text.splitlines():
        if not line:
            continue
        if ended or not line.startswith(':'):
            raise ValueError('bad HEX ordering')
        record = bytes.fromhex(line[1:])
        if len(record)<5 or len(record)!=record[0]+5 or sum(record)&255:
            raise ValueError('bad HEX length/checksum')
        n,address,kind=record[0],int.from_bytes(record[1:3],'big'),record[3]
        if kind==1 and n==0 and address==0:
            ended=True
        elif kind==0:
            for i,byte in enumerate(record[4:-1]):
                at=address+i
                if at in memory or not any(lo<=at<hi for lo,hi in REGIONS):
                    raise ValueError('overlay outside version regions or duplicate data')
                memory[at]=byte
        else:
            raise ValueError('unsupported HEX record')
    if not ended or not all(at in memory for at in (0x7f00,0x7f40,0x7fa0,0x7fb0)):
        raise ValueError('missing version entry/data or EOF')
    for at,command in ((0x7fa0,4),(0x7fb0,6)):
        if bytes(memory.get(a,255) for a in range(at,at+16))!=BODIES[command]:
            raise ValueError('unexpected captured version body')
    return memory


def assemble():
    with tempfile.TemporaryDirectory(prefix='vl103-versions-') as directory:
        directory=Path(directory)
        shutil.copyfile(ASM / 'versions.asm',directory/'versions.asm')
        for command in (['sdas8051','-los','versions.asm'],['sdld','-n','-i','versions.rel']):
            result=subprocess.run(command,cwd=directory,text=True,stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT,timeout=30)
            if result.returncode:
                raise RuntimeError(result.stdout)
        return parse_hex((directory/'versions.ihx').read_text())


def build_candidate(base):
    if len(base)!=0x8000 or sha(base)!=BASE_SHA:
        raise ValueError('requires exact v6 query02 image')
    if stored_and_computed(base)[0]!=stored_and_computed(base)[1]:
        raise ValueError('invalid base CRC')
    for at,old,new in HOOKS:
        if len(old)!=len(new) or base[at:at+len(old)]!=old:
            raise ValueError(f'version hook mismatch at{at:04X}')
    for lo,hi in REGIONS:
        if base[lo:hi]!=b'\xff'*(hi-lo):
            raise ValueError('version CODE region not erased')
    overlay=assemble()
    image=bytearray(base)
    for at,old,new in HOOKS:
        image[at:at+len(new)]=new
    for at,byte in overlay.items():
        image[at]=byte
    image[-2:]=crc16_usb(image[:-2]).to_bytes(2,'little')
    image=bytes(image)
    changed=[i for i,(a,b) in enumerate(zip(base,image)) if a!=b]
    allowed=set(overlay)|{0x7ffe,0x7fff}
    for at,old,new in HOOKS:
        allowed.update(range(at,at+len(old)))
    if len(image)!=0x8000 or not set(changed)<=allowed:
        raise ValueError('unexpected version footprint')
    stored,computed=stored_and_computed(image)
    if stored!=computed:
        raise ValueError('candidate CRC mismatch')
    return image,{
        'experiment':'vl103-native-responder-v7-versions',
        'base_sha256':BASE_SHA,'output_sha256':sha(image),'size_bytes':len(image),
        'source_sha256':sha((ASM / 'versions.asm').read_bytes()),
        'crc16_usb':f'0x{stored:04X}','overlay_bytes':len(overlay),
        'hooks':[{'offset':at,'old':old.hex(),'new':new.hex()} for at,old,new in HOOKS],
        'requests':{str(c):['057E0001',f'{c:08X}'] for c in BODIES},
        'replies':{str(c):['057E0041',f'{c:08X}']+[f'{v:08X}' for v in struct.unpack('<4I',b)]
                   for c,b in BODIES.items()},
        'scope':'Exact NDO2 query04/06 only, under inherited entered/source-UFP/ready guards.',
        'reply_ndo':6,'payload_bytes':16,'copy_counter':'bank0R7, not shared67',
        'additional_stack_bytes':0,'new_xdata_bytes':0,'new_persistent_state':False,
        'hardware_validated':False,'flash_approved':False,'recovery_verified':False,
        'unchanged':['v6 query02 and all earlier replies/identity/power/DP/USB metadata.',
                     'All other unknown/update commands remain native fallback.',
                     'Original busy/error/freshRX arbitration and optimistic mode state.'],
        'limits':['Virtual official version records, NOT actual VIA/RTD2142 firmware versions.',
                  'Unverified compatibility diagnostic, NOT an HDR fix or physical feature implementation.',
                  'Source behavior may change; do not initiate official dock firmware updates.',
                  'No converter/GPIO or new update/flash handlers.',
                  'Inherited IRQ/stack/cave/recovery and3W physical headroom unverified; USB ports empty.',
                  'No device access or automatic flashing; preserve v5/v6 baselines.'],
        'changed_byte_count':len(changed),
        'changes':[{'offset':i,'old':base[i],'new':image[i]} for i in changed],
    }
