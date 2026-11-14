# switch2-hub-patcher

[![CI](https://github.com/doublegate/switch2-hub-patcher/actions/workflows/ci.yml/badge.svg)](https://github.com/doublegate/switch2-hub-patcher/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/doublegate/switch2-hub-patcher)](https://github.com/doublegate/switch2-hub-patcher/releases)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Platforms](https://img.shields.io/badge/platforms-Linux%20%7C%20macOS-lightgrey)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **About this fork.** This is a fork of [mkopec/switch2-hub-patcher](https://github.com/mkopec/switch2-hub-patcher) by the
> author of the patches. It produces byte-identical patched images and adds dump and
> flash tooling for Linux and macOS, offline tests, DP-port HDR/VRR research and
> repository infrastructure. See [CHANGELOG.md](CHANGELOG.md).

Turns one specific USB-C hub, the **Cable Matters 201031-BLK**, into a working
**Nintendo Switch 2 dock**: TV mode, faster docking, and correct **HDR colours** on the
HDMI port.

The patcher works on firmware dumps **you made from your own hub**. It applies small
hash-checked 8051 patches and writes new images. Patching is fully offline, and the
repository contains no vendor firmware. Optional commands dump and flash the hub's two
chips on **Linux and macOS**, and every write is verified. Background and the full
story: <https://blog.nozomi.space/posts/sw2_dock/>.

> **Warning.** Flashing modified firmware can brick the hub. The patches were tested
> on one hub, with one firmware version of each chip and the Switch 2 system software
> of November 2026. You use them at your own risk. Keep your stock dumps, and keep a
> SOIC-8 clip and an SPI programmer within reach.

**Contents:** [What it does](#what-it-does) · [Supported hardware](#supported-hardware) ·
[Requirements](#requirements) · [Usage](#usage) · [Command reference](#command-reference) ·
[Safety model](#safety-model) · [How it is built](#how-it-is-built) ·
[Development](#development) · [Research](#research-dp-port-hdr-and-vrr) ·
[Credits](#credits) · [License](#license)

## What it does

| Chip | Patch | Effect |
| --- | --- | --- |
| VIA **VL103** (USB-PD controller) | Nintendo SVID, modes and vendor-message replies; the official dock's PD3 identity; 15 V / 2.8 A power offer; version-query replies | Switch 2 enters **TV mode** and docks without the ~3 s pause |
| Realtek **RTD2142** (DP→HDMI converter) | HDMI AVI InfoFrame marked BT.2020 whenever PQ/HLG HDR metadata is present; refreshed when HDR turns on or off | Intended: **HDR no longer washed out** on the hub's HDMI port. Upstream validated it in a simulator only. On one hub (2026-11-14) HDR from a Mac looked right, but a Switch 2 gave **no HDMI picture** with HDR on or off; the same Switch worked on an image without it. Treat it as unproven; see the system-version table |

Not fixed, and things to avoid:

- **VRR does not work.** Docked VRR arrived with Switch 2 system update 23.0.0. The
  Switch offers it because the hub now looks like the official dock; **turn VRR off**
  in the Switch settings.
- **Never accept a "Dock Update"** (Settings › System › Dock Update) with the patched
  hub. The hub only replays the official dock's version records. It has no update
  handler, and what the console does on that path is untested.
- **HDR through the hub's DisplayPort port** is still washed out or not offered. See
  [Research](#research-dp-port-hdr-and-vrr).
- **HDR to SDR switching (stock RTD2142 bug).** After a source switches from HDR to SDR
  while connected (for example macOS turning HDR off), the TV can keep re-detecting the
  signal (SDR, HDR, HLG in turn) until the hub is replugged. The stock firmware keeps
  the HDR colorimetry (BT.2020) after the source has moved back to SDR. A fix
  candidate, `rtd2142 --sdr-fix`, is built and tested offline but not yet on a hub; see
  [Research](#research-dp-port-hdr-and-vrr).
- The power patch lowers the hub's own power reserve from 7 W to 3 W. Keep
  power-hungry USB devices off the hub while docked.

The replies to Nintendo's version queries are copied from the official dock. They
are not versions of anything in this hub, and no feature behind those commands is
implemented. Unknown commands still get the stock firmware's "Not supported" reply.

## Supported hardware

**Cable Matters 201031-BLK** USB-C multiport adapter with HDMI, DisplayPort and VGA
(VIA VL817 hub + VL103 PD controller, Realtek RTD2142, XTX XT25F16B flash). Other
models may use different chips or firmware, even from Cable Matters. For example, the
201431-BLK is a 100 W triple-display hub. The patcher only accepts these exact stock
images and refuses anything else:

| Image | Size | Stock SHA-256 | Patched SHA-256 |
| --- | --- | --- | --- |
| VL103 PD firmware 10.48.3.22 | 32 KiB | `3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3` | `6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e` |
| RTD2142 flash | 2 MiB | `17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802` | `f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1` |
| RTD2142 flash, SDR-fix candidate v4 (`--sdr-fix`, not yet tested on a hub) | 2 MiB | same | `390ed39dc2bb2880c0251d63d6889856438c8ec775123c203f77b720740737cd` |

If your dump has a different hash, your hub has different firmware and these patches
don't apply. Please don't force them.

### Switch 2 system versions

Nintendo's console updates can change how the Switch 2 treats a dock: 21.0.0 stopped
video on many third-party docks, and 23.0.0 added docked VRR. Results recorded so far:

| System version | Hub state | Result |
| --- | --- | --- |
| 23.0.1 | VL103 patched (`6b5b0eff…888e`), RTD2142 stock | Works: enters TV mode; docking delay roughly halved (about 1.5 s, judged by eye); HDMI picture good, HDR still somewhat washed out as expected with the RTD2142 stock. Tested with VRR off, no Dock Update, no USB devices on the hub |
| Same console, 2026-11-14 | VL103 patched, RTD2142 patched (`f242d130…42f1`) | **No HDMI picture** with the Switch's HDR setting on or off: the TV detected a signal but showed nothing. Under investigation; the RTD2142 was flashed back to stock. HDR from a Mac through the same hub looked right |
| Same console, 2026-11-14 | VL103 patched, RTD2142 SDR-fix candidate v1 (`f191da0f…8e92`, no BT.2020 patch) | **Works in SDR and HDR.** The first connection needed several replugs and SDR/HDR toggles before a picture appeared; after that it stayed stable, and the next replug came up at once in both modes. HDR colours not assessed; this image has no BT.2020 change, so expect the stock look |

Before you accept a console update, check here, and keep your stock dumps so you can
roll the hub back.

## Requirements

- **Python ≥ 3.9**, standard library only. Patching works on any OS.
- **[SDCC](https://sdcc.sourceforge.net/)** (`sdas8051`, `sdld`) to assemble the
  patches: `apt install sdcc`, `dnf install sdcc` or `brew install sdcc`. SDCC 4.6.0
  reproduces the patches; `switch2-hub-patcher doctor` checks yours.
- **For dumping and flashing**, one of:
  - **Linux** with an AMD/Intel GPU whose DisplayPort AUX shows up as `/dev/i2c-*`. A
    VM won't do for the RTD2142 step. Load `i2c-dev` with `sudo modprobe i2c-dev` if
    `/dev/i2c-*` is missing.
  - **macOS on Apple silicon.** See [macOS](#macos-apple-silicon); reading and
    flashing the RTD2142 both work (2026-11-14).
- **[fwupd](https://github.com/fwupd/fwupd)** with the `vli` plugin for the VL103
  (`brew install fwupd` on macOS). The `vl103-*` commands ship
  `contrib/via-vl817-vl103.quirk`, which binds this hub's generic VIA USB IDs, and use
  it from a private state directory, so nothing is installed system-wide.
- **Optional, Linux:** [flashrom](https://flashrom.org) with the `realtek_mst_i2c_spi`
  programmer and XT25F16B support, for the manual path. Check with
  `flashrom -L | grep XT25F16B` and `flashrom -h`; apply
  `contrib/flashrom-xt25f16b.patch` if the chip is missing. The `rtd-*` commands do
  the same job without flashrom.
- **Strongly recommended:** a SOIC-8 clip and an SPI programmer as a way back from a
  bad flash. Use a CH341A with the 3.3 V fix; the XT25F16B is a 2.7–3.6 V part.

```sh
git clone https://github.com/doublegate/switch2-hub-patcher.git && cd switch2-hub-patcher
pip install .            # or run in place: python3 -m switch2_hub_patcher ...
# or install a release wheel from https://github.com/doublegate/switch2-hub-patcher/releases
```

## Usage

Keep every dump: they are your way back.

### Quick path (Linux or macOS)

Connect the hub's USB-C cable to the computer, with a monitor on the hub's HDMI port.

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

To restore, swap the two images. For example:
`rtd-flash rtd2142-stock.bin --base rtd2142-patched.bin --allow-brick`.

On Linux, run the hardware commands as root (`sudo -E switch2-hub-patcher …`), or
give your user access to the USB device and `/dev/i2c-*`. Use `--bus N` (from
`find-aux`) to pick the I²C bus.

### macOS (Apple silicon)

- **VL103:** uses Homebrew's `fwupd`; version 2.1.9 loads the `vli` plugin and the
  quirk. Whether macOS lets it talk to the hub's VIA controller is unconfirmed until
  the first run.
- **RTD2142:** the `rtd-*` commands port flashrom's `realtek_mst_i2c_spi` protocol
  onto macOS's private IOAVService I²C path, the one DDC/CI brightness tools use.
  Connect the hub to a USB-C/Thunderbolt port with a monitor on the hub, then run
  `switch2-hub-patcher find-aux --probe` to find it.
- Reading and writing work: on 2026-11-14 `rtd-probe` and `rtd-dump` read a stock
  RTD2142 through this path (about 9 minutes per full read; the picture stayed on),
  and `rtd-flash` patched it (about 18 minutes, most of it the two whole-chip reads).
  That is one hub so far, so keep the SOIC-8 clip ready. On macOS, `rtd-flash` still refuses to
  write unless a full read of the chip, made in that same run, matches the base
  image's hash.
- Step by step: [RTD2142 on macOS](docs/macos-rtd2142.md).

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

Find the AUX I²C bus of the hub's connector, and make sure it's the Realtek branch
device. The read-only helper does both and prints the flashrom programmer string:

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

flashrom requires `allow_brick=yes` for all I²C programmers; it confirms that you
checked the bus. To restore, write your own stock dumps back the same way
(`install-blob vl103-stock.bin …`, `flashrom … -w rtd2142-stock.bin`).

## Command reference

| Command | Touches hardware | Purpose |
| --- | --- | --- |
| `vl103 IN OUT [--manifest JSON]` | no | Patch a VL103 dump (six hash-locked steps) |
| `rtd2142 IN OUT [--manifest JSON] [--sdr-fix]` | no | Patch an RTD2142 dump; `--sdr-fix` builds the HDR-to-SDR fix candidate from stock instead |
| `identify FILE…` | no | Stock / patched / partly patched / unknown, with SHA-256 |
| `doctor` | no | SDCC present, and assembling to the 4.6.0 reference output |
| `status` | read-only | Readiness checklist and the next step |
| `guide` | yes, asks first | Interactive dump → patch → flash |
| `find-aux [--probe]` | read-only | Linux: Realtek DP AUX bus. macOS: external display paths (`--probe` asks the ISP) |
| `vl103-devices` | read-only | VIA devices fwupd sees, with the bundled quirk |
| `vl103-dump OUT [--reads N] [--device-id ID]` | read | VL103 dump via fwupd; N dumps must agree (default 2) |
| `vl103-flash TARGET --base BASE --allow-brick` | **write** | Install a known image via fwupd; checks the chip first and reads back after |
| `rtd-probe` | read | Enter ISP mode; flash JEDEC ID and status register |
| `rtd-dump OUT [--reads N]` | read | Whole 2 MiB flash; N reads must agree (default 2) |
| `rtd-flash TARGET --base BASE --allow-brick` | **write** | Rewrite only the changed 4 KiB sectors, verified |
| `rtd-peek ADDR…` | read | Experimental: live XDATA registers over the firmware's 0x35 debug interface; self-checks first, no write commands |
| `rtd-clear-bits ADDR MASK --volatile-ram-write` | RAM | Experiment: clears allow-listed bits (E362 bit 1, 5B07[7:4]) over the debug interface; never flash, undone by unplugging |
| `rtd-set-bits ADDR MASK --volatile-ram-write` | RAM | Experiment: sets allow-listed bits (E10B bit 3, the slow-sink scrambling wait) over the debug interface; never flash, undone by unplugging |
| `survey DUMP` | no | Research: code that touches DP/HDMI colorimetry and VRR registers |

The `rtd-*` commands take `--bus N` (Linux), `--mac-service N` (macOS), `--chunk
{16,32,64,128}` and `--no-reset`. Output files are never overwritten. The RTD2142's
MCU stops video while it is in ISP mode, and the tool resets it afterwards.

`status` and `guide` look for images in the current directory. If a `firmware/`
directory exists there, they use `firmware/stock/` for dumps and `firmware/patched/`
for flashable images (each `.bin` with its `.json` manifest), and `status` also lists
`firmware/*/*.bin`, for example untested builds in `firmware/candidates/`. The
`firmware/` directory is gitignored except for
[`firmware/README.md`](firmware/README.md), which describes the layout and the expected
files.

## Safety model

- **Known images only.** Patch inputs must hash to the supported stock images. Every
  intermediate and final image must match the hash recorded on hardware, so a
  different firmware version or a different assembler output is refused before
  anything is written.
- **Check the chip before writing.** `vl103-flash` and `rtd-flash` accept only the
  known stock and patched images as base and target. They read the live chip first
  and refuse unless it holds `--base`. For the RTD2142 this is a whole-chip read,
  which also proves the I²C path works on that machine.
- **Minimal, verified writes.** `rtd-flash` checks the flash ID (XT25F16B `0b4015`)
  and refuses if block protection is set. It erases and programs only the differing
  4 KiB sectors (the patch touches one, at 0x2F000) and verifies each by reading it
  back, with one retry. It then re-reads the whole chip and requires the target hash.
  `vl103-flash` dumps the chip again after installing and requires the target hash.
- **Explicit consent.** Flashing needs `--allow-brick`. In `guide`, it also needs the
  typed words `flash vl103` or `flash rtd2142`.

## How it is built

Each patch is 8051 assembly (`switch2_hub_patcher/asm/`) plus a Python builder. The
builder checks the exact input hash, the original bytes at every hook, and that the
patch space is erased; for the VL103 it then fixes the CRC-16/USB trailer. The VL103
patch is applied as six consecutive steps, the same ones tested on hardware. Every
intermediate and final image must match the recorded hash, so a different SDCC output
is caught.

```text
switch2_hub_patcher/
  pipeline.py        step tables, hashes, identify, assembler fingerprints
  hexfile.py         SDCC driver + guarded Intel HEX loader
  patch_*.py, build_target_candidate.py   per-step builders (asm/ holds the sources)
  cli.py             command-line interface
  rtdisp.py          RTD2142 ISP protocol (port of flashrom realtek_mst_i2c_spi)
  i2c.py             I²C transports: Linux /dev/i2c-N, macOS IOAVService
  fwupd.py           fwupdtool vli wrapper with the bundled quirk (data/)
  dpaux.py           DP AUX discovery;  status.py / guide.py  checklist, walk-through
  rtd2142_map.py     register names for `survey`
  rtddbg.py          read-only 0x35 debug client for `rtd-peek`
contrib/             fwupd quirk, flashrom XT25F16B patch
research/            DP-port HDR and VRR notes, draft routine, register-DB decoder,
                     RTD2142 symbol map, Ghidra headless scripts (research/ghidra/)
tests/               offline tests (synthetic images, simulated RTD2142 and debug slave)
```

## Development

```sh
python3 -m unittest discover -s tests          # offline, no vendor firmware needed
S2HUB_VL103_DUMP=vl103-stock.bin S2HUB_RTD2142_DUMP=rtd2142-stock.bin \
    python3 -m unittest discover -s tests      # plus the full pipeline on real dumps
ruff check . && ruff format --check .          # lint and format (config in pyproject.toml)
pyright                                         # types (config in pyproject.toml)
```

- `tests/synthetic.py` builds vendor-free 32 KiB and 2 MiB stand-ins that hold only
  the guarded hook bytes and erased caves. With the builders' hash guards mocked,
  every builder runs offline, and its output is pinned for SDCC 4.6.0.
- `tests/fake_rtd.py` simulates the RTD2142 ISP engine and the NOR flash, for the
  dump and flash logic.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the rules (especially: never loosen a hash
check, never commit firmware) and [CHANGELOG.md](CHANGELOG.md) for history.

## Research: DP-port HDR and VRR

[`research/DP_HDR_AND_VRR.md`](research/DP_HDR_AND_VRR.md) collects the groundwork.
It is not part of the patch pipeline.

- **DP-port HDR.** A public register database for the related RTD2172 names the DP
  output's colorimetry registers. That allows the DP 1.4 BT.2020 signalling: the VSC
  SDP colorimetry bytes, with MSA MISC1 bit 6 set. The draft routine is
  `research/dp_hdr_vsc.asm`.
- **VRR.** The same database documents a hardware VRR mode in the DP receiver
  (`vrr_mode`/`deonly_mode`), which may remove the need to rewrite the input lock.
- `survey` finds the matching code in a real dump.
- **From the stock dump (2026-11-14):** the DP output is TX1, the firmware already
  forwards the HDR metadata SDP there and has its own VSC-colorimetry path, which it
  takes only for "extended" input colorimetry. The likely DP-port fix is a hook at
  that gate. For VRR, the receiver runs in full-last-line mode and never enables the
  hardware VRR mode; the fix order is in the notes. The 0x35 live-register debug
  protocol is decoded, and `rtd-peek` uses it. It works on a real chip.
  `research/ghidra/` and `research/rtd2142_symbols.tsv` reproduce the analysis.
- **Live reads (2026-11-14):** the hub's input is DP RX stream 2, not stream 1. The
  HDR-to-SDR re-detect loop is the stock firmware keeping the VSC SDP's BT.2020
  colorimetry after the source clears MSA MISC1 bit 6 (DP 1.4a Table 2-96 makes MISC0
  authoritative then), plus a stale 12-bit HDMI colour depth. `rtd2142 --sdr-fix`
  addresses both.

## Credits

- Patches, reverse engineering and the original tool: Michał Kopeć,
  <https://blog.nozomi.space/posts/sw2_dock/>, upstream repository
  [mkopec/switch2-hub-patcher](https://github.com/mkopec/switch2-hub-patcher).
- The RTD2142 ISP protocol is a port of flashrom's
  [`realtek_mst_i2c_spi`](https://github.com/flashrom/flashrom/blob/main/programmers/realtek_mst_i2c_spi.c)
  programmer.
- Register names: the RTD2172 database in the RTDTool distribution published at
  [roufsweb/portable-display](https://github.com/roufsweb/portable-display).

## License

MIT, see `LICENSE`. This covers the scripts and assembly in this repository only.
Firmware images remain the property of their vendors and are not included.
