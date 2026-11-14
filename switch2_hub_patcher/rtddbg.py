"""Read-only client for the RTD2142 firmware's debug interface (I2C 0x35 over DP AUX).

The protocol is decoded from the stock firmware and has not been confirmed on a chip
(research/DP_HDR_AND_VRR.md, section 3). Only four commands are ever sent:

  0x55 00     enter debug mode
  0x01 hi     set the XDATA address high byte (any non-table command with low nibble 1)
  0x3A lo     read XDATA[hi:lo] into the reply register; an I2C read returns it
  0x2F 00     leave debug mode

The firmware's write commands (0x3B, 0xBA) are deliberately not implemented. Every session
first reads the debug slave's own address register (FF23), which must hold 0x6A; if it
does not, the decode is wrong for this firmware and nothing is reported.
"""

import contextlib
import time

DEBUG_ADDR = 0x35  # 7-bit; the firmware writes 0x6A (8-bit) to FF23
CMD_ENTER = 0x55
CMD_EXIT = 0x2F
CMD_ADDR_HI = 0x01
CMD_READ = 0x3A
SELF_CHECK = (0xFF23, 0x6A)
READ_ONLY_COMMANDS = frozenset({CMD_ENTER, CMD_EXIT, CMD_ADDR_HI, CMD_READ})
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

    def _send(self, command, value):
        if command not in READ_ONLY_COMMANDS:
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

    def self_check(self):
        address, want = SELF_CHECK
        got = self.read(address)
        if got != want:
            raise DebugError(
                f'debug interface did not answer as decoded ({address:04X} read {got:#04x}, '
                f'expected {want:#04x}); nothing reported'
            )


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
