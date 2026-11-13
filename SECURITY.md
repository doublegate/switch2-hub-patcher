# Security and safety

## Reporting a problem

Report privately anything that could make the tool write unintended data to a hub,
bypass a hash or verification check, or harm the host system. Use GitHub's
**Report a vulnerability** button
(<https://github.com/doublegate/switch2-hub-patcher/security/advisories/new>), or contact the
maintainer through the address on their profile. Please don't open a public issue for
these.

Include the tool version (`switch2-hub-patcher --version`), OS, the command line,
and the output. Never attach firmware images; give their SHA-256 instead.

## Scope

In scope:

- A path where `vl103-flash`, `rtd-flash` or `guide` writes without:
  - `--allow-brick`;
  - a known stock/patched base and target;
  - the live pre-check;
  - read-back verification.
- A read-only command (`status`, `find-aux`, `vl103-devices`, `rtd-probe`,
  `rtd-dump`, `vl103-dump`, `survey`, `identify`, `doctor`) changing hub or host
  state, beyond the documented ISP-mode entry and MCU reset of the RTD2142.
- Patch inputs or outputs that bypass the hash locks in `pipeline.py`.
- Unsafe handling of files outside the paths the user gives.

Out of scope:

- Bricking caused by writing modified firmware with other tools.
- Using hardware other than the Cable Matters 201031-BLK.
- Behaviour of the Switch 2 console, including its Dock Update and VRR features.

## Supported versions

Only the latest release gets fixes.

## Safety notes for users

- Keep your stock dumps and a SOIC-8 clip + SPI programmer as a way back.
- Never accept a Switch 2 "Dock Update" on a patched hub, and keep VRR off.
- On macOS, the RTD2142 path uses a private Apple API that hasn't been tested on this
  chip. Probe and dump first; do your first write on Linux.
