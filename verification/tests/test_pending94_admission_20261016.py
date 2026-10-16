"""Negative controls for current-image specialized audit admission."""
import copy
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'verification'), str(ROOT / 'verification/coverage')]
from collect_pending94_20261016 import overlay, BUILD


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.original = dict(cases=[dict(index=i, status='PASS' if i < 704 else 'CHECKER_REQUIRED',
                                        evidence=['original.json']) for i in range(798)])

    def test_missing_cases_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Missing pending-case audits'):
            overlay(self.original, [])

    def test_wrong_original_population_rejected(self):
        self.original['cases'][704]['status'] = 'PASS'
        with self.assertRaisesRegex(ValueError, '704'):
            overlay(self.original, [])

    def test_duplicate_original_index_rejected(self):
        self.original['cases'][0]['index'] = 1
        with self.assertRaisesRegex(ValueError, '798'):
            overlay(self.original, [])

    def fake_read(self, value):
        if str(value).endswith('summary.json'):
            return dict(cases=[dict(index=704, status='PASS', report='/tmp/detail.json')])
        return dict(index=704, status='PASS', input_pins={})

    def test_clean_exit_without_semantic_evidence_rejected(self):
        with patch('collect_pending94_20261016.read', side_effect=self.fake_read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            with self.assertRaisesRegex(ValueError, 'authenticated evidence'):
                overlay(self.original, ['/tmp/summary.json'])

    def test_summary_detail_disagreement_rejected(self):
        def read(path):
            result = self.fake_read(path)
            if str(path).endswith('detail.json'):
                result['status'] = 'FAIL'
            return result
        with patch('collect_pending94_20261016.read', side_effect=read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            with self.assertRaisesRegex(ValueError, 'disagreement'):
                overlay(self.original, ['/tmp/summary.json'])

    def test_failure_preserved_and_original_unchanged(self):
        before = copy.deepcopy(self.original)
        summary = dict(cases=[dict(index=i, status='FAIL', report=f'/tmp/e{i}.json') for i in range(704, 798)])
        def read(path):
            if str(path).endswith('summary.json'):
                return summary
            i = int(Path(path).stem[1:])
            return dict(index=i, status='FAIL', reason='real oracle mismatch')
        with patch('collect_pending94_20261016.read', side_effect=read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            rows, _ = overlay(self.original, ['/tmp/summary.json'])
        self.assertEqual(sum(r['status'] == 'FAIL' for r in rows), 94)
        self.assertEqual(before, self.original)

    def passing_fixture(self):
        plan_path = ROOT / 'verification/out/full-regression-20261015-01/extensions/e0704/plan.json'
        work = str(plan_path.parent / 'work')
        image = str(BUILD / 'sim/simv')
        plan = dict(work=work, command=[image], elf_sha256='x')
        bound = {str(p): 'x' for p in (plan_path, plan_path.parent / 'simulation-exit.json',
                                      plan_path.parent / 'input.elf', Path(image),
                                      Path(work) / 'commit_trace.csv', Path(work) / 'vector_trace.csv')}
        detail = dict(index=704, status='PASS', input_pins=bound, old_PASS_reused=False)
        summary = dict(cases=[dict(index=i, status='PASS' if i == 704 else 'FAIL',
                                  report=f'/tmp/e{i}.json') for i in range(704, 798)])
        def read(path):
            path = str(path)
            if path == '/tmp/summary.json':
                return summary
            if path == '/tmp/e704.json':
                return detail
            if path == str(plan_path):
                return plan
            if path.endswith('simulation-exit.json'):
                return dict(executed=True, returncode=0, timed_out=False, cancelled=False,
                            command=[image], cwd=work)
            if path == str(BUILD / 'build-image.json'):
                return {image: 'x'}
            return dict(index=int(Path(path).stem[1:]), status='FAIL', reason='oracle mismatch')
        return read, detail, plan

    def test_current_authenticated_pass_can_be_admitted(self):
        read, _, _ = self.passing_fixture()
        with patch('collect_pending94_20261016.read', side_effect=read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            rows, _ = overlay(self.original, ['/tmp/summary.json'])
        self.assertEqual(rows[704]['status'], 'PASS')
        self.assertEqual(sum(r['status'] == 'PASS' for r in rows), 705)

    def test_different_elf_identity_rejected(self):
        read, _, plan = self.passing_fixture()
        plan['elf_sha256'] = 'wrong'
        with patch('collect_pending94_20261016.read', side_effect=read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            with self.assertRaisesRegex(ValueError, 'ELF identity'):
                overlay(self.original, ['/tmp/summary.json'])

    def test_historical_pass_reuse_rejected(self):
        read, detail, _ = self.passing_fixture()
        detail['old_PASS_reused'] = True
        with patch('collect_pending94_20261016.read', side_effect=read), \
             patch('collect_pending94_20261016.sha', return_value='x'):
            with self.assertRaisesRegex(ValueError, 'Historical PASS'):
                overlay(self.original, ['/tmp/summary.json'])


if __name__ == '__main__':
    unittest.main()
