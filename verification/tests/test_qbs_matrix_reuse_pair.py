import importlib.util
from pathlib import Path
import sys
import unittest

QBS = Path(__file__).resolve().parents[1] / "qbs"
sys.path.insert(0, str(QBS))
spec = importlib.util.spec_from_file_location("matrix_pair", QBS / "run_matrix_reuse_pair.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

LOG = """QBS end-to-end case 0 PASS profile=1 M=4 N=32 Kb=6 layouts=2/2 cycles=99
QBS phase case=0 setup=9 activation=10 weight=10 compute=30 overlap=20 drain=5 scheduler=5 commit=10 terminal=1
QBS traffic case=0 weight=27648 activation=7008 payload=34672 ranges=55 dot=6144 prefetch_wait=0
QBS FP probe case=0 blocked=0 issued=4608
QBS engine PASS: 1 functional cases
"""


class MatrixPairTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(module.checked_log(LOG, 4, 32, 6)["cycles"], 99)

    def test_reject_bad_geometry(self):
        with self.assertRaises(ValueError):
            module.checked_log(LOG, 8, 16, 6)

    def test_reject_phase_sum(self):
        with self.assertRaises(ValueError):
            module.checked_log(LOG.replace("cycles=99", "cycles=100"), 4, 32, 6)

    def test_reject_missing_or_error(self):
        for text in (LOG.split("QBS engine")[0], LOG + "Error: mismatch\n", LOG + LOG,
                     LOG.replace("QBS FP probe", "No probe")):
            with self.assertRaises(ValueError):
                module.checked_log(text, 4, 32, 6)

    def test_coordinates(self):
        text = "\n".join(f"O {r*16+c} {r*16+c:08x}" for r in range(8) for c in range(16))
        result = module.outputs(text, 0, 8, 16, 16)
        self.assertEqual(len(result), 128)
        self.assertEqual(result[7, 31], 127)

    def test_reject_missing_duplicate_or_invalid_outputs(self):
        valid = "O 0 00000001\nO 1 00000002\n"
        for text in (valid.splitlines()[0], valid + "O 1 00000002\n", valid.replace("O 1", "O 32")):
            with self.assertRaises(ValueError):
                module.outputs(text, 0, 1, 0, 2)


if __name__ == "__main__":
    unittest.main()
