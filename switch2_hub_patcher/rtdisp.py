"""Realtek MST (RTD2142) ISP over I2C: read, and guarded sector writes, of its SPI flash.

A port of flashrom's realtek_mst_i2c_spi programmer (programmers/realtek_mst_i2c_spi.c)
onto a small transport interface, so the same code drives Linux /dev/i2c-N and the
macOS IOAVService I2C path. Writes are deliberately narrow:

* the whole chip is read first and must hash to a known stock or patched image;
* only the 4 KiB sectors that differ between that image and the target are
  erased and programmed, each verified by read-back;
* the whole chip is read again and must hash to the target.

The target itself must also be a known image, so this can only move between the
stock and patched RTD2142 images that the pipeline produces.
"""

import abc
import hashlib
import time

ISP_ADDR = 0x4A  # 7-bit (0x94 >> 1)
MCU_MODE = 0x6F
MCU_ISP_MODE_MASK = 0x80
START_WRITE_XFER = 0xA0
WRITE_XFER_STATUS_MASK = 0x20
MCU_DATA_PORT = 0x70
MAP_PAGE = (0x64, 0x65, 0x66)  # byte2 (block), byte1 (page), byte0 (byte)
GPIO_CONFIG_ADDRESS = 0x104F
GPIO_VALUE_ADDRESS = 0xFE3F
MAX_WAIT = 1000

FLASH_SIZE = 0x200000
SECTOR = 0x1000
BLOCK = 0x10000

JEDEC_RDID, JEDEC_RDSR, JEDEC_SE = 0x9F, 0x05, 0x20
XT25F16B_ID = bytes.fromhex('0b4015')
STATUS_WIP, STATUS_BP_MASK = 0x01, 0x7C


class ISPError(Exception):
    pass


class Transport(abc.ABC):
    """Byte-level access to the chip at ISP_ADDR.

    write_reg(reg, data): one I2C write of [reg] + data.
    read_reg(reg, n):     select reg, then read n bytes (n <= chunk).
    read_more(n):         read n more bytes from the register selected last.
    """

    chunk = 128
    name = 'transport'

    @abc.abstractmethod
    def write_reg(self, reg: int, data: bytes) -> None: ...

    @abc.abstractmethod
    def read_reg(self, reg: int, n: int = 1) -> bytes: ...

    @abc.abstractmethod
    def read_more(self, n: int) -> bytes: ...

    def close(self):
        """Release the transport; optional, most hold nothing."""
        return None


