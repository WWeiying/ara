"""Tiny budget/boundary/framing tests only; no original CSV or fullstream."""
import io
import json
from types import SimpleNamespace
import unittest

import diagnostic_scan as d


class BudgetTests(unittest.TestCase):
    def test_warmup_not_predicted(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        self.assertIsNone(f.update(16*1024*1024, 1000)['predicted_finish_s'])
        self.assertIsNone(f.baseline)

    def test_two_bad_checkpoints_stop(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        self.assertIsNone(f.update(32*1024*1024, 100)['predicted_finish_s'])
        self.assertFalse(f.update(40*1024*1024, 200)['stop'])
        self.assertTrue(f.update(48*1024*1024, 300)['stop'])

    def test_good_prediction_resets_consecutive(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        f.update(32*1024*1024, 100)
        self.assertEqual(f.update(40*1024*1024, 200)['consecutive_over'], 1)
        self.assertEqual(f.update(128*1024*1024, 210)['consecutive_over'], 0)

    def test_startup_and_warmup_excluded_from_rate(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        f.update(32*1024*1024, 500)
        p = f.update(40*1024*1024, 510)
        self.assertEqual(p['bytes_per_s'], 8*1024*1024/10)
        self.assertAlmostEqual(p['predicted_finish_s'], 510+p['remaining_s'])

    def test_eof_not_early_stopped(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        f.update(32*1024*1024, 10)
        p = f.update(d.EXPECTED_BYTES, 1700)
        self.assertFalse(p['stop'])
        self.assertEqual(p['remaining_s'], 0)

    def test_bad_progress_rejected(self):
        f = d.Forecast(d.EXPECTED_BYTES)
        f.update(32*1024*1024, 100)
        with self.assertRaises(ValueError):
            f.update(32*1024*1024, 101)
        with self.assertRaises(ValueError):
            d.Forecast(d.EXPECTED_BYTES).update(d.EXPECTED_BYTES+1, 100)

    def test_after_digest_before_next_fetch(self):
        events = []
        source = dict(zip(d.old.FIELDS, ['0']*len(d.old.FIELDS)))
        source.update(event='retire', insn='00000013')

        class Reader:
            fieldnames = d.old.FIELDS
            def __iter__(self):
                for index in range(2):
                    events.append(('fetch', index))
                    yield dict(source, cycle=str(index), order=str(index))

        observer = d.fast.OwnerObserver(d.old.protocol)
        class Check:
            def boundary(self):
                self_outer.assertEqual(observer.before.digest(), observer.after.digest())
                events.append(('boundary', observer.count['unmodified_delivered_rows']))
        self_outer = self
        for row in observer.rows(d.BoundaryReader(Reader(), Check())):
            events.append(('consume', int(row['order'])))
        self.assertEqual(events, [('boundary', 0), ('fetch', 0), ('consume', 0),
            ('boundary', 1), ('fetch', 1), ('consume', 1), ('boundary', 2)])

    def test_bad_tail_still_rejects(self):
        state = d.old.StreamState()
        raw = (','.join(d.old.FIELDS)+'\n').encode()+b'1,retire'
        with self.assertRaises(ValueError):
            list(state.lines(io.BytesIO(raw)))
        self.assertEqual(state.bytes, len(raw))


if __name__ == '__main__':
    unittest.main(verbosity=2)
