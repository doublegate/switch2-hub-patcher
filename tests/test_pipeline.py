"""Tests that need no vendor firmware run always; full pipeline tests need dumps.

Set S2HUB_VL103_DUMP and/or S2HUB_RTD2142_DUMP to your own stock dumps to run them.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthetic

from switch2_hub_patcher import (
    cli,
    dpaux,
    hexfile,
    patch_rtd2142_sdr_fix,
    pipeline,
    rtd2142_map,
)
from switch2_hub_patcher.vl103_crc import crc16_usb, stored_and_computed

HAVE_SDCC = bool(shutil.which('sdas8051') and shutil.which('sdld'))

# Outputs of the builders on the synthetic images with SDCC 4.6.0. They lock the
# builders' behaviour so refactors can be checked without vendor firmware.
SYNTHETIC_VL103 = (
    '4924dcf78566e45ae20e2485726e36dd8a5bf1f4fa7d9d3a02a68e97c90bf93b',
    'bdad63c893db5a8c8f4f4dc55ff332437846923c248d4a14a06f8a547c5fc011',
    '58f30a6547e70bef43d3e120af1e0571d7748763d17d057f2e9c6239b3fccfa0',
    'a33208d13d6fd4c59b66c215f74d2d2d8a24e352aad6a4a3a1b352607ad78d5f',
    'f4068d18380030034a0f84702011468a6abb4aa53da97e9289796c0bd09241f2',
    '1e7ae24aa2ce36d25bb243851ec9721da769514bcac175974eba5ea976860278',
)
SYNTHETIC_RTD2142_SDR_FIX = 'd75629f67aa5547520f5232036467407721ead22226c2ddc9e538a0ef3b3ee70'
SYNTHETIC_RTD2142 = 'fa03c9a336b3f9280154d41465402cd185ffaae2e13bb27a4c4219e7c10955f9'


def quiet(_):
    pass


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class OfflineTests(unittest.TestCase):
    def test_crc16_usb_check_value(self):
        self.assertEqual(crc16_usb(b'123456789'), 0xB4C8)

    def test_wrong_input_is_refused(self):
        with self.assertRaises(pipeline.PatchError):
            pipeline.patch_vl103(b'\xff' * 0x8000, log=quiet)
        with self.assertRaises(pipeline.PatchError):
            pipeline.patch_rtd2142(b'\xff' * 0x200000, log=quiet)

    def test_asm_sources_present(self):
        asm = Path(pipeline.__file__).parent / 'asm'
        for name, module in pipeline.OVERLAYS:
            names = [part[0] for part in getattr(module, 'PARTS', ())] or [name]
            for source in names:
                self.assertTrue((asm / f'{source}.asm').is_file(), source)

    def test_step_hash_chain_matches_readme(self):
        self.assertEqual(
            pipeline.VL103_STEPS[-1][2],
            '6b5b0eff3e72be89b1b226739face9194f2ec30812b8c1fda5346cae90f4888e',
        )
        self.assertEqual(
            pipeline.RTD2142_STEPS[-1][2],
            'f242d130c7a0947f75bc673eb6100160c3cdb8e1d2f5cb9d1a5dca5332a742f1',
        )
        readme = (Path(__file__).resolve().parents[1] / 'README.md').read_text()
        for digest in (
            pipeline.VL103_STOCK,
            pipeline.RTD2142_STOCK,
            pipeline.VL103_STEPS[-1][2],
            pipeline.RTD2142_STEPS[-1][2],
        ):
            self.assertIn(digest, readme)

    def test_missing_toolchain_is_a_clean_error(self):
        with (
            mock.patch.object(pipeline.shutil, 'which', return_value=None),
            mock.patch.object(pipeline, 'sha256', return_value=pipeline.VL103_STOCK),
            self.assertRaisesRegex(pipeline.PatchError, 'SDCC tools not found'),
        ):
            pipeline.patch_vl103(b'', log=quiet)

    def test_builder_failure_becomes_patch_error(self):
        def broken(_):
            raise ValueError('hook guard failed at 0x5d3f')

        steps = (('broken step', broken, '0' * 64),)
        with (
            mock.patch.object(pipeline, 'check_toolchain'),
            self.assertRaisesRegex(pipeline.PatchError, 'broken step.*hook guard'),
        ):
            pipeline.run(b'x', pipeline.sha256(b'x'), steps, log=quiet)

    def test_identify(self):
        with mock.patch.object(pipeline, 'sha256', return_value=pipeline.VL103_STEPS[2][2]):
            self.assertIn('partly patched (after step 3/6', pipeline.identify(b''))
        with mock.patch.object(pipeline, 'sha256', return_value=pipeline.VL103_STEPS[-1][2]):
            self.assertEqual(pipeline.identify(b''), 'VL103 patched')
        sdr_fix = pipeline.RTD2142_SDR_FIX_STEPS[-1][2]
        with mock.patch.object(pipeline, 'sha256', return_value=sdr_fix):
            self.assertIn('not yet tested on a hub', pipeline.identify(b''))
        for digest, _ in pipeline.RTD2142_SDR_FIX_SUPERSEDED:
            with mock.patch.object(pipeline, 'sha256', return_value=digest):
                self.assertIn('superseded', pipeline.identify(b''))
        self.assertIn('VL103-sized', pipeline.identify(b'\0' * 0x8000))
        self.assertIn('RTD2142-sized', pipeline.identify(b'\0' * 0x200000))
        self.assertEqual(pipeline.identify(b'abc'), 'unknown')


class CliTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir)

    def test_missing_input(self):
        code, _, err = run_cli('vl103', str(self.dir / 'nope.bin'), str(self.dir / 'out.bin'))
        self.assertEqual(code, 1)
        self.assertIn('cannot read', err)

    def test_refuses_existing_output_and_manifest(self):
        (self.dir / 'in.bin').write_bytes(b'')
        (self.dir / 'm.json').write_text('{}')
        code, _, err = run_cli(
            'vl103',
            str(self.dir / 'in.bin'),
            str(self.dir / 'out.bin'),
            '--manifest',
            str(self.dir / 'm.json'),
        )
        self.assertEqual(code, 1)
        self.assertIn('refusing to overwrite', err)

    def test_wrong_image_writes_nothing(self):
        (self.dir / 'in.bin').write_bytes(b'\0' * 0x8000)
        code, _, err = run_cli('vl103', str(self.dir / 'in.bin'), str(self.dir / 'out.bin'))
        self.assertEqual(code, 1)
        self.assertIn('not the supported stock image', err)
        self.assertFalse((self.dir / 'out.bin').exists())

    def test_manifest_written(self):
        (self.dir / 'in.bin').write_bytes(b'stock')

        def patcher(_image, manifests=None):
            assert manifests is not None
            manifests.append({'step': 's', 'output_sha256': 'x', 'manifest': {'k': 1}})
            return b'patched'

        args = mock.Mock(
            input=str(self.dir / 'in.bin'),
            output=str(self.dir / 'out.bin'),
            manifest=str(self.dir / 'm.json'),
        )
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.cmd_patch(args, patcher), 0)
        record = json.loads((self.dir / 'm.json').read_text())
        self.assertEqual(record['output_sha256'], pipeline.sha256(b'patched'))
        self.assertEqual(record['steps'][0]['manifest'], {'k': 1})

    def test_identify_reports_unreadable(self):
        code, _, err = run_cli('identify', str(self.dir / 'nope.bin'))
        self.assertEqual(code, 1)
        self.assertIn('cannot read', err)


class DpAuxTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        self.sys = self.root / 'sys'
        self.dev = self.root / 'dev'
        self.dev.mkdir()

    def connector(self, name, status, aux, bus):
        path = self.sys / name
        path.mkdir(parents=True)
        (path / 'status').write_text(status + '\n')
        (path / aux).mkdir()
        (path / f'i2c-{bus}').mkdir()

    def test_parse_branch(self):
        block = bytes.fromhex('00e04c') + b'2142\0\0' + bytes([0x10, 3, 7])
        info = dpaux.parse_branch(block)
        assert info is not None
        self.assertTrue(info['realtek'])
        self.assertEqual(
            (info['device_id'], info['hw_rev'], info['fw_rev']), ('2142', '1.0', '3.7')
        )
        self.assertIsNone(dpaux.parse_branch(b'\0' * 3))

    def test_finds_single_realtek_bus(self):
        self.connector('card1-DP-1', 'connected', 'drm_dp_aux0', 7)
        self.connector('card1-DP-2', 'connected', 'drm_dp_aux1', 8)
        self.connector('card1-DP-3', 'disconnected', 'drm_dp_aux2', 9)
        (self.dev / 'i2c-7').touch()
        (self.dev / 'i2c-8').touch()
        blocks = {
            'drm_dp_aux0': bytes.fromhex('00e04c') + b'\0' * 9,
            'drm_dp_aux1': bytes.fromhex('001cf8') + b'\0' * 9,
        }
        records = dpaux.scan(str(self.sys), str(self.dev), lambda p: blocks[Path(p).name])
        lines = []
        self.assertEqual(dpaux.report(records, lines.append), 0)
        self.assertIn('realtek_mst_i2c_spi:bus=7,allow_brick=yes,reset_mcu=1', '\n'.join(lines))

    def test_missing_i2c_dev_is_reported(self):
        self.connector('card0-DP-1', 'connected', 'drm_dp_aux0', 4)
        records = dpaux.scan(
            str(self.sys), str(self.dev), lambda _: bytes.fromhex('00e04c') + b'\0' * 9
        )
        lines = []
        self.assertEqual(dpaux.report(records, lines.append), 1)
        self.assertIn('modprobe i2c-dev', '\n'.join(lines))

    def test_permission_error(self):
        self.connector('card0-DP-1', 'connected', 'drm_dp_aux0', 4)

        def denied(_):
            raise PermissionError(13, 'Permission denied')

        lines = []
        self.assertEqual(
            dpaux.report(dpaux.scan(str(self.sys), str(self.dev), denied), lines.append), 1
        )
        self.assertIn('run as root', '\n'.join(lines))


class SurveyTests(unittest.TestCase):
    def test_xrefs_finds_writes_and_reads(self):
        image = bytearray(0x30000)
        image[0x21234:0x21238] = bytes.fromhex('90 4d b6 f0')  # bank 2: write MISC1
        image[0x00100:0x00104] = bytes.fromhex('90 5b 6b e0')  # bank 0: read HDMI pkt enable
        image[0x00200:0x00204] = bytes.fromhex('90 12 34 f0')  # unknown register
        refs = rtd2142_map.xrefs(bytes(image))
        self.assertEqual(refs[0x4DB6], [(2, 0x1234, 0xF0)])
        self.assertEqual(refs[0x5B6B], [(0, 0x0100, 0xE0)])
        self.assertNotIn(0x1234, refs)
        text = '\n'.join(rtd2142_map.summary(bytes(image)))
        self.assertIn('MN_STRM_ATTR_MISC1', text)
        self.assertIn('bank 2 1234  write', text)

    def test_register_map_is_consistent(self):
        regs = rtd2142_map.REGISTERS
        self.assertEqual(regs[0x4E14][1], 'SEC_PSR_DB16')
        self.assertEqual(regs[0xBC14][1], 'SEC_PSR_DB16')
        self.assertEqual(regs[0xB19A][1], 'DP_RSVA')
        self.assertEqual(regs[0xB2FC][1], 'DUMMY_2')

    def test_survey_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, 'rtd.bin')
            path.write_bytes(bytes.fromhex('90 5b 49 f0') + bytes(0x200000 - 4))
            code, out, _ = run_cli('survey', str(path))
        self.assertEqual(code, 0)
        self.assertIn('DATA_ISLAND_PACKETIZER_20', out)


@unittest.skipUnless(HAVE_SDCC, 'SDCC (sdas8051/sdld) not installed')
class AssemblerTests(unittest.TestCase):
    def test_overlay_digests(self):
        digests = pipeline.overlay_digests()
        if digests != pipeline.OVERLAY_DIGESTS_SDCC_4_6_0:
            self.skipTest(
                f'assembler output differs from SDCC 4.6.0 ({pipeline.toolchain_version()})'
            )

    def test_synthetic_vl103_chain(self):
        image = synthetic.vl103_image()
        results = synthetic.run_vl103_chain(image)
        for (out, _), expected in zip(results, SYNTHETIC_VL103):
            self.assertEqual(len(out), 0x8000)
            stored, computed = stored_and_computed(out)
            self.assertEqual(stored, computed)
            if pipeline.overlay_digests() == pipeline.OVERLAY_DIGESTS_SDCC_4_6_0:
                self.assertEqual(synthetic.sha(out), expected)

    def test_synthetic_rtd2142(self):
        image, manifest = synthetic.run_rtd2142(synthetic.rtd2142_image())
        self.assertEqual(manifest['banks_changed'], [2])
        self.assertEqual(manifest['changed_byte_count'], 108)  # matches the published patch size
        if pipeline.overlay_digests() == pipeline.OVERLAY_DIGESTS_SDCC_4_6_0:
            self.assertEqual(synthetic.sha(image), SYNTHETIC_RTD2142)

    def test_synthetic_rtd2142_sdr_fix(self):
        image, manifest = synthetic.run_rtd2142_sdr_fix(synthetic.rtd2142_sdr_fix_image())
        self.assertEqual(manifest['banks_changed'], [2, 5])
        self.assertEqual(manifest['changed_byte_count'], 71)  # 3 hooks (8 bytes differ) + 62 + 1
        self.assertEqual(
            [(b['bank'], b['address'], b['old'], b['new']) for b in manifest['byte_patches']],
            [(2, 'c432', '6077', '8077')],
        )
        self.assertFalse(manifest['hardware_validated'])
        hooks = {(h['bank'], h['address']): h['new'] for h in manifest['hooks']}
        self.assertEqual(
            hooks, {(5, 'c476'): '02fd80', (5, 'dead'): '02fd9b', (2, 'e952'): '02ff00'}
        )
        if pipeline.overlay_digests() == pipeline.OVERLAY_DIGESTS_SDCC_4_6_0:
            self.assertEqual(synthetic.sha(image), SYNTHETIC_RTD2142_SDR_FIX)

    def test_sdr_fix_overlays_rejoin_the_stock_code(self):
        memory, symbols = patch_rtd2142_sdr_fix.assemble()
        bank5 = bytes(memory[(5, a)] for a in range(0xFD80, 0xFD9B))
        field8 = bytes(memory[(5, a)] for a in range(0xFD9B, 0xFDAF))
        # rx2_field8: MISC1 bit 6 clear -> A = 0; else A = E3E6 & 1F; both to the stock DF00
        self.assertEqual(field8.hex(), '90b403e030e60990e3e6e0541f02df00e402df00')
        bank2 = bytes(memory[(2, a)] for a in range(0xFF00, 0xFF0F))
        # MISC1 bit 6 set -> stock; E3E6[4:0] == 0 -> stock (DPTR = B403 again);
        # else E3E6 &= E0, C = 0, ret. Stock continues at C479.
        self.assertEqual(bank5.hex(), '90b403e020e61190e3e6e0541f6006e054e0f0c32290b40302c479')
        # 5B06 &= FC, inc dptr, 5B07 &= 0F, ljmp E959
        self.assertEqual(bank2.hex(), '905b06e054fcf0a3e0540ff002e959')
        self.assertEqual(symbols['rx2_fmt_'], (5, 0xFD80))
        self.assertEqual(symbols['rx2_fiel'], (5, 0xFD9B))
        self.assertEqual(symbols['hdmi_dee'], (2, 0xFF00))

    def test_sdr_fix_rejects_bad_guards(self):
        good = synthetic.rtd2142_sdr_fix_image()
        for at, value, message in (
            (5 * 0x10000 + 0xC476, 0x12, 'hook mismatch at 5:c476'),
            (2 * 0x10000 + 0xFF10, 0x00, 'region 2:ff00 not erased'),
            (2 * 0x10000 + 0xC432, 0x80, 'byte patch mismatch at 2:c432'),
        ):
            image = bytearray(good)
            image[at] = value
            with self.assertRaisesRegex(ValueError, message):
                synthetic.run_rtd2142_sdr_fix(bytes(image))

    def test_sdr_fix_needs_the_exact_stock_image(self):
        with self.assertRaisesRegex(ValueError, 'exact original RTD2142'):
            patch_rtd2142_sdr_fix.build(synthetic.rtd2142_sdr_fix_image())

    def test_research_draft_assembles(self):
        research = Path(__file__).resolve().parents[1] / 'research'
        with mock.patch.object(hexfile, 'ASM', research):
            memory, symbols = hexfile.assemble_with_symbols('dp_hdr_vsc', ((0, 0x200),))
        self.assertIn('dp_vsc_a', symbols)
        self.assertLess(len(memory), 0x80)

    def test_builders_reject_bad_guards(self):
        image = bytearray(synthetic.vl103_image())
        image[0x7800] = 0  # CODE cave no longer erased
        image[-2:] = crc16_usb(bytes(image[:-2])).to_bytes(2, 'little')
        with self.assertRaisesRegex(ValueError, 'cave'):
            synthetic.run_vl103_chain(bytes(image))


@unittest.skipUnless(HAVE_SDCC, 'SDCC (sdas8051/sdld) not installed')
class DumpTests(unittest.TestCase):
    def _run(self, env, patcher, expected):
        path = os.environ.get(env)
        if not path:
            self.skipTest(f'{env} not set')
        image = patcher(Path(path).read_bytes(), log=quiet)
        self.assertEqual(pipeline.sha256(image), expected)

    def test_vl103(self):
        self._run('S2HUB_VL103_DUMP', pipeline.patch_vl103, pipeline.VL103_STEPS[-1][2])

    def test_rtd2142(self):
        self._run('S2HUB_RTD2142_DUMP', pipeline.patch_rtd2142, pipeline.RTD2142_STEPS[-1][2])

    def test_rtd2142_sdr_fix(self):
        self._run(
            'S2HUB_RTD2142_DUMP',
            pipeline.patch_rtd2142_sdr_fix_only,
            pipeline.RTD2142_SDR_FIX_STEPS[-1][2],
        )


if __name__ == '__main__':
    unittest.main()
