# Review Style Guide: switch2-hub-patcher

This tool turns user-made firmware dumps into firmware that users write to real
hardware. A wrong byte can brick a hub, so review for safety first. The full rules
are in `CONTRIBUTING.md`; these are the ones to enforce.

## What to flag as BLOCKING

- **Firmware in the repository.** Any dump, patched image, manifest of a real dump,
  or vendor database (`*.bin`, `*-patched.json`, Realtek `DB.bin`) being added.
  Hashes are fine; bytes are not.
- **A loosened hash lock.** Any change that lets the pipeline accept an input other
  than the exact stock SHA-256, skips a per-step output hash, or widens a builder's
  check of original bytes at a hook or of an erased patch region.
- **Changed patch output without the full record.** A change to `asm/*.asm` or a
  builder that alters output bytes must update, in the same PR: the hashes in
  `pipeline.py` (including `OVERLAY_DIGESTS_SDCC_4_6_0`), the README hash table, the
  synthetic pins in `tests/test_pipeline.py`, and a hardware-test description.
- **An unguarded write path.** New or changed code that writes to a chip (fwupd,
  flashrom, the RTD2142 ISP in `rtdisp.py`) must accept known images only, read the
  live chip and compare it with `--base` before writing, write the minimum, verify
  by reading back, and require `--allow-brick`. A read-only command that gains a
  write is blocking.
- **Overwriting user files.** Output files must keep being opened exclusively
  (`open(..., 'xb')`); never overwrite a dump.
- **Research wired into shipping.** Code from `research/` hooked into the pipeline
  or the CLI's flash paths without a recorded hardware test.
- **Absolute home paths** (`/home/<name>/`, `/Users/<name>/`) anywhere. This is a
  public repository.
- **Unsafe advice to users.** Docs or messages that suggest accepting a Switch 2
  "Dock Update" on a patched hub, turning on VRR, or skipping the stock-dump backup.

## Conventions

- Python >= 3.9 and standard library only at runtime. Flag syntax or stdlib APIs
  newer than 3.9, such as `match` statements or `X | Y` unions evaluated at runtime.
- ruff style from `pyproject.toml`: single quotes, 100 columns. pyright must stay clean.
- Builders stay deterministic: identical input and SDCC 4.6.0 must give identical bytes.
- Every user-visible change adds a line under `## [Unreleased]` in `CHANGELOG.md`.
- Conventional Commits; no emojis in code, comments, commits, or docs.
- Markdown tables use spaced separator rows (`| --- | --- |`); CI's markdownlint
  0.24.0 enforces MD060.

## What to keep as SUGGESTION / NITPICK

- Wording and structure in `README.md`, `research/` and docstrings.
- Test coverage for read-only or offline paths.
- Refactors that do not change any output byte.
