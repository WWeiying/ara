import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from copy import deepcopy

QBS = Path(__file__).resolve().parents[1] / "qbs"
sys.path.insert(0, str(QBS))
spec = importlib.util.spec_from_file_location("matrix_replay", QBS / "replay_matrix_reuse_pair.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixture():
    cases = {}
    for profile, (_, k) in module.PROFILES.items():
        dot = 4 * 32 * k // 32
        for name, *_ in module.SLICES:
            extra = 100 if name.startswith("m8") else 0
            cases[profile + "_" + name] = {
                "cycles": dot + 200 + extra,
                "phases": {"activation": 100 + extra, "compute": dot, "other": 101},
                "traffic": {"dot": dot, "weight": 100, "activation": 50, "payload": 166, "ranges": 3},
                "fp": {"issued": 10, "cast_issue": 3, "half_issue": 0},
            }
    return cases


class ReplayTests(unittest.TestCase):
    def test_sums_and_floor(self):
        result = module.summarize(fixture())["q4_K"]
        self.assertEqual(result["ideal_integer_issue_floor_cycles"], 12288)
        self.assertEqual(result["m8_minus_m4_phase_cycles"]["activation"], 200)
        self.assertLess(result["m8_speedup_over_m4"], 1)

    def test_reject_missing_case_or_bad_dot(self):
        cases = fixture()
        del cases["q4_K_m4a"]
        with self.assertRaises(KeyError):
            module.summarize(cases)
        cases = fixture()
        cases["q4_K_m4a"]["traffic"]["dot"] += 1
        with self.assertRaises(ValueError):
            module.summarize(cases)

    def test_reject_phase_delta(self):
        cases = fixture()
        cases["q4_K_m8b"]["cycles"] += 1
        with self.assertRaises(ValueError):
            module.summarize(cases)

    def test_work_invariants(self):
        before = fixture()["q4_K_m4a"]
        after = deepcopy(before)
        after["cycles"] += 100
        module.compare_work(before, after)
        for family, key in (("traffic", "payload"), ("traffic", "ranges"), ("fp", "issued")):
            changed = deepcopy(after)
            changed[family][key] += 1
            with self.assertRaises(ValueError):
                module.compare_work(before, changed)

    def test_profile_identity(self):
        text = "QBS end-to-end case 0 PASS profile=1 M=4"
        module.check_profile(text, "q4_K")
        for bad in (text.replace("profile=1", "profile=2"), text + "\n" + text, ""):
            with self.assertRaises(ValueError):
                module.check_profile(bad, "q4_K")

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input"
            path.write_text("frozen")
            pins = {str(path): module.digest(path)}
            module.unchanged(pins)
            path.write_text("changed")
            with self.assertRaises(ValueError):
                module.unchanged(pins)


if __name__ == "__main__":
    unittest.main()
