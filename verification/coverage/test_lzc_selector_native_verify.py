from pathlib import Path
import tempfile
import unittest

from lzc_selector_native_verify import verify_states


class StateTests(unittest.TestCase):
    def test_exact_selected_and_empty_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.tsv'
            rows = [['branch', '0', '1', 'expr'], ['cond', '2', '0', 'expr2']]
            path.write_text('position\tmetric\tid\tvector\texcluded\n0\tbranch\t0\t1\t0\n1\tcond\t2\t0\t1\n')
            verify_states(path, rows, 1)
            with self.assertRaises(ValueError):
                verify_states(path, rows, -1)
            with self.assertRaises(ValueError):
                verify_states(path, rows[:1], 1)

    def test_collateral_exclusion_wrong_id_or_missing_row_rejected(self):
        good = 'position\tmetric\tid\tvector\texcluded\n0\tbranch\t0\t1\t0\n1\tcond\t2\t0\t1\n'
        rows = [['branch', '0', '1', 'expr'], ['cond', '2', '0', 'expr2']]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'audit.tsv'
            for text in (good.replace('0\tbranch\t0\t1\t0', '0\tbranch\t0\t1\t1'),
                         good.replace('1\tcond\t2', '1\tcond\t3'),
                         '\n'.join(good.splitlines()[:2]) + '\n'):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    verify_states(path, rows, 1)


if __name__ == '__main__':
    unittest.main()
