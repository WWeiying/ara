import unittest
from pathlib import Path

from analyze_projection_phases import analyze

ROOT = Path(__file__).resolve().parents[2]


class Attribution(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT/'verification/out/q8k-current-projection-vcs-20261026-01/work/run.vcs.log'
        cls.text = '\n'.join(line for line in path.read_text().splitlines()
                             if line.startswith(('[QBS_PERF] ', 'Q8K_CURRENT_TRIAL ')))

    def test_accepted_data(self):
        row = analyze(self.text)['sums']['canonical']
        self.assertEqual(row['busy_cycles'], 670471)
        self.assertEqual(row['execute_outside_engine'], 43410)
        self.assertEqual(row['prep'], 392004)

    def test_reject_bad_association(self):
        for text in (self.text.replace('seq=1 ', 'seq=2 ', 1),
                     self.text.replace('success=1 ', 'success=0 ', 1),
                     self.text.replace('phase_terminal_cycles=1 ', 'phase_terminal_cycles=2 ', 1),
                     self.text.replace('commands=48 ', 'commands=47 ', 1),
                     '\n'.join(self.text.splitlines()[1:])):
            with self.subTest(), self.assertRaises(ValueError):
                analyze(text)


if __name__ == '__main__':
    unittest.main()
