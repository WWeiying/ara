"""Keep all sixteen original gate tests; add declaration-order regression tests."""
import importlib
import inspect
import unittest

import balanced_seed_gate_v2 as fix


class DeclarationOrderSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.namespace, cls.report = fix.build()
        cls.parent = importlib.import_module('balanced_seed_gate')
        cls.original = (fix.FIRST / 'qbs_balanced_seed_tb.sv').read_text()
        cls.block = cls.parent.OBSERVATIONS
        cls.fixed = fix.relocate_observers(cls.original, cls.block)

    def test_original_failure_remains_exact_and_compile_only(self):
        fix.admit_failure(fix.read(fix.FIRST / 'worker/result.json'),
                          fix.read(fix.FIRST / 'worker/commands.json'),
                          (fix.FIRST / 'worker/compile.log').read_text())
        self.assertEqual(fix.digest(fix.FIRST / 'worker/result.json'), fix.FIRST_FAILED_SHA)
        self.assertFalse(self.report['original_failure_relabelled'])

    def test_original_late_declaration_is_reproduced_and_rejected(self):
        with self.assertRaisesRegex(ValueError, 'declaration must precede'):
            fix.validate_declaration_order(self.original)
        self.assertGreater(self.original.index('  int bsg_case='), self.original.index('    bsg_k++;'))
        fix.validate_declaration_order(self.fixed)

    def test_identical_block_only_moved_and_inverse_restores_original(self):
        self.assertEqual(self.fixed.count(self.block), 1)
        self.assertEqual(self.fixed.replace(self.block, '', 1), self.original.replace(self.block, '', 1))
        location = "\n  qbs_compute_engine_balanced #(.SeedRestoreEnable(1'b1),"
        inverse = self.fixed.replace(self.block, '', 1).replace(location, self.block + location, 1)
        self.assertEqual(inverse, self.original)
        self.assertEqual(fix.sha(self.fixed), self.report['generated_tb_sha256'])

    def test_generated_successor_bench_matches_the_scoped_movement(self):
        text, _ = self.namespace['bench_source'](self.parent.TB.read_text(), self.parent.CONTINUATION.read_text())
        self.assertEqual(text, self.fixed)
        self.assertLess(text.index('logic [31:0] prefix_counters [9];'), text.index('  int bsg_case='))
        self.assertLess(text.index('  task automatic bsg_checkpoint;'), text.index('  task automatic continue_after_prefix;'))

    def test_original_module_globals_and_sources_not_mutated(self):
        self.assertEqual(self.parent.OUT, fix.FIRST)
        self.assertEqual(self.parent.OWNED, ('balanced_seed_gate.py', 'test_balanced_seed_gate.py'))
        fix.verify_original_helpers()
        self.assertIs(self.namespace['check_log'], self.parent.check_log)
        self.assertIs(self.namespace['check_pair'], self.parent.check_pair)
        self.assertIs(self.namespace['vectors'], self.parent.vectors)
        self.assertEqual(inspect.getsource(self.parent.execute), self.namespace['SPECIALIZED_FUNCTIONS']['execute'])

    def test_rejects_any_other_failure_or_additional_simulation(self):
        record = fix.read(fix.FIRST / 'worker/result.json')
        commands = fix.read(fix.FIRST / 'worker/commands.json')
        log = (fix.FIRST / 'worker/compile.log').read_text()
        for bad in ({**record, 'state': 'PASS'}, {**record, 'target_executed': True},
                    {**record, 'rtl_compiled': True}, {**record, 'post_pins_match': False}):
            with self.assertRaises(ValueError):
                fix.admit_failure(bad, commands, log)
        with self.assertRaises(ValueError):
            fix.admit_failure(record, commands + [dict(label='split0', returncode=0)], log)
        for bad in (log.replace("Identifier 'bsg_k'", "Identifier 'other'"),
                    log + '\nError-[OTHER] unrelated\n'):
            with self.assertRaises(ValueError):
                fix.admit_failure(record, commands, bad)

    def test_rejects_fixture_or_function_drift(self):
        for bad in (self.original + '\n', self.original * 2, self.fixed):
            with self.assertRaises(ValueError):
                fix.relocate_observers(bad, self.block)
        with self.assertRaises(ValueError):
            fix.patch_function('def prepare(): pass\n', 'prepare', [])

    def test_new_namespace_is_fresh_and_execution_still_requires_review(self):
        self.assertEqual(self.namespace['OUT'], fix.OUT)
        self.assertEqual(self.namespace['OWNED'], fix.OWNED)
        self.assertEqual(self.namespace['PREPARED'], fix.PREPARED)
        with self.assertRaises(ValueError):
            self.namespace['execute'](fix.OUT, None)
        self.assertIn("__import__('test_balanced_seed_gate_v2')", self.namespace['SPECIALIZED_FUNCTIONS']['prepare'])

    def test_all_numerical_and_seed_guards_remain_literal(self):
        for token in ('BSG_ZERO_M4_CHECKPOINT', 'BSG_FIRST_BLOCK_OR_OWNER', 'BSG_SEED_NOT_WRITTEN',
                      'BSG_RESTORED_ADDEND_CHANGED', 'BSG_UNKNOWN_CONTROL', 'BSG_MISSING_ACCUMULATOR_WORK',
                      'command counter/flags mismatch', 'QBS_SEED_CANCEL_PASS reset=',
                      'if(ordinal==0) seed_fault_or_reset(0)', 'if(ordinal==1) seed_fault_or_reset(1)',
                      'check_pipeline_fault(stage)', 'BSG_TRAILING_VECTOR'):
            self.assertEqual(self.original.count(token), self.fixed.count(token))
        raw = self.parent.RAW36.read_text()
        self.assertEqual(self.namespace['vectors'](raw)[0], (fix.FIRST / 'vectors-balanced.txt').read_text())


def load_tests(loader, tests, pattern):
    fix.verify_original_helpers()
    original = importlib.import_module('test_balanced_seed_gate')
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(original))
    suite.addTests(loader.loadTestsFromTestCase(DeclarationOrderSuccessorTests))
    return suite


if __name__ == '__main__':
    unittest.main(verbosity=2)
