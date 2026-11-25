import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('diag', Path(__file__).with_name('gate_rvv_xdiag_v1.py'))
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)


class Tests(unittest.TestCase):
    def test_scope(self):
        self.assertTrue(d.wanted('ara_tb.dut.i_ara_soc.i_system.i_ariane.pc_commit'))
        self.assertFalse(d.wanted('ara_tb.unrelated.pc_commit'))

    def test_unknown_not_sanitized(self):
        rows, values = {}, {}
        d.update(rows, values, 'a', '10x1', 12)
        d.update(rows, values, 'a', '1011', 13)
        self.assertEqual(rows['a']['first_unknown_tick'], 12)
        self.assertEqual(rows['a']['unknown_records'], 1)
        self.assertEqual(rows['a']['initial'], '10x1')

    def test_warnings(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'log'
            path.write_text('Warning soc.vrf : input D/DM unknown/high-Z in write cycle at simulation time 15235.5\n')
            self.assertEqual(d.log_evidence(path)['first']['D/DM']['ns'], '15235.5')


if __name__ == '__main__':
    unittest.main()
