"""rtd-peek: the read-only 0x35 debug client, against a simulated debug slave."""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_dbg import FakeDebugSlave

from switch2_hub_patcher import cli, rtddbg


def no_sleep(_):
    pass


class DebugSessionTests(unittest.TestCase):
    def test_reads_values_and_leaves_debug_mode(self):
        chip = FakeDebugSlave({0xB130: 0x80, 0xB191: 0x09, 0x0012: 0x34})
        got = rtddbg.peek(chip, [0x0012, 0xB130, 0xB191], sleep=no_sleep)
        self.assertEqual(got, [(0x0012, 0x34), (0xB130, 0x80), (0xB191, 0x09)])
        self.assertFalse(chip.debug)

    def test_only_read_only_commands_are_sent(self):
        chip = FakeDebugSlave({0xB130: 0x80})
        rtddbg.peek(chip, [0xB130, 0xB131], sleep=no_sleep)
        commands = {reg for reg, data in chip.log if data}
        self.assertLessEqual(commands, rtddbg.READ_ONLY_COMMANDS)
        self.assertNotIn(0x3B, commands)
        self.assertNotIn(0xBA, commands)
        self.assertEqual(chip.log[0], (0x55, b'\x00'))
        self.assertEqual(chip.log[-1], (0x2F, b'\x00'))

    def test_self_check_failure_reports_nothing_and_still_leaves(self):
        chip = FakeDebugSlave({0xB130: 0x80}, slave_address=0x00)
        with self.assertRaisesRegex(rtddbg.DebugError, 'did not answer as decoded'):
            rtddbg.peek(chip, [0xB130], sleep=no_sleep)
        self.assertFalse(chip.debug)

    def test_a_write_command_is_refused_before_it_reaches_the_bus(self):
        chip = FakeDebugSlave()
        session = rtddbg.DebugSession(chip, sleep=no_sleep)
        with self.assertRaises(rtddbg.DebugError):
            session._send(0x3B, 0)
        self.assertEqual(chip.log, [])

    def test_address_parsing(self):
        self.assertEqual(rtddbg.parse_addresses(['b131', 'B130-b132']), [0xB130, 0xB131, 0xB132])
        for bad in (['zz'], ['B150-B140'], ['10000'], ['0000-01FF']):
            with self.assertRaises(rtddbg.DebugError, msg=bad):
                rtddbg.parse_addresses(bad)


