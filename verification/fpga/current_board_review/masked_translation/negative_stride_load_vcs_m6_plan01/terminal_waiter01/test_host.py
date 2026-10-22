"""Small terminal admission/data tests; no service queries or DUT artifact reads."""
import copy
import csv
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
import waiter as w
import test_csv as fixture


class Host(unittest.TestCase):
    def test_terminal_actual_numeric_gate(self):
        row = dict(name=w.c.NAME, status='PASS', returncode=0, elapsed_s=123.0, reason='')
        terminal = dict(status='PASS_M6_NEGATIVE_STRIDE_SOURCE_SINGLE_NOT_LINUX', aborted=False,
                        pins_unchanged=True, retries=0, plan_sha256=w.PLAN_SHA, results=[row])
        meta = dict(status='COMPLETE', status_counts={'PASS': 1}, tests=[w.c.NAME], jobs=1, timeout_s=3600)
        monitor = dict(returncode=0, elapsed_s=123.0, timed_out=False, failure_seen=False,
                       abort_set=False, architectural_acceptance=False)
        child = dict(row, architectural_acceptance=False)
        args = [terminal, meta, [row], monitor, child]
        self.assertEqual(w.terminal_gate(*args), row)
        for index, key, value in [(0, 'status', 'NOT_PASS'), (0, 'aborted', True),
                                  (1, 'status', 'INTERRUPTED'), (3, 'returncode', None),
                                  (3, 'returncode', False), (3, 'returncode', 255),
                                  (3, 'abort_set', True), (4, 'returncode', None)]:
            changed = copy.deepcopy(args)
            changed[index][key] = value
            with self.subTest(index=index, key=key, value=value), self.assertRaises(ValueError):
                w.terminal_gate(*changed)

    def test_numerical_full_synthetic_and_two_corruptions(self):
        spec = w.read(w.RUN / 'plan.json')['spec']
        rows, labels = fixture.synthetic(spec)
        check = w.Numerical(spec)
        for row in rows:
            check.row(row)
        result = check.finish()
        self.assertEqual(result['checks'], 17274)
        self.assertEqual(result['memory_halfword_reads'], 16384)
        for label in ('out3', 'out65'):
            check = w.Numerical(spec)
            with self.subTest(label=label), self.assertRaises(ValueError):
                for i, row in enumerate(rows):
                    if i == labels[label]:
                        row = dict(row, rd_wdata='0000000000000000')
                    check.row(row)
                check.finish()

    def test_combined_generic_single_stream(self):
        class Counter:
            def __init__(self): self.rows = 0
            def row(self, _): self.rows += 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.csv'
            with path.open('w') as stream:
                writer = csv.writer(stream)
                writer.writerow(w.scalar_decoder.FIELDS)
                writer.writerow([1, 'retire', 0, 0, 0, '80000000', '13', 0, '0', '0', '0', '0', '0', 0])
            counter = Counter()
            wrapped = w.CombinedPath(path, counter)
            result = w.validate_trace(wrapped)
            self.assertEqual(result['retire_count'], 1)
            self.assertEqual(counter.rows, 1)
            self.assertEqual(wrapped.digest.hexdigest(), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_terminal_event_rename_and_already_present(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'complete.json'
            def publish():
                temporary = path.with_suffix('.tmp')
                temporary.write_text('{}')
                temporary.rename(path)
            timer = threading.Timer(0.05, publish)
            timer.start()
            try:
                w.wait_terminal(path, 2)
                w.wait_terminal(path, 2)
            finally:
                timer.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
