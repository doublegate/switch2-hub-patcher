<!-- Managed by Master-Claude. Universal rules come from the imported/inlined core.
     Edit only inside the MC-PROJECT block; mc-sync overwrites everything else. -->
<!-- mc-core: 0.2.0 | mode=import | lang=python -->
# AGENTS.md — switch2-hub-patcher

@~/.claude/master-core/AGENTS.base.md
@~/.claude/master-core/lang/python.md
@~/.claude/master-core/modules/10-commits-and-versioning.md
@~/.claude/master-core/modules/20-testing-and-accuracy.md
@~/.claude/master-core/modules/30-quality-gates.md
@~/.claude/master-core/modules/40-docs-and-adrs.md
@~/.claude/master-core/modules/50-architecture-patterns.md
@~/.claude/master-core/modules/60-security.md
@~/.claude/master-core/modules/70-release-ceremony.md
@~/.claude/master-core/modules/80-phase-sprint-workflow.md
@~/.claude/master-core/modules/90-multi-language-integration.md
@~/.claude/master-core/modules/91-agent-system-architecture.md
@~/.claude/master-core/modules/95-named-pattern-library.md

<<< MC-PROJECT-START >>>

## Project: switch2-hub-patcher

- **What it is:** Offline patcher that turns user-made firmware dumps of the Cable Matters 201031-BLK USB-C hub (VIA VL103 PD controller + Realtek RTD2142 DP→HDMI) into Switch 2 dock firmware (TV mode, HDR colours). It never talks to hardware and ships no vendor firmware.
- **Stack:** Python ≥ 3.9, standard library only (setuptools packaging), plus 8051 assembly in `switch2_hub_patcher/asm/` assembled at run time by SDCC (`sdas8051`, `sdld`).
- **Build / run:** `pip install .`; commands: `vl103`/`rtd2142` (patch, `--manifest`; `rtd2142 --sdr-fix` builds the HDR-to-SDR fix candidate from stock), `identify`, `doctor`, `status`, `guide` (interactive), `vl103-devices|dump|flash` (fwupd vli, private quirk state dir), `rtd-probe|dump|flash` (Realtek ISP over Linux /dev/i2c-N or macOS IOAVService), `rtd-peek` (experimental, read-only, firmware debug interface at I2C 0x35, works on a chip), `rtd-clear-bits` / `rtd-set-bits` (experiments: allow-listed volatile writes over the same interface), `find-aux [--probe]`, `survey`.
- **Test:** `python3 -m unittest discover -s tests`. Synthetic-image tests (`tests/synthetic.py`, no vendor code) run every builder offline when SDCC is present, with outputs pinned for SDCC 4.6.0. The real-dump tests skip unless `S2HUB_VL103_DUMP` / `S2HUB_RTD2142_DUMP` point at stock dumps.
- **Lint / format gate:** `ruff check .`, `ruff format --check .` (single quotes, 100 cols, rules in `pyproject.toml`), `pyright` (py3.9, `[tool.pyright]`), `npx markdownlint-cli2@0.24.0 "**/*.md"` (the CI pin; older versions lack MD060), `bash scripts/agy-review-selftest.sh`. CI (`.github/workflows/ci.yml`) runs these plus the tests on Ubuntu/macOS × Python 3.9/3.13.

### Architecture — load-bearing facts

- Every patch step is hash-locked (`pipeline.py`): the input must be the exact stock SHA-256, and each step's output must match the recorded hash of the image tested on hardware. A different firmware version or a different SDCC output fails the run, and nothing gets written. Changing any asm or builder means re-recording hashes, which in turn needs re-testing on hardware.
- The VL103 patch is six ordered steps (`VL103_STEPS`), and each step consumes the previous step's exact output. Builders check the original bytes at every hook and that the patch space is erased, then fix the trailing CRC-16/USB (`vl103_crc.py`).
- The CLI refuses to overwrite output files (`open(..., 'xb')`).

### Gotchas / institutional knowledge

