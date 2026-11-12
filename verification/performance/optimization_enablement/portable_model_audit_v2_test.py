"""Negative controls for the captured whole-call ABI audit, not model evidence."""
import importlib.util
import sys
import unittest

from portable_model_audit_v2 import RUN, checked_successor, load_original

sys.path.insert(0, str(RUN / 'inputs'))
spec = importlib.util.spec_from_file_location('preserved_refact_tests', RUN / 'inputs/portable_model_test.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def fixture():
    rows = old.fixture()
    for i, row in enumerate(rows):
        if row.startswith('PORTABLE_DECODE '):
            row = row.replace('before_fcsr=1', 'before_fcsr=23').replace(' fcsr=1', ' fcsr=23')
            row = row.replace('before_vcsr=5', 'before_vcsr=0' if 'step=0 ' in row else 'before_vcsr=2')
            rows[i] = row.replace(' vcsr=5', ' vcsr=2')
    return rows


class Audit(unittest.TestCase):
    def checked(self, rows):
        check, transitions = checked_successor()
        return check(rows, old.SYMBOLS, old.MODEL), transitions

    def reject(self, old_text, new_text, occurrence=0):
        rows = fixture()
        indices = [i for i, row in enumerate(rows) if row == old_text]
        rows[indices[occurrence]] = new_text
        with self.assertRaises(ValueError):
            self.checked(rows)

    def test_original_failure_reproduced(self):
        with self.assertRaisesRegex(ValueError, '^Decode/CSR contract$'):
            load_original().check(fixture(), old.SYMBOLS, old.MODEL)

    def test_preserved_fixture_still_passes(self):
        proof, transitions = self.checked(old.fixture())
        self.assertEqual(transitions, [])
        self.assertEqual(proof['portable_groups'], 8)

    def test_exact_two_transitions(self):
        proof, transitions = self.checked(fixture())
        self.assertEqual([row['arm'] for row in transitions], [0, 1])
        self.assertEqual(proof['csr'][0]['before_vcsr'], 0)
        self.assertEqual(proof['csr'][0]['vcsr'], 2)

    def test_prefill_other_transition_rejected(self):
        source = next(row for row in fixture() if row.startswith('PORTABLE_DECODE step=0'))
        for old_text, new_text in (('rows=3', 'rows=4'), ('before_vcsr=0', 'before_vcsr=1'),
                                  (' vcsr=2', ' vcsr=4'), ('before_fcsr=23', 'before_fcsr=22'),
                                  (' fcsr=23', ' fcsr=31'), ('rc=0', 'rc=1')):
            with self.subTest(old=old_text, new=new_text):
                self.reject(source, source.replace(old_text, new_text))

    def test_decode_csr_change_rejected(self):
        source = next(row for row in fixture() if row.startswith('PORTABLE_DECODE step=1'))
        for old_text, new_text in ((' vcsr=2', ' vcsr=0'), ('before_vcsr=2', 'before_vcsr=0'),
                                  (' fcsr=23', ' fcsr=22'), ('vstart=0', 'vstart=1'),
                                  (' fcsr=23', ' fcsr=55')):
            with self.subTest(old=old_text, new=new_text):
                self.reject(source, source.replace(old_text, new_text))

    def test_two_arm_csr_mismatch_rejected(self):
        rows = fixture()
        indices = [i for i, row in enumerate(rows) if row.startswith('PORTABLE_DECODE step=1')]
        rows[indices[1]] = rows[indices[1]].replace('before_vcsr=2', 'before_vcsr=4').replace(' vcsr=2', ' vcsr=4')
        with self.assertRaisesRegex(ValueError, 'CSR/API mismatch'):
            self.checked(rows)

    def test_missing_csr_field_rejected(self):
        source = next(row for row in fixture() if row.startswith('PORTABLE_DECODE step=0'))
        self.reject(source, source.replace(' before_vcsr=0', ''))

    def test_original_numerical_guards_retained(self):
        for step in (0, 1):
            rows = fixture()
            index = rows.index('PORTABLE_LOGITS_BEGIN mode=1 step=' + str(step) + ' values=6') + 1
            rows[index] = rows[index].replace('40a00000', '3f800000')
            with self.assertRaises(ValueError):
                self.checked(rows)

    def test_native_guards_retained(self):
        for old_text, new_text in (
            ('Trace 0: 0xcc [0/2000/0/0] features', 'ignored'),
            ('Trace 0: 0xaa [0/1000/0/0] qbs', 'Trace 0: 0xaa [0/3000/0/0] unrelated'),
            ('GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0',
             'GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=1'),
            ('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1')):
            with self.subTest(old=old_text):
                self.reject(old_text, new_text)


def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromTestCase(old.Checker))
    return tests


if __name__ == '__main__':
    unittest.main(verbosity=2)