class RealtekISP:
    def __init__(self, transport, log=print, reset_mcu=True):
        self.t = transport
        self.log = log
        self.reset_mcu = reset_mcu
        self.active = False

    # register helpers (flashrom: write_register / read_register / indexed)
    def wr(self, reg, value):
        self.t.write_reg(reg, bytes([value]))

    def rd(self, reg):
        return self.t.read_reg(reg, 1)[0]

    def wait(self, reg, mask, target, multiplier=1):
        for _ in range(MAX_WAIT * multiplier):
            if self.rd(reg) & mask == target:
                return
        raise ISPError(f'timeout waiting for reg {reg:#04x} & {mask:#04x} == {target:#04x}')

    def select_indexed(self, address):
        self.wr(0xF4, 0x9F)
        self.wr(0xF5, address >> 8)
        self.wr(0xF4, address & 0xFF)

    def write_indexed(self, address, value):
        self.select_indexed(address)
        self.wr(0xF5, value)

    def read_indexed(self, address):
        self.select_indexed(address)
        return self.rd(0xF5)

    # session
    def mcu_mode(self):
        return self.rd(MCU_MODE)

    def enter(self):
        self.wr(MCU_MODE, MCU_ISP_MODE_MASK)
        self.wait(MCU_MODE, MCU_ISP_MODE_MASK, MCU_ISP_MODE_MASK)
        self.active = True
        self.wr(0xF4, 0x9F)  # internal oscillator divider to default (0x06A0 = 0x74)
        self.wr(0xF5, 0x06)
        self.wr(0xF4, 0xA0)
        self.wr(0xF5, 0x74)
        self.gpio88(True)

    def gpio88(self, value):
        config = self.read_indexed(GPIO_CONFIG_ADDRESS)
        self.write_indexed(GPIO_CONFIG_ADDRESS, (config & 0xF0) | 0x01)
        current = self.read_indexed(GPIO_VALUE_ADDRESS)
        self.write_indexed(GPIO_VALUE_ADDRESS, (current & 0xFE) | int(value))

    def leave(self):
        if not self.active:
            return
        try:
            self.gpio88(False)
        finally:
            self.active = False
            if self.reset_mcu:
                try:  # flashrom ignores the result: the MCU may not answer while resetting
                    if self.mcu_mode() & MCU_ISP_MODE_MASK:
                        value = self.rd(0xEE)
                        self.wr(0xEE, (value & 0xFD) | 0x02)
                except (OSError, ISPError):
                    pass

    def __enter__(self):
        self.enter()
        return self

    def __exit__(self, *_exc):
        self.leave()
        self.t.close()

    # SPI commands (flashrom: realtek_mst_i2c_spi_send_command)
    def command(self, opcode, args=b'', readcnt=0):
        if len(args) > 3 or readcnt > 3:
            raise ISPError('command too long for the ISP engine')
        ctrl = (len(args) << 3) | (readcnt << 1)
        multiplier = 1
        if opcode == JEDEC_SE:
            ctrl |= 0x20 | (4 << 5)
        else:
            ctrl |= 2 << 5
        self.wr(0x60, ctrl)
        self.wr(0x61, opcode)
        for i, byte in enumerate(args):
            self.wr(0x64 + i, byte)
        self.wr(0x60, ctrl | 1)
        self.wait(0x60, 0x01, 0, multiplier)
        return bytes(self.rd(0x67 + i) for i in range(readcnt))

    def rdid(self):
        return self.command(JEDEC_RDID, readcnt=3)

    def status(self):
        return self.command(JEDEC_RDSR, readcnt=1)[0]

    def wait_idle(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while self.status() & STATUS_WIP:
            if time.monotonic() > deadline:
                raise ISPError('flash stayed busy (WIP) too long')

    def map_page(self, address):
        for reg, shift in zip(MAP_PAGE, (16, 8, 0)):
            self.wr(reg, (address >> shift) & 0xFF)

    # bulk read (flashrom: realtek_mst_i2c_spi_read); start must be 256-aligned
    def read(self, start, length, progress=None):
        if start & 0xFF:
            raise ISPError('read start must be 256-byte aligned')
        self.wr(0x60, 0x46)
        self.wr(0x61, 0x03)
        self.map_page((start - 1) & 0xFFFFFF)
        self.wr(0x6A, 0x03)
        self.wr(0x60, 0x47)
        self.wait(0x60, 0x01, 0)
        self.t.read_reg(MCU_DATA_PORT, 1)  # leading dummy byte
        out = bytearray()
        while len(out) < length:
            n = min(self.t.chunk, length - len(out))
            out += self.t.read_more(n)
            if progress:
                progress(len(out))
        return bytes(out)

    def read_range(self, start, length, progress=None):
        out = bytearray()
        for at in range(start, start + length, BLOCK):
            out += self.read(at, min(BLOCK, start + length - at))
            if progress:
                progress(len(out))
        return bytes(out)

    def erase_sector(self, address):
        if address % SECTOR:
            raise ISPError('sector address not aligned')
        self.command(JEDEC_SE, bytes([(address >> 16) & 0xFF, (address >> 8) & 0xFF, 0]))
        self.wait_idle()

    # page program (flashrom: realtek_mst_i2c_spi_write_256), in transport-sized pieces
    def program(self, address, data):
        if address & 0xFF:
            raise ISPError('program start must be 256-byte aligned')
        piece = min(self.t.chunk, 128)
        self.wr(0x6D, 0x02)
        self.wr(0x71, piece - 1)
        for i in range(0, len(data), piece):
            part = data[i : i + piece]
            if len(part) != piece:
                self.wr(0x71, len(part) - 1)
            self.map_page(address + i)
            self.wait(MCU_MODE, 0x10, 0x10)  # buffer empty
            self.t.write_reg(MCU_DATA_PORT, bytes(part))
            self.wr(MCU_MODE, START_WRITE_XFER)
            self.wait(MCU_MODE, WRITE_XFER_STATUS_MASK, 0)
        self.wait_idle()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def changed_sectors(base, target):
    if len(base) != len(target):
        raise ISPError('images differ in size')
    return sorted({i // SECTOR * SECTOR for i in range(len(base)) if base[i] != target[i]})


def check_chip(isp):
    """RDID and block protection; returns the status register."""
    ident = isp.rdid()
    if ident != XT25F16B_ID:
        raise ISPError(
            f'unexpected flash ID {ident.hex()} (XT25F16B is {XT25F16B_ID.hex()}); '
            'wrong device or the I2C path does not work'
        )
    status = isp.status()
    return status


def dump(isp, progress=None):
    check_chip(isp)
    return isp.read_range(0, FLASH_SIZE, progress)


def flash(isp, base, target, known, log=print, progress=None):
    """Move the chip from image `base` to image `target` (both in `known`, sha -> label)."""
    for image, role in ((base, 'base'), (target, 'target')):
        if len(image) != FLASH_SIZE or sha256(image) not in known:
            raise ISPError(f'{role} image is not a known RTD2142 stock/patched image')
    sectors = changed_sectors(base, target)
    if not sectors:
        log('nothing to do: base and target are identical')
        return []
    status = check_chip(isp)
    if status & STATUS_BP_MASK:
        raise ISPError(
            f'flash status {status:#04x}: block protection is set; not unlocking it '
            'here (use flashrom on Linux)'
        )
    log('reading the whole chip to prove the read path and the current content...')
    live = isp.read_range(0, FLASH_SIZE, progress)
    if sha256(live) != sha256(base):
        raise ISPError(f'chip content {sha256(live)} is not the base image; nothing written')
    log(
        f'chip matches {known[sha256(base)]}; rewriting {len(sectors)} sector(s): '
        + ', '.join(f'{s:#08x}' for s in sectors)
    )
    for sector in sectors:
        want = target[sector : sector + SECTOR]
        for attempt in (1, 2):
            isp.erase_sector(sector)
            isp.program(sector, want)
            got = isp.read(sector, SECTOR)
            if got == want:
                log(f'  ok  {sector:#08x}')
                break
            log(f'  verify failed at {sector:#08x} (attempt {attempt})')
        else:
            raise ISPError(
                f'sector {sector:#08x} did not verify. DO NOT power-cycle the hub; '
                'rerun the same command, or write the base image back with the '
                'same tool or flashrom (SOIC-8 clip as last resort)'
            )
    log('re-reading the whole chip...')
    final = isp.read_range(0, FLASH_SIZE, progress)
    if sha256(final) != sha256(target):
        raise ISPError(
            f'final chip content {sha256(final)} is not the target image; '
            'do not power-cycle; rerun the command'
        )
    log(f'chip now holds {known[sha256(target)]}')
    return sectors
