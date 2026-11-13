# switch2-hub-patcher

Offline patcher that turns one specific USB-C hub, the **Cable Matters 201031-BLK**,
into a working **Nintendo Switch 2 dock**: TV mode, faster docking and correct **HDR colours** on the HDMI port.

It takes firmware dumps **you made from your own hub**, applies small hash-checked
patches and writes new images. It never talks to hardware and contains no vendor
firmware. Background and the full story: <https://blog.nozomi.space/posts/sw2_dock/>.

> **Warning.** Flashing modified firmware can brick the hub. This was tested on one
> hub, with one firmware version of each chip and the Switch 2 system software of
> November 2026. You use it at your own risk.

## What it does

| Chip | Patch | Effect |
|---|---|---|
| VIA **VL103** (USB-PD controller) | Nintendo SVID, modes and vendor-message replies; the official dock's PD3 identity; 15 V / 2.8 A power offer; version-query replies | Switch 2 enters **TV mode** and docks without the ~3 s pause |
| Realtek **RTD2142** (DP→HDMI converter) | HDMI AVI InfoFrame marked BT.2020 whenever PQ/HLG HDR metadata is present; refreshed on HDR on/off | **HDR no longer washed out** on the hub's HDMI port |

Not fixed:
- **VRR does not work.** The Switch offers it (docked VRR arrived with system
  update 23.0.0) because the hub now looks like the official dock; **turn VRR off**
  in the Switch settings.
- **Never accept a "Dock Update"** (Settings › System › Dock Update) with the
  patched hub. The hub only replays the official dock's version records; it has no
  update handler, and what the console does on that path is untested.
- **HDR through the hub's DisplayPort port** is still washed out / not offered.
- The power patch lowers the hub's own power reserve from 7 W to 3 W. Keep
  power-hungry USB devices off the hub while docked.

The replies to Nintendo's version queries are copied from the official dock; they
are not versions of anything in this hub, and no feature behind those commands is
implemented. Unknown commands still get the stock firmware's "Not supported" reply.

## Supported hardware

**Cable Matters 201031-BLK** USB-C multiport adapter with HDMI, DisplayPort and VGA
(VIA VL817 hub + VL103 PD controller, Realtek RTD2142, XTX XT25F16B flash). Other
models, even from Cable Matters, may use different chips or firmware. The patcher only accepts
these exact stock images and refuses anything else:

| Image | Size | Stock SHA-256 | Patched SHA-256 |
|---|---|---|---|
| VL103 PD firmware 10.48.3.22 | 32 KiB | `3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3` | `6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e` |
| RTD2142 flash | 2 MiB | `17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802` | `f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1` |

If your dump has a different hash, your hub has different firmware and these
patches don't apply. Please don't force them.

## Requirements

- Python ≥ 3.9. Patching works on any OS. Dumping and flashing work on **Linux**
  (AMD/Intel GPU) and on **macOS on Apple silicon** (see "macOS" below); a VM
  will not do for the RTD2142 step
