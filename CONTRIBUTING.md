# Contributing

Thanks for helping. This tool writes firmware to real hardware, so the rules below
are about not bricking anyone's hub.

## Ground rules

1. **Never commit firmware.** Dumps, patched images, manifests of real dumps and
   vendor databases stay out of the repository. `*.bin` and the manifest names are
   gitignored. Report hashes instead.
2. **Never loosen a hash check.** The pipeline only accepts the exact stock images,
   and every step must produce the hash recorded on hardware. A change to any
   `asm/*.asm` file or builder that alters output needs:
   - new hashes recorded in `pipeline.py`;
   - the README table updated;
   - a hardware test, described in the pull request;
   - the synthetic pins in `tests/test_pipeline.py` updated.
3. **Write paths must stay guarded.** New hardware-writing code must:
   - accept known images only;
   - check the live chip against the expected base before writing;
   - write the minimum;
   - verify by reading back;
   - require `--allow-brick`.

   Read-only commands must stay read-only.
4. **Research is not shipping.** Drafts live in `research/` and are never wired into
   the pipeline without a hardware test.

## Development setup

```sh
brew install sdcc          # or: apt install sdcc / dnf install sdcc
python3 -m pip install -e . ruff pyright
switch2-hub-patcher doctor # expect: matches the SDCC 4.6.0 reference output
git config core.hooksPath .githooks   # pre-commit/pre-push guards (see below)
```

The hooks in `.githooks/` block commits and pushes that contain absolute home paths
(`/Users/<name>`, `/home/<name>/`), which would leak a username into the public
repository. CI runs the same check (`.githooks/check-home-paths`). A typical source is
an older Master-Claude (or one run with `--absolute-imports`), which writes `AGENTS.md`
imports with `$HOME`; keep them as `@~/.claude/master-core/...`. Current Master-Claude
writes `@~/` itself, and its `mc-sync` converts old absolute imports.

## Before opening a pull request

```sh
ruff check .
ruff format --check .
pyright
python3 -m unittest discover -s tests
npx --yes markdownlint-cli2@0.24.0 "**/*.md"
bash scripts/agy-review-selftest.sh
```

If you have stock dumps, also run the full pipeline:

```sh
S2HUB_VL103_DUMP=vl103-stock.bin S2HUB_RTD2142_DUMP=rtd2142-stock.bin \
    python3 -m unittest discover -s tests
```

CI runs the same checks on Linux and macOS with Python 3.9 and 3.13.

## Code style

- Python ≥ 3.9, standard library only at runtime.
- ruff, configured in `pyproject.toml`: single quotes, 100 columns.
- Keep builders deterministic. Their outputs are pinned by `tests/synthetic.py`, so
  a refactor that changes a single byte fails the tests.
- The builder docstrings ("EXPERIMENTAL", "never flash") are the original
  experiment notes from development. The shipped pipeline is the hardware-tested
  combination of those steps.

## Commits and changelog

- Write imperative, descriptive commit messages. Explain *why*, and give the hashes
  when a patch's output changes.
- Add a line under `## [Unreleased]` in `CHANGELOG.md` for every user-visible
  change.

## Reporting hardware results

Use the **Hardware report** issue template. Include the hub model, the
`switch2-hub-patcher identify` output for your dumps (hashes only), OS, tool
versions, and what worked.
