"""Strict receipt selection, state, inventories and canonical replay checks."""
import json
from pathlib import Path
import tempfile
import unittest

import collect_wide_ingress as c


class ReplayTests(unittest.TestCase):
    def test_tuple_json_comparison(self):
        c.same({'rows': [(1, 2)]}, {'rows': [[1, 2]]})
        with self.assertRaises(ValueError): c.same({'rows': [(1, 3)]}, {'rows': [[1, 2]]})

    def test_wrong_receipt_identity_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'result.json').write_text('{}')
            with self.assertRaises(ValueError): c.load_accepted(path, '0' * 64, 'PASS')

    def test_matching_hash_cannot_override_failed_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'result.json').write_text(json.dumps(dict(state='FAIL')))
            with self.assertRaises(ValueError):
                c.load_accepted(path, c.digest(path / 'result.json'), 'PASS')

    def test_exact_default_anchor(self):
        value = c.ACCEPTED['default']
        self.assertEqual(value[1], 'fc937bdf96d44abac0d95eb14cd1bd974775afba2ec2c3a0fe47ceaa29c82b76')
        self.assertEqual(len({row[0] for row in c.ACCEPTED.values()}), 3)


if __name__ == '__main__':
    unittest.main()
