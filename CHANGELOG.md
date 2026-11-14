# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `.githooks/` pre-commit and pre-push guards (`git config core.hooksPath .githooks`)
  that block absolute home paths before they leave the machine; CI now calls the same
  `.githooks/check-home-paths` script.
- README "Switch 2 system versions" table recording which console versions the patched
  hub has been checked on. First entry: 23.0.1 with the VL103 patched and the RTD2142
  stock enters TV mode with the docking delay roughly halved.
- `docs/macos-rtd2142.md`: step-by-step RTD2142 dump, offline patch and guarded flash on
  macOS (Apple silicon), linked from the README's macOS section.
- Antigravity CLI (`agy`) PR reviewer: `.github/workflows/antigravity-review.yml` and
  `scripts/agy-review*.sh` from the antigravity-pr-review template, run on a self-hosted
  runner labelled `agy`, with a project style guide in `.github/agy-review.md` (hash
  locks, write guards, no firmware in the repository). CI's `lint` job runs
  `scripts/agy-review-selftest.sh`. The vendored
  `.github/AGY-REVIEWER.md` is excluded from markdownlint. With the reviewer on `main`,
  the workflow's first-install bootstrap steps (a PR-head checkout that could only ever
  run once) are removed.
- `research/DP_HDR_AND_VRR.md`: what the official dock does differently for VRR (an
  HDMI 2.1-class RTD2175N converter that already passes VRR from other sources), why the
  fix is RTD2142 firmware rather than VL103, the missing live-register tool (the 0x35
  debug interface), and an ordered work plan starting from RTD2142 access.
- `research/rtd2142_symbols.tsv` and `research/ghidra/*.java`: a curated name map for
  the RTD2142 stock firmware (functions, XDATA variables, registers) and Ghidra 12
  headless scripts to seed functions in a raw 8051 bank, apply the names, decompile
  around given addresses and print listings. Addresses and names only, no firmware.
- `research/DP_HDR_AND_VRR.md` findings from the stock RTD2142 dump: the DP output is
  TX1; the firmware already forwards the HDR metadata SDP (type 87h) on it and has a
  VSC-colorimetry path (header 05h/13h, `SEC_FUNCTION_CTRL` bit 7, MISC1 bit 6) that
  it takes only for extended input colorimetry; the stock firmware never touches the
  DP RX hardware VRR registers. Also the decoded (untested) 0x35 debug protocol and
  the bank-call layout. `research/dp_hdr_vsc.asm` now uses the TX1 addresses and
  records the revised approach.
- `rtd-peek ADDR|START-END …` (experimental, read-only): reads live RTD2142 XDATA
  registers through the firmware's debug interface at I2C 0x35, as decoded from the
  stock dump (`switch2_hub_patcher/rtddbg.py`). It sends only enter, address-high, read
  and leave commands, refuses to report unless `FF23` reads back `0x6A`, and caps a run
  at 256 addresses. Tested against `tests/fake_dbg.py`; not yet run on a chip. The
  transports take the I2C address as a parameter.
- `research/ghidra/db_to_tsv.py`: turns the decoded RTD2172 register database into
  Ghidra labels (`NAME_ADDR`) for every bank, so decompiles name all 6,600+ registers.
- VRR findings from the stock dump in `research/DP_HDR_AND_VRR.md`: stream 1's display
  format generator runs in full-last-line mode and the hardware VRR mode
  (`vrr_mode`, `vsc_for_vrr_en`) is never enabled; `MSA_TIMING_PAR_IGNORED` is not in a
  ROM table; the hook is the end of the DPF timing routine (bank 6 `A0BC`).
- `.gitignore` covers the research by-products that are derived from vendor firmware or
  tools: Ghidra projects and exports (`*.gpr`, `*.rep/`, `*.gzf`, lock files), the
  decoded register label tables and the RTD2172 DB's `ReadAll.txt`.

### Changed

- `AGENTS.md` re-synced with Master-Claude, which now writes home-relative `@~/` imports
  itself ([Master-Claude#33](https://github.com/doublegate/Master-Claude/pull/33)). The
  hand-written header note about the imports is gone because it is redundant. The notes in
  CONTRIBUTING, AGENTS.md and the hook script no longer claim that `mc-sync` re-adds `$HOME`
  paths.
- Antigravity CLI (`agy`) gets the Master-Claude core through the `master-claude` agy plugin
  (Master-Claude `mc-agy.sh`). This project's `AGENTS.md` is 5.6 KB, well under agy's
  24,000-byte rule-file cap.
- CI pins `markdownlint-cli2` 0.24.0 (was 0.18.1). The old pin predated rule MD060, so a
  newer local binary reported 32 table findings that CI never gated; the five affected
  table separator rows in `README.md` and `research/DP_HDR_AND_VRR.md` are now spaced.
- The SDCC 4.6.0 VL103 overlay digests are confirmed rather than provisional: a real stock
  VL103 dump (`3763c9f3…cff3`) passed the six-step pipeline with SDCC 4.6.0 and produced
  the hardware-tested image `6b5b0eff…888e`. The RTD2142 overlay is confirmed too: a real
  stock RTD2142 dump (`17eea728…d802`) patched to the hardware-tested `f242d130…42f1`.
- The macOS RTD2142 path has read a real chip: `find-aux --probe`, `rtd-probe` (XT25F16B,
  no block protection) and a two-read `rtd-dump` that matched the stock image, at about
  9 minutes per read. It has also written one: `rtd-flash` moved a stock RTD2142 to the
  hardware-tested patched image `f242d130…42f1` (one 4 KiB sector, verified, then a
  whole-chip re-read; about 18 minutes in all). The README and `docs/macos-rtd2142.md`
  say so.

- `rtd-dump` and `rtd-flash` report progress when stderr is not a terminal (a log, a
  pipe, an agent): one line per 10 % with the elapsed time. Before, only a terminal got
  progress, so a slow whole-chip read over macOS IOAVService printed nothing for many
  minutes. `rtd-flash` reports both of its whole-chip reads: the shared progress
  printer starts a new pass when the byte count goes back down (the final re-read
  used to print nothing).

### Fixed

- Typo in the `patch_versions` manifest's limits text ("and3W" -> "and 3W").
- The `guide` tests no longer reach real hardware. With a hub attached to a Mac, a test
  that answered "y" to every prompt ran a real `rtd-dump` and ISP probe against the live
  RTD2142 (and hung while another dump held the chip). Every hardware command the guide
  calls is now mocked for all guide tests.

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
