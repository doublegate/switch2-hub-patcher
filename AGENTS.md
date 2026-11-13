<!-- Managed by Master-Claude. Universal rules come from the imported/inlined core.
     Edit only inside the MC-PROJECT block; mc-sync overwrites everything else. -->
<!-- mc-core: 0.2.0 | mode=import | lang=python -->
# AGENTS.md — switch2-hub-patcher

@/Users/parobek/.claude/master-core/AGENTS.base.md
@/Users/parobek/.claude/master-core/lang/python.md
@/Users/parobek/.claude/master-core/modules/10-commits-and-versioning.md
@/Users/parobek/.claude/master-core/modules/20-testing-and-accuracy.md
@/Users/parobek/.claude/master-core/modules/30-quality-gates.md
@/Users/parobek/.claude/master-core/modules/40-docs-and-adrs.md
@/Users/parobek/.claude/master-core/modules/50-architecture-patterns.md
@/Users/parobek/.claude/master-core/modules/60-security.md
@/Users/parobek/.claude/master-core/modules/70-release-ceremony.md
@/Users/parobek/.claude/master-core/modules/80-phase-sprint-workflow.md
@/Users/parobek/.claude/master-core/modules/90-multi-language-integration.md
@/Users/parobek/.claude/master-core/modules/91-agent-system-architecture.md
@/Users/parobek/.claude/master-core/modules/95-named-pattern-library.md

<<< MC-PROJECT-START >>>

## Project: switch2-hub-patcher

- **What it is:** Offline patcher that turns user-made firmware dumps of the Cable Matters 201031-BLK USB-C hub (VIA VL103 PD controller + Realtek RTD2142 DP→HDMI) into Switch 2 dock firmware (TV mode, HDR colours). It never talks to hardware and ships no vendor firmware.
- **Stack:** Python ≥ 3.9, standard library only (setuptools packaging), plus 8051 assembly in `switch2_hub_patcher/asm/` assembled at run time by SDCC (`sdas8051`, `sdld`).
- **Build / run:** `pip install .`; commands: `vl103`/`rtd2142` (patch, `--manifest`), `identify`, `doctor`, `status`, `guide` (interactive), `vl103-devices|dump|flash` (fwupd vli, private quirk state dir), `rtd-probe|dump|flash` (Realtek ISP over Linux /dev/i2c-N or macOS IOAVService), `find-aux [--probe]`, `survey`.
- **Test:** `python3 -m unittest discover -s tests`. Synthetic-image tests (`tests/synthetic.py`, no vendor code) run every builder offline when SDCC is present, with outputs pinned for SDCC 4.6.0. The real-dump tests skip unless `S2HUB_VL103_DUMP` / `S2HUB_RTD2142_DUMP` point at stock dumps.
- **Lint / format gate:** `ruff check .`, `ruff format --check .` (single quotes, 100 cols, rules in `pyproject.toml`), `pyright` (py3.9, `[tool.pyright]`), `npx markdownlint-cli2 "**/*.md"`. CI (`.github/workflows/ci.yml`) runs these plus the tests on Ubuntu/macOS × Python 3.9/3.13.

### Architecture — load-bearing facts

- Every patch step is hash-locked (`pipeline.py`): the input must be the exact stock SHA-256, and each step's output must match the recorded hash of the image tested on hardware. A different firmware version or a different SDCC output fails the run, and nothing gets written. Changing any asm or builder means re-recording hashes, which in turn needs re-testing on hardware.
- The VL103 patch is six ordered steps (`VL103_STEPS`), and each step consumes the previous step's exact output. Builders check the original bytes at every hook and that the patch space is erased, then fix the trailing CRC-16/USB (`vl103_crc.py`).
- The CLI refuses to overwrite output files (`open(..., 'xb')`).

### Gotchas / institutional knowledge

- Supported images are exactly the four hashes in the README table. Never loosen the hash checks to accept other dumps.
- `OVERLAY_DIGESTS_SDCC_4_6_0` in `pipeline.py` is provisional until a real dump passes the pipeline with SDCC 4.6.0.
- macOS IOAVService I2C semantics (offset handling, transfer size) are assumptions until a hub is attached; `rtd-flash` writes only after a full same-session read matches the base hash.
- Never accept a Switch "Dock Update" on a patched hub (no update handler).
- `*.bin` is gitignored. Never commit firmware dumps or patched images, because they are vendor property.
- The flashing workflow (fwupd `vli` plugin with `contrib/via-vl817-vl103.quirk`, flashrom `realtek_mst_i2c_spi`) is Linux-only and documented in the README. The patcher itself runs anywhere SDCC does.

### Where things live

- `switch2_hub_patcher/pipeline.py` — step tables, stock/expected hashes, `identify`
- `switch2_hub_patcher/patch_*.py`, `build_target_candidate.py` — per-step builders
- `switch2_hub_patcher/asm/` — 8051 patch sources (shipped as package data)
- `switch2_hub_patcher/cli.py` — CLI entry point
- `switch2_hub_patcher/hexfile.py` — shared SDCC assemble + guarded Intel HEX loader
- `switch2_hub_patcher/dpaux.py`, `rtd2142_map.py` — read-only AUX bus finder; RTD2142 register xref survey (names from the RTD2172 DB)
- `switch2_hub_patcher/rtdisp.py`, `i2c.py`, `fwupd.py`, `status.py`, `guide.py` — RTD2142 ISP port of flashrom (`tests/fake_rtd.py` simulates the chip), I2C transports, fwupd wrapper, checklist, walk-through
- `CHANGELOG.md` (Keep a Changelog; add to `[Unreleased]`), `CONTRIBUTING.md` (hash-lock and write-guard rules), `SECURITY.md`, `.github/` (CI, issue/PR templates, Dependabot)
- `research/` — DP-port HDR and VRR notes and a draft (unhooked) VSC SDP routine; not part of the pipeline
- `contrib/` — fwupd quirk and flashrom XT25F16B patch
- `tests/test_pipeline.py` — unit tests plus dump-gated end-to-end tests

### Status / next

- See `CLAUDE.local.md` for volatile session state (current phase/sprint, recent decisions).
<<< MC-PROJECT-END >>>

