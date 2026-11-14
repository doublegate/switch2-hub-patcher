"""Mechanical names for the RTD2142 firmware, from bank-call stubs and register usage.

Usage:
  python3 -I auto_names.py stubs BANKDIR            -> per-bank cross-bank entry addresses
  python3 -I auto_names.py names REPORTDIR OUT.tsv   -> auto symbol TSV (RenameSymbols format)

BANKDIR holds bank0.bin..bank7.bin (64 KiB each). REPORTDIR holds bankN.tsv files from
FunctionReport.java. Names already confirmed in research/rtd2142_symbols.tsv are never
touched (only Ghidra's default FUN_* names are replaced).

Scheme (all lower case, address last so names stay unique):
  call_b<N>_<addr>     common-area stub: MOV DPTR,#addr; LJMP bank_call<N>
  <sub>_<addr>         function whose hardware accesses are mostly in subsystem <sub>
  <sub>_ram_<addr>     only RAM accesses; <sub> from the subsystems of its callees
  fn_<addr>            nothing to go on
The page -> subsystem table comes from the RTD2172 register database's register names.
"""

import collections
import sys
from pathlib import Path

BANK_CALL = {0x0CB8 + 0x12 * n: n for n in range(8)}  # stub LJMP target -> bank
COMMON = 0x2000  # the first 8 KiB is identical in every bank

# XDATA page -> subsystem (from the dominant register names per page in the RTD2172 DB)
PAGES = {
    0x02: 'pll',
    0x03: 'pll',
    0x06: 'osc',
    0x0A: 'mst',
    0x0B: 'hdcp',
    0x10: 'pinmux',
    0x16: 'dptx_meas',
    0x17: 'dprx_phy',
    0x1A: 'combo_phy',
    0x1C: 'phy_cal',
    0x1D: 'bandgap',
    0x21: 'buf',
    0x30: 'csc',
    0x31: 'csc_hdmitx',
    0x32: 'csc_dptx0',
    0x33: 'csc_dptx1',
    0x36: 'dac',
    0x40: 'top',
    0x41: 'pll',
    0x42: 'autoadj',
    0x43: 'autoadj',
    0x44: 'autoadj',
    0x4D: 'dptx0',
    0x4E: 'dptx0',
    0x4F: 'dptx0_aux',
    0x52: 'hdmitx_b',
    0x53: 'hdmitx_b',
    0x54: 'hdcp_b',
    0x55: 'hdmitx_c',
    0x56: 'hdmitx_c',
    0x57: 'hdcp_c',
    0x58: 'cec',
    0x59: 'cec',
    0x5A: 'hdmitx_phy',
    0x5B: 'hdmitx',
    0x5C: 'hdmitx_hdcp',
    0x62: 'div',
    0x63: 'hdcp',
    0x64: 'usb_clk',
    0x65: 'pd',
    0x66: 'typec',
    0x6F: 'adi',
    0x75: 'pd',
    0x76: 'typec',
    0x7F: 'i2cm',
    0x80: 'top',
    0x81: 'usb3',
    0x82: 'usb3',
    0x86: 'chg',
    0x96: 'dptx_meas',
    0x97: 'usb2',
    0x98: 'usb2',
    0x9A: 'bb',
    0xB0: 'dprx_sel',
    0xB1: 'dprx1',
    0xB2: 'dprx1',
    0xB3: 'dprx2',
    0xB4: 'dprx2',
    0xB5: 'dprx3',
    0xB6: 'dprx3',
    0xB7: 'dpcd',
    0xB8: 'dprx4',
    0xB9: 'dprx4',
    0xBB: 'dptx1',
    0xBC: 'dptx1',
    0xBD: 'dptx1_aux',
    0xC1: 'phy',
    0xC2: 'phy',
    0xFD: 'i2cm',
    0xFE: 'gpio',
    0xFF: 'sys',
}
RAM = range(0xC000, 0xF000)  # firmware variables


def subsystem(addr):
    if addr in RAM:
        return None
    return PAGES.get(addr >> 8, 'hw%02x' % (addr >> 8))


def stubs(bank0):
    """{stub address: (bank, target)} from the common area."""
    found = {}
    for at in range(0x0030, COMMON - 6):
        if bank0[at] == 0x90 and bank0[at + 3] == 0x02:
            dest = (bank0[at + 4] << 8) | bank0[at + 5]
            if dest in BANK_CALL:
                found[at] = (BANK_CALL[dest], (bank0[at + 1] << 8) | bank0[at + 2])
    return found


