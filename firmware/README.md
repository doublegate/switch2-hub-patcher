# firmware/

A local home for firmware images. **Only this README is tracked by git.** Everything
else here is vendor property and stays on your machine (`.gitignore` ignores
`/firmware/*` except this file). Share hashes, never images.

`switch2-hub-patcher status` and `guide` use this layout when `firmware/` exists in the
current directory. `status` lists every `firmware/*/*.bin` with its identity, and
`guide` dumps into `stock/` and builds into `patched/`. Without a `firmware/` directory
both use the flat layout in the current directory, as before.

## Layout

| Folder | What goes there | Written by |
| --- | --- | --- |
| `stock/` | Your own dumps of the hub's original firmware. Keep them, and keep a copy off this machine: they are the only way back to stock. | `vl103-dump`, `rtd-dump` |
| `patched/` | Flashable patched images, each `.bin` next to its `.json` manifest (a per-step record of every changed byte). | `vl103 … --manifest`, `rtd2142 … --manifest` |
| `candidates/` | Builds that are not yet proven on a hub, with their manifests. Superseded candidates stay here while a hub may still hold them, because `rtd-flash` can only move a chip between images it knows. | `rtd2142 --sdr-fix …`, research builds |
| `analysis/decompiled/` | Ghidra pseudo-C of the RTD2142 stock firmware, one `bankN.c` per code bank, for every function named in `research/rtd2142_symbols.tsv`, with those names applied. Each function lists its callers. Vendor-derived, so local only. | `research/ghidra/RenameSymbols.java` + `DecompSites.java` (see `research/DP_HDR_AND_VRR.md` section 4) |
| `analysis/ghidra/` | A Ghidra 12 project (`rtd.gpr`) with the eight stock code banks imported as 8051 programs (`bank0.bin` … `bank7.bin`), functions seeded and every name applied. Open it in Ghidra to browse and keep naming. | `analyzeHeadless … -import`, `SeedFunctions.java`, `RenameSymbols.java` |

## Expected files

| File | Image | SHA-256 |
| --- | --- | --- |
| `stock/vl103-stock.bin` | VL103 PD firmware 10.48.3.22, 32 KiB | `3763c9f3ed64316dc2faeb94dfe14dfb18da4fb1589298740a27979f3737cff3` |
| `stock/rtd2142-stock.bin` | RTD2142 flash, 2 MiB | `17eea7286255892698066e0b46085dcb5a42855f9797f067041c2ee45104d802` |
| `patched/vl103-patched.bin` (+ `.json`) | VL103 patched (TV mode, PD3 identity, 15 V) | `6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e` |
| `patched/rtd2142-patched.bin` (+ `.json`) | RTD2142 BT.2020 AVI patch; unproven on hardware (see the README) | `f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1` |
| `candidates/rtd2142-sdrfix-v1.bin` (+ `.json`) | RTD2142 SDR-fix v1, superseded | `f191da0f7201fe26c9f9924b11a7f486ce18faa305c145b806cb0f251e518e92` |
| `candidates/rtd2142-sdrfix-v2.bin` (+ `.json`) | RTD2142 SDR-fix v2, superseded | `d249fa204f68e8963fe8246578319e1be544fe9a8fe656ecdda5237a8a54a695` |
| `candidates/rtd2142-sdrfix-v3.bin` (+ `.json`) | RTD2142 SDR-fix v3, superseded | `f5de8f43f8c44338822bec2ec31b67bda326f5e985f867410caf6f099cf22b8b` |
| `candidates/rtd2142-sdrfix-v4.bin` (+ `.json`) | RTD2142 SDR-fix v4, superseded | `390ed39dc2bb2880c0251d63d6889856438c8ec775123c203f77b720740737cd` |
| `candidates/rtd2142-sdrfix-v5.bin` (+ `.json`) | RTD2142 SDR-fix v5, superseded | `cc2241056e8cd1311234a232403f35fdfd12ceff456d9ca5ac514fd987920ca0` |
| `candidates/rtd2142-sdrfix-v6.bin` (+ `.json`) | RTD2142 SDR-fix v6, not yet tested on a hub | `3a56a3aa183f7249743c7d9b7a19b89ac528053bc1deb0882126178c21cbfd62` |

Check any file with `switch2-hub-patcher identify firmware/*/*.bin`. A file that
reports "unknown" is a different firmware version or a corrupt dump; don't flash it.

## Naming

- `<chip>-stock.bin`: the dump as read from the hub.
- `<chip>-patched.bin` / `.json`: the released patch for that chip, with its manifest.
- `<chip>-<name>-vN.bin` / `.json`: a candidate. Bump `N` for each rebuild that changes
  the image, and leave older versions in place until no hub holds them.

## Common commands

```sh
# From the project root (macOS: add --mac-service N from `find-aux --probe`)
switch2-hub-patcher rtd-dump firmware/stock/rtd2142-stock.bin
switch2-hub-patcher rtd2142 firmware/stock/rtd2142-stock.bin firmware/patched/rtd2142-patched.bin \
  --manifest firmware/patched/rtd2142-patched.json
switch2-hub-patcher rtd-flash firmware/patched/rtd2142-patched.bin \
  --base firmware/stock/rtd2142-stock.bin --allow-brick
# Back to stock: swap the target and --base
switch2-hub-patcher rtd-flash firmware/stock/rtd2142-stock.bin \
  --base firmware/patched/rtd2142-patched.bin --allow-brick
```

`--base` must be the image the chip holds now: `rtd-flash` reads the whole chip first
and writes nothing unless it matches. Output files are never overwritten, so delete or
rename an old build before rebuilding it under the same name.

Offline tests against your dumps:

```sh
S2HUB_VL103_DUMP=firmware/stock/vl103-stock.bin \
S2HUB_RTD2142_DUMP=firmware/stock/rtd2142-stock.bin \
python3 -m unittest discover -s tests
```
