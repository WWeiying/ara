import copy
import json
import unittest
from pathlib import Path
import run_gap98_simulation as m


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.pre = json.loads((m.PRE / "preflight-manifest.json").read_bytes())

    def test_actual_contract(self):
        self.assertEqual(m.validate(self.pre), self.pre["main_case"])

    def test_reject_slot2_only(self):
        self.pre["physical_scope_count"] = 4
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_reject_baseline705(self):
        self.pre["baseline_tests"] = 705
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_reject_changed_elf(self):
        self.pre["pins"][self.pre["main_case"]["input_elf"]] = "0" * 64
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_reject_wrong_flags(self):
        self.pre["main_case"]["validation"]["exact_division_flags"] = [0] * 8
        with self.assertRaises(ValueError):
            m.validate(self.pre)

    def test_command(self):
        cmd = m.command(m.validate(self.pre), Path("/tmp/independent-gap98"))
        self.assertIn("+PRELOAD=" + self.pre["main_case"]["input_elf"], cmd)
        self.assertEqual(cmd[0], str(m.life.IMAGE))
        self.assertIn("+NO_FSDB", cmd)
        self.assertNotIn("inf-flags-spike-only", " ".join(cmd))


if __name__ == "__main__":
    unittest.main()
