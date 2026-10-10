import tempfile
from pathlib import Path
import unittest

import collect_dtlb_ppn_swap1200_schema as m


class Schema(unittest.TestCase):
    def test_exact_zero(self):
        m.vector_zero(m.zero_schema())

    def test_counter_types_and_nonzero(self):
        for key, expected in m.zero_schema().items():
            if type(expected) is int:
                for bad in (None, False, [], 1):
                    with self.subTest(key=key, bad=bad):
                        r = m.zero_schema(); r[key] = bad
                        with self.assertRaises(ValueError): m.vector_zero(r)

    def test_all_evidence_lists_must_be_empty(self):
        for key, expected in m.zero_schema().items():
            if type(expected) is list:
                for bad in (0, None, [243]):
                    with self.subTest(key=key, bad=bad):
                        r = m.zero_schema(); r[key] = bad
                        with self.assertRaises(ValueError): m.vector_zero(r)

    def test_missing_extra_status_mismatch_prefix(self):
        for mutate in (lambda r: r.pop('verified_probed_load_faults'),
                       lambda r: r.update(extra=0), lambda r: r.update(status='PASS'),
                       lambda r: r.update(first_mismatch={}),
                       lambda r: r.update(stopped_at_spike_index=1)):
            r = m.zero_schema(); mutate(r)
            with self.assertRaises(ValueError): m.vector_zero(r)

    def test_actual_parser_zero_return_schema(self):
        # Invoke the real parser/comparator, not a guessed return fixture.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spike, commit, vector = (root / n for n in ('spike', 'commit', 'vector'))
            spike.write_text('core   0: 3 0x0000000080000000 (0x00000013)\n')
            commit.write_text(','.join(m.frozen.FIELDS) + '\n')
            actual = Path(m.life.OUT / 'dtlb-ppn-swap1200-parent-20261008-01/vector_trace.csv')
            vector.write_bytes(actual.read_bytes())
            result = m.frozen.vector_commit.compare_vector_commits(spike, commit, vector, 0x80000000)
            m.vector_zero(result)
            self.assertEqual(result, m.zero_schema())

    def test_private_consumer_leaves_original_unchanged(self):
        old = m.frozen.collect.__globals__['vector_zero']
        new = m.consumer()
        self.assertIs(new.__code__, m.frozen.collect.__code__)
        self.assertIs(new.__globals__['vector_zero'], m.vector_zero)
        self.assertIs(m.frozen.collect.__globals__['vector_zero'], old)
        for key in ('memory_gate', 'wave_gate', 'terminal_gate', 'identity_gate',
                    'reference_check', 'logs', 'runner', 'life'):
            self.assertIs(new.__globals__[key], m.frozen.collect.__globals__[key])


if __name__ == '__main__':
    unittest.main()
