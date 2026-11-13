# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-11-13

The patch outputs are byte-for-byte unchanged. The hardware-tested images (VL103
`6b5b0eff…888e`, RTD2142 `f242d130…42f1`) are still the only ones produced.

### Added

- Dumping and flashing commands for **Linux and macOS (Apple silicon)**:
  - `vl103-devices`, `vl103-dump`, `vl103-flash`: fwupdtool `vli` wrapper. It ships
    the VIA quirk as package data and uses it from a private `FWUPD_LOCALSTATEDIR`.
  - `rtd-probe`, `rtd-dump`, `rtd-flash`: port of flashrom's `realtek_mst_i2c_spi` to
    Linux `/dev/i2c-N` and macOS IOAVService I²C.
  - Flash commands accept only the known stock and patched images. They check the
    live chip against `--base` before writing and read back after. `rtd-flash`
    rewrites only the changed 4 KiB sectors.
- `status` readiness checklist and `guide` interactive walk-through.
- `find-aux [--probe]`: Realtek DP AUX discovery (Linux sysfs + DPCD 0x500; macOS
  external display paths).
- `doctor`: SDCC check against recorded SDCC 4.6.0 overlay fingerprints.
- `--manifest JSON` on `vl103` and `rtd2142`: per-step record of every changed byte.
- `identify` recognises partly patched VL103 images and wrongly sized files.
- `survey`: read-only list of the code that touches the RTD2142 DP/HDMI colorimetry
  and VRR registers.
- `research/`: DP-port HDR and VRR notes from the RTD2172 register database, a draft
  VSC SDP colorimetry routine (`dp_hdr_vsc.asm`), and a decoder for the register
  database (`rtd_db_dump.py`).
- Offline test suite (48 tests):
  - synthetic, vendor-free images run every builder with pinned outputs;
  - a simulated RTD2142 ISP engine and NOR flash for the dump and flash logic;
  - tests for the CLI, fwupd, status and guide.
- Repository files: CHANGELOG, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT,
  `.editorconfig`, GitHub Actions CI, issue and PR templates, Dependabot.
- Published as the public fork [doublegate/switch2-hub-patcher](https://github.com/doublegate/switch2-hub-patcher)
  of the upstream repository.
- Release workflow: tagged pushes build the sdist and wheel, test the wheel, and
  attach both, with SHA-256 sums, to a GitHub release.
- `.gitattributes` (LF endings, binary firmware, language stats), `CODEOWNERS`,
  and a CI check that fails on absolute home paths.

### Changed

- One shared SDCC driver and strict Intel HEX loader (`hexfile.py`) replaces six
  copies of the old code. The RTD2142 builder's parser now gets the full
  length/checksum/EOF checks.
- Builder, assembler and I/O failures are reported as one-line errors instead of
  tracebacks; nothing is written on failure.
- README rewritten: Linux and macOS requirements, quick path, command reference,
  safety model, project layout, development, research, credits.
- `AGENTS.md` imports are home-relative (`@~/.claude/master-core/…`) instead of
  absolute paths.
- Project URLs, badges and changelog links point at the fork; upstream is credited
  and linked.
- Code formatted with ruff (single quotes, 100 columns). Pyright and ruff configs
  live in `pyproject.toml`. Python 3.9 compatibility is checked.

### Fixed

- README now documents `modprobe i2c-dev` and how to check the flashrom programmer
  and chip support.
- `vl103_crc.py` closes its files.

### Security

- Warn never to accept a Switch 2 "Dock Update" on a patched hub, and to keep VRR off
  (system update 23.0.0 added docked VRR).

## [1.0.0] - 2026-11-13

### Added

- Initial release by Michał Kopeć: offline, hash-locked patcher for the Cable Matters
  201031-BLK.
  - VL103 (six steps): Nintendo SVID, modes and vendor replies; the official dock's
    PD3 identity; 15 V / 2.8 A offer; query 02/04/06 replies.
  - RTD2142: HDMI AVI InfoFrame marked BT.2020 when PQ/HLG HDR metadata is present.
- fwupd quirk for the hub's generic VIA IDs, and flashrom XT25F16B chip patch.

[Unreleased]: https://github.com/doublegate/switch2-hub-patcher/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/doublegate/switch2-hub-patcher/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/doublegate/switch2-hub-patcher/releases/tag/v1.0.0
