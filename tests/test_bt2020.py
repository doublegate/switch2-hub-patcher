"""Executes the BT.2020 AVI overlay (asm/rtd2142_bt2020_avi.asm) in an 8051 simulator.

The stock routines it calls are modelled in Python: hdmi_build_avi (B9F6) writes a
configurable AVI into the once-packet registers, hdmi_pkt_build (F36F) rebuilds it
through the hooked F390 call, and the HDR packet helpers set or clear 5B6B bit 5. The
sink EDID is synthetic, built from CTA-861 data blocks; no real EDID or firmware is used.
"""

import contextlib
import io
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthetic
from sim8051 import Sim

from switch2_hub_patcher import cli, patch_rtd2142_bt2020, pipeline

HAVE_SDCC = bool(shutil.which('sdas8051') and shutil.which('sdld'))

PB1, PB2, PB3, CHECKSUM = 0x5B4A, 0x5B49, 0x5B48, 0x5B4B
FLAG, EOTF, HDR_STATUS, Y_SOURCE, DRM_EN = 0xE9F1, 0xDD9F, 0xE362, 0xE0E6, 0x5B6B
EDID = 0xC600
RGB, YCC422, YCC444, YCC420 = 0, 1, 2, 3
PQ, HLG, SDR = 2, 3, 0
# Colorimetry Data Block byte 3 bits
BT2020_RGB, BT2020_YCC = 0x80, 0x40


def cdb(flags, md=0):
    return bytes([0xE3, 0x05, flags, md])  # tag 7, length 3, extended tag 5


def hdr_static():
    return bytes([0xE3, 0x06, 0x0D, 0x01])  # extended tag 6: SDR, PQ, HLG


