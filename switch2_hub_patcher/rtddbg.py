"""Read-only client for the RTD2142 firmware's debug interface (I2C 0x35 over DP AUX).

The protocol is decoded from the stock firmware and confirmed on a chip (2026-11-14:
reads, and the single-byte write below; research/DP_HDR_AND_VRR.md, section 3). Reads use
four commands:

  0x55 00     enter debug mode
  0x01 hi     set the XDATA address high byte (any non-table command with low nibble 1)
  0x3A lo     read XDATA[hi:lo] into the reply register; an I2C read returns it
  0x2F 00     leave debug mode

Every session first reads the debug slave's own address register (FF23), which must hold
0x6A; if it does not, the decode is wrong for this firmware and nothing is reported.

Two experiment-only writes exist: ``clear_bits`` may clear bits listed in CLEARABLE and
``set_bits`` may set bits listed in SETTABLE (working RAM or a live register, never flash),
using two more commands:

  0x03 value  set the write-data byte (non-table command with low nibble 3)
  0x3B lo     write the data byte to XDATA[hi:lo]

A power cycle (unplugging the hub) restores both. The block-write command (0xBA) and
writes to any other address or bit are refused before anything reaches the bus.
"""

import contextlib
import time

DEBUG_ADDR = 0x35  # 7-bit; the firmware writes 0x6A (8-bit) to FF23
CMD_ENTER = 0x55
CMD_EXIT = 0x2F
CMD_ADDR_HI = 0x01
CMD_READ = 0x3A
CMD_WDATA = 0x03
CMD_WRITE = 0x3B
SELF_CHECK = (0xFF23, 0x6A)
READ_ONLY_COMMANDS = frozenset({CMD_ENTER, CMD_EXIT, CMD_ADDR_HI, CMD_READ})
WRITE_COMMANDS = frozenset({CMD_WDATA, CMD_WRITE})
# The only bits clear_bits may touch: address -> (clearable mask, what it is).
CLEARABLE = {
    0xE362: (
        0x02,
        'port-1 HDR metadata present (DP RX status); the HDMI side then stops sending '
        'the HDR packet until the RX path sets it again',
    ),
    0x5B07: (
        0xF0,
        'HDMI TX dp_color_depth; 0 is the 8-bit value a fresh start uses (stock firmware '
        'leaves 12-bit here after an HDR to SDR switch)',
    ),
}
# The only bits set_bits may touch: address -> (settable mask, what it is).
SETTABLE = {
    0xE10B: (
        0x08,
        'hdmi_sink_quirk_flags bit 3: the slow-sink quirk; hdmi_scdc_scramble_start then waits '
        '500 ms instead of 100 ms after the SCDC TMDS_Config write. Recomputed from the EDID '
        'at the next hot plug',
    ),
}
MAX_ADDRESSES = 256


class DebugError(Exception):
    pass


class DebugSession:
    """Context manager: enters debug mode, reads XDATA bytes, always tries to leave."""

    def __init__(self, transport, settle=0.005, sleep=time.sleep):
        self.t = transport
        self.settle = settle
        self.sleep = sleep
        self.active = False

    def _send(self, command, value, write=False):
        allowed = READ_ONLY_COMMANDS | (WRITE_COMMANDS if write else frozenset())
        if command not in allowed:
            raise DebugError(f'command {command:#04x} is not a read-only debug command')
        self.t.write_reg(command, bytes([value]))
        self.sleep(self.settle)  # the main loop, not the ISR, executes the command

    def __enter__(self):
        self._send(CMD_ENTER, 0x00)
        self.active = True
        return self

    def __exit__(self, *_exc):
        if self.active:
            self.active = False
            with contextlib.suppress(OSError):  # a power cycle also leaves debug mode
                self._send(CMD_EXIT, 0x00)
        return False

    def read(self, address):
        if not 0 <= address <= 0xFFFF:
            raise DebugError(f'address {address:#x} is outside XDATA')
        self._send(CMD_ADDR_HI, address >> 8)
        self._send(CMD_READ, address & 0xFF)
        return self.t.read_reg(CMD_READ, 1)[0]

    def _write_byte(self, address, value):
        self._send(CMD_ADDR_HI, address >> 8)
        self._send(CMD_WDATA, value & 0xFF, write=True)
        self._send(CMD_WRITE, address & 0xFF, write=True)

    def clear_bits(self, address, mask):
        """Clear `mask` at `address` (CLEARABLE only): (before, after), re-read from the chip."""
        check_allowed(CLEARABLE, 'clearable', address, mask)
        before = self.read(address)
        if before & mask:
            self._write_byte(address, before & ~mask)
        return before, self.read(address)

    def set_bits(self, address, mask):
        """Set `mask` at `address` (SETTABLE only): (before, after), re-read from the chip."""
        check_allowed(SETTABLE, 'settable', address, mask)
        before = self.read(address)
        if before & mask != mask:
            self._write_byte(address, before | mask)
        return before, self.read(address)

    def self_check(self):
        address, want = SELF_CHECK
        got = self.read(address)
        if got != want:
            raise DebugError(
                f'debug interface did not answer as decoded ({address:04X} read {got:#04x}, '
                f'expected {want:#04x}); nothing reported'
            )


def check_allowed(table, kind, address, mask):
    allowed = table.get(address)
    if allowed is None:
        raise DebugError(
            f'{address:04X} is not a {kind} address (allowed: '
            + ', '.join(f'{a:04X}' for a in table)
            + ')'
        )
    if not mask or mask & ~allowed[0]:
        raise DebugError(
            f'mask {mask:#04x} at {address:04X} is outside the {kind} bits {allowed[0]:#04x}'
        )


def check_clearable(address, mask):
    check_allowed(CLEARABLE, 'clearable', address, mask)


def check_settable(address, mask):
    check_allowed(SETTABLE, 'settable', address, mask)


def parse_addresses(specs):
    """'B130', 'b141-b150' -> sorted unique addresses; at most MAX_ADDRESSES."""
    found = set()
    for spec in specs:
        lo, _, hi = spec.partition('-')
        try:
            start = int(lo, 16)
            end = int(hi, 16) if hi else start
        except ValueError:
            raise DebugError(f'not a hex address or range: {spec!r}') from None
        if not 0 <= start <= end <= 0xFFFF:
            raise DebugError(f'bad range: {spec!r}')
        found.update(range(start, end + 1))
        if len(found) > MAX_ADDRESSES:
            raise DebugError(f'at most {MAX_ADDRESSES} addresses per run')
    return sorted(found)


def peek(transport, addresses, settle=0.005, sleep=time.sleep):
    """Self-check, then read each address: [(address, value), ...]."""
    with DebugSession(transport, settle, sleep) as session:
        session.self_check()
        return [(a, session.read(a)) for a in addresses]


def clear_bits(transport, address, mask, settle=0.005, sleep=time.sleep):
    """Self-check, then clear allowed RAM bits: (before, after)."""
    check_clearable(address, mask)
    with DebugSession(transport, settle, sleep) as session:
        session.self_check()
        return session.clear_bits(address, mask)


def set_bits(transport, address, mask, settle=0.005, sleep=time.sleep):
    """Self-check, then set allowed RAM bits: (before, after)."""
    check_settable(address, mask)
    with DebugSession(transport, settle, sleep) as session:
        session.self_check()
        return session.set_bits(address, mask)
