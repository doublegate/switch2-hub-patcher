"""switch2-hub-patcher: Switch 2 dock firmware for the Cable Matters 201031 hub.

Patching is offline. Dumping and flashing (vl103-*, rtd-*) talk to the hub through
fwupd and DP AUX I2C on Linux and macOS, with hash-checked, read-back-verified writes.
"""

import argparse
import json
import platform
import sys
import time
from pathlib import Path

from . import __version__, dpaux, fwupd, rtd2142_map, rtdisp, status
from .pipeline import (
    OVERLAY_DIGESTS_SDCC_4_6_0,
    RTD2142_SDR_FIX_LABEL,
    RTD2142_SDR_FIX_STEPS,
    RTD2142_SDR_FIX_SUPERSEDED,
    RTD2142_STEPS,
    RTD2142_STOCK,
    VL103_STEPS,
    VL103_STOCK,
    PatchError,
    check_toolchain,
    identify,
    overlay_digests,
    patch_rtd2142,
    patch_rtd2142_sdr_fix_only,
    patch_vl103,
    sha256,
    toolchain_version,
)


def error(message):
    print(f'error: {message}', file=sys.stderr)
    return 1


def write_new(path, data):
    with open(path, 'xb') as f:  # refuse to overwrite anything
        f.write(data)


def cmd_patch(args, patcher):
    for path in filter(None, (args.output, args.manifest)):
        if Path(path).exists():
            return error(f'{path} already exists; refusing to overwrite')
    try:
        source = Path(args.input).read_bytes()
    except OSError as exc:
        return error(f'cannot read {args.input}: {exc.strerror or exc}')
    print(f'input  {args.input}  {sha256(source)}')
    manifests = [] if args.manifest else None
    try:
        image = patcher(source, manifests=manifests)
    except PatchError as exc:
        return error(exc)
    try:
        write_new(args.output, image)
        if args.manifest:
            record = {
                'tool': f'switch2-hub-patcher {__version__}',
                'assembler': toolchain_version(),
                'input': str(args.input),
                'input_sha256': sha256(source),
                'output': str(args.output),
                'output_sha256': sha256(image),
                'steps': manifests,
            }
            write_new(args.manifest, (json.dumps(record, indent=1) + '\n').encode())
    except OSError as exc:
        return error(f'cannot write output: {exc.strerror or exc}')
    print(f'output {args.output}  {sha256(image)}')
    if args.manifest:
        print(f'manifest {args.manifest}')
    return 0


def cmd_identify(args):
    status = 0
    for name in args.files:
        try:
            data = Path(name).read_bytes()
        except OSError as exc:
            status = error(f'cannot read {name}: {exc.strerror or exc}')
            continue
        print(f'{name}: {identify(data)}  {sha256(data)}')
    return status


def cmd_doctor():
    try:
        check_toolchain()
        digests = overlay_digests()
    except PatchError as exc:
        return error(exc)
    print(f'assembler: {toolchain_version()}')
    ok = True
    for name, digest in digests.items():
        same = OVERLAY_DIGESTS_SDCC_4_6_0.get(name) == digest
        ok &= same
        print(f'  {"ok " if same else "DIFF"} {name:18} {digest[:16]}')
    if ok:
        print('assembled patches match the SDCC 4.6.0 reference output')
        return 0
    print(
        'assembled output differs from the SDCC 4.6.0 reference; patching will most likely '
        'fail its hash checks (nothing would be written). Try SDCC 4.6.0.'
    )
    return 1


def cmd_survey(args):
    try:
        image = Path(args.dump).read_bytes()
    except OSError as exc:
        return error(f'cannot read {args.dump}: {exc.strerror or exc}')
    if len(image) != 0x200000:
        print(f'warning: {len(image):#x} bytes, an RTD2142 dump is 0x200000', file=sys.stderr)
    print(f'{args.dump}: {identify(image)}')
    for line in rtd2142_map.summary(image):
        print(line)
    return 0


def open_transport(args, address=rtdisp.ISP_ADDR):
    if getattr(args, 'bus', None) is not None:
        from .i2c import LinuxI2C

        return LinuxI2C(args.bus, address=address, chunk=args.chunk or 128)
    if platform.system() == 'Darwin':
        from .i2c import MacAVI2C

        return MacAVI2C(args.mac_service, address=address, chunk=args.chunk or 32)
    raise OSError('give --bus N (Linux /dev/i2c-N, see find-aux)')