- [SDCC](https://sdcc.sourceforge.net/) (`sdas8051`, `sdld`) to assemble the patches
  (`apt install sdcc`, `dnf install sdcc`, `brew install sdcc`). SDCC 4.6.0 is
  known to reproduce the patches; `switch2-hub-patcher doctor` checks yours
- [fwupd](https://github.com/fwupd/fwupd) with the `vli` plugin (`brew install fwupd`
  on macOS). The `vl103-*` commands bring their own copy of
  `contrib/via-vl817-vl103.quirk` (binds this hub's generic VIA USB IDs) in a
  private state directory, so nothing is installed system-wide
- Optional on Linux: [flashrom](https://flashrom.org) with the `realtek_mst_i2c_spi`
  programmer (the `rtd-*` commands do the same job without it) and
  XT25F16B support (`contrib/flashrom-xt25f16b.patch` if your flashrom lacks it)
  (`flashrom -L | grep XT25F16B`; `realtek_mst_i2c_spi` must be in the
  programmer list of `flashrom -h`)
- An AMD/Intel GPU whose DisplayPort AUX shows up as `/dev/i2c-*` for the RTD2142
  step (connect the hub to the PC like a monitor hub; load `i2c-dev` with
  `sudo modprobe i2c-dev` if `/dev/i2c-*` is missing)
- Strongly recommended: a SOIC-8 clip and an SPI programmer (CH341A with the 3.3 V
  fix; the XT25F16B is a 2.7-3.6 V part) as a way back from a bad flash

```sh
pip install .            # or run in place: python3 -m switch2_hub_patcher ...
```

## Usage

Keep every dump: they are your way back.

### Quick path (Linux or macOS)

```sh
switch2-hub-patcher status     # tools, hub, images found here, and the next step
switch2-hub-patcher guide      # interactive: dump, patch, flash; asks before each step
```

Or step by step:

```sh
switch2-hub-patcher vl103-dump vl103-stock.bin            # two fwupd dumps that must agree
switch2-hub-patcher rtd-dump rtd2142-stock.bin            # two full reads that must agree
switch2-hub-patcher vl103 vl103-stock.bin vl103-patched.bin --manifest vl103-patched.json
switch2-hub-patcher rtd2142 rtd2142-stock.bin rtd2142-patched.bin
switch2-hub-patcher vl103-flash vl103-patched.bin --base vl103-stock.bin --allow-brick
# unplug and replug the hub
switch2-hub-patcher rtd-flash rtd2142-patched.bin --base rtd2142-stock.bin --allow-brick
```

Each flash command works the same way. It refuses unless both images are the
known stock/patched ones. It then reads the chip and requires that it holds the
`--base` image, and only after that does it write. When the write finishes, it
reads the chip back and compares it with the target. `rtd-flash` only rewrites
the 4 KiB sector that the patch touches. To restore, swap the two files:
`rtd-flash rtd2142-stock.bin --base rtd2142-patched.bin --allow-brick`.
On Linux, run these commands as root (`sudo -E ...`), or give your user access to
the USB device and `/dev/i2c-*`. On Linux, `--bus N` (from `find-aux`) picks the
I²C bus.

### macOS (Apple silicon)

- VL103: Homebrew's `fwupd` (2.1.9 tested to load the `vli` plugin and the quirk).
  Whether macOS lets it talk to the hub's VIA controller is unconfirmed until the
  first run.
- RTD2142: the `rtd-*` commands port flashrom's `realtek_mst_i2c_spi` protocol onto
  macOS's private IOAVService I²C path, the one DDC/CI brightness tools use.
  Connect the hub to a USB-C/Thunderbolt port with a monitor on the hub, then run
  `switch2-hub-patcher find-aux --probe` to find it.
- That path is new and has not been tested on this chip. **Start with
  `rtd-probe` and `rtd-dump`, and compare the dump with a Linux dump if you can.**
  Do your first write on Linux with flashrom or `rtd-flash` and keep the SOIC-8
  clip ready. `rtd-flash` on macOS still refuses to write unless a full read of
  the chip, made in that same run, matches the base image's hash.

### Manual path (Linux, fwupdtool + flashrom)

#### 1. VL103 (TV mode)

```sh
sudo cp contrib/via-vl817-vl103.quirk /var/lib/fwupd/quirks.d/
sudo systemctl restart fwupd
fwupdtool get-devices --plugins vli          # note the VL103 device ID

sudo fwupdtool --plugins vli firmware-dump vl103-stock.bin <VL103-device-id>
switch2-hub-patcher vl103 vl103-stock.bin vl103-patched.bin
sudo fwupdtool --plugins vli --allow-reinstall --prepare --cleanup \
     install-blob vl103-patched.bin <VL103-device-id>
sudo fwupdtool --plugins vli firmware-dump vl103-readback.bin <VL103-device-id>
cmp vl103-patched.bin vl103-readback.bin
```

Unplug and replug the hub (power cycle) afterwards.

#### 2. RTD2142 (HDR colours)

Connect the hub's USB-C cable to the PC, with a monitor on the hub. Find the AUX
I²C bus of that connector and make sure it's the Realtek branch device. The
read-only helper does both and prints the flashrom programmer string:

```sh
sudo modprobe i2c-dev
sudo switch2-hub-patcher find-aux
```

or by hand:

```sh
ls -d /sys/class/drm/card*-DP-*/i2c-*                      # e.g. .../card1-DP-1/i2c-7
sudo dd if=/dev/drm_dp_aux0 bs=1 skip=$((0x500)) count=3 status=none | xxd -p   # 00e04c
```

Then (replace `bus=7`):

```sh
P=realtek_mst_i2c_spi:bus=7,allow_brick=yes,reset_mcu=1
sudo flashrom -p $P -r rtd2142-stock.bin
sudo flashrom -p $P -r rtd2142-stock-2.bin && cmp rtd2142-stock.bin rtd2142-stock-2.bin
switch2-hub-patcher rtd2142 rtd2142-stock.bin rtd2142-patched.bin
sudo flashrom -p $P -w rtd2142-patched.bin
```

`allow_brick=yes` is required by flashrom for all I²C programmers; it confirms that
you checked the bus. A SOIC-8 clip and an SPI programmer are a good safety net.

### Restoring

Write your own stock dumps back the same way (`install-blob vl103-stock.bin …`,
`flashrom … -w rtd2142-stock.bin`).

### Checking files

```sh
switch2-hub-patcher doctor            # SDCC present and assembling as expected
switch2-hub-patcher identify *.bin    # stock / patched / partly patched / unknown
```

Add `--manifest vl103-patched.json` to `vl103` or `rtd2142` to also record every
changed byte of every step, with the assembler version used.

`switch2-hub-patcher survey rtd2142-stock.bin` is a read-only research aid: it
lists the code that touches the DP/HDMI colorimetry and VRR registers (see
`research/DP_HDR_AND_VRR.md`).

## How it is built

Each patch is 8051 assembly (`switch2_hub_patcher/asm/`) plus a Python builder that
checks the exact input hash, the original bytes at every hook and that the patch
space is erased, then fixes the VL103 CRC-16. The VL103 patch is applied as six
consecutive steps, the same ones tested on hardware; every intermediate and final
image must match the recorded hash, so a different SDCC output is caught.

The tests run offline: synthetic images that contain no vendor code exercise
every builder, with their outputs pinned for SDCC 4.6.0. With real dumps, the full
pipeline is checked against the hardware-tested hashes:

```sh
python3 -m unittest discover -s tests
S2HUB_VL103_DUMP=vl103-stock.bin S2HUB_RTD2142_DUMP=rtd2142-stock.bin \
    python3 -m unittest discover -s tests
```

## License

MIT, see `LICENSE`. This covers the scripts and assembly in this repository only.
Firmware images remain the property of their vendors and are not included.
