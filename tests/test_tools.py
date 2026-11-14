"""Offline tests for the fwupd wrapper, status checklist and VL103 flash guards."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from switch2_hub_patcher import cli, fwupd, pipeline, status

ROOT = Path(__file__).resolve().parents[1]


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FwupdTests(unittest.TestCase):
    def test_bundled_quirk_matches_contrib(self):
        self.assertEqual(
            fwupd.QUIRK_SOURCE.read_bytes(), (ROOT / 'contrib' / fwupd.QUIRK_NAME).read_bytes()
        )

    def test_prepare_state_installs_quirk(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = fwupd.prepare_state(tmp)
            quirk = state / 'lib' / 'fwupd' / 'quirks.d' / fwupd.QUIRK_NAME
            self.assertEqual(quirk.read_bytes(), fwupd.QUIRK_SOURCE.read_bytes())

    def test_parse_devices(self):
        self.assertEqual(
            fwupd.parse_devices(json.dumps({'Error': {'Message': 'No detected devices'}})), []
        )
        with self.assertRaises(fwupd.FwupdError):
            fwupd.parse_devices(json.dumps({'Error': {'Message': 'permission denied'}}))
        with self.assertRaises(fwupd.FwupdError):
            fwupd.parse_devices('not json')
        devices = fwupd.parse_devices(
            json.dumps(
                {
                    'Devices': [
                        {'DeviceId': 'aaaa1111', 'Name': 'VL817'},
                        {'DeviceId': 'bbbb2222', 'Name': 'VL103 USB-C PD'},
                        {'Name': 'no id'},
                    ]
                }
            )
        )
        self.assertEqual([d['DeviceId'] for d in devices], ['aaaa1111', 'bbbb2222'])
        self.assertEqual(fwupd.pick_pd(devices)['DeviceId'], 'bbbb2222')
        self.assertEqual(fwupd.pick_pd(devices, 'aaaa')['DeviceId'], 'aaaa1111')
        with self.assertRaises(fwupd.FwupdError):
            fwupd.pick_pd([])


class Vl103FlashTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)
        self.stock, self.patched = self.dir / 'stock.bin', self.dir / 'patched.bin'
        self.stock.write_bytes(b'S')
        self.patched.write_bytes(b'P')
        digest = {b'S': pipeline.VL103_STOCK, b'P': pipeline.VL103_STEPS[-1][2]}
        self.sha = mock.patch.object(cli, 'sha256', side_effect=lambda d: digest.get(d, 'x' * 64))
        self.sha.start()
        self.addCleanup(self.sha.stop)
        self.device = {'DeviceId': 'bbbb2222', 'Name': 'VL103'}

    def flash(self, live, after=b'P'):
        with (
            mock.patch.object(fwupd, 'devices', return_value=[self.device]),
            mock.patch.object(fwupd, 'dump', side_effect=[live, after]),
            mock.patch.object(fwupd, 'install') as install,
        ):
            result = run_cli(
                'vl103-flash', str(self.patched), '--base', str(self.stock), '--allow-brick'
            )
        return result, install

    def test_requires_allow_brick(self):
        code, _, err = run_cli('vl103-flash', str(self.patched), '--base', str(self.stock))
        self.assertEqual(code, 1)
        self.assertIn('--allow-brick', err)

    def test_happy_path(self):
        (code, out, _), install = self.flash(live=b'S')
        self.assertEqual(code, 0, out)
        install.assert_called_once()
        self.assertIn('read-back matches VL103 patched', out)

    def test_live_mismatch_writes_nothing(self):
        (code, _, err), install = self.flash(live=b'other')
        self.assertEqual(code, 1)
        self.assertIn('not the base image', err)
        install.assert_not_called()

    def test_bad_readback_reported(self):
        (code, _, err), _ = self.flash(live=b'S', after=b'S')
        self.assertEqual(code, 1)
        self.assertIn('read-back', err)

    def test_unknown_target_refused(self):
        bad = self.dir / 'bad.bin'
        bad.write_bytes(b'?')
        code, _, err = run_cli('vl103-flash', str(bad), '--base', str(self.stock), '--allow-brick')
        self.assertEqual(code, 1)
        self.assertIn('target image is not a known', err)


class ProgressTests(unittest.TestCase):
    def run_progress(self, tty, steps, total=1000):
        ticks = iter(range(0, 10_000, 7))
        err = io.StringIO()
        err.isatty = lambda: tty
        with contextlib.redirect_stderr(err):
            show = cli.progress_printer(total, clock=lambda: next(ticks))
            for done in steps:
                show(done)
        return err.getvalue()

    def test_non_terminal_prints_a_line_per_ten_percent_with_elapsed_time(self):
        out = self.run_progress(False, range(31, 1001, 31))
        lines = out.splitlines()
        self.assertEqual([line.split()[0] for line in lines], [f'{p}%' for p in range(10, 100, 10)])
        self.assertNotIn('\r', out)
        self.assertRegex(lines[0], r'^ +10%  \d+m\d\ds$')

    def test_non_terminal_reports_completion_once(self):
        out = self.run_progress(False, [500, 1000, 1000])
        self.assertEqual([line.split()[0] for line in out.splitlines()], ['50%', '100%'])

    def test_second_pass_with_the_same_printer_reports_again(self):
        # rtd-flash: whole-chip read, sector rewrite, whole-chip re-read, one printer.
        out = self.run_progress(False, [500, 1000, 500, 1000])
        self.assertEqual(
            [line.split()[0] for line in out.splitlines()], ['50%', '100%', '50%', '100%']
        )

    def test_terminal_keeps_the_updating_percentage(self):
        out = self.run_progress(True, [500, 1000])
        self.assertEqual(out, '\r   50%\r  100%\n')


class StatusTests(unittest.TestCase):
    def test_next_step(self):
        base = [(status.OK, 'SDCC', ''), (status.OK, 'VIA VL817 hub on USB', 'present')]
        self.assertIn('vl103-dump', status.next_step([*base, (status.INFO, 'images here', '')]))
        self.assertIn(
            'rtd-dump',
            status.next_step([*base, (status.INFO, 'images here', 'a.bin: VL103 stock')]),
        )
        self.assertIn(
            'connect the hub',
            status.next_step(
                [(status.OK, 'SDCC', ''), (status.INFO, 'VIA VL817 hub on USB', 'not connected')]
            ),
        )
        self.assertIn('install SDCC', status.next_step([(status.FAIL, 'SDCC', 'missing')]))

    def test_images_are_found_flat_and_in_the_firmware_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'flat.bin').write_bytes(b'\0' * 0x8000)
            Path(tmp, 'notes.bin').write_bytes(b'\0' * 10)  # wrong size: ignored
            for sub, size in (('stock', 0x8000), ('candidates', 0x200000)):
                Path(tmp, 'firmware', sub).mkdir(parents=True)
                Path(tmp, 'firmware', sub, f'{sub}.bin').write_bytes(b'\0' * size)
            names = [line.split(':')[0] for line in status.images(tmp)]
        self.assertEqual(
            names, ['flat.bin', 'firmware/candidates/candidates.bin', 'firmware/stock/stock.bin']
        )

    def test_report_runs(self):
        lines = []
        code = status.report([(status.OK, 'a', 'b'), (status.FAIL, 'SDCC', 'x')], lines.append)
        self.assertEqual(code, 1)
        self.assertTrue(any(line.strip().startswith('next:') for line in lines))


class GuideTests(unittest.TestCase):
    def setUp(self):
        # The guide must never reach real hardware from a test: with a hub attached, an
        # unmocked dump or ISP probe talks to the live chip (and races any running dump).
        from switch2_hub_patcher import guide

        self.hardware = {}
        for owner, name, value in (
            (cli, 'cmd_vl103_dump', 0),
            (cli, 'cmd_vl103_flash', 0),
            (cli, 'cmd_rtd_dump', 0),
            (cli, 'cmd_rtd_flash', 0),
            (guide, 'transport_args', SimpleNamespace()),
        ):
            patcher = mock.patch.object(owner, name, return_value=value)
            self.hardware[name] = patcher.start()
            self.addCleanup(patcher.stop)

    def test_declines_everything(self):
        from switch2_hub_patcher import guide

        rows = [(status.OK, 'SDCC', ''), (status.OK, 'VIA VL817 hub on USB', 'present')]
        lines = []
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(status, 'checks', return_value=rows),
        ):
            code = guide.run(cli, answer=lambda _: 'n', out=lines.append, cwd=tmp)
        self.assertEqual(code, 0)
        self.assertIn('done.', lines[-1])

    def test_flash_needs_typed_confirmation(self):
        from switch2_hub_patcher import guide

        rows = [(status.OK, 'SDCC', '')]
        flash = self.hardware['cmd_vl103_flash']
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(status, 'checks', return_value=rows),
        ):
            for name in ('vl103-stock.bin', 'vl103-patched.bin'):
                Path(tmp, name).write_bytes(b'')
            guide.run(cli, answer=lambda _: 'y', out=lambda _: None, cwd=tmp)
            self.hardware['cmd_rtd_dump'].assert_called_once()  # 'y' reaches the dump step
            flash.assert_not_called()
            guide.run(
                cli,
                answer=lambda p: 'flash vl103' if 'VL103' in p else 'n',
                out=lambda _: None,
                cwd=tmp,
            )
            flash.assert_called_once()

    def test_paths_follow_the_firmware_layout(self):
        from switch2_hub_patcher import guide

        with tempfile.TemporaryDirectory() as tmp:
            flat = guide.paths(tmp)
            self.assertEqual(flat['vl103-stock'], str(Path(tmp, 'vl103-stock.bin')))
            Path(tmp, 'firmware').mkdir()
            nested = guide.paths(tmp)
        self.assertEqual(nested['rtd-stock'], str(Path(tmp, 'firmware/stock/rtd2142-stock.bin')))
        self.assertEqual(
            nested['vl103-patched'], str(Path(tmp, 'firmware/patched/vl103-patched.bin'))
        )

    def test_flash_uses_the_firmware_layout_when_present(self):
        from switch2_hub_patcher import guide

        rows = [(status.OK, 'SDCC', '')]
        flash = self.hardware['cmd_vl103_flash']
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.object(status, 'checks', return_value=rows),
        ):
            Path(tmp, 'firmware').mkdir()
            guide.run(cli, answer=lambda _: 'n', out=lambda _: None, cwd=tmp)  # creates dirs
            for sub, name in (('stock', 'vl103-stock.bin'), ('patched', 'vl103-patched.bin')):
                Path(tmp, 'firmware', sub, name).write_bytes(b'')
            guide.run(
                cli,
                answer=lambda p: 'flash vl103' if 'VL103' in p else 'n',
                out=lambda _: None,
                cwd=tmp,
            )
        flash.assert_called_once()
        args = flash.call_args.args[0]
        self.assertTrue(args.target.endswith('firmware/patched/vl103-patched.bin'))
        self.assertTrue(args.base.endswith('firmware/stock/vl103-stock.bin'))

    def test_stops_on_fail(self):
        from switch2_hub_patcher import guide

        with mock.patch.object(status, 'checks', return_value=[(status.FAIL, 'SDCC', 'x')]):
            self.assertEqual(guide.run(cli, answer=lambda _: 'y', out=lambda _: None), 1)


if __name__ == '__main__':
    unittest.main()
