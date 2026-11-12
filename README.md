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
- **VRR does not work.** The Switch offers it because the hub now looks like the
  official dock; **turn VRR off** in the Switch settings.
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

- Linux, Python ≥ 3.9
- [SDCC](https://sdcc.sourceforge.net/) (`sdas8051`, `sdld`) to assemble the patches
- [fwupd](https://github.com/fwupd/fwupd) with the `vli` plugin, plus the quirk in
  `contrib/via-vl817-vl103.quirk` (binds this hub's generic VIA USB IDs)
- [flashrom](https://flashrom.org) with the `realtek_mst_i2c_spi` programmer and
  XT25F16B support (`contrib/flashrom-xt25f16b.patch` if your flashrom lacks it)
- An AMD/Intel GPU whose DisplayPort AUX shows up as `/dev/i2c-*` for the RTD2142
  step (connect the hub to the PC like a monitor hub)

```sh
pip install .            # or run in place: python3 -m switch2_hub_patcher ...
```

## Usage

Keep every dump: they are your way back.

### 1. VL103 (TV mode)

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

### 2. RTD2142 (HDR colours)

Connect the hub's USB-C cable to the PC, with a monitor on the hub. Find the AUX
I²C bus of that connector and make sure it's the Realtek branch device:

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
switch2-hub-patcher identify *.bin
```

## How it is built

Each patch is 8051 assembly (`switch2_hub_patcher/asm/`) plus a Python builder that
checks the exact input hash, the original bytes at every hook and that the patch
space is erased, then fixes the VL103 CRC-16. The VL103 patch is applied as six
consecutive steps, the same ones tested on hardware; every intermediate and final
image must match the recorded hash, so a different SDCC output is caught.

```sh
python3 -m unittest discover -s tests
S2HUB_VL103_DUMP=vl103-stock.bin S2HUB_RTD2142_DUMP=rtd2142-stock.bin \
    python3 -m unittest discover -s tests
```

## License

MIT, see `LICENSE`. This covers the scripts and assembly in this repository only.
Firmware images remain the property of their vendors and are not included.
