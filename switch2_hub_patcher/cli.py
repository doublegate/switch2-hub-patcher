"""switch2-hub-patcher: offline patcher for a user-supplied firmware dump.

Never talks to hardware. Dump and flash with fwupd / flashrom (see README).
"""
import argparse
import sys
from pathlib import Path

from .pipeline import PatchError, identify, patch_rtd2142, patch_vl103, sha256


def write_new(path, data):
    with open(path, 'xb') as f:          # refuse to overwrite anything
        f.write(data)


def cmd_patch(args, patcher):
    if Path(args.output).exists():
        print(f'error: {args.output} already exists; refusing to overwrite', file=sys.stderr)
        return 1
    source = Path(args.input).read_bytes()
    print(f'input  {args.input}  {sha256(source)}')
    try:
        image = patcher(source)
    except PatchError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1
    write_new(args.output, image)
    print(f'output {args.output}  {sha256(image)}')
    return 0


def cmd_identify(args):
    for name in args.files:
        data = Path(name).read_bytes()
        print(f'{name}: {identify(data)}  {sha256(data)}')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='switch2-hub-patcher', description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest='command', required=True)
    for name, helptext in (('vl103', 'patch a VL103 PD firmware dump (32 KiB)'),
                           ('rtd2142', 'patch an RTD2142 flash dump (2 MiB)')):
        p = sub.add_parser(name, help=helptext)
        p.add_argument('input')
        p.add_argument('output', help='must not exist')
    p = sub.add_parser('identify', help='report whether files are known stock/patched images')
    p.add_argument('files', nargs='+')
    args = ap.parse_args(argv)
    if args.command == 'vl103':
        return cmd_patch(args, patch_vl103)
    if args.command == 'rtd2142':
        return cmd_patch(args, patch_rtd2142)
    return cmd_identify(args)


if __name__ == '__main__':
    sys.exit(main())
