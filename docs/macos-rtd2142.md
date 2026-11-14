# RTD2142 on macOS (Apple silicon): dump, patch, flash

This guide covers the RTD2142 step (HDR colours on the hub's HDMI port) on a Mac.
The RTD2142 is reached over the hub's DisplayPort input, not over USB, so the
computer has to drive a display through the hub. A Mac can. A desktop whose only
display output is a discrete GPU without a USB-C DisplayPort port cannot.

The macOS path (the `rtd-*` commands over the private IOAVService I²C interface) is
**untested on this chip**. Steps 1 to 4 are read-only or offline. Step 5 writes
flash; read the cautions there first.

## 1. Set up

The tool uses only the Python standard library, so it runs from a checkout without
installing anything else.

```sh
brew install sdcc
git clone https://github.com/doublegate/switch2-hub-patcher.git
cd switch2-hub-patcher
python3 -m switch2_hub_patcher doctor
```

`doctor` must report that the assembled patches match the SDCC 4.6.0 reference. If
Homebrew installs a different SDCC version, the patch step refuses to build (the
output would not match the hardware-tested image), but dumping still works.

## 2. Connect the hub and confirm a picture

Plug the hub's USB-C cable into a Thunderbolt/USB-C port on the Mac, and a monitor
into the hub's HDMI port. Confirm that macOS shows the external display before going
further. If you already flashed the VL103 patch, this also confirms the hub still
works as a normal DisplayPort hub for a computer.

## 3. Find the hub and read the chip (read-only)

```sh
python3 -m switch2_hub_patcher find-aux --probe
python3 -m switch2_hub_patcher rtd-probe --mac-service N
python3 -m switch2_hub_patcher rtd-dump rtd2142-stock.bin --mac-service N
python3 -m switch2_hub_patcher identify rtd2142-stock.bin
```

- `N` is the external display path index that `find-aux --probe` reports for the
  Realtek ISP (default 0).
- `rtd-probe` must print `flash ID 0b4015 (XT25F16B)` and a `status register` line
  without `block protection set` after it.
- The monitor may blank briefly while the chip is in ISP mode; the tool resets the
  hub MCU when it is done.
- `rtd-dump` reads the full 2 MiB twice and requires both reads to match. macOS
  transfers 32 bytes at a time by default (`--chunk`), so expect it to take a while.
- `identify` must report RTD2142 stock,
  `17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802`. Any other hash
  means different firmware: stop, the patch does not apply.
- Try without `sudo` first.

**Keep `rtd2142-stock.bin` safe, and copy it off the Mac.** It is the only way back
to stock. Never commit it: dumps are vendor firmware (`*.bin` is gitignored).

## 4. Patch offline

```sh
python3 -m switch2_hub_patcher rtd2142 rtd2142-stock.bin rtd2142-patched.bin
python3 -m switch2_hub_patcher identify rtd2142-patched.bin
S2HUB_RTD2142_DUMP="$PWD/rtd2142-stock.bin" python3 -m unittest tests.test_pipeline.DumpTests.test_rtd2142
```

`identify` must report RTD2142 patched,
`f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1`, the image tested on
hardware. A real dump passing this step is also what confirms the RTD2142 entry of
the SDCC 4.6.0 overlay digests in `pipeline.py`; please report it (hashes only) with
the Hardware report issue template.

## 5. Flash (writes the chip)

Before writing:

- Have a **SOIC-8 clip and an SPI programmer** (for example a CH341A) on hand. If a
  write leaves the RTD2142 unresponsive over I²C, that is the only recovery.
- The README advises doing the first RTD2142 write on Linux. If you write from
  macOS, you are the first to do so on this chip.

```sh
python3 -m switch2_hub_patcher rtd-flash rtd2142-patched.bin --base rtd2142-stock.bin --allow-brick --mac-service N
```

`rtd-flash` refuses to write unless a full read of the chip, made in that same run,
matches `--base`. It checks the flash ID and block protection, rewrites only the
changed 4 KiB sector (at 0x2F000), verifies it by reading it back, then re-reads the
whole chip and requires the patched hash.

To restore stock, swap the images:

```sh
python3 -m switch2_hub_patcher rtd-flash rtd2142-stock.bin --base rtd2142-patched.bin --allow-brick --mac-service N
```

After flashing, test HDR on the hub's HDMI port. Keep VRR off and never accept a
Switch 2 "Dock Update" with the patched hub (see the README).
