"""Read-only discovery of the RTD2142's DP AUX I2C bus on Linux.

Walks /sys/class/drm connectors, reads the DPCD branch-device block (0x500..0x50B)
through /dev/drm_dp_auxN and reports which /dev/i2c-N belongs to a Realtek branch
device. Never writes to any device.
"""
import platform
from pathlib import Path

REALTEK_OUI = bytes.fromhex('00e04c')
DPCD_BRANCH = 0x500
DPCD_BRANCH_LEN = 12


def parse_branch(block):
    """Decode DPCD 0x500..0x50B: OUI, device ID string, HW revision, FW revision."""
    if len(block) < DPCD_BRANCH_LEN:
        return None
    device_id = block[3:9].split(b'\0', 1)[0].decode('ascii', 'replace')
    return {
        'oui': block[0:3].hex(),
        'realtek': block[0:3] == REALTEK_OUI,
        'device_id': device_id,
        'hw_rev': f'{block[9] >> 4}.{block[9] & 15}',
        'fw_rev': f'{block[10]}.{block[11]}',
    }


def read_branch(aux_dev):
    with open(aux_dev, 'rb', buffering=0) as f:
        f.seek(DPCD_BRANCH)
        return f.read(DPCD_BRANCH_LEN)


def scan(sysfs='/sys/class/drm', dev='/dev', reader=read_branch):
    """Return one record per DisplayPort connector (including USB-C DP alt mode)."""
    results = []
    root = Path(sysfs)
    if not root.is_dir():
        return results
    for connector in sorted(root.glob('card*-DP-*')):
        record = {'connector': connector.name, 'status': None, 'aux': None, 'i2c': None,
                  'i2c_dev_present': False, 'branch': None, 'error': None}
        status = connector / 'status'
        if status.is_file():
            record['status'] = status.read_text().strip()
        auxes = sorted(p.name for p in connector.glob('drm_dp_aux*'))
        buses = sorted(p.name for p in connector.glob('i2c-*'))
        if auxes:
            record['aux'] = auxes[0]
        if buses:
            record['i2c'] = buses[0]
            record['i2c_dev_present'] = Path(dev, buses[0]).exists()
        if record['aux'] and record['status'] == 'connected':
            try:
                record['branch'] = parse_branch(reader(str(Path(dev, record['aux']))))
            except OSError as exc:
                record['error'] = f'{exc.strerror or exc} (run as root?)'
        results.append(record)
    return results


def programmer_string(bus):
    return f'realtek_mst_i2c_spi:bus={bus},allow_brick=yes,reset_mcu=1'


def report(records, out=print):
    """Print a human-readable summary; return 0 if exactly one Realtek bus is usable."""
    if not records:
        out('no DisplayPort connectors under /sys/class/drm (Linux with an AMD/Intel GPU '
            'and a DP-capable USB-C port is required)')
        return 1
    candidates = []
    for r in records:
        line = f"{r['connector']}: {r['status'] or '?'}"
        if r['aux']:
            line += f"  aux=/dev/{r['aux']}"
        if r['i2c']:
            line += f"  i2c=/dev/{r['i2c']}" + ('' if r['i2c_dev_present'] else ' (missing)')
        b = r['branch']
        if b:
            line += (f"  branch OUI {b['oui']} id '{b['device_id']}' hw {b['hw_rev']} "
                     f"fw {b['fw_rev']}" + ('  <- Realtek' if b['realtek'] else ''))
            if b['realtek'] and r['i2c']:
                candidates.append(r)
        if r['error']:
            line += f"  DPCD read failed: {r['error']}"
        out(line)
    if any(r['i2c'] and not r['i2c_dev_present'] for r in records):
        out('note: /dev/i2c-* nodes missing; load the driver with: sudo modprobe i2c-dev')
    if len(candidates) == 1:
        bus = candidates[0]['i2c'].split('-', 1)[1]
        out(f'\nRealtek branch device on /dev/i2c-{bus}. flashrom programmer:')
        out(f'  -p {programmer_string(bus)}')
        return 0 if candidates[0]['i2c_dev_present'] else 1
    if not candidates:
        out('\nno Realtek (OUI 00e04c) branch device found; connect the hub to the PC with '
            'a monitor on the hub, and run as root so DPCD can be read')
    else:
        out('\nmore than one Realtek branch device; disconnect the others and retry')
    return 1


def mac_report(services, probe=None, out=print):
    """List external display paths on macOS; optionally probe each for the RTD2142 ISP."""
    if not services:
        out('no external display found. Connect the hub to a USB-C/Thunderbolt port with a '
            'monitor on the hub, and make sure macOS shows the monitor')
        return 1
    hits = []
    for s in services:
        line = f"service #{s['index']}: {s['display'] or 'unknown display'}  " \
               f"(registry id {s['registry_id']:#x})"
        if probe:
            try:
                mode = probe(s['index'])
                line += f'  ISP@0x4a answers, MCU mode {mode:#04x}  <- Realtek MST'
                hits.append(s['index'])
            except OSError as exc:
                line += f'  no ISP answer ({exc})'
        out(line)
    if probe and len(hits) == 1:
        out(f'\nuse: --mac-service {hits[0]}')
        return 0
    if probe and not hits:
        out('\nno Realtek ISP answered at I2C 0x4a on any external display path')
    return 0 if not probe else 1


def main(probe=False):
    if platform.system() == 'Darwin':
        from . import i2c, rtdisp

        def probe_service(index):
            transport = i2c.MacAVI2C(index)
            try:
                return rtdisp.RealtekISP(transport, log=None).mcu_mode()
            finally:
                transport.close()
        return mac_report(i2c.mac_services(), probe_service if probe else None)
    if platform.system() != 'Linux':
        print('find-aux supports Linux (/dev/i2c-* on DP AUX) and macOS (IOAVService)')
        return 1
    return report(scan())
