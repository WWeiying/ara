import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ethernet"))
import ara_init as init


def elf(address=0, memory=16, flags=5, machine=189):
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<HHIIIIIHHHHHH", 2, machine, 1, 0, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    return ident + header + struct.pack("<8I", 1, 84, address, address, 4, memory, flags, 4) + bytes(4)


class InitTests(unittest.TestCase):
    def test_clock_option_after_guard(self):
        for guarded in (True, False):
            with self.subTest(guarded=guarded), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                firmware = root / "firmware.elf"
                firmware.write_bytes(elf())
                args = ["ara_init", "--elf", str(firmware), "--sha256",
                        hashlib.sha256(elf()).hexdigest(), "--probes", "test.ltx",
                        "--out", str(root / "run"), "--fresh-bitstream-confirmed",
                        "--prepare-phy-clock"]
                with patch.object(sys, "argv", args), \
                        patch.object(init.load, "VivadoTransport"), \
                        patch.object(init, "fresh_guard", return_value={}, side_effect=None if guarded else RuntimeError("active")), \
                        patch.object(init.subprocess, "run") as run, \
                        patch.object(init.socket, "socket"), \
                        patch.object(init.load, "firmware_identity", return_value={"ready": True}):
                    self.assertEqual(init.main(), 0 if guarded else 1)
                    if guarded:
                        self.assertEqual(run.call_args.args[0][-1], "--prepare-phy-clock")
                    else:
                        run.assert_not_called()

    def test_valid_elf(self):
        data = elf()
        self.assertEqual(init.validate_firmware(data, hashlib.sha256(data).hexdigest()), [(0, 16)])

    def test_bad_images(self):
        for data in (elf(0x80000000), elf(0xFF000000), elf(memory=0x80001), elf(machine=243), elf()[:60]):
            with self.subTest(data=data), self.assertRaises(ValueError):
                init.validate_firmware(data, hashlib.sha256(data).hexdigest())
        with self.assertRaisesRegex(ValueError, "SHA256"):
            init.validate_firmware(elf(), "0" * 64)

    def test_never_reset_active_loader(self):
        transport = Mock()
        with patch.object(init.load.host, "identity", return_value={"caps": 1}), \
                patch.object(init.load, "cold_guard", return_value={}), \
                patch.object(init.load, "verify_rom", return_value="hash"):
            transport.ethernet_status.return_value = 0x45544831
            init.fresh_guard(transport)
            for shift in (32, 64, 96, 128, 160, 192):
                transport.ethernet_status.return_value = 0x45544831 | 1 << shift
                with self.subTest(shift=shift), self.assertRaises(RuntimeError):
                    init.fresh_guard(transport)


if __name__ == "__main__":
    unittest.main()
