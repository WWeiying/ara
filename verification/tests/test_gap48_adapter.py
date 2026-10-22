import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import run_gap48_checked_batch as batch


class FakeProof:
    def __init__(self, records):
        self.records = records
        self.checked = None

    def hashes(self, entries):
        self.checked = dict(entries)

    def read(self, path):
        return copy.deepcopy(self.records[str(path)])


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.base = Path('/reviewed/baseline')
        self.case = {'name': 'rvv:csr_gap44_absent', 'timeout_s': 300,
                     'binary': '/reviewed/csr.elf'}
        self.spec = {'status': 'COMPOSED_REQUIRES_CHECKED_ADMISSION',
                     'baseline': str(self.base), 'baseline_bits': str(self.base / 'combined-bits.json'),
                     'cases': [self.case],
                     'composition': {'maximum_concurrent_workers': 8, 'case_limit_seconds': 600,
                                     'baseline_passed': 641, 'drafts': ['/draft.json'],
                                     'files': {str(batch.COMPOSER): 'composer', '/draft.json': 'draft',
                                               str(self.base / 'combined-bits.json'): 'bits'}}}
        self.spec['composition']['files'].update({
            str(self.base / name): name for name in
            ('checkpoint.json', 'collection.json', 'all-passed-outcomes.json')})
        self.spec['composition']['files'][self.case['binary']] = 'elf'
        self.records = {'/draft.json': {'cases': [self.case]},
                        str(self.base / 'checkpoint.json'): {'coverage_status': 'COMPLETE', 'aggregate_passed': 641},
                        str(self.base / 'collection.json'): {'status': 'PASS', 'passed': 641}}

    def check(self, spec=None):
        with patch.object(Path, 'resolve', lambda self, **kwargs: self):
            return batch.check_composition(spec or self.spec, FakeProof(self.records))

    def test_exact_composition(self):
        self.assertEqual(self.check(), ['run_gap44_csr_checked_extension'])

    def test_case_edits_rejected(self):
        changed = copy.deepcopy(self.spec)
        changed['cases'][0]['timeout_s'] = 301
        with self.assertRaises(ValueError):
            self.check(changed)

    def test_unbound_draft_rejected(self):
        del self.spec['composition']['files']['/draft.json']
        with self.assertRaises(ValueError):
            self.check()

    def test_incomplete_baseline_rejected(self):
        self.records[str(self.base / 'checkpoint.json')]['coverage_status'] = 'PENDING'
        with self.assertRaises(ValueError):
            self.check()

    def test_baseline_count_mismatch_rejected(self):
        self.spec['composition']['baseline_passed'] = 640
        with self.assertRaises(ValueError):
            self.check()

    def test_missing_required_pin_rejected(self):
        paths = [str(self.base / name) for name in
                 ('checkpoint.json', 'collection.json', 'all-passed-outcomes.json',
                  'combined-bits.json')]
        paths.append(self.case['binary'])
        for path in paths:
            spec = copy.deepcopy(self.spec)
            del spec['composition']['files'][path]
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.check(spec)

    def test_unknown_adapter_rejected(self):
        with self.assertRaises(ValueError):
            batch.adapter_names([{'name': 'app:arbitrary'}])

    def test_same_module_installed_once(self):
        names = batch.adapter_names([{'name': 'rvv:vgap47_sv39_indexed_pmp0'},
                                     {'name': 'rvv:vgap47_sv39_indexed_pmp0'}])
        self.assertEqual(names, ['run_gap47_rvv_checked_extension_v2'])

    def test_unreviewed_gap47_case_rejected(self):
        for name in ('rvv:vgap47_sv39_indexed', 'rvv:vgap47_arbitrary'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                batch.adapter_names([{'name': name}])

    def runtime_plan(self):
        return {'source_selection': {'selection': '/selection.json'},
                'files': {'/selection.json': 'selection', '/reviewed/csr.elf': 'elf'},
                'cases': [{'source_name': self.case['name'], 'timeout_s': 300,
                           'elf_sha256': 'elf'}]}

    def test_runtime_selection_verified_before_read(self):
        events = []
        with patch.object(batch.checked.full, 'check', side_effect=lambda _: events.append('check')), \
             patch.object(batch.checked.full, 'read', side_effect=lambda _: events.append('read') or self.spec):
            self.assertEqual(batch.runtime_selection(self.runtime_plan()), self.spec)
        self.assertEqual(events, ['check', 'read'])

    def test_runtime_changed_selection_not_read(self):
        with patch.object(batch.checked.full, 'check', side_effect=ValueError('hash mismatch')), \
             patch.object(batch.checked.full, 'read') as read:
            with self.assertRaises(ValueError):
                batch.runtime_selection(self.runtime_plan())
            read.assert_not_called()

    def test_runtime_unbound_selection_rejected(self):
        plan = self.runtime_plan()
        del plan['files']['/selection.json']
        with patch.object(batch.checked.full, 'read') as read:
            with self.assertRaises(ValueError):
                batch.runtime_selection(plan)
            read.assert_not_called()

    def test_runtime_different_case_identity_rejected(self):
        for field, value in [('source_name', 'app:wrong'), ('timeout_s', 301),
                             ('elf_sha256', 'other')]:
            plan = self.runtime_plan()
            plan['cases'][0][field] = value
            with self.subTest(field=field), patch.object(batch.checked.full, 'check'), \
                 patch.object(batch.checked.full, 'read', return_value=self.spec), \
                 self.assertRaises(ValueError):
                batch.runtime_selection(plan)


if __name__ == '__main__':
    unittest.main()
