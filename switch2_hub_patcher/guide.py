"""Interactive walk-through: check, dump, patch, flash, each step confirmed.

Works in the current directory with the standard file names. Every action is one
of the regular commands, so the guide adds no new way to touch the hardware.
"""
import argparse
import platform
from pathlib import Path

from . import dpaux, status

FILES = {
    'vl103-stock': 'vl103-stock.bin', 'vl103-patched': 'vl103-patched.bin',
    'rtd-stock': 'rtd2142-stock.bin', 'rtd-patched': 'rtd2142-patched.bin',
}


def ask(prompt, answer=None, expect='y'):
    reply = answer(prompt) if answer else input(prompt)
    return reply.strip().lower() == expect


def transport_args(out=print):
    """Pick the RTD2142 path automatically: one Realtek bus (Linux) or service (macOS)."""
    ns = argparse.Namespace(bus=None, mac_service=0, chunk=None, no_reset=False)
    if platform.system() == 'Linux':
        candidates = [r for r in dpaux.scan() if r['branch'] and r['branch']['realtek']
                      and r['i2c']]
        if len(candidates) != 1:
            out('could not find exactly one Realtek DP AUX bus; run `find-aux` as root')
            return None
        ns.bus = int(candidates[0]['i2c'].split('-', 1)[1])
        out(f'using /dev/i2c-{ns.bus}')
    elif platform.system() == 'Darwin':
        from . import i2c, rtdisp
        hits = []
        for s in i2c.mac_services():
            transport = None
            try:
                transport = i2c.MacAVI2C(s['index'])
                rtdisp.RealtekISP(transport, log=None).mcu_mode()
                hits.append(s['index'])
            except OSError:
                pass
            finally:
                if transport:
                    transport.close()
        if len(hits) != 1:
            out('could not find exactly one external display path with a Realtek ISP; '
                'run `find-aux --probe`')
            return None
        ns.mac_service = hits[0]
        out(f'using macOS display service #{ns.mac_service}')
    return ns


def run(cli, answer=None, out=print, cwd='.'):
    here = Path(cwd)
    path = {k: str(here / v) for k, v in FILES.items()}
    rows = status.checks(cwd)
    if status.report(rows, out):
        out('fix the FAIL items first')
        return 1

    def have(key):
        return Path(path[key]).exists()

    if (not have('vl103-stock')
            and ask(f"dump the VL103 to {FILES['vl103-stock']}? [y/N] ", answer)
            and cli.cmd_vl103_dump(argparse.Namespace(output=path['vl103-stock'], reads=2,
                                                      device_id=None))):
        return 1
    if not have('rtd-stock') and ask(f"dump the RTD2142 to {FILES['rtd-stock']}? "
                                     '(video stops briefly) [y/N] ', answer):
        ns = transport_args(out)
        if ns is None:
            return 1
        ns.output, ns.reads = path['rtd-stock'], 2
        if cli.cmd_rtd_dump(ns):
            return 1
    for chip, patcher in (('vl103', cli.patch_vl103), ('rtd', cli.patch_rtd2142)):
        if have(f'{chip}-stock') and not have(f'{chip}-patched') and \
                ask(f"build {FILES[chip + '-patched']}? [y/N] ", answer):
            ns = argparse.Namespace(input=path[f'{chip}-stock'], output=path[f'{chip}-patched'],
                                    manifest=path[f'{chip}-patched'][:-4] + '.json')
            if cli.cmd_patch(ns, patcher):
                return 1
    if have('vl103-stock') and have('vl103-patched') and \
            ask('flash the VL103 (TV mode)? type "flash vl103": ', answer, 'flash vl103'):
        if cli.cmd_vl103_flash(argparse.Namespace(target=path['vl103-patched'],
                                                  base=path['vl103-stock'], device_id=None,
                                                  allow_brick=True)):
            return 1
        out('unplug and replug the hub before the next step')
    if have('rtd-stock') and have('rtd-patched') and \
            ask('flash the RTD2142 (HDR colours)? type "flash rtd2142": ', answer,
                'flash rtd2142'):
        ns = transport_args(out)
        if ns is None:
            return 1
        ns.target, ns.base, ns.allow_brick = path['rtd-patched'], path['rtd-stock'], True
        if cli.cmd_rtd_flash(ns):
            return 1
    out('done. Keep the *-stock.bin files: they are your way back.')
    return 0
