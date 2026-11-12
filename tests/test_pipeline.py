"""Tests that need no vendor firmware run always; full pipeline tests need dumps.

Set S2HUB_VL103_DUMP and/or S2HUB_RTD2142_DUMP to your own stock dumps to run them.
"""
import os
import shutil
import unittest
from pathlib import Path

from switch2_hub_patcher import pipeline
from switch2_hub_patcher.vl103_crc import crc16_usb

HAVE_SDCC = shutil.which('sdas8051') and shutil.which('sdld')


class OfflineTests(unittest.TestCase):
    def test_crc16_usb_check_value(self):
        self.assertEqual(crc16_usb(b'123456789'), 0xB4C8)

    def test_wrong_input_is_refused(self):
        with self.assertRaises(pipeline.PatchError):
            pipeline.patch_vl103(b'\xff' * 0x8000, log=lambda _: None)
        with self.assertRaises(pipeline.PatchError):
            pipeline.patch_rtd2142(b'\xff' * 0x200000, log=lambda _: None)

    def test_asm_sources_present(self):
        asm = Path(pipeline.__file__).parent / 'asm'
        for name in ('target_responder', 'power_15v', 'identity_pd3', 'query02', 'versions',
                     'rtd2142_hdr_avi'):
            self.assertTrue((asm / f'{name}.asm').is_file(), name)


@unittest.skipUnless(HAVE_SDCC, 'SDCC (sdas8051/sdld) not installed')
class DumpTests(unittest.TestCase):
    def _run(self, env, patcher, expected):
        path = os.environ.get(env)
        if not path:
            self.skipTest(f'{env} not set')
        image = patcher(Path(path).read_bytes(), log=lambda _: None)
        self.assertEqual(pipeline.sha256(image), expected)

    def test_vl103(self):
        self._run('S2HUB_VL103_DUMP', pipeline.patch_vl103, pipeline.VL103_STEPS[-1][2])

    def test_rtd2142(self):
        self._run('S2HUB_RTD2142_DUMP', pipeline.patch_rtd2142, pipeline.RTD2142_STEPS[-1][2])


if __name__ == '__main__':
    unittest.main()
