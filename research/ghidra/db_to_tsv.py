"""Turn `rtd_db_dump.py` output into a RenameSymbols TSV of XDATA register labels.

Usage:
  python3 -I research/rtd_db_dump.py DB.bin > fields.txt
  python3 -I research/ghidra/db_to_tsv.py fields.txt > registers.tsv

Every "ADDR NAME" line becomes one EXTMEM label NAME_ADDR for all banks (the database
repeats names per stream and port, so the address keeps them unique); the first name wins
where the database lists several for one address (indexed ports such as DPCD_DATA_PORT).
Field lines are folded into the note, shortened. The output is derived from Realtek's
RTD2172 database, so generate it locally instead of committing it.
"""

import re
import sys
from pathlib import Path


def main(path):
    seen = {}
    order = []
    current = None
    for line in Path(path).read_text(errors='replace').splitlines():
        m = re.match(r'^([0-9A-F]{4}) (\w+)$', line)
        if m:
            address = int(m.group(1), 16)
            current = address if address not in seen else None
            if current is not None:
                seen[address] = [m.group(2), []]
                order.append(address)
            continue
        f = re.match(r'^\s+\[(\d+):(\d+)\] (\w+)', line)
        if f and current is not None and f.group(3) != 'Reserved':
            hi, lo, name = f.groups()
            seen[current][1].append(f'{name}.{lo}' if hi == lo else f'{name}[{hi}:{lo}]')
    for address in order:
        name, fields = seen[address]
        note = ' '.join(fields)[:160]
        print(f'*\tEXTMEM\t{address:04x}\t{name}_{address:04X}\t{note}')


if __name__ == '__main__':
    main(sys.argv[1])