def progress_printer(total, step=10, clock=time.monotonic):
    """Progress on stderr: an updating percentage on a terminal; otherwise (a log, a pipe,
    an agent) one plain line per `step` percent with the elapsed time, so long reads over
    slow transports show they are moving and how fast. A count lower than the previous one
    starts a new pass (rtd-flash reads the whole chip twice with one printer)."""
    state = {'last': -1, 'start': clock(), 'done': 0}

    def show(done):
        if done < state['done']:
            state.update(last=-1, start=clock())
        state['done'] = done
        pct = done * 100 // total
        if sys.stderr.isatty():
            if pct != state['last']:
                state['last'] = pct
                print(f'\r  {pct:3d}%', end='', file=sys.stderr, flush=True)
                if done >= total:
                    print(file=sys.stderr)
            return
        mark = pct - pct % step
        if mark > state['last'] and mark > 0:
            state['last'] = mark
            secs = int(clock() - state['start'])
            print(f'  {mark:3d}%  {secs // 60}m{secs % 60:02d}s', file=sys.stderr, flush=True)

    return show


def run_isp(args, action):
    try:
        transport = open_transport(args)
    except OSError as exc:
        return error(exc)
    print(f'transport: {transport.name}, {transport.chunk}-byte transfers')
    print('note: the hub stops video while its MCU is in ISP mode; it is reset afterwards')
    try:
        with rtdisp.RealtekISP(transport, log=print, reset_mcu=not args.no_reset) as isp:
            return action(isp)
    except (OSError, rtdisp.ISPError) as exc:
        return error(exc)


def cmd_rtd_probe(args):
    def action(isp):
        ident = isp.rdid()
        status = isp.status()
        print(
            f'flash ID {ident.hex()} '
            + ('(XT25F16B)' if ident == rtdisp.XT25F16B_ID else '(UNEXPECTED)')
        )
        print(
            f'status register {status:#04x}'
            + ('  block protection set' if status & rtdisp.STATUS_BP_MASK else '')
        )
        return 0 if ident == rtdisp.XT25F16B_ID else 1

    return run_isp(args, action)


def cmd_rtd_dump(args):
    if Path(args.output).exists():
        return error(f'{args.output} already exists; refusing to overwrite')

    def action(isp):
        reads = []
        for n in range(args.reads):
            print(f'read {n + 1}/{args.reads}...')
            reads.append(rtdisp.dump(isp, progress_printer(rtdisp.FLASH_SIZE)))
            print(f'  sha256 {sha256(reads[-1])}')
        if any(r != reads[0] for r in reads):
            return error('reads differ; the I2C path is unreliable, nothing written')
        write_new(args.output, reads[0])
        print(f'{args.output}: {identify(reads[0])}')
        return 0

    return run_isp(args, action)


def cmd_rtd_peek(args):
    from . import rtd2142_map, rtddbg

    try:
        addresses = rtddbg.parse_addresses(args.addresses)
    except rtddbg.DebugError as exc:
        return error(exc)
    try:
        transport = open_transport(args, address=rtddbg.DEBUG_ADDR)
    except OSError as exc:
        return error(exc)
    print(f'transport: {transport.name}, debug interface at I2C {rtddbg.DEBUG_ADDR:#04x}')
    print('experimental: protocol decoded from the stock firmware; read commands only')
    try:
        values = rtddbg.peek(transport, addresses)
    except (OSError, rtddbg.DebugError) as exc:
        return error(exc)
    finally:
        transport.close()
    print(f'self-check ok: {rtddbg.SELF_CHECK[0]:04X} = {rtddbg.SELF_CHECK[1]:#04x}')
    for address, value in values:
        block, name, _ = rtd2142_map.REGISTERS.get(address, ('', '', ''))
        label = f'  {name} ({block})' if name else ''
        print(f'{address:04X}  {value:#04x}  {value:08b}{label}')
    return 0


