import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "coverage"))
import merge_exploration as merge


class ExplorationSamplesTest(unittest.TestCase):
    def sample(self, root):
        for name in ("simv", "input.elf", "sim.log"):
            (root / name).write_text(name)
        (root / "coverage.dat").write_text("C '\x01f\x02rtl.sv\x01t\x02v_line' 1\n")
        data = {"status": "FAIL", "self_check_pass": False,
                "simv": str(root / "simv"), "elf": str(root / "input.elf")}
        for name, key in (("simv", "simv_sha256"), ("input.elf", "elf_sha256"),
                          ("sim.log", "sim_log_sha256"), ("coverage.dat", "coverage_sha256")):
            data[key] = merge.sha256(root / name)
        p = root / "result.json"
        p.write_text(json.dumps(data))
        return p

    def test_failed_sample_stays_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            result = merge.validate_sample(self.sample(Path(directory)))
            self.assertEqual(result["simulation_status"], "FAIL")
            self.assertFalse(result["self_check_pass"])

    def test_reject_changed_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = self.sample(root)
            (root / "simv").write_text("changed")
            with self.assertRaises(ValueError):
                merge.validate_sample(p)

    def test_reject_missing_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            p = self.sample(root)
            (root / "coverage.dat").unlink()
            with self.assertRaises(ValueError):
                merge.validate_sample(p)