def edid(blocks=(), tag=0x02, d=None):
    base = bytearray(128)
    base[0:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'
    base[0x7E] = 1
    ext = bytearray(128)
    ext[0], ext[1] = tag, 3
    payload = b''.join(blocks)
    ext[4 : 4 + len(payload)] = payload
    ext[2] = 4 + len(payload) if d is None else d
    return bytes(base + ext)


def checksum_ok(sim, version=2, length=13):
    total = 0x82 + version + length + sum(sim.xdata[a] for a in (PB1, PB2, PB3, CHECKSUM))
    return total & 0xFF == 0


@unittest.skipUnless(HAVE_SDCC, 'SDCC (sdas8051/sdld) not installed')
class Bt2020OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.memory, cls.symbols = patch_rtd2142_bt2020.assemble()

    def make(self, *, y=RGB, eotf=PQ, metadata=True, sink=None, avi=None):
        """A simulator with the overlay, stock stubs and the given input state."""
        if sink is None:
            sink = edid([cdb(BT2020_YCC)])
        # PB1: Y in 6:5 plus A0; PB2: C/M/R (C = 2, BT.709, 16:9); PB3: EC/Q
        self.avi = dict(avi or {PB1: (y << 5) | 0x10, PB2: 0xA8, PB3: 0x00})
        self.builds = 0

        def build_avi(sim):  # B9F6: stock AVI build into 5B44..
            self.builds += 1
            for at, value in self.avi.items():
                sim.xdata[at] = value
            total = 0x82 + 2 + 13 + sum(self.avi.values())
            sim.xdata[CHECKSUM] = (-total) & 0xFF

        def pkt_build(sim):  # F36F with R5 = 0: rebuild the AVI through the F390 hook
            assert sim.r(5) == 0, 'AVI builder expected'
            sim.run(self.symbols['avi_wrap'])
            sim.c = True

        def drm_guard(sim):  # v7b FF20: HDR packet on only for EOTF != 0
            on = sim.xdata[EOTF] & 7
            sim.xdata[DRM_EN] = (sim.xdata[DRM_EN] | 0x20) if on else (sim.xdata[DRM_EN] & 0xDF)

        def drm_en_read(sim):  # 4AE7
            sim.dptr = DRM_EN
            sim.a = sim.xdata[DRM_EN] & 0xDF

        sim = Sim(
            self.memory,
            {0xB9F6: build_avi, 0xF36F: pkt_build, 0xFF20: drm_guard, 0x4AE7: drm_en_read},
        )
        sim.xdata[EOTF] = eotf
        sim.xdata[HDR_STATUS] = 0x23 if metadata else 0x21
        sim.xdata[Y_SOURCE] = y
        sim.xdata[DRM_EN] = 0x20
        sim.xdata[EDID : EDID + len(sink)] = sink
        return sim

    def build(self, sim):
        sim.run(self.symbols['avi_wrap'])
        self.assertTrue(checksum_ok(sim), 'AVI checksum')
        return sim.xdata[PB2] >> 6, (sim.xdata[PB3] >> 4) & 7

    def test_ycbcr_hdr_to_a_bt2020_ycc_sink_gets_bt2020(self):
        for y in (YCC422, YCC444, YCC420):
            sim = self.make(y=y)
            self.assertEqual(self.build(sim), (3, 6))
            self.assertEqual(sim.xdata[FLAG], 0x01)
            self.assertEqual(sim.xdata[PB2] & 0x3F, 0x28, 'M and R kept')

    def test_rgb_is_not_claimed_to_a_ycc_only_sink(self):
        sim = self.make(y=RGB, sink=edid([hdr_static(), cdb(BT2020_YCC)]))
        self.assertEqual(self.build(sim), (2, 0))
        self.assertEqual(sim.xdata[FLAG], 0x00)

    def test_rgb_to_a_bt2020_rgb_sink_gets_bt2020(self):
        sim = self.make(y=RGB, sink=edid([hdr_static(), cdb(BT2020_RGB | BT2020_YCC)]))
        self.assertEqual(self.build(sim), (3, 6))

    def test_ycbcr_is_not_claimed_to_an_rgb_only_sink(self):
        sim = self.make(y=YCC420, sink=edid([cdb(BT2020_RGB)]))
        self.assertEqual(self.build(sim), (2, 0))

    def test_hlg_counts_as_hdr_and_sdr_does_not(self):
        self.assertEqual(self.build(self.make(y=YCC420, eotf=HLG)), (3, 6))
        self.assertEqual(self.build(self.make(y=YCC420, eotf=SDR)), (2, 0))
        self.assertEqual(self.build(self.make(y=YCC420, metadata=False)), (2, 0))
        self.assertEqual(self.build(self.make(y=YCC420, eotf=6)), (2, 0))  # reserved EOTF

    def test_extended_avi_from_the_source_is_left_as_built(self):
        for pb2, pb3 in ((0xE8, 0x60), (0xE8, 0x70), (0xE8, 0x40), (0xC0, 0x50)):
            avi = {PB1: (YCC420 << 5) | 0x10, PB2: pb2, PB3: pb3}
            sim = self.make(y=YCC420, avi=avi)
            sim.run(self.symbols['avi_wrap'])
            self.assertEqual((sim.xdata[PB2], sim.xdata[PB3]), (pb2, pb3))
            self.assertTrue(checksum_ok(sim))
            self.assertEqual(sim.xdata[FLAG], 0x02)
            sim.run(self.symbols['drm_on'])  # the source's colorimetry stands: no rebuild
            self.assertEqual(self.builds, 1)

    def test_no_claim_without_a_usable_colorimetry_data_block(self):
        for sink in (
            edid([hdr_static()]),  # no Colorimetry Data Block
            edid([cdb(BT2020_YCC)], tag=0x00),  # no CTA-861 extension
            edid([cdb(BT2020_YCC)], d=0),  # no data blocks
            edid([cdb(BT2020_YCC)], d=6),  # block runs past d
            edid([bytes([0xE1, 0x05]), cdb(BT2020_YCC)[:0]]),  # length 1: too short
            edid([cdb(BT2020_YCC)], d=0x90),  # d > 127
            bytes(256),  # no EDID at all (buffer cleared at power-up)
        ):
            sim = self.make(y=YCC420, sink=sink)
            self.assertEqual(self.build(sim), (2, 0), sink[128:140].hex())

    def test_colorimetry_block_found_after_other_blocks(self):
        video = bytes([0x44, 0x10, 0x1F, 0x61, 0x60])  # Video Data Block, 4 VICs
        audio = bytes([0x23, 0x09, 0x07, 0x07])
        vsdb = bytes([0x67, 0xD8, 0x5D, 0xC4, 0x01, 0x78, 0x80, 0x03])
        sim = self.make(y=YCC420, sink=edid([video, audio, vsdb, hdr_static(), cdb(0x40)]))
        self.assertEqual(self.build(sim), (3, 6))

    def test_decision_follows_the_metadata_and_rebuilds_only_on_change(self):
        sim = self.make(y=YCC420, eotf=SDR)  # output start: AVI built before HDR metadata
        self.assertEqual(self.build(sim), (2, 0))
        sim.run(self.symbols['drm_on'])  # still SDR: no rebuild
        self.assertEqual(self.builds, 1)
        sim.xdata[EOTF] = PQ  # the new metadata arrives
        sim.run(self.symbols['drm_on'])
        self.assertEqual(self.builds, 2)
        self.assertEqual((sim.xdata[PB2] >> 6, (sim.xdata[PB3] >> 4) & 7), (3, 6))
        self.assertTrue(sim.xdata[DRM_EN] & 0x20, 'v7b guard still runs')
        sim.run(self.symbols['drm_on'])  # unchanged: no rebuild
        self.assertEqual(self.builds, 2)
        sim.xdata[HDR_STATUS] = 0x21  # metadata stops (HDR -> SDR)
        sim.run(self.symbols['drm_off'])
        self.assertEqual(self.builds, 3)
        self.assertEqual(sim.xdata[PB2] >> 6, 2)
        self.assertFalse(sim.xdata[DRM_EN] & 0x20, 'HDR packet off')
        self.assertTrue(checksum_ok(sim))


SYNTHETIC_RTD2142_BT2020 = '914cd548610732ad547e81f8f9b52437dcf1f6d5ca0ebd08f9f37b169eb5dd67'


class Bt2020BuilderGuardTests(unittest.TestCase):
    def test_refuses_anything_but_v7b(self):
        with self.assertRaises(ValueError):
            patch_rtd2142_bt2020.build(bytes(0x200000))

    def test_stacks_on_the_v7b_step(self):
        steps = pipeline.RTD2142_SDR_FIX_BT2020_STEPS
        self.assertEqual(steps[:-1], pipeline.RTD2142_SDR_FIX_STEPS)
        self.assertEqual(patch_rtd2142_bt2020.BASE_SHA, pipeline.RTD2142_SDR_FIX_STEPS[-1][2])
        with mock.patch.object(pipeline, 'sha256', return_value=steps[-1][2]):
            self.assertIn('BT.2020 candidate v1', pipeline.identify(b''))

    def test_cli_needs_sdr_fix_for_bt2020(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(['rtd2142', 'in.bin', 'out.bin', '--bt2020'])


@unittest.skipUnless(HAVE_SDCC, 'SDCC (sdas8051/sdld) not installed')
class Bt2020SyntheticTests(unittest.TestCase):
    def test_synthetic_build(self):
        image, manifest = synthetic.run_rtd2142_bt2020(synthetic.rtd2142_bt2020_image())
        self.assertEqual(manifest['banks_changed'], [2])
        self.assertEqual(
            manifest['overlay'], {'bank': 2, 'start': 'ff36', 'end': 'fffd', 'bytes': 200}
        )
        self.assertEqual(
            {h['address']: h['new'] for h in manifest['hooks']},
            {'f390': '12ff36', 'f31f': '02ff72', 'f326': '02ff77'},
        )
        self.assertFalse(manifest['hardware_validated'])
        if pipeline.overlay_digests() == pipeline.OVERLAY_DIGESTS_SDCC_4_6_0:
            self.assertEqual(synthetic.sha(image), SYNTHETIC_RTD2142_BT2020)

    def test_rejects_bad_guards(self):
        good = synthetic.rtd2142_bt2020_image()
        base = patch_rtd2142_bt2020.BANK_BASE
        for at, value, message in (
            (base + 0xF31F, 0x12, 'hook mismatch at 2:f31f'),  # not the v7b guard jump
            (base + 0xF390, 0x02, 'hook mismatch at 2:f390'),
            (base + 0xFFFF, 0x00, 'region 2:ff36 not erased'),
        ):
            image = bytearray(good)
            image[at] = value
            with self.assertRaisesRegex(ValueError, message):
                synthetic.run_rtd2142_bt2020(bytes(image))

    def test_real_dump_chain(self):
        path = os.environ.get('S2HUB_RTD2142_DUMP')
        if not path:
            self.skipTest('S2HUB_RTD2142_DUMP not set')
        image = pipeline.patch_rtd2142_sdr_fix_bt2020(Path(path).read_bytes(), log=lambda *_: None)
        self.assertEqual(pipeline.sha256(image), pipeline.RTD2142_SDR_FIX_BT2020_STEPS[-1][2])


if __name__ == '__main__':
    unittest.main()