def cmd_rtd_change_bits(args, setting):
    from . import rtddbg

    try:
        address, mask = int(args.address, 16), int(args.mask, 16)
        (rtddbg.check_settable if setting else rtddbg.check_clearable)(address, mask)
    except ValueError:
        return error('address and mask must be hex, e.g. E362 02')
    except rtddbg.DebugError as exc:
        return error(exc)
    if not args.volatile_ram_write:
        return error(
            'this writes chip RAM or a live register through the debug interface; pass --volatile-ram-write '
            '(nothing is flashed; unplugging the hub undoes it)'
        )
    try:
        transport = open_transport(args, address=rtddbg.DEBUG_ADDR)
    except OSError as exc:
        return error(exc)
    print(f'transport: {transport.name}, debug interface at I2C {rtddbg.DEBUG_ADDR:#04x}')
    table = rtddbg.SETTABLE if setting else rtddbg.CLEARABLE
    op = '|=' if setting else '&= ~'
    print(f'experimental volatile write: {address:04X} {op}{mask:#04x} ({table[address][1]})')
    try:
        change = rtddbg.set_bits if setting else rtddbg.clear_bits
        before, after = change(transport, address, mask)
    except (OSError, rtddbg.DebugError) as exc:
        return error(exc)
    finally:
        transport.close()
    print(f'{address:04X}  before {before:#04x}  after {after:#04x}')
    wanted = mask if setting else 0
    if before & mask == wanted:
        print(f'bits were already {"set" if setting else "clear"}; nothing written')
    elif after & mask != wanted:
        print('note: the bits read back changed again (the firmware may have rewritten them)')
    print('unplug the hub to restore its RAM')
    return 0


def cmd_rtd_flash(args):
    if not args.allow_brick:
        return error(
            'writing can brick the hub; pass --allow-brick once you have your stock '
            'dump and a recovery plan (SOIC-8 clip)'
        )
    try:
        target = Path(args.target).read_bytes()
        base = Path(args.base).read_bytes()
    except OSError as exc:
        return error(f'cannot read image: {exc.strerror or exc}')
    known = {
        RTD2142_STOCK: 'RTD2142 stock',
        RTD2142_STEPS[-1][2]: 'RTD2142 patched',
        RTD2142_SDR_FIX_STEPS[-1][2]: RTD2142_SDR_FIX_LABEL,
        **dict(RTD2142_SDR_FIX_SUPERSEDED),
    }
    if platform.system() == 'Darwin' and args.bus is None:
        print(
            'warning: macOS writes go through the private IOAVService I2C API. The tool '
            'only writes after a full read of the chip matches the base image, but a first '
            'write is safer on Linux with flashrom.'
        )

    def action(isp):
        rtdisp.flash(
            isp, base, target, known, log=print, progress=progress_printer(rtdisp.FLASH_SIZE)
        )
        return 0

    return run_isp(args, action)


def vl103_device(args):
    found = fwupd.devices()
    return fwupd.pick_pd(found, args.device_id)


def cmd_vl103_devices():
    try:
        found = fwupd.devices()
    except fwupd.FwupdError as exc:
        return error(exc)
    if not found:
        print('no VIA (vli) devices found; plug in the hub (with data) and retry')
        return 1
    for d in found:
        mark = '  <- VL103 PD' if fwupd.is_pd(d) else ''
        print(f'{d["DeviceId"][:12]}  {d.get("Name", "?")}  version {d.get("Version", "?")}{mark}')
    return 0


def cmd_vl103_dump(args):
    if Path(args.output).exists():
        return error(f'{args.output} already exists; refusing to overwrite')
    try:
        device = vl103_device(args)
        print(f'device {device["DeviceId"][:12]} {device.get("Name", "")}')
        reads = []
        for n in range(args.reads):
            reads.append(fwupd.dump(device['DeviceId']))
            print(f'read {n + 1}/{args.reads}: {sha256(reads[-1])}')
    except fwupd.FwupdError as exc:
        return error(exc)
    if any(r != reads[0] for r in reads):
        return error('dumps differ; nothing written')
    write_new(args.output, reads[0])
    print(f'{args.output}: {identify(reads[0])}')
    return 0


