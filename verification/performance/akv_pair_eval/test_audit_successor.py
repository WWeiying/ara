import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('postrun_audit', Path(__file__).with_name('audit_successor.py'))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class TestAudit(unittest.TestCase):
    def test_only_exact_reviewed_checker_rejection_is_admissible(self):
        for kind in audit.FAILURES:
            report = dict(state='FAIL', error=audit.FAILURES[kind], hardware_changed=False, whole_model=False)
            audit.original_failure(report, kind)
            for field, value in [('state', 'TIMEOUT'), ('error', 'RTL numerical mismatch'),
                                 ('hardware_changed', True), ('whole_model', True)]:
                bad = copy.deepcopy(report)
                bad[field] = value
                with self.assertRaises(ValueError):
                    audit.original_failure(bad, kind)

    def test_unknown_scope_does_not_load_a_successor(self):
        with self.assertRaises(ValueError):
            audit.load_checker('qwen3_abba')


if __name__ == '__main__':
    unittest.main()
