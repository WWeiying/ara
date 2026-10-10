from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_targeted_extension as run


class ExtensionTest(unittest.TestCase):
    def test_hierarchy_keeps_lanes_distinct(self):
        text = 'Name,Depth,Line\nara_tb,0,80%\ndut,1,90%\nlane0,2,70%\nqueue,3,60%\nlane1,2,72%\nqueue,3,65%\n'
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'summary.csv'
            path.write_text(text)
            rows = run.hierarchy_rows(path)
            self.assertEqual(rows['ara_tb.dut.lane0.queue']['Line'], '60%')
            self.assertEqual(rows['ara_tb.dut.lane1.queue']['Line'], '65%')

    def test_hierarchy_rejects_missing_parent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'summary.csv'
            path.write_text('Name,Depth\nara_tb,0\nqueue,3\n')
            with self.assertRaises(ValueError):
                run.hierarchy_rows(path)

    def test_ledger_requires_audited_membership(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            (directory / 'all-passed-outcomes.json').write_text('[]')
            record = {'status': 'PASS', 'passed': 1, 'reports': {}}
            with patch.object(run.full, 'read', return_value=record), patch.object(run.full, 'check'):
                with self.assertRaisesRegex(ValueError, 'unbound'):
                    run.ledger(directory)

    def test_complete_checkpoint_coverage_status(self):
        saved = {}
        state = {'status': 'PASS', 'phase': 'complete', 'coverage_status': 'PENDING'}
        collection = {'passed': 623, 'reports': {}}
        def read(path):
            return state if path.name == 'checkpoint.json' else collection
        with patch.object(run.full, 'execute', return_value=0), patch.object(run.full, 'read', side_effect=read), \
                patch.object(run.full, 'check'), patch.object(run.full, 'save', side_effect=lambda p, r: saved.update(r)):
            self.assertEqual(run.execute(Path('/unused')), 0)
        self.assertEqual(saved['coverage_status'], 'COMPLETE')
        self.assertEqual(saved['aggregate_passed'], 623)


if __name__ == '__main__':
    unittest.main()
