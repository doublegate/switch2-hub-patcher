"""I2C transports for rtdisp: Linux /dev/i2c-N and macOS IOAVService (Apple silicon)."""
import ctypes
import os
import platform
import time

from .rtdisp import ISP_ADDR, Transport

I2C_SLAVE = 0x0703


class LinuxI2C(Transport):
    """Plain I2C on a DP AUX adapter, exactly as flashrom uses it."""

    def __init__(self, bus, address=ISP_ADDR, chunk=128):
        import fcntl
        self.name = f'/dev/i2c-{bus}'
        self.fd = os.open(self.name, os.O_RDWR)
        fcntl.ioctl(self.fd, I2C_SLAVE, address)
        self.chunk = chunk

    def write_reg(self, reg, data):
        payload = bytes([reg]) + bytes(data)
        if os.write(self.fd, payload) != len(payload):
            raise OSError('short I2C write')

    def read_reg(self, reg, n=1):
        self.write_reg(reg, b'')
        return self.read_more(n)

    def read_more(self, n):
        data = os.read(self.fd, n)
        if len(data) != n:
            raise OSError('short I2C read')
        return data

    def close(self):
        os.close(self.fd)


# macOS -------------------------------------------------------------------------

_LIBS = {}


def _frameworks():
    """(CoreFoundation, IOKit) with argument/return types declared; loaded once."""
    if not _LIBS:
        _LIBS['cf'] = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.'
                                              'framework/CoreFoundation')
        _LIBS['iokit'] = ctypes.cdll.LoadLibrary('/System/Library/Frameworks/IOKit.framework/'
                                                 'IOKit')
        _declare(_LIBS['cf'], _LIBS['iokit'])
    return _LIBS['cf'], _LIBS['iokit']


def _declare(cf, iokit):
    vp, u32 = ctypes.c_void_p, ctypes.c_uint32
    cf.CFStringCreateWithCString.restype = vp
    cf.CFStringCreateWithCString.argtypes = [vp, ctypes.c_char_p, u32]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [vp, ctypes.c_char_p, ctypes.c_long, u32]
    cf.CFGetTypeID.restype = ctypes.c_ulong
    cf.CFGetTypeID.argtypes = [vp]
    cf.CFStringGetTypeID.restype = ctypes.c_ulong
    cf.CFDataGetLength.restype = ctypes.c_long
    cf.CFDataGetLength.argtypes = [vp]
    cf.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
    cf.CFDataGetBytePtr.argtypes = [vp]
    cf.CFRelease.argtypes = [vp]
    iokit.IOServiceMatching.restype = vp
    iokit.IOServiceMatching.argtypes = [ctypes.c_char_p]
    iokit.IOServiceGetMatchingServices.argtypes = [u32, vp, ctypes.POINTER(u32)]
    iokit.IOIteratorNext.restype = u32
    iokit.IOIteratorNext.argtypes = [u32]
    iokit.IOObjectRelease.argtypes = [u32]
    iokit.IORegistryEntryCreateCFProperty.restype = vp
    iokit.IORegistryEntryCreateCFProperty.argtypes = [u32, vp, vp, u32]
    iokit.IORegistryEntryGetRegistryEntryID.argtypes = [u32, ctypes.POINTER(ctypes.c_uint64)]
    iokit.IOAVServiceCreateWithService.restype = vp
    iokit.IOAVServiceCreateWithService.argtypes = [vp, u32]
    for name in ('IOAVServiceReadI2C', 'IOAVServiceWriteI2C'):
        fn = getattr(iokit, name)
        fn.restype = ctypes.c_int
        fn.argtypes = [vp, u32, u32, vp, u32]
    iokit.IOAVServiceCopyEDID.restype = ctypes.c_int
    iokit.IOAVServiceCopyEDID.argtypes = [vp, ctypes.POINTER(vp)]


def _cfstr(text):
    cf, _ = _frameworks()
    return cf.CFStringCreateWithCString(None, text.encode(), 0x08000100)