- Supported images are exactly the hashes in the README table (four, plus the RTD2142 SDR-fix candidate v4 `390ed39d…37cd`, labelled as not yet tested on a hub until it is, and the superseded v1 `f191da0f…8e92`, v2 `d249fa20…a695` and v3 `f5de8f43…2b8b`, known only so `rtd-flash` can move a hub off them). Never loosen the hash checks to accept other dumps.
- The RTD2142 BT.2020 patch (`f242d130…42f1`) was validated upstream in a simulator only. On one hub it gave correct HDR from a Mac but no HDMI picture from a Switch 2, while the same Switch worked on SDR-fix v1 (no BT.2020 change). Don't describe it as hardware-tested.
- `OVERLAY_DIGESTS_SDCC_4_6_0` in `pipeline.py`: the first six entries are confirmed (on 2026-11-14 real stock VL103 and RTD2142 dumps passed the pipeline with SDCC 4.6.0 and produced `6b5b0eff…888e` and `f242d130…42f1`); `rtd2142_sdr_fix` is recorded from the real stock dump, for a candidate image.
- macOS IOAVService I2C reads work on the real hub (2026-11-14: `rtd-dump` about 9 min per read at 32-byte chunks); the first macOS `rtd-flash` (stock -> patched, about 18 min) succeeded the same day. `rtd-flash` writes only after a full same-session read matches the base hash.
- Tests must never reach real hardware: with a hub attached to the Mac, an unmocked `cmd_rtd_dump`/`transport_args` talks to the live chip. Don't run the suite while a dump or flash is in progress.
- Absolute home paths must never be committed (public repo): `.githooks/` (enable with `git config core.hooksPath .githooks`) blocks them on commit/push and CI re-checks. Master-Claude writes home-relative `@~/` imports (its `mc-sync` converts legacy absolute ones); never run it here with `--absolute-imports`.
- Never accept a Switch "Dock Update" on a patched hub (no update handler).
- `*.bin` and `/firmware/` are gitignored. Never commit firmware dumps or patched images, because they are vendor property. Local layout: `firmware/stock/` (dumps), `firmware/patched/` (flashable images + `.json` manifests), `firmware/candidates/` (untested builds); `status` and `guide` use it when `firmware/` exists (flat cwd otherwise). Dump-gated tests here: `S2HUB_VL103_DUMP=firmware/stock/vl103-stock.bin S2HUB_RTD2142_DUMP=firmware/stock/rtd2142-stock.bin`.
- The flashing workflow (fwupd `vli` plugin with `contrib/via-vl817-vl103.quirk`, flashrom `realtek_mst_i2c_spi`) is Linux-only and documented in the README. The patcher itself runs anywhere SDCC does.

### Where things live

- `switch2_hub_patcher/pipeline.py` — step tables, stock/expected hashes, `identify`
- `switch2_hub_patcher/patch_*.py`, `build_target_candidate.py` — per-step builders
- `switch2_hub_patcher/asm/` — 8051 patch sources (shipped as package data)
- `switch2_hub_patcher/cli.py` — CLI entry point
- `switch2_hub_patcher/hexfile.py` — shared SDCC assemble + guarded Intel HEX loader
- `switch2_hub_patcher/dpaux.py`, `rtd2142_map.py` — read-only AUX bus finder; RTD2142 register xref survey (names from the RTD2172 DB)
- `switch2_hub_patcher/rtddbg.py` — 0x35 debug client (`tests/fake_dbg.py` simulates it): reads, plus `clear_bits`/`set_bits` limited to `CLEARABLE`/`SETTABLE` (volatile RAM/registers). Never widen the allowlist or add the block write (0xBA) without a separate review
- `switch2_hub_patcher/patch_rtd2142_sdr_fix.py` + `asm/rtd2142_rx2_colorimetry.asm`, `asm/rtd2142_hdmi_deep_color.asm` — HDR-to-SDR fix candidate (banks 5 and 2); findings in `research/DP_HDR_AND_VRR.md` section 5
- `switch2_hub_patcher/rtdisp.py`, `i2c.py`, `fwupd.py`, `status.py`, `guide.py` — RTD2142 ISP port of flashrom (`tests/fake_rtd.py` simulates the chip), I2C transports, fwupd wrapper, checklist, walk-through
- `CHANGELOG.md` (Keep a Changelog; add to `[Unreleased]`), `CONTRIBUTING.md` (hash-lock and write-guard rules), `SECURITY.md`, `.github/` (CI, issue/PR templates, Dependabot)
- `research/ghidra/` — headless Ghidra scripts: `SeedFunctions`, `RenameSymbols`, `DecompSites`, `Listing`, plus the whole-firmware pass `FunctionReport.java` → `auto_names.py` (subsystem names from register usage and call-graph propagation) → `DecompileAll.java`; outputs go to the gitignored `firmware/analysis/`
- `research/` — DP-port HDR and VRR notes, a draft (unhooked) VSC SDP routine, the RTD2142 symbol map (`rtd2142_symbols.tsv`) and Ghidra headless scripts (`ghidra/`); not part of the pipeline. Ghidra projects and decoded register tables stay outside the repo (gitignored)
- `contrib/` — fwupd quirk and flashrom XT25F16B patch
- `tests/test_pipeline.py` — unit tests plus dump-gated end-to-end tests

### Status / next

- See `CLAUDE.local.md` for volatile session state (current phase/sprint, recent decisions).
<<< MC-PROJECT-END >>>

