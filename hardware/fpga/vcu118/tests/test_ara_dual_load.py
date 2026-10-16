from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ethernet"))
import ara_load as load
import ara_init as init


class DualLoadTests(unittest.TestCase):
    def test_profiles(self):
        for caps in (1, 3):
            load.require_host_profile(caps)
        for caps in (0, 2, 5, 7):
            with self.assertRaises(RuntimeError):
                load.require_host_profile(caps)

    def test_dual_cold_guard(self):
        fields = ("ar_count", "aw_count", "r_bytes", "w_bytes", "read_outstanding",
                  "write_outstanding", "error_count")
        snapshot = {"identity": {"caps": 3}, "core": {"last_pc": 0x02000840, "trap_count": 0},
                    "ddr1": dict.fromkeys(fields, 0), "ddr2": dict.fromkeys(fields, 0)}
        transport = Mock()
        transport.exchange.return_value = [bytes(8), b"\xff" + bytes(7)]
        with patch.object(load.host, "read_debug", return_value=[0, 0]), \
                patch.object(load.host, "check_passive_boot"), \
                patch.object(load.host, "capture_snapshot", return_value=snapshot):
            load.cold_guard(transport)
            for field in fields:
                snapshot["ddr2"][field] = 1
                with self.assertRaises(RuntimeError):
                    load.cold_guard(transport)
                snapshot["ddr2"][field] = 0

    def test_init_dual(self):
        transport = Mock()
        transport.ethernet_status.return_value = 0x45544831
        with patch.object(load.host, "identity", return_value={"caps": 3}), \
                patch.object(load, "cold_guard", return_value={}), \
                patch.object(load, "verify_rom", return_value="hash"):
            self.assertEqual(init.fresh_guard(transport)["identity"]["caps"], 3)

    def test_image_still_cannot_use_ddr2(self):
        image = Mock(caps=3, segments=[])
        with patch.object(load.fast, "validate_segments"), self.assertRaises(ValueError):
            load.validate_image(image)


if __name__ == "__main__":
    unittest.main()
