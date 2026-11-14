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
