import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import observer_scope_741_v2 as adapter


class SerializationTests(unittest.TestCase):
    def test_exact_successor_gates(self):
        n = adapter.namespace()
        self.assertEqual(len(n['TARGETS']), 4)
        self.assertEqual(len(adapter.REPLACEMENTS), 3)
        self.assertEqual(len(n['source_contract']()), 6)

    def test_raw_files_not_json_strings(self):
        n = adapter.namespace()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'inputs.txt'
            n['common'].save(p, '/a.vdb\n/b.vdb\n')
            self.assertEqual(p.read_text().splitlines(), ['/a.vdb', '/b.vdb'])
            p = Path(d) / 'observer-plan.tcl'
            n['common'].save(p, 'set observer_scopes {{a.b}}\n')
            self.assertEqual(p.read_bytes(), b'set observer_scopes {{a.b}}\n')

    def test_source_drift_rejected(self):
        with patch.object(Path, 'read_bytes', return_value=b'foreign'):
            with self.assertRaises(ValueError):
                adapter.namespace()


if __name__ == '__main__':
    unittest.main()
