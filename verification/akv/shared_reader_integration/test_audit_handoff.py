import copy
import unittest
from audit_handoff import compare_records


class MatchedCounterTests(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(seq=i, busy_cycles=10, ar=2) for i in range(71)]

    def test_identical(self):
        self.assertEqual(compare_records(self.rows, copy.deepcopy(self.rows)), [])

    def test_detects_cycle_and_traffic_change(self):
        other = copy.deepcopy(self.rows)
        other[33]['busy_cycles'] += 1
        other[33]['ar'] += 1
        result = compare_records(self.rows, other)
        self.assertEqual(result[0]['command'], 33)
        self.assertEqual(set(result[0]['fields']), {'busy_cycles', 'ar'})

    def test_no_schema_relaxation(self):
        other = copy.deepcopy(self.rows)
        del other[0]['ar']
        with self.assertRaisesRegex(ValueError, 'schema'):
            compare_records(self.rows, other)

    def test_no_partial_acceptance(self):
        with self.assertRaisesRegex(ValueError, 'all matched'):
            compare_records(self.rows, self.rows[:-1])


if __name__ == '__main__':
    unittest.main()
