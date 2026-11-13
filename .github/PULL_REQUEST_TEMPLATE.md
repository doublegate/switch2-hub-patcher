## What and why

<!-- What does this change, and why? Link issues. -->

## Checklist

- [ ] `ruff check .`, `ruff format --check .` and `pyright` are clean
- [ ] `python3 -m unittest discover -s tests` passes
- [ ] No firmware, dumps, manifests of real dumps or vendor databases are added
- [ ] Hash locks unchanged, **or** new hashes recorded in `pipeline.py`, the README
      table and `tests/test_pipeline.py`, with the hardware test described below
- [ ] Any new hardware-writing path accepts known images only, checks the live chip
      first, writes the minimum, reads back, and requires `--allow-brick`
- [ ] `CHANGELOG.md` updated under `[Unreleased]`

## Hardware testing

<!-- Hub model, identify hashes, host OS, what was flashed and verified, or "none". -->