def cmd_vl103_flash(args):
    if not args.allow_brick:
        return error(
            'writing can brick the hub; pass --allow-brick once you have your stock '
            'dump and a recovery plan'
        )
    try:
        target = Path(args.target).read_bytes()
        base = Path(args.base).read_bytes()
    except OSError as exc:
        return error(f'cannot read image: {exc.strerror or exc}')
    known = {VL103_STOCK: 'VL103 stock', VL103_STEPS[-1][2]: 'VL103 patched'}
    for image, role in ((base, 'base'), (target, 'target')):
        if sha256(image) not in known:
            return error(f'{role} image is not a known VL103 stock/patched image')
    if base == target:
        print('nothing to do: base and target are identical')
        return 0
    try:
        device = vl103_device(args)
        device_id = device['DeviceId']
        print(f'device {device_id[:12]} {device.get("Name", "")}')
        live = fwupd.dump(device_id)
        if sha256(live) != sha256(base):
            return error(
                f'the hub holds {identify(live)} ({sha256(live)}), not the base image; '
                'nothing written'
            )
        print(f'hub holds {known[sha256(base)]}; installing {known[sha256(target)]}...')
        fwupd.install(args.target, device_id)
        after = fwupd.dump(vl103_device(args)['DeviceId'])
    except fwupd.FwupdError as exc:
        return error(
            f'{exc}\nif the hub misbehaves, install your stock dump the same way '
            '(vl103-flash STOCK --base PATCHED) before power-cycling'
        )
    if sha256(after) != sha256(target):
        return error(
            f'read-back {sha256(after)} is not the target image; reinstall before unplugging'
        )
    print(f'read-back matches {known[sha256(target)]}. Unplug and replug the hub to restart it.')
    return 0