class ClearBitsTests(unittest.TestCase):
    def test_clears_only_the_allowed_bit(self):
        chip = FakeDebugSlave({0xE362: 0x23})
        self.assertEqual(rtddbg.clear_bits(chip, 0xE362, 0x02, sleep=no_sleep), (0x23, 0x21))
        self.assertEqual(chip.xdata[0xE362], 0x21)
        self.assertFalse(chip.debug)
        writes = [(reg, data) for reg, data in chip.log if reg in rtddbg.WRITE_COMMANDS]
        self.assertEqual(writes, [(0x03, b'\x21'), (0x3B, b'\x62')])

    def test_clears_the_hdmi_colour_depth_nibble_only(self):
        chip = FakeDebugSlave({0x5B07: 0x63})
        self.assertEqual(rtddbg.clear_bits(chip, 0x5B07, 0xF0, sleep=no_sleep), (0x63, 0x03))
        with self.assertRaises(rtddbg.DebugError):
            rtddbg.clear_bits(chip, 0x5B07, 0x0F, sleep=no_sleep)

    def test_nothing_is_written_when_already_clear(self):
        chip = FakeDebugSlave({0xE362: 0x21})
        self.assertEqual(rtddbg.clear_bits(chip, 0xE362, 0x02, sleep=no_sleep), (0x21, 0x21))
        self.assertFalse([reg for reg, _ in chip.log if reg in rtddbg.WRITE_COMMANDS])

    def test_other_addresses_and_bits_are_refused_before_the_bus(self):
        for address, mask in ((0xE35D, 0x02), (0xE362, 0x01), (0xE362, 0x00), (0xFFFF, 0x02)):
            chip = FakeDebugSlave({0xE362: 0x23, 0xE35D: 0x23})
            with self.assertRaises(rtddbg.DebugError, msg=(address, mask)):
                rtddbg.clear_bits(chip, address, mask, sleep=no_sleep)
            self.assertEqual(chip.log, [])

    def test_failed_self_check_writes_nothing(self):
        chip = FakeDebugSlave({0xE362: 0x23}, slave_address=0x00)
        with self.assertRaises(rtddbg.DebugError):
            rtddbg.clear_bits(chip, 0xE362, 0x02, sleep=no_sleep)
        self.assertEqual(chip.xdata[0xE362], 0x23)
        self.assertFalse([reg for reg, _ in chip.log if reg in rtddbg.WRITE_COMMANDS])

    def test_cli_needs_the_flag_and_refuses_before_opening_hardware(self):
        for argv in (
            ['rtd-clear-bits', 'E362', '02'],
            ['rtd-clear-bits', 'E35D', '02', '--volatile-ram-write'],
        ):
            with (
                mock.patch.object(cli, 'open_transport') as opened,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertNotEqual(cli.main(argv), 0, argv)
            opened.assert_not_called()

    def test_cli_clears_and_reports(self):
        chip = FakeDebugSlave({0xE362: 0x23})
        out = io.StringIO()
        with (
            mock.patch.object(cli, 'open_transport', return_value=chip),
            mock.patch.object(rtddbg.time, 'sleep'),
            contextlib.redirect_stdout(out),
        ):
            code = cli.main(['rtd-clear-bits', 'E362', '02', '--volatile-ram-write'])
        self.assertEqual(code, 0)
        self.assertIn('E362  before 0x23  after 0x21', out.getvalue())


class SetBitsTests(unittest.TestCase):
    def test_sets_only_the_allowed_bit(self):
        chip = FakeDebugSlave({0xE10B: 0x01})
        self.assertEqual(rtddbg.set_bits(chip, 0xE10B, 0x08, sleep=no_sleep), (0x01, 0x09))
        writes = [(reg, data) for reg, data in chip.log if reg in rtddbg.WRITE_COMMANDS]
        self.assertEqual(writes, [(0x03, b'\x09'), (0x3B, b'\x0b')])
        self.assertFalse(chip.debug)

    def test_nothing_is_written_when_already_set(self):
        chip = FakeDebugSlave({0xE10B: 0x09})
        self.assertEqual(rtddbg.set_bits(chip, 0xE10B, 0x08, sleep=no_sleep), (0x09, 0x09))
        self.assertFalse([reg for reg, _ in chip.log if reg in rtddbg.WRITE_COMMANDS])

    def test_other_addresses_and_bits_are_refused_before_the_bus(self):
        for address, mask in ((0xE10B, 0x01), (0xE10B, 0x18), (0xE10C, 0x08), (0xE362, 0x02)):
            chip = FakeDebugSlave({0xE10B: 0x00})
            with self.assertRaises(rtddbg.DebugError, msg=(address, mask)):
                rtddbg.set_bits(chip, address, mask, sleep=no_sleep)
            self.assertEqual(chip.log, [])

    def test_cli_sets_and_reports(self):
        chip = FakeDebugSlave({0xE10B: 0x00})
        out = io.StringIO()
        with (
            mock.patch.object(cli, 'open_transport', return_value=chip),
            mock.patch.object(rtddbg.time, 'sleep'),
            contextlib.redirect_stdout(out),
        ):
            code = cli.main(['rtd-set-bits', 'E10B', '08', '--volatile-ram-write'])
        self.assertEqual(code, 0)
        self.assertIn('E10B  before 0x00  after 0x08', out.getvalue())

    def test_cli_set_needs_the_flag_and_the_allowlist(self):
        for argv in (
            ['rtd-set-bits', 'E10B', '08'],
            ['rtd-set-bits', 'E362', '02', '--volatile-ram-write'],
        ):
            with (
                mock.patch.object(cli, 'open_transport') as opened,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertNotEqual(cli.main(argv), 0, argv)
            opened.assert_not_called()


class PeekCommandTests(unittest.TestCase):
    def test_cli_prints_named_registers(self):
        chip = FakeDebugSlave({0xB130: 0x80})
        out = io.StringIO()
        with (
            mock.patch.object(cli, 'open_transport', return_value=chip) as opened,
            mock.patch.object(rtddbg.time, 'sleep'),
            contextlib.redirect_stdout(out),
        ):
            code = cli.main(['rtd-peek', 'B130'])
        self.assertEqual(code, 0)
        self.assertEqual(opened.call_args.kwargs['address'], rtddbg.DEBUG_ADDR)
        self.assertIn('B130  0x80  10000000  DPF_CTRL_0 (dp-rx-st1)', out.getvalue())

    def test_cli_rejects_bad_addresses_without_opening_hardware(self):
        err = io.StringIO()
        with (
            mock.patch.object(cli, 'open_transport') as opened,
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(['rtd-peek', 'nothex'])
        self.assertNotEqual(code, 0)
        opened.assert_not_called()


if __name__ == '__main__':
    unittest.main()
