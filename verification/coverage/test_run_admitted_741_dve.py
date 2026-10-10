import csv
from pathlib import Path
import tempfile
import unittest
import run_admitted_741_dve as tool


class Summary(unittest.TestCase):
    def test_actual_raw740(self):
        row = tool.system_row(tool.PRIOR)
        self.assertEqual(row['FSM'], '60.54%')
        self.assertEqual(row['Toggle'], '63.33%')

    def test_missing_or_duplicate_root_and_invalid_percentage(self):
        with tool.PRIOR.open(newline='') as stream:
            original = list(csv.DictReader(stream))
        for mutation in ('missing', 'duplicate', 'invalid'):
            rows = [dict(r) for r in original]
            root = next(r for r in rows if r['Name'] == 'i_system')
            if mutation == 'missing':
                root['Name'] = 'not_system'
            elif mutation == 'duplicate':
                rows[-1]['Name'] = 'i_system'
            else:
                root['Toggle'] = 'NA'
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'summary.csv'
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                with self.assertRaises(ValueError):
                    tool.system_row(path)


if __name__ == '__main__':
    unittest.main()
