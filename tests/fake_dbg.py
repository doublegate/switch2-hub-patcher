"""A simulated RTD2142 debug slave (I2C 0x35), implementing rtdisp.Transport.

It follows the stock firmware as decoded in research/DP_HDR_AND_VRR.md section 3: the
first byte of a write is the command, commands run only with at least one data byte,
0x55 enters debug mode, and outside debug mode everything is ignored. Every command is
logged so tests can prove that the client never sent a write command.
"""

from switch2_hub_patcher import rtdisp

TABLE = {0x2F, 0x3A, 0x3B, 0x41, 0x44, 0x45, 0x7A, 0x80, 0xBA, 0xBB, 0xC9, 0xCA}


class FakeDebugSlave(rtdisp.Transport):
    name = 'fake-debug'
    chunk = 32

    def __init__(self, xdata=None, slave_address=0x6A):
        self.xdata = dict(xdata or {})
        self.xdata.setdefault(0xFF23, slave_address)
        self.debug = False
        self.addr_hi = 0
        self.wdata = 0
        self.tx = 0xFF
        self.log = []

    def write_reg(self, reg, data):
        data = bytes(data)
        self.log.append((reg, data))
        if not data:
            return  # sub-address only (the write half of a read): no command runs
        value = data[0]
        if reg == 0x55:
            self.debug = True
        elif not self.debug:
            return
        elif reg == 0x2F:
            self.debug = False
        elif reg == 0x3A:
            self.tx = self.xdata.get((self.addr_hi << 8) | value, 0x00)
        elif reg == 0x3B:
            self.xdata[(self.addr_hi << 8) | value] = self.wdata
        elif reg not in TABLE and reg & 0x0F in (1, 2):
            self.addr_hi = value
        elif reg not in TABLE and reg & 0x0F in (3, 6):
            self.wdata = value

    def read_reg(self, reg, n=1):
        self.log.append((reg, b''))
        return bytes([self.tx]) * n

    def read_more(self, n):
        return bytes([self.tx]) * n
