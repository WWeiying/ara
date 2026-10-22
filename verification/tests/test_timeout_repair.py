import importlib
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_timeout_repair as repair


class RetryTests(unittest.TestCase):
    def test_reuses_exact_archived_elf(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            elf = root / 'input.elf'
            elf.write_bytes(b'archived elf')
            case = {'name': 'old', 'test': 'rvv:old', 'kind': 'directed',
                    'frozen_elf': str(elf), 'elf_sha256': repair.batch.sha256(elf),
                    'directed_test': {'name': 'rvv:old', 'kind': 'rvv',
                        'binary': str(elf), 'build_target': 'old', 'testcase': 'old',
                        'timeout_s': 300}}
            repair.batch.save(root / 'outcomes/old.json', {'status': 'TIMEOUT'})
            with patch.object(repair, 'selection_data', {'retries': {'rvv:retry': 'rvv:old'}}), \
                 patch.object(repair, 'previous_root', root):
                rows = repair.select_tests(SimpleNamespace(tests={}), {'cases': [case]}, ['rvv:retry'])
                self.assertEqual(rows[0][1].binary, elf)
                self.assertEqual(rows[0][2], case['elf_sha256'])
                self.assertEqual(rows[0][1].testcase, 'repair_old')
                repair.batch.save(root / 'outcomes/old.json', {'status': 'PASS'})
                with self.assertRaises(ValueError):
                    repair.select_tests(SimpleNamespace(tests={}), {'cases': [case]}, ['rvv:retry'])

    def test_matrix_shards_have_complete_disjoint_union(self):
        sets = [{i for i in range(464) if i % 32 == s} for s in range(32)]
        self.assertEqual(set.union(*sets), set(range(464)))
        self.assertEqual(sum(map(len, sets)), 464)
        self.assertEqual({len(s) for s in sets}, {14, 15})

    def test_nonpass_stops_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repair.batch.save(root / 'outcomes/case.json', {'status': 'TIMEOUT'})
            with patch.object(repair, 'normal_worker', return_value=0):
                self.assertEqual(repair.worker(root, 'case'), 1)
                self.assertTrue((root / 'repair_stop_case.json').exists())


if __name__ == '__main__':
    unittest.main()
