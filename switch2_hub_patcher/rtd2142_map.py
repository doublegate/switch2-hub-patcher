"""Read-only survey of an RTD2142 dump: which code touches which hardware registers.

Register addresses and names come from the public Realtek tool database for the
related RTD2172 (same 8051 XDATA page layout; its HDMI 2.0 TX packetizer page 0x5B
matches the registers the existing HDMI patch uses). They are assumptions for the
RTD2142 until the survey of a real dump confirms them. Never modifies anything.
"""
from collections import defaultdict

BANK_SIZE = 0x10000

# address: (block, name, note)
REGISTERS = {
    # HDMI 2.0 TX MAC0, data-island packetizer (used by the existing HDMI patch)
    0x5B48: ('hdmi-tx', 'DATA_ISLAND_PACKETIZER_19', 'staged AVI PB3 (EC) in the HDMI patch'),
    0x5B49: ('hdmi-tx', 'DATA_ISLAND_PACKETIZER_20', 'staged AVI PB2 (C) in the HDMI patch'),
    0x5B4B: ('hdmi-tx', 'DATA_ISLAND_PACKETIZER_22', 'staged AVI checksum in the HDMI patch'),
    0x5B6B: ('hdmi-tx', 'DATA_ISLAND_PACKETIZER_54', 'bit5 = HDR packet enable in the HDMI patch'),
}

for prefix, tx in ((0x4D00, 'dp-tx0'), (0xBB00, 'dp-tx1')):
    sec = prefix + 0x100
    REGISTERS.update({
        prefix + 0xB4: (tx, 'MSA_CTRL', 'bit7 msa_db: double-buffer MSA'),
        prefix + 0xB5: (tx, 'MSA_MISC0', '[7:5] bpc, [4] BT601/709, [3] CEA range, [2:1] format'),
        prefix + 0xB6: (tx, 'MN_STRM_ATTR_MISC1', 'bit6: colorimetry is in the VSC SDP'),
        sec + 0x00: (tx, 'SEC_FUNCTION_CTRL', 'bit2 psr_en: VSC SDP transmit; bit4 AVI; bit7 rsv0'),
        sec + 0x02: (tx, 'SEC_DBUF_CTRL', 'bit0 sec_db: latch SDP header/payload; bit1 at vblank'),
        sec + 0x14: (tx, 'SEC_PSR_DB16', 'VSC DB16: [7:4] pixel encoding, [3:0] colorimetry'),
        sec + 0x15: (tx, 'SEC_PSR_DB17', 'VSC DB17: [7] CEA range, [2:0] bpc'),
        sec + 0x16: (tx, 'SEC_PSR_DB18', 'VSC DB18: content type'),
        sec + 0x26: (tx, 'DP_INFO_FM_RSV0_HB2', 'reserved SDP slot 0 header (HDR metadata?)'),
        sec + 0x27: (tx, 'DP_INFO_FM_RSV0_HB3', ''),
        sec + 0x53: (tx, 'DP_INFO_FM_RSV0', 'reserved SDP slot 0 type'),
        sec + 0x55: (tx, 'DP_INFO_FM_ADR', 'SDP payload port address'),
        sec + 0x56: (tx, 'DP_INFO_FM_DAT', 'SDP payload port data'),
    })
    for n in range(16):
        REGISTERS[sec + 0x04 + n] = (tx, f'SEC_PSR_DB{n}', 'VSC SDP payload')

for stream, base in ((1, 0xB100), (2, 0xB300), (3, 0xB500), (4, 0xB800)):
    rx = f'dp-rx-st{stream}'
    REGISTERS.update({
        base + 0x30: (rx, 'DPF_CTRL_0', 'bit5 frame_sync_mode, bit4 deonly_mode'),
        base + 0x90: (rx, 'DP_RSV0', 'bit0 drr_mode'),
        base + 0x91: (rx, 'DP_RSV1', 'bit7 deonly_full_mode, bit6 de_window_fix_en'),
        base + 0x9A: (rx, 'DP_RSVA', 'bit0 vrr_mode (VS from Adaptive-Sync SDP), bit1 vrr_vs_mode'),
        base + 0x1FC: (rx, 'DUMMY_2', 'bit0 vsc_for_vrr_en: pass Adaptive-Sync info to DPF'),
    })
REGISTERS[0xB202] = ('dp-rx-st1', 'MN_STRM_ATTR_MISC', 'received MSA MISC0')
REGISTERS[0xB203] = ('dp-rx-st1', 'MN_STRM_ATTR_MISC1', 'received MSA MISC1')


def xrefs(image, registers=REGISTERS):
    """Find `mov dptr,#imm16` (90 hi lo) that load a known register address.

    Returns {address: [(bank, code_address, next_opcode), ...]}. next_opcode 0xF0
    is `movx @dptr,a` (a write), 0xE0 is `movx a,@dptr` (a read).
    """
    found = defaultdict(list)
    for at in range(len(image) - 3):
        if image[at] != 0x90:
            continue
        address = (image[at + 1] << 8) | image[at + 2]
        if address in registers:
            found[address].append((at // BANK_SIZE, at % BANK_SIZE, image[at + 3]))
    return dict(found)


def summary(image, registers=REGISTERS):
    """Per-block counts and per-register sites, as printable lines."""
    refs = xrefs(image, registers)
    lines = []
    blocks = defaultdict(int)
    for address, sites in refs.items():
        blocks[registers[address][0]] += len(sites)
    lines.append('references per block (8051 `mov dptr,#addr`):')
    for block in sorted({b for b, _, _ in registers.values()}):
        lines.append(f'  {block:12} {blocks.get(block, 0)}')
    lines.append('')
    for address in sorted(refs):
        block, name, note = registers[address]
        lines.append(f'{address:04X} {block:11} {name:28} {note}')
        for bank, code, op in refs[address][:12]:
            kind = {0xF0: 'write', 0xE0: 'read'}.get(op, f'next {op:02X}')
            lines.append(f'      bank {bank} {code:04X}  {kind}')
        if len(refs[address]) > 12:
            lines.append(f'      ... {len(refs[address]) - 12} more')
    return lines
