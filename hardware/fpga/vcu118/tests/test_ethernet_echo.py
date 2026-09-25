import importlib.util
from pathlib import Path
import shutil
import subprocess
import unittest


ETHERNET = Path(__file__).resolve().parents[1] / "ethernet"
SPEC = importlib.util.spec_from_file_location("echo_packets", ETHERNET / "echo_packets.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EchoPacketTests(unittest.TestCase):
    def test_frame_pairs(self):
        host = MODULE.mac_bytes("00:e0:4c:87:d1:2d")
        for size in MODULE.FRAME_SIZES:
            sent, expected = MODULE.frame_pair(size, host, b"12345678")
            self.assertEqual(len(sent), size)
            self.assertEqual(len(expected), size)
            self.assertEqual(sent[:6], MODULE.BOARD_MAC)
            self.assertEqual(expected[:6], host)
            self.assertEqual(expected[6:12], MODULE.BOARD_MAC)
            self.assertEqual(expected[12:], sent[12:])

    def test_reject_invalid_mac_and_lengths(self):
        for mac in ("00:00:00:00:00:00", "01:00:00:00:00:01", "bad"):
            with self.assertRaises(ValueError):
                MODULE.mac_bytes(mac)
        for size in (59, 1515):
            with self.assertRaises(ValueError):
                MODULE.frame_pair(size, b"\0\1\2\3\4\5", b"12345678")

    @unittest.skipUnless(shutil.which("tclsh"), "tclsh is unavailable")
    def test_control_tcl_loads_without_vivado(self):
        script = ("set ::eth_echo_library_only 1\n"
                  f"source {{{(ETHERNET / 'echo_control.tcl').as_posix()}}}\n"
                  "if {![catch {eth_echo::require_pcs_link 0x8000} message]} {error \"missing link accepted\"}\n"
                  "if {![string match {*link/sync not ready*} $message]} {error $message}\n"
                  "eth_echo::require_pcs_link 0x0030\n"
                  "puts ECHO_LIBRARY_READY\n")
        result = subprocess.run(["tclsh"], input=script, text=True,
                                capture_output=True, check=True)
        self.assertIn("ECHO_LIBRARY_READY", result.stdout)
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