def add_transport_args(p, reset=True):
    p.add_argument('--bus', type=int, help='Linux: /dev/i2c-N of the hub (see find-aux)')
    p.add_argument(
        '--mac-service',
        type=int,
        default=0,
        help='macOS: external display path index from find-aux --probe (default 0)',
    )
    p.add_argument(
        '--chunk',
        type=int,
        choices=(16, 32, 64, 128),
        help='bytes per I2C transfer (default 128 Linux, 32 macOS)',
    )
    if reset:
        p.add_argument(
            '--no-reset',
            action='store_true',
            help='do not reset the hub MCU when done (flashrom reset_mcu=0)',
        )


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='switch2-hub-patcher', description=(__doc__ or '').splitlines()[0]
    )
    ap.add_argument('--version', action='version', version=f'%(prog)s {__version__}')
    sub = ap.add_subparsers(dest='command', required=True)
    for name, helptext in (
        ('vl103', 'patch a VL103 PD firmware dump (32 KiB)'),
        ('rtd2142', 'patch an RTD2142 flash dump (2 MiB)'),
    ):
        p = sub.add_parser(name, help=helptext)
        p.add_argument('input')
        p.add_argument('output', help='must not exist')
        p.add_argument(
            '--manifest',
            metavar='JSON',
            help='also write a per-step record of every changed byte (must not exist)',
        )
        if name == 'rtd2142':
            p.add_argument(
                '--sdr-fix',
                action='store_true',
                help='build the HDR -> SDR fix candidate from stock instead of the BT.2020 '
                'patch (not yet tested on a hub)',
            )
    p = sub.add_parser('identify', help='report whether files are known stock/patched images')
    p.add_argument('files', nargs='+')
    sub.add_parser('doctor', help='check SDCC and that it assembles the patches as expected')
    p = sub.add_parser(
        'find-aux',
        help="find the hub's DP AUX I2C path (Linux /dev/i2c-N, macOS display service); read-only",
    )
    p.add_argument(
        '--probe',
        action='store_true',
        help='macOS: ask each external display path whether a Realtek ISP answers',
    )
    sub.add_parser('status', help='readiness checklist and the next step (read-only)')
    sub.add_parser('guide', help='interactive walk-through: dump, patch, flash (asks each step)')
    sub.add_parser('vl103-devices', help='list VIA hub devices fwupd sees (bundled quirk applied)')
    p = sub.add_parser('vl103-dump', help='read the VL103 PD firmware (32 KiB) via fwupd')
    p.add_argument('output')
    p.add_argument('--reads', type=int, default=2, help='dumps that must agree (default 2)')
    p.add_argument('--device-id', help='fwupd device ID (prefix), if not detected')
    p = sub.add_parser(
        'vl103-flash',
        help='install a known VL103 stock/patched image via fwupd, '
        'with live pre-check and read-back',
    )
    p.add_argument('target')
    p.add_argument('--base', required=True, help='image the hub holds now')
    p.add_argument('--device-id')
    p.add_argument('--allow-brick', action='store_true')
    p = sub.add_parser('rtd-probe', help='enter RTD2142 ISP mode, read flash ID and status')
    add_transport_args(p)
    p = sub.add_parser('rtd-dump', help='read the RTD2142 flash (2 MiB) into a new file')
    p.add_argument('output')
    p.add_argument('--reads', type=int, default=2, help='full reads that must agree (default 2)')
    add_transport_args(p)
    p = sub.add_parser(
        'rtd-flash',
        help='move the RTD2142 between known stock/patched images, rewriting only changed sectors',
    )
    p.add_argument('target', help='image to write (known stock or patched)')
    p.add_argument(
        '--base',
        required=True,
        help='image the chip holds now (your stock dump, or the patched image when restoring)',
    )
    p.add_argument('--allow-brick', action='store_true')
    add_transport_args(p)
    p = sub.add_parser(
        'rtd-peek',
        help='experimental: read live RTD2142 XDATA registers over the 0x35 debug '
        'interface (read-only)',
    )
    p.add_argument(
        'addresses', nargs='+', metavar='ADDR', help='hex address or range, e.g. B130 or B141-B150'
    )
    add_transport_args(p, reset=False)
    p = sub.add_parser(
        'rtd-clear-bits',
        help='experiment: clear allow-listed RAM bits over the 0x35 debug interface '
        '(volatile; never flash)',
    )
    p.add_argument('address', metavar='ADDR', help='hex XDATA address (allow-listed: E362, 5B07)')
    p.add_argument('mask', metavar='MASK', help='hex bits to clear (E362: 02, 5B07: F0)')
    p.add_argument('--volatile-ram-write', action='store_true')
    add_transport_args(p, reset=False)
    p = sub.add_parser(
        'rtd-set-bits',
        help='experiment: set allow-listed RAM bits over the 0x35 debug interface '
        '(volatile; never flash)',
    )
    p.add_argument('address', metavar='ADDR', help='hex XDATA address (allow-listed: E10B)')
    p.add_argument('mask', metavar='MASK', help='hex bits to set (E10B: 08)')
    p.add_argument('--volatile-ram-write', action='store_true')
    add_transport_args(p, reset=False)
    p = sub.add_parser(
        'survey',
        help='research: list RTD2142 code touching DP/HDMI '
        'colorimetry and VRR registers (read-only)',
    )
    p.add_argument('dump')
    args = ap.parse_args(argv)
    if args.command == 'vl103':
        return cmd_patch(args, patch_vl103)
    if args.command == 'rtd2142':
        return cmd_patch(args, patch_rtd2142_sdr_fix_only if args.sdr_fix else patch_rtd2142)
    if args.command == 'doctor':
        return cmd_doctor()
    if args.command == 'find-aux':
        return dpaux.main(probe=args.probe)
    if args.command == 'status':
        return status.report(status.checks())
    if args.command == 'guide':
        from . import guide

        try:
            return guide.run(sys.modules[__name__])
        except (EOFError, KeyboardInterrupt):
            print('\nstopped')
            return 130
    if args.command == 'vl103-devices':
        return cmd_vl103_devices()
    if args.command == 'vl103-dump':
        return cmd_vl103_dump(args)
    if args.command == 'vl103-flash':
        return cmd_vl103_flash(args)
    if args.command == 'rtd-probe':
        return cmd_rtd_probe(args)
    if args.command == 'rtd-dump':
        return cmd_rtd_dump(args)
    if args.command == 'rtd-flash':
        return cmd_rtd_flash(args)
    if args.command == 'rtd-peek':
        return cmd_rtd_peek(args)
    if args.command in ('rtd-clear-bits', 'rtd-set-bits'):
        return cmd_rtd_change_bits(args, args.command == 'rtd-set-bits')
    if args.command == 'survey':
        return cmd_survey(args)
    return cmd_identify(args)


if __name__ == '__main__':
    sys.exit(main())
