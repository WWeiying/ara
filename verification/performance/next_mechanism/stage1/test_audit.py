import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from audit import checked_manifest, phases, pv_boundary


class AuditTest(unittest.TestCase):
    def setUp(self):
        self.m = dict(kind='fixed_history_replay_not_free_generation', worker_count=1,
            kv='f16/f16', single_token_evaluations=1, prompt_tokens=135,
            prefill_compute_ns=100, decode_compute_ns=20, inference_window_ns=130,
            model_load_ns=400, context_init_ns=10,
            phases=[dict(phase='prefill', eval_tokens=135, compute_ns=100),
                    dict(phase='decode', step=0, compute_ns=20)])
        self.log = 'STAGE1_PROGRESS prefill tokens=135 ns=100\nSTAGE1_PROGRESS decode=1/1 ns=20\nSTAGE1_MODEL_COMPLETED\n'

    def test_phases_are_not_operator_share(self):
        result = phases(self.m, self.log)
        self.assertEqual(result['compute_seconds'], 120 / 1e9)
        self.assertEqual(result['non_compute_window_seconds'], 10 / 1e9)
        self.assertFalse(result['operator_times_measured'])

    def test_bad_totals_or_raw_log_rejected(self):
        for key in ('prefill_compute_ns', 'decode_compute_ns', 'single_token_evaluations'):
            m = copy.deepcopy(self.m)
            m[key] += 1
            with self.assertRaises(ValueError):
                phases(m, self.log)
        with self.assertRaises(ValueError):
            phases(self.m, self.log + 'STAGE1_MODEL_COMPLETED\n')
        with self.assertRaises(ValueError):
            phases(self.m, self.log.replace('ns=20', 'ns=21'))

    def test_boundary_attempts_not_pass(self):
        log = 'PV_BOUNDARY_DONE cases=21 successes=21 rejected=12 compat=1 errors=2\nCore Test *** FAILED ***'
        result = pv_boundary(log, {'state': 'FAIL'})
        self.assertEqual(result['firmware_errors'], 2)
        self.assertFalse(result['deployment_approved'])
        with self.assertRaises(ValueError):
            pv_boundary(log, {'state': 'PASS'})

    def test_manifest_changes_duplicates_and_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'data'
            path.write_bytes(b'evidence')
            row = dict(path='data', sha256=hashlib.sha256(b'evidence').hexdigest())
            self.assertEqual(len(checked_manifest(root, [row])), 1)
            with self.assertRaises(ValueError):
                checked_manifest(root, [row, row])
            with self.assertRaises(ValueError):
                checked_manifest(root, [dict(path=str(Path(__file__).resolve()), sha256=row['sha256'])])
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                checked_manifest(root, [row])


if __name__ == '__main__':
    unittest.main()
