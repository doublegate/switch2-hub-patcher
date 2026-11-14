"""Offline tests of the RTD2142 ISP port against a simulated chip."""

import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_rtd import FakeRTD

from switch2_hub_patcher import rtdisp


def images():
    rng = random.Random(7)
    base = bytes(rng.randrange(256) for _ in range(rtdisp.FLASH_SIZE))
    target = bytearray(base)
    target[0x2F31F:0x2F322] = b'\x02\xff\xc1'  # same sector as the HDMI patch
    target[0x2FF80:0x2FFE7] = bytes(range(0x67))
    return base, bytes(target)


BASE, TARGET = images()
KNOWN = {rtdisp.sha256(BASE): 'base image', rtdisp.sha256(TARGET): 'target image'}


def quiet(_):
    pass


class RealtekISPTests(unittest.TestCase):
    def run_isp(self, chip, fn):
        with rtdisp.RealtekISP(chip, log=quiet) as isp:
            return fn(isp)

    def test_rdid_and_status(self):
        chip = FakeRTD(BASE)
        self.assertEqual(self.run_isp(chip, lambda isp: isp.rdid()), rtdisp.XT25F16B_ID)
        self.assertTrue(chip.reset_requested)
        self.assertEqual(chip.indexed[rtdisp.GPIO_VALUE_ADDRESS] & 1, 0)  # strap released

    def test_dump_matches_flash(self):
        for chunk in (128, 32, 16):
            chip = FakeRTD(BASE, chunk=chunk)
            self.assertEqual(self.run_isp(chip, rtdisp.dump), BASE, chunk)

    def test_wrong_flash_id_refused(self):
        chip = FakeRTD(BASE, ident=b'\xff\xff\xff')
        with self.assertRaisesRegex(rtdisp.ISPError, 'unexpected flash ID'):
            self.run_isp(chip, rtdisp.dump)

    def test_flash_rewrites_only_changed_sector(self):
        chip = FakeRTD(BASE, chunk=32)
        sectors = self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, TARGET, KNOWN, quiet))
        self.assertEqual(sectors, [0x2F000])
        self.assertEqual(chip.erased, [0x2F000])
        self.assertEqual(bytes(chip.flash), TARGET)

    def test_flash_reports_progress_for_both_whole_chip_reads(self):
        import contextlib
        import io

        from switch2_hub_patcher import cli

        err = io.StringIO()
        err.isatty = lambda: False
        chip = FakeRTD(BASE, chunk=128)
        with contextlib.redirect_stderr(err):
            show = cli.progress_printer(rtdisp.FLASH_SIZE)
            self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, TARGET, KNOWN, quiet, show))
        marks = [line.split()[0] for line in err.getvalue().splitlines()]
        self.assertEqual(marks, [f'{p}%' for p in range(10, 101, 10)] * 2)

    def test_restore(self):
        chip = FakeRTD(TARGET)
        self.run_isp(chip, lambda isp: rtdisp.flash(isp, TARGET, BASE, KNOWN, quiet))
        self.assertEqual(bytes(chip.flash), BASE)

    def test_live_content_mismatch_writes_nothing(self):
        other = bytearray(BASE)
        other[0x100000] ^= 0xFF
        chip = FakeRTD(other)
        with self.assertRaisesRegex(rtdisp.ISPError, 'not the base image'):
            self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, TARGET, KNOWN, quiet))
        self.assertEqual(chip.erased, [])

    def test_unknown_images_refused(self):
        chip = FakeRTD(BASE)
        with self.assertRaisesRegex(rtdisp.ISPError, 'target image is not a known'):
            self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, BASE[:-1] + b'x', KNOWN, quiet))
        self.assertEqual(chip.erased, [])

    def test_block_protection_refused(self):
        chip = FakeRTD(BASE, status=0x1C)
        with self.assertRaisesRegex(rtdisp.ISPError, 'block protection'):
            self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, TARGET, KNOWN, quiet))
        self.assertEqual(chip.erased, [])

    def test_verify_failure_is_reported(self):
        chip = FakeRTD(BASE, corrupt_program=True)
        with self.assertRaisesRegex(rtdisp.ISPError, 'did not verify'):
            self.run_isp(chip, lambda isp: rtdisp.flash(isp, BASE, TARGET, KNOWN, quiet))
        self.assertEqual(chip.erased, [0x2F000, 0x2F000])  # one retry, then stop


if __name__ == '__main__':
    unittest.main()
