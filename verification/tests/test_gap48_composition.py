import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compose_gap48_selection as composer


class CompositionTests(unittest.TestCase):
    def setUp(self):
        self.row = {'name': 'old', 'elf_sha256': 'old-sha'}
        self.case = {'name': 'rvv:first', 'binary': '/new.elf', 'timeout_s': 300,
                     'rationale': 'Specific missing branch', 'targets': ['product'],
                     'source_audit': 'reviewed', 'sources': ['/source.c'],
                     'evidence': ['/preflight.json'], 'precheck': {'format': 'rvv-spike-v1'}}

    def merge(self, cases, digest='new-sha'):
        return composer.merge_cases([(Path('/draft.json'), {'cases': cases})],
                                    [self.row], lambda _: digest)

    def test_preserves_exact_sealed_case(self):
        original = copy.deepcopy(self.case)
        result = self.merge([self.case])
        self.assertEqual(self.case, original)
        self.assertEqual(result[0], original)
        self.assertIsNot(result[0], self.case)

    def test_duplicate_labels_across_kinds_rejected(self):
        other = dict(self.case, name='app:first')
        with self.assertRaises(ValueError):
            self.merge([self.case, other])

    def test_existing_pass_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([dict(self.case, name='rvv:old')])

    def test_existing_elf_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([self.case], 'old-sha')

    def test_duplicate_elf_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([self.case, dict(self.case, name='app:second')])

    def test_budget_cannot_be_implicitly_extended(self):
        for value in (0, -1, 601, True, 300.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.merge([dict(self.case, timeout_s=value)])

    def test_no_precheck_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([dict(self.case, precheck=None)])

    def test_no_target_rejected(self):
        with self.assertRaises(ValueError):
            self.merge([dict(self.case, targets=[])])


if __name__ == '__main__':
    unittest.main()
