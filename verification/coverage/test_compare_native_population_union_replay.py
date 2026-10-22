import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import compare_native_population_union_replay as audit


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.prefix = b'EXACT742_LIVE pid=10 launch=9\n'
        self.q = dict(status='QUALIFIED', system={'raw': {'Toggle': '50%'}},
                      output_pins={str(self.out / 'service.log'): hashlib.sha256(self.prefix).hexdigest(),
                                   str(self.out / 'protected.tsv'): 'a' * 64})
        (self.out / 'live-identity.json').write_text(json.dumps(dict(pid=10, launch_pid=9)))
        tail = (json.dumps(dict(status=self.q['status'], seal='b' * 64, system=self.q['system'])) + '\n').encode()
        (self.out / 'service.log').write_bytes(self.prefix + tail)
        self.actual = copy.deepcopy(self.q)
        self.actual['output_pins'][str(self.out / 'service.log')] = audit.life.digest(self.out / 'service.log')

    def compare(self):
        return audit.compare_results(self.out, self.q, self.actual, 'b' * 64)

    def test_exact_only_known_append_pass(self):
        result = self.compare()
        self.assertEqual(result['unchanged_output_pins'], 1)
        self.assertEqual(len(result['approved_lifecycle_differences']), 1)

    def test_substantive_field_difference_hold(self):
        self.actual['system']['raw']['Toggle'] = '51%'
        with self.assertRaises(ValueError):
            self.compare()

    def test_protected_output_drift_hold(self):
        self.actual['output_pins'][str(self.out / 'protected.tsv')] = 'c' * 64
        with self.assertRaises(ValueError):
            self.compare()

    def test_new_lifecycle_file_not_blanket_allowed(self):
        self.actual['output_pins'][str(self.out / 'extra.log')] = 'c' * 64
        with self.assertRaises(ValueError):
            self.compare()

    def test_deleted_output_hold(self):
        del self.actual['output_pins'][str(self.out / 'protected.tsv')]
        with self.assertRaises(ValueError):
            self.compare()

    def test_arbitrary_or_duplicate_stdout_append_hold(self):
        p = self.out / 'service.log'
        p.write_bytes(p.read_bytes() + b'extra\n')
        with self.assertRaises(ValueError):
            self.compare()

    def test_prefix_mutation_hold(self):
        p = self.out / 'service.log'
        p.write_bytes(p.read_bytes().replace(b'pid=10', b'pid=11'))
        with self.assertRaises(ValueError):
            self.compare()

    def test_result_presence_difference_reported(self):
        self.assertEqual(audit.differences({'a': 1}, {}),
                         [dict(path='/a', before=1, after=None, presence_changed=True)])


if __name__ == '__main__':
    unittest.main()
