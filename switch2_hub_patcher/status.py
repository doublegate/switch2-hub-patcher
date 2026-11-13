"""Read-only readiness checklist: tools, hub connection, local images, next step."""

import platform
import re
import shutil
import subprocess
from pathlib import Path

from . import fwupd, pipeline

OK, WARN, FAIL, INFO = 'ok', 'warn', 'FAIL', 'info'
VIA_IDS = {(0x2109, 0x0817), (0x2109, 0x2817)}


def _run(command, timeout=20):
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def usb_ids():
    """(vendor, product) pairs of attached USB devices, without opening any of them."""
    system = platform.system()
    found = set()
    if system == 'Darwin':
        text = _run(['ioreg', '-p', 'IOUSB', '-l', '-w0']) or ''
        vendor = None
        for line in text.splitlines():
            m = re.search(r'"(idVendor|idProduct)" = (\d+)', line)
            if not m:
                continue
            if m[1] == 'idVendor':
                vendor = int(m[2])
            elif vendor is not None:
                found.add((vendor, int(m[2])))
                vendor = None
    elif system == 'Linux':
        for device in Path('/sys/bus/usb/devices').glob('*'):
            try:
                found.add(
                    (
                        int((device / 'idVendor').read_text(), 16),
                        int((device / 'idProduct').read_text(), 16),
                    )
                )
            except (OSError, ValueError):
                continue
    return found


def checks(cwd='.'):
    system = platform.system()
    rows = [
        (INFO, 'platform', f'{system} {platform.machine()}, Python {platform.python_version()}')
    ]

    try:
        pipeline.check_toolchain()
        same = pipeline.overlay_digests() == pipeline.OVERLAY_DIGESTS_SDCC_4_6_0
        rows.append(
            (
                OK if same else WARN,
                'SDCC',
                (pipeline.toolchain_version() or '?')
                + ('' if same else ' (output differs from 4.6.0 reference)'),
            )
        )
    except pipeline.PatchError as exc:
        rows.append((FAIL, 'SDCC', str(exc)))

    try:
        version = (_run([fwupd.tool(), '--version']) or '').strip().splitlines()
        rows.append((OK, 'fwupd', next((v for v in version if 'fwupd' in v), 'present')))
    except fwupd.FwupdError as exc:
        rows.append((FAIL, 'fwupd', str(exc)))

    if system == 'Linux':
        flashrom = shutil.which('flashrom')
        if flashrom:
            chips = _run([flashrom, '-L'], timeout=60) or ''
            programmers = _run([flashrom, '-h']) or ''
            rows.append(
                (
                    OK if 'XT25F16B' in chips else WARN,
                    'flashrom XT25F16B',
                    'supported'
                    if 'XT25F16B' in chips
                    else 'missing (apply contrib/flashrom-xt25f16b.patch, or use rtd-* commands)',
                )
            )
            rows.append(
                (
                    OK if 'realtek_mst_i2c_spi' in programmers else WARN,
                    'flashrom realtek_mst_i2c_spi',
                    'built in'
                    if 'realtek_mst_i2c_spi' in programmers
                    else 'not built (rtd-* commands of this tool work without flashrom)',
                )
            )
        else:
            rows.append((INFO, 'flashrom', 'not installed (optional: rtd-* commands replace it)'))
        has_i2c = any(Path('/dev').glob('i2c-*'))
        rows.append(
            (
                OK if has_i2c else WARN,
                'i2c-dev',
                '/dev/i2c-* present' if has_i2c else 'load it: modprobe i2c-dev (as root)',
            )
        )
    elif system == 'Darwin':
        from .i2c import mac_services

        services = mac_services()
        rows.append(
            (
                OK if services else INFO,
                'external display paths',
                ', '.join(f'#{s["index"]} {s["display"] or "?"}' for s in services)
                or 'none (hub + monitor not connected)',
            )
        )

    hub = usb_ids() & VIA_IDS
    rows.append(
        (OK if hub else INFO, 'VIA VL817 hub on USB', 'present' if hub else 'not connected')
    )

    images = []
    for path in sorted(Path(cwd).glob('*.bin')):
        try:
            if path.stat().st_size in pipeline.SIZES:
                images.append(f'{path.name}: {pipeline.identify(path.read_bytes())}')
        except OSError:
            continue
    rows.append((INFO, 'images here', '; '.join(images) or 'no 32 KiB / 2 MiB *.bin files'))
    return rows


def next_step(rows):
    state = {name: level for level, name, _ in rows}
    text = ' '.join(detail for _, _, detail in rows)
    if state.get('SDCC') == FAIL:
        return 'install SDCC, then run `switch2-hub-patcher doctor`'
    if state.get('VIA VL817 hub on USB') != OK:
        return 'connect the hub (USB-C to this computer, monitor on the hub) and rerun status'
    if 'VL103 stock' not in text:
        return 'dump the VL103: `switch2-hub-patcher vl103-dump vl103-stock.bin`'
    if 'RTD2142 stock' not in text:
        return 'dump the RTD2142: `switch2-hub-patcher rtd-dump rtd2142-stock.bin`'
    if 'VL103 patched' not in text or 'RTD2142 patched' not in text:
        return 'build the patched images: `switch2-hub-patcher vl103 ...` / `rtd2142 ...`'
    return 'flash with vl103-flash / rtd-flash (see README); keep the stock dumps'


def report(rows, out=print):
    width = max(len(name) for _, name, _ in rows)
    for level, name, detail in rows:
        out(f'  [{level:4}] {name:{width}}  {detail}')
    out(f'\nnext: {next_step(rows)}')
    return 1 if any(level == FAIL for level, _, _ in rows) else 0
