"""A simulated RTD2142 ISP engine + XT25F16B flash, implementing rtdisp.Transport.

It models what flashrom's realtek_mst_i2c_spi programmer relies on: ISP mode, the
indexed-register window, the SPI command engine at 0x60.., the page buffer at 0x70,
the read stream, and NOR semantics (erase sets 0xFF, programming only clears bits).
"""

from switch2_hub_patcher import rtdisp


class FakeRTD(rtdisp.Transport):
    name = 'fake'

    def __init__(
        self, flash, chunk=128, status=0x00, ident=rtdisp.XT25F16B_ID, corrupt_program=False
    ):
        self.flash = bytearray(flash)
        self.chunk = chunk
        self.regs = {}
        self.indexed = {}
        self.index_addr = 0
        self.index_state = None
        self.isp = False
        self.buffer = bytearray()
        self.stream = None
        self.status_reg = status
        self.ident = ident
        self.corrupt_program = corrupt_program
        self.erased = []
        self.programmed = 0
        self.selected = None
        self.reset_requested = False

    def _addr(self):
        return (
            (self.regs.get(0x64, 0) << 16) | (self.regs.get(0x65, 0) << 8) | self.regs.get(0x66, 0)
        )

    def write_reg(self, reg, data):
        data = bytes(data)
        self.selected = reg
        if not data:
            return
        if reg == rtdisp.MCU_DATA_PORT:
            self.buffer += data
            return
        value = data[0]
        if reg == rtdisp.MCU_MODE:
            if value == rtdisp.MCU_ISP_MODE_MASK:
                self.isp = True
            elif value == rtdisp.START_WRITE_XFER:
                self._program()
            return
        if not self.isp and reg not in (0xEE,):
            raise OSError(f'register {reg:#x} written outside ISP mode')
        if reg == 0xEE and value & 0x02:
            self.reset_requested = True
        if reg == 0xF4:
            if value == 0x9F:
                self.index_state = 'hi'
            elif self.index_state == 'lo':
                self.index_addr = (self.index_addr << 8) | value
                self.index_state = 'ready'
            return
        if reg == 0xF5:
            if self.index_state == 'hi':
                self.index_addr = value
                self.index_state = 'lo'
            elif self.index_state == 'ready':
                self.indexed[self.index_addr] = value
            return
        self.regs[reg] = value
        if reg == 0x60 and value & 1:
            self._command(value)

    def _command(self, ctrl):
        opcode = self.regs.get(0x61)
        if opcode == rtdisp.JEDEC_RDID:
            for i, byte in enumerate(self.ident):
                self.regs[0x67 + i] = byte
        elif opcode == rtdisp.JEDEC_RDSR:
            self.regs[0x67] = self.status_reg
        elif opcode == rtdisp.JEDEC_SE:
            at = self._addr() & ~0xFFF
            self.flash[at : at + 0x1000] = b'\xff' * 0x1000
            self.erased.append(at)
        elif opcode == 0x03 and ctrl == 0x47:
            self.stream = (self._addr() + 1) & 0xFFFFFF
            self.dummy = True
        self.regs[0x60] = ctrl & ~1

    def _program(self):
        at = self._addr()
        length = self.regs.get(0x71, 127) + 1
        data = self.buffer[:length]
        self.buffer = self.buffer[length:]
        for i, value in enumerate(data):
            byte = value ^ 0x01 if self.corrupt_program and i == 0 else value
            self.flash[at + i] &= byte
        self.programmed += len(data)

    def read_reg(self, reg, n=1):
        self.selected = reg
        if reg == rtdisp.MCU_MODE:
            value = (0x80 if self.isp else 0) | 0x10  # buffer empty, no write busy
            return bytes([value])[:n]
        if reg == 0xF5 and self.index_state == 'ready':
            return bytes([self.indexed.get(self.index_addr, 0)])
        if reg == rtdisp.MCU_DATA_PORT:
            if getattr(self, 'dummy', False):
                self.dummy = False
                return b'\0' * n
            return self.read_more(n)
        return bytes([self.regs.get(reg, 0)])

    def read_more(self, n):
        if self.selected == rtdisp.MCU_DATA_PORT and self.stream is not None:
            data = bytes(self.flash[self.stream : self.stream + n])
            self.stream += n
            return data
        if self.selected is None:
            raise OSError('read before selecting a register')
        return self.read_reg(self.selected, n)
