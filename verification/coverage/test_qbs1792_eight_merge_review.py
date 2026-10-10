import copy
from pathlib import Path
import tempfile
import unittest

import prepare_qbs1792_eight_merge_review as p


class Merge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eight_raw=(p.EIGHT/'applied.el').read_bytes();cls.qbs_raw=(p.qualified.RUN/'first.el').read_bytes()
        cls.eight=p.records(cls.eight_raw);cls.qbs=p.records(cls.qbs_raw)

    def test_actual5892_plus1792_exact7684(self):
        self.assertEqual(p.union_gate(self.eight_raw+self.qbs_raw,self.eight,self.qbs),7684)
        self.assertEqual(p.union_gate(self.qbs_raw+self.eight_raw,self.eight,self.qbs),7684)

    def test_shared_scope_not_numeric_ID_only_conflict(self):
        result=p.mutual(self.eight,self.qbs)
        self.assertEqual(len(result['shared_scopes']),2)
        self.assertEqual(result['existing_QBS_condition_records'],0)
        self.assertEqual(result['native_point_identity_overlap_count'],0)
        self.assertFalse(result['final_application'])

    def test_missing_duplicate_extra_scope_wholecondition_rejected(self):
        for raw in (self.eight_raw,self.eight_raw+self.qbs_raw+self.qbs_raw,
                    self.eight_raw+self.qbs_raw.replace(b'bank0',b'bank2',1),
                    self.eight_raw+self.qbs_raw+b'INSTANCE: unexpected\n',
                    self.eight_raw+self.qbs_raw+b'Condition 8260\n'):
            with self.assertRaises(ValueError):p.union_gate(raw,self.eight,self.qbs)

    def test_all_numeric_signature_and_annotation_drift(self):
        for old,new in ((b'Condition 8260',b'Condition 999999'),(b'(3 "11")',b'(999 "11")'),
            (b'4245564008',b'4245564009'),(b'1651389237',b'1651389238'),(b'2947893042',b'2947893043'),
            (b' 1 -1',b' 2 -1'),(b' 1 -1',b' 1 0'),(b'(3 "11")',b'(3 "10")'),
            (b'activation_valid_i[0]',b'activation_valid_i[1]'),
            (b'vcs_gen_start:row=0,b=0:',b'vcs_gen_start:row=1,b=0:')):
            with self.subTest(field=old):
                self.assertIn(old,self.qbs_raw);changed=self.qbs_raw.replace(old,new,1)
                with self.assertRaises(ValueError):p.union_gate(self.eight_raw+changed,self.eight,self.qbs)

    def test_scope_module_mismatch_and_protected_condition_intrusion(self):
        row=list(self.qbs[0]);row[1]='wrong';qbs=[tuple(row)]+self.qbs[1:]
        with self.assertRaises(ValueError):p.mutual(self.eight,qbs)
        eight=copy.copy(self.eight);eight[0]=self.qbs[0]
        with self.assertRaises(ValueError):p.mutual(eight,self.qbs)
        row=list(self.qbs[0]);row[4]='999999';row[8]='10'
        eight=copy.copy(self.eight);eight[0]=tuple(row)
        with self.assertRaises(ValueError):p.mutual(eight,self.qbs)

    def test_pin_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'pin';path.write_bytes(b'old');pins={str(path):p.f.sha(path)}
            path.write_bytes(b'new')
            with self.assertRaises(ValueError):p.f.check_pins(pins)


if __name__=='__main__':unittest.main()