def _string_property(entry, key):
    cf, iokit = _frameworks()
    name = _cfstr(key)
    value = iokit.IORegistryEntryCreateCFProperty(entry, name, None, 0)
    cf.CFRelease(name)
    if not value:
        return None
    try:
        if cf.CFGetTypeID(value) != cf.CFStringGetTypeID():
            return None
        buf = ctypes.create_string_buffer(256)
        return buf.value.decode() if cf.CFStringGetCString(value, buf, 256, 0x08000100) else None
    finally:
        cf.CFRelease(value)


def edid_name(edid):
    for at in range(54, 126, 18):
        block = edid[at:at + 18]
        if len(block) == 18 and block[:3] == b'\0\0\0' and block[3] == 0xFC:
            return block[5:].split(b'\n')[0].decode('ascii', 'replace').strip()
    return None


def mac_services():
    """External DCPAVServiceProxy entries: [{index, entry, registry_id, display}]."""
    if platform.system() != 'Darwin':
        return []
    cf, iokit = _frameworks()
    iterator = ctypes.c_uint32()
    if iokit.IOServiceGetMatchingServices(0, iokit.IOServiceMatching(b'DCPAVServiceProxy'),
                                          ctypes.byref(iterator)):
        return []
    found = []
    while True:
        entry = iokit.IOIteratorNext(iterator)
        if not entry:
            break
        if _string_property(entry, 'Location') != 'External':
            iokit.IOObjectRelease(entry)
            continue
        rid = ctypes.c_uint64()
        iokit.IORegistryEntryGetRegistryEntryID(entry, ctypes.byref(rid))
        record = {'index': len(found), 'entry': entry, 'registry_id': rid.value, 'display': None}
        service = iokit.IOAVServiceCreateWithService(None, entry)
        if service:
            data = ctypes.c_void_p()
            if iokit.IOAVServiceCopyEDID(service, ctypes.byref(data)) == 0 and data.value:
                n = cf.CFDataGetLength(data)
                record['display'] = edid_name(bytes(cf.CFDataGetBytePtr(data)[:n]))
                cf.CFRelease(data)
            cf.CFRelease(service)
        found.append(record)
    iokit.IOObjectRelease(iterator.value)
    return found


class MacAVI2C(Transport):
    """I2C through IOAVService (DCP) on an external DP/USB-C display path.

    IOAVServiceWriteI2C(chip, a, buf, n) sends [a] + buf; IOAVServiceReadI2C(chip, a,
    buf, n) selects a and reads n bytes. Both are private, undocumented APIs; reads
    of the data port are re-addressed to it on every chunk, which is why a whole-chip
    read must hash to a known image before rtdisp will write anything.
    """

    def __init__(self, index=0, address=ISP_ADDR, chunk=32, delay=0.001, retries=3):
        services = mac_services()
        if index >= len(services):
            raise OSError(f'no external display service #{index} (found {len(services)}); '
                          'connect the hub to the Mac with a monitor on the hub')
        _, iokit = _frameworks()
        self.iokit = iokit
        self.service = iokit.IOAVServiceCreateWithService(None, services[index]['entry'])
        if not self.service:
            raise OSError('IOAVServiceCreateWithService failed')
        self.name = f"IOAVService #{index} ({services[index]['display'] or 'unknown display'})"
        self.address, self.chunk, self.delay, self.retries = address, chunk, delay, retries
        self.selected = None

    def _call(self, fn, sub, buf, n):
        for _ in range(self.retries):
            if fn(self.service, self.address, sub, buf, n) == 0:
                if self.delay:
                    time.sleep(self.delay)
                return
            time.sleep(0.01)
        raise OSError(f'IOAVService I2C transfer failed (chip {self.address:#04x}, reg {sub:#04x})')

    def write_reg(self, reg, data):
        data = bytes(data)
        buf = ctypes.create_string_buffer(data, max(len(data), 1))
        self._call(self.iokit.IOAVServiceWriteI2C, reg, buf, len(data))
        self.selected = reg

    def read_reg(self, reg, n=1):
        buf = ctypes.create_string_buffer(n)
        self._call(self.iokit.IOAVServiceReadI2C, reg, buf, n)
        self.selected = reg
        return buf.raw[:n]

    def read_more(self, n):
        if self.selected is None:
            raise OSError('read_more before selecting a register')
        return self.read_reg(self.selected, n)

    def close(self):
        if self.service:
            _frameworks()[0].CFRelease(self.service)
            self.service = None
