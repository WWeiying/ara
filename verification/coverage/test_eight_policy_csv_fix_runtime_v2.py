"""Exact attribute/duplicate/seal regressions, including frozen729 native exports."""
from pathlib import Path
import unittest
from unittest.mock import patch

import eight_policy_csv_fix_runtime_v2 as m

HEADER = b'CHECKSUM: "10 20"\nINSTANCE: dut.lane[0].queue\n'
A = b'ANNOTATION: "proof A"\nBranch 1 "30" "cmd.conv" (7) "cmd.conv EW8 ,1"\n'
B = b'ANNOTATION: "proof B"\nBranch 2 "31" "ready" (3) "ready 1,0"\n'
C = (b'CHECKSUM: "10 21"\nINSTANCE: dut.lane[0].lzc\n'
     b'ANNOTATION: "vcs_gen_start:level=2:vcs_gen_end:proof"\n'
     b'Condition 20 "32" "select 1 -1" (2 "1")\n')


class Identity(unittest.TestCase):
    def test_escaped_debug_quotes_are_preserved_exactly(self):
        raw=HEADER+A.replace(b'cmd.conv',b'$test$plusargs(\\"DEBUG\\")')
        self.assertEqual(m.compare(raw,raw)['records'],1)
        with self.assertRaises(ValueError):
            m.compare(raw,raw.replace(b'DEBUG',b'OTHER',1))

    def test_record_and_block_order_only(self):
        result = m.compare(HEADER+A+B+C, C+HEADER+B+A)
        self.assertEqual(result['records'], 3)
        self.assertEqual(result['kinds'], {'Branch':2, 'Condition':1})
        self.assertFalse(result['exact_bytes_equal'])
        self.assertFalse(result['record_order_equal'])
        self.assertTrue(result['exact_attributes_equal'])

    def test_every_identity_and_attribute_mutation_rejected(self):
        raw = HEADER+A+B+C
        for before, after in ((b'10 20',b'11 20'),(b'10 20',b'10 22'),
                              (b'dut.lane[0].queue',b'dut.lane[1].queue'),
                              (b'Branch 1 ',b'Branch 3 '),(b'"30"',b'"99"'),
                              (b'"cmd.conv"',b'"cmd.other"'),(b'(7)',b'(8)'),
                              (b'EW8 ,1',b'EW8 ,0'),(b'proof A',b'proof X'),
                              (b'Condition 20',b'Condition 21'),
                              (b'select 1 -1',b'select 2 -1'),
                              (b'(2 "1")',b'(2 "0")')):
            with self.subTest(before=before):
                with self.assertRaises(ValueError):m.compare(raw,raw.replace(before,after,1))

    def test_duplicate_missing_and_equal_count_substitution_rejected(self):
        for raw in (HEADER+A+A,HEADER+A+HEADER+A,HEADER+A,
                    HEADER+A+B.replace(b'(3)',b'(4)')):
            with self.assertRaises(ValueError):m.compare(HEADER+A+B,raw)
        # Repeating both sides identically must not bypass duplicate rejection.
        with self.assertRaises(ValueError):m.compare(HEADER+A+A,HEADER+A+A)

    def test_unknown_attributes_comments_wholeinstance_and_dangling_annotation(self):
        for raw in (HEADER,HEADER+A+b'ANNOTATION: "dangling"\n',
                    HEADER+A+b'// ignored?\n',HEADER+A+b'PROPERTY: "x"\n',
                    HEADER+b'ANNOTATION: "extra"\n'+A,
                    HEADER+A.replace(b'ANNOTATION: "proof A"\n',b'')):
            with self.assertRaises(ValueError):m.records(raw)


class Actual729(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result=m.diagnostic(m.DEFAULT,m.DEFAULT_SEAL)

    def test_actual_full_record_attributes_and_native_binders(self):
        result=self.result
        self.assertTrue(result['comparison']['exact_attributes_equal'])
        self.assertFalse(result['comparison']['exact_bytes_equal'])
        self.assertEqual(result['comparison']['records'],5892)
        self.assertTrue(result['native_binding_checks_passed'])
        self.assertEqual(result['original_status']['status'],'FAILED')
        self.assertFalse(result['full_protected_and_report_verification'])
        self.assertFalse(result['application_approval'])

    def test_runtime_seal_is_not_csv_plan_seal_and_matches_pin(self):
        self.assertEqual(self.result['runtime_plan_sha256'],
                         'ce61cc90b42f1bf25dca7f4ae9058583fcb9cb55e805a7c4cda160daa64bb794')
        self.assertEqual(self.result['csv_plan_sha256'],m.DEFAULT_SEAL)
        with self.assertRaises(ValueError):
            m.prior.frozen.load_sealed(m.DEFAULT/'runtime-plan.json',m.DEFAULT_SEAL)
        for seal in ('0'*64,self.result['runtime_plan_sha256']):
            with self.assertRaises(ValueError):m.sealed_runtime(m.DEFAULT,seal)

    def test_missing_or_wrong_runtime_pin_rejected(self):
        load=m.prior.frozen.load_sealed
        for mode in ('missing','drift'):
            def changed(path,seal):
                value=load(path,seal)
                if Path(path).name==m.prior.PLAN:
                    value=dict(value,pins=dict(value['pins']))
                    key=str(m.DEFAULT/'runtime-plan.json')
                    if mode=='missing':value['pins'].pop(key)
                    else:value['pins'][key]='0'*64
                return value
            with patch.object(m.prior.frozen,'load_sealed',changed):
                with self.assertRaises(ValueError):m.sealed_runtime(m.DEFAULT,m.DEFAULT_SEAL)

    def test_gui_error_never_offline_qualified_or_ignored(self):
        self.assertTrue(any('Combined EL actual reload bytes differ' in e
                            for e in self.result['gui_failure_markers']))
        with patch.object(m,'verifier') as full:
            with self.assertRaisesRegex(ValueError,'Original GUI session failed'):
                m.verify(m.DEFAULT,m.DEFAULT_SEAL)
            full.assert_not_called()

    def test_frozen_verifier_changes_only_exact_native_equality(self):
        verifier=m.verifier(m.DEFAULT,m.DEFAULT_SEAL)
        self.assertIn('semantic_equal',verifier.__code__.co_names)
        self.assertIn('seven_verifier',verifier.__code__.co_names)
        self.assertIn('read_lzc_states',verifier.__code__.co_names)
        bind=next(code for code in verifier.__code__.co_consts
                  if hasattr(code,'co_name') and code.co_name=='bind')
        self.assertIn('split_bind',bind.co_names)
        self.assertIn('Eight session failed',verifier.__code__.co_consts)
        runtime_path=m.DEFAULT/'runtime-plan.json'
        loaded=verifier.__globals__['frozen'].load_sealed(runtime_path,m.DEFAULT_SEAL)
        self.assertEqual(loaded['population'],729)
        with self.assertRaises(ValueError):
            verifier.__globals__['frozen'].load_sealed(runtime_path,'0'*64)


if __name__ == '__main__':
    unittest.main()
