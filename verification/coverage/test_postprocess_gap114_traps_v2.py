import json
import unittest
import postprocess_gap114_traps_v2 as m
from test_postprocess_gap114_traps import Traps


class ActualScalar(unittest.TestCase):
    def fixture(self):
        actual = json.loads((m.RUN/'scalar-comparison.json').read_bytes())
        counts = json.loads((m.PRE/'successor-preflight.json').read_bytes())['counts']
        return actual, counts

    def test_actual_traps_and_full_scalar(self):
        actual, counts = self.fixture(); m.scalar_exact(actual, counts)
        self.assertEqual(actual['ara_retired_instructions'], 65306)
        self.assertEqual(actual['ara_committed_instructions'], 65298)
        with (m.RUN/'commit_trace.csv').open() as stream:
            rows = list(m.csv.DictReader(stream))
        symbols = json.loads((m.PRE/'successor-preflight.json').read_bytes())['symbols']
        m.traps_exact(rows, symbols)

    def test_changed_counts_or_skip_rejected(self):
        for key in ('ara_retired_instructions', 'ara_committed_instructions', 'ara_trap_events',
                    'matched_scalar_writes', 'matched_scalar_memory_accesses', 'skipped_unobservable_register_values'):
            actual, counts = self.fixture(); actual[key] += 1
            with self.assertRaises(ValueError): m.scalar_exact(actual, counts)

    def test_mismatch_rejected(self):
        actual, counts = self.fixture(); actual['mismatch'] = {'pc': 'bad'}
        with self.assertRaises(ValueError): m.scalar_exact(actual, counts)


if __name__ == '__main__': unittest.main()
