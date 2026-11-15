"""A minimal 8051 interpreter for executing patch overlays in tests.

It covers only the instructions the overlays use and raises on anything else, so a new
instruction in an overlay fails loudly instead of running wrongly. Code memory is the
assembled overlay; calls to addresses outside it go to Python stubs, which model the
stock firmware routines an overlay relies on. Registers are bank 0 (R0..R7 at 00..07).
"""

ACC, B, PSW, SP, DPL, DPH = 0xE0, 0xF0, 0xD0, 0x81, 0x82, 0x83
CY = 0x80


class Unsupported(Exception):
    pass


class Sim:
    def __init__(self, code, stubs=None):
        self.code = dict(code)
        self.stubs = dict(stubs or {})
        self.xdata = bytearray(0x10000)
        self.iram = bytearray(0x100)
        self.sfr = {SP: 0x60, PSW: 0, ACC: 0, B: 0, DPL: 0, DPH: 0}
        self.bits = set()  # bit-addressable RAM bits 00..7F that are set
        self.calls = []

    # --- registers and flags
    @property
    def a(self):
        return self.sfr[ACC]

    @a.setter
    def a(self, v):
        self.sfr[ACC] = v & 0xFF

    @property
    def c(self):
        return bool(self.sfr[PSW] & CY)

    @c.setter
    def c(self, v):
        self.sfr[PSW] = (self.sfr[PSW] | CY) if v else (self.sfr[PSW] & ~CY & 0xFF)

    @property
    def dptr(self):
        return self.sfr[DPH] << 8 | self.sfr[DPL]

    @dptr.setter
    def dptr(self, v):
        self.sfr[DPH], self.sfr[DPL] = (v >> 8) & 0xFF, v & 0xFF

    def r(self, n):
        return self.iram[n]

    def set_r(self, n, v):
        self.iram[n] = v & 0xFF

    def get_bit(self, bit):
        if bit < 0x80:
            return bit in self.bits
        return bool(self.sfr.get(bit & 0xF8, 0) >> (bit & 7) & 1)

    def set_bit(self, bit, v):
        if bit < 0x80:
            (self.bits.add if v else self.bits.discard)(bit)
            return
        reg = bit & 0xF8
        mask = 1 << (bit & 7)
        self.sfr[reg] = (self.sfr.get(reg, 0) | mask) if v else (self.sfr.get(reg, 0) & ~mask)

    def set_direct(self, addr, v):
        if addr < 0x80:
            self.iram[addr] = v & 0xFF
        else:
            self.sfr[addr] = v & 0xFF

    # --- stack
    def push16(self, v):
        for byte in (v & 0xFF, v >> 8):
            self.sfr[SP] = (self.sfr[SP] + 1) & 0xFF
            self.iram[self.sfr[SP]] = byte

    def pop16(self):
        hi = self.iram[self.sfr[SP]]
        lo = self.iram[(self.sfr[SP] - 1) & 0xFF]
        self.sfr[SP] = (self.sfr[SP] - 2) & 0xFF
        return hi << 8 | lo

    # --- execution
    def fetch(self, pc):
        if pc not in self.code:
            raise Unsupported(f'no code at {pc:04x}')
        return self.code[pc]

    def subb(self, v):
        res = self.a - v - int(self.c)
        self.c = res < 0
        self.a = res

    def add(self, v):
        res = self.a + v
        self.c = res > 0xFF
        self.a = res

    def call(self, target, ret):
        if target in self.stubs:
            self.calls.append(target)
            self.stubs[target](self)
            return ret
        self.push16(ret)
        return target

    def run(self, entry, max_steps=100000):
        """Call entry and run until it returns (the sentinel return address)."""
        sentinel = 0x0000
        self.push16(sentinel)
        pc = entry
        for _ in range(max_steps):
            if pc == sentinel:
                return
            pc = self.step(pc)
        raise RuntimeError('step limit')

    def step(self, pc):  # one branch per opcode
        op = self.fetch(pc)

        def b(i):
            return self.fetch(pc + i)

        def rel(i, length):
            off = b(i)
            return pc + length + (off - 0x100 if off & 0x80 else off)

        if op == 0x90:  # mov dptr,#data16
            self.dptr = b(1) << 8 | b(2)
            return pc + 3
        if op == 0xE0:  # movx a,@dptr
            self.a = self.xdata[self.dptr]
            return pc + 1
        if op == 0xF0:  # movx @dptr,a
            self.xdata[self.dptr] = self.a
            return pc + 1
        if op == 0xA3:  # inc dptr
            self.dptr = (self.dptr + 1) & 0xFFFF
            return pc + 1
        if op == 0x74:  # mov a,#data
            self.a = b(1)
            return pc + 2
        if op == 0xE4:  # clr a
            self.a = 0
            return pc + 1
        if op == 0x04:  # inc a
            self.a = self.a + 1
            return pc + 1
        if op == 0x54:  # anl a,#data
            self.a = self.a & b(1)
            return pc + 2
        if op == 0x44:  # orl a,#data
            self.a = self.a | b(1)
            return pc + 2
        if op == 0x24:  # add a,#data
            self.add(b(1))
            return pc + 2
        if 0x28 <= op <= 0x2F:  # add a,rn
            self.add(self.r(op & 7))
            return pc + 1
        if 0x98 <= op <= 0x9F:  # subb a,rn
            self.subb(self.r(op & 7))
            return pc + 1
        if 0x68 <= op <= 0x6F:  # xrl a,rn
            self.a = self.a ^ self.r(op & 7)
            return pc + 1
        if 0xF8 <= op <= 0xFF:  # mov rn,a
            self.set_r(op & 7, self.a)
            return pc + 1
        if 0xE8 <= op <= 0xEF:  # mov a,rn
            self.a = self.r(op & 7)
            return pc + 1
        if 0x78 <= op <= 0x7F:  # mov rn,#data
            self.set_r(op & 7, b(1))
            return pc + 2
        if op == 0xF5:  # mov direct,a
            self.set_direct(b(1), self.a)
            return pc + 2
        if op == 0x75:  # mov direct,#data
            self.set_direct(b(1), b(2))
            return pc + 3
        if op == 0x33:  # rlc a
            carry = self.a >> 7
            self.a = (self.a << 1) | int(self.c)
            self.c = carry
            return pc + 1
        if op == 0xC3:  # clr c
            self.c = False
            return pc + 1
        if op == 0xD3:  # setb c
            self.c = True
            return pc + 1
        if op == 0xC2:  # clr bit
            self.set_bit(b(1), False)
            return pc + 2
        if op == 0xA2:  # mov c,bit
            self.c = self.get_bit(b(1))
            return pc + 2
        if op == 0xB4:  # cjne a,#data,rel
            v = b(1)
            self.c = self.a < v
            return rel(2, 3) if self.a != v else pc + 3
        if op == 0x60:  # jz
            return rel(1, 2) if self.a == 0 else pc + 2
        if op == 0x70:  # jnz
            return rel(1, 2) if self.a != 0 else pc + 2
        if op == 0x40:  # jc
            return rel(1, 2) if self.c else pc + 2
        if op == 0x50:  # jnc
            return rel(1, 2) if not self.c else pc + 2
        if op == 0x20:  # jb bit,rel
            return rel(2, 3) if self.get_bit(b(1)) else pc + 3
        if op == 0x30:  # jnb bit,rel
            return rel(2, 3) if not self.get_bit(b(1)) else pc + 3
        if op == 0x80:  # sjmp
            return rel(1, 2)
        if op == 0x02:  # ljmp
            target = b(1) << 8 | b(2)
            if target in self.stubs:  # tail call into stock code: run it, then return
                self.calls.append(target)
                self.stubs[target](self)
                return self.pop16()
            return target
        if op == 0x12:  # lcall
            return self.call(b(1) << 8 | b(2), pc + 3)
        if op & 0x1F == 0x11:  # acall
            target = (pc + 2) & 0xF800 | (op >> 5) << 8 | b(1)
            return self.call(target, pc + 2)
        if op == 0x22:  # ret
            return self.pop16()
        raise Unsupported(f'opcode {op:02x} at {pc:04x}')
