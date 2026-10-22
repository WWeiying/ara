import csv
import tempfile
import unittest
from pathlib import Path

import observer_scope_741_rooted as audit


class RootedTests(unittest.TestCase):
    def test_frozen_measured_reader(self):
        self.assertEqual(audit.life.digest(audit.LIB), audit.LIB_SHA)
        text = audit.LIB.read_text()
        self.assertIn('gui_covtable_setroot -id CoverageTable.1 $token', text)
        self.assertIn('gui_process_events -mstime 100', text)

    def test_exact_four_and_nonrecursive(self):
        self.assertEqual(len(audit.TARGETS), 4)
        self.assertEqual(len(audit.ROOTS), 8)
        self.assertNotIn('-recursive', (audit.HERE / 'observer_scope_741_rooted.tcl').read_text())

    def test_wrong_native_root_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'roots.csv'
            fields = ['Stage', 'Scope', 'Token', 'Handle', 'GUIPath', 'Name', *audit.METRICS]
            with p.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fields)
                writer.writeheader()
                for scope in audit.ROOTS:
                    writer.writerow(dict(Stage='raw', Scope=scope, Token=scope, Handle='1',
                        GUIPath=scope.split('.')[-1], Name=scope.split('.')[-1],
                        **{m: '1.00%' for m in audit.METRICS}))
            self.assertEqual(len(audit.rooted(p, 'raw')), 8)
            p.write_text(p.read_text().replace('"', '').replace('i_system,', 'foreign,'))
            with self.assertRaises(ValueError):
                audit.rooted(p, 'raw')


if __name__ == '__main__':
    unittest.main()