def read_report(path):
    rows = {}
    with open(path) as f:
        next(f)
        for line in f:
            entry, name, size, callers, callees, reads, writes = line.rstrip('\n').split('\t')
            split = lambda s: [int(x, 16) for x in s.split(',') if x]  # noqa: E731
            rows[int(entry, 16)] = {
                'name': name,
                'size': int(size),
                'callers': int(callers),
                'callees': split(callees),
                'refs': split(reads) + split(writes),
            }
    return rows


def classify(banks, stub_map, rounds=6):
    """{(bank, entry): name} for default-named functions, over all banks at once.

    Subsystems come from direct hardware accesses first; then, for up to `rounds`
    passes, an unclassified function takes the most common subsystem among its
    callees and callers (cross-bank calls through the common-area stubs included).
    """
    subs = {}
    for bank, rows in banks.items():
        for entry, r in rows.items():
            hw = collections.Counter(s for s in map(subsystem, r['refs']) if s)
            if hw:
                subs[bank, entry] = hw.most_common(1)[0][0]
    direct = set(subs)

    def resolve(bank, target):
        if target in stub_map:  # call through a bank-call stub
            return stub_map[target]
        return (0 if target < COMMON else bank), target

    callers = collections.defaultdict(list)
    for bank, rows in banks.items():
        for entry, r in rows.items():
            for c in r['callees']:
                callers[resolve(bank, c)].append((bank, entry))
    for _ in range(rounds):
        added = {}
        for bank, rows in banks.items():
            for entry, r in rows.items():
                key = (bank, entry)
                if key in subs:
                    continue
                votes = collections.Counter(subs.get(resolve(bank, c)) for c in r['callees'])
                votes.update(subs.get(k) for k in callers.get(key, ()))
                votes.pop(None, None)
                if votes:
                    added[key] = votes.most_common(1)[0][0]
        if not added:
            break
        subs.update(added)
    names = {}
    for bank, rows in banks.items():
        for entry, r in rows.items():
            if not r['name'].startswith('FUN_'):
                continue
            key = (bank, entry)
            if key not in subs:
                names[key] = f'fn_{entry:04x}'
            elif key in direct:
                names[key] = f'{subs[key]}_{entry:04x}'
            else:
                kind = 'ram' if r['refs'] else 'ctl'
                names[key] = f'{subs[key]}_{kind}_{entry:04x}'
    return names


def main():
    mode = sys.argv[1]
    if mode == 'stubs':
        bank0 = Path(sys.argv[2], 'bank0.bin').read_bytes()
        per_bank = collections.defaultdict(list)
        for _, (bank, target) in sorted(stubs(bank0).items()):
            per_bank[bank].append(f'{target:04x}')
        for bank in range(8):
            print(bank, ' '.join(sorted(set(per_bank[bank]))))
        return
    report_dir, out = Path(sys.argv[2]), Path(sys.argv[3])
    bank0 = (
        Path(report_dir, 'bank0.bin').read_bytes()
        if Path(report_dir, 'bank0.bin').exists()
        else None
    )
    stub_map = stubs(bank0) if bank0 else {}
    lines = [
        '# auto names (research/ghidra/auto_names.py); confirmed names are in rtd2142_symbols.tsv'
    ]
    for at, (bank, target) in sorted(stub_map.items()):
        lines.append(
            f'*\tCODE\t{at:04x}\tcall_b{bank}_{target:04x}\tstub -> bank {bank} {target:04X}'
        )
    banks = {}
    for bank in range(8):
        path = report_dir / f'bank{bank}.tsv'
        if path.exists():
            banks[bank] = read_report(path)
    names = classify(banks, stub_map)
    counts = {b: [len(rows), 0] for b, rows in banks.items()}
    for (bank, entry), name in sorted(names.items()):
        if entry < COMMON and bank != 0:
            continue  # common area: named once, from bank 0
        counts[bank][1] += 1
        scope = '*' if entry < COMMON else str(bank)
        lines.append(f'{scope}\tCODE\t{entry:04x}\t{name}\tauto')
    out.write_text('\n'.join(lines) + '\n')
    for bank, (total, named) in counts.items():
        print(f'bank {bank}: {total} functions, {named} auto-named')
    print(f'{len(stub_map)} bank-call stubs')


if __name__ == '__main__':
    main()
