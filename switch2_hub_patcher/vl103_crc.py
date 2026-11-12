#!/usr/bin/env python3
"""Verify or fix the trailer checksum of a VIA VL103 PD firmware image.

Image layout (from a 32 KiB fwupd dump of fw 10.48.3.22):
  0x0000..0x7FFD  8051 code/data (LJMP reset vector at 0x0000)
  0x7FFE..0x7FFF  CRC-16/USB of bytes 0x0000..0x7FFD, stored little-endian

Usage:
  vl103_crc.py check IMAGE
  vl103_crc.py fix IMAGE [OUT]     # rewrite the trailer (in place if OUT omitted)
"""
import sys

IMAGE_SIZE = 0x8000


def crc16_usb(data: bytes) -> int:
    # poly 0x8005 reflected (0xA001), init 0xFFFF, xorout 0xFFFF
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc ^ 0xFFFF


def stored_and_computed(img: bytes):
    return int.from_bytes(img[-2:], "little"), crc16_usb(img[:-2])


def main(argv) -> int:
    if len(argv) < 3 or argv[1] not in ("check", "fix"):
        print(__doc__.strip(), file=sys.stderr)
        return 2
    img = open(argv[2], "rb").read()
    if len(img) != IMAGE_SIZE:
        print(f"error: expected {IMAGE_SIZE:#x} bytes, got {len(img):#x}", file=sys.stderr)
        return 1
    stored, computed = stored_and_computed(img)
    if argv[1] == "check":
        ok = stored == computed
        print(f"stored 0x{stored:04X}  computed 0x{computed:04X}  {'OK' if ok else 'MISMATCH'}")
        return 0 if ok else 1
    out = argv[3] if len(argv) > 3 else argv[2]
    open(out, "wb").write(img[:-2] + computed.to_bytes(2, "little"))
    print(f"wrote {out}: checksum 0x{stored:04X} -> 0x{computed:04X}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
