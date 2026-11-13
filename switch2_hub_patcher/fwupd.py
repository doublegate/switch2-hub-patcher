"""VL103 dump/flash through fwupdtool's vli plugin, on Linux and macOS (Homebrew fwupd).

The hub's generic VIA IDs need the bundled quirk. Instead of writing to system
directories, fwupdtool runs with FWUPD_LOCALSTATEDIR pointing at a private state
directory that holds the quirk, so nothing outside it is changed.
"""
import json
import os
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

QUIRK_NAME = 'via-vl817-vl103.quirk'
QUIRK_SOURCE = Path(__file__).resolve().parent / 'data' / QUIRK_NAME


class FwupdError(Exception):
    pass


def state_dir():
    if platform.system() == 'Darwin':
        base = Path.home() / 'Library' / 'Application Support'
    else:
        base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local' / 'state')
    return base / 'switch2-hub-patcher' / 'fwupd'


def prepare_state(directory=None):
    """Create the private fwupd state dir with the quirk; return it."""
    directory = Path(directory or state_dir())
    quirks = directory / 'lib' / 'fwupd' / 'quirks.d'
    quirks.mkdir(parents=True, exist_ok=True)
    target = quirks / QUIRK_NAME
    if not target.is_file() or target.read_bytes() != QUIRK_SOURCE.read_bytes():
        shutil.copyfile(QUIRK_SOURCE, target)
    return directory


def tool():
    path = shutil.which('fwupdtool')
    if not path:
        hint = 'brew install fwupd' if platform.system() == 'Darwin' else \
            'install fwupd (apt install fwupd / dnf install fwupd)'
        raise FwupdError(f'fwupdtool not found; {hint}')
    return path


def run(args, state=None, timeout=600):
    env = dict(os.environ, FWUPD_LOCALSTATEDIR=str(prepare_state(state)))
    try:
        result = subprocess.run([tool(), *args], env=env, text=True, capture_output=True,
                                timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise FwupdError(f'fwupdtool {args[0]} timed out') from exc
    return result


def parse_devices(text):
    """Device records from `fwupdtool get-devices --json` output."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FwupdError('could not parse fwupdtool JSON output') from exc
    if 'Error' in data:
        message = data['Error'].get('Message', 'unknown error')
        if 'No detected devices' in message:
            return []
        raise FwupdError(message)
    return [d for d in data.get('Devices', []) if d.get('DeviceId')]


def is_pd(device):
    text = ' '.join(str(device.get(k, '')) for k in ('Name', 'Summary', 'Guid', 'InstanceIds'))
    return 'VL103' in text or 'PD' in device.get('Name', '')


def devices(state=None):
    result = run(['get-devices', '--plugins', 'vli', '--json'], state)
    if not result.stdout.strip():
        raise FwupdError(result.stderr.strip() or 'fwupdtool returned nothing')
    return parse_devices(result.stdout)


def pick_pd(found, device_id=None):
    if device_id:
        for d in found:
            if d['DeviceId'].startswith(device_id):
                return d
        raise FwupdError(f'no vli device with ID {device_id}')
    pds = [d for d in found if is_pd(d)]
    if len(pds) == 1:
        return pds[0]
    if not found:
        raise FwupdError('no VIA hub found by fwupd; is the hub plugged in (data, not only power)?')
    raise FwupdError('cannot tell which device is the VL103; pass --device-id (see vl103-devices)')


def dump(device_id, state=None):
    with tempfile.TemporaryDirectory(prefix='s2hub-vl103-') as tmp:
        out = Path(tmp) / 'dump.bin'
        result = run(['--plugins', 'vli', 'firmware-dump', str(out), device_id], state)
        if result.returncode or not out.is_file():
            raise FwupdError('firmware-dump failed: ' + (result.stderr or result.stdout).strip())
        return out.read_bytes()


def install(path, device_id, state=None):
    result = run(['--plugins', 'vli', '--allow-reinstall', '--prepare', '--cleanup',
                  '--no-reboot-check', 'install-blob', str(path), device_id], state)
    if result.returncode:
        raise FwupdError('install-blob failed: ' + (result.stderr or result.stdout).strip())
    return result.stdout
