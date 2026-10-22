import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import report_population783_fpnew90 as m


def el(scope,name,left,checks='1 2'):
    return 'CHECKSUM: "%s"\nINSTANCE: %s\nANNOTATION: "fixture"\nToggle %s "logic %s[%d:0]"\n'%(checks,scope,name,name,left)


class Batch(unittest.TestCase):
    def addition(self):return el('a.round','id_i',33)+el('a.block','fmt_outputs[3].tag.operand_a',4225)
    def test_preserve_prior_and_exact_new_union(self):
        base=el('a.other','data',7);result=m.union_gate(base,self.addition())
        old=m.prior.frozen.physical(m.stable.semantic(base));new=m.prior.frozen.physical(m.stable.semantic(result))
        self.assertTrue(all(new[k]==v for k,v in old.items()))
        self.assertEqual(sum(bin(v).count('1') for v in new.values())-sum(bin(v).count('1') for v in old.values()),8520)
    def test_overlap_existing_field_rejected(self):
        with self.assertRaises(ValueError):m.union_gate(el('a.round','id_i',0),self.addition())
    def test_checksum_fingerprint_collision_rejected(self):
        with self.assertRaises(ValueError):m.union_gate(el('a.round','other',0,'9 9'),self.addition())
    def test_struct_owner_collision_rejected(self):
        with self.assertRaises(ValueError):m.union_gate(el('a.block','fmt_outputs[3].tag',0),self.addition())
    def test_ancestor_FSM_preserved_not_whole_scope(self):
        base='CHECKSUM: "1 2"\nINSTANCE: a\nFsm state_q "2"\nTransition A->B "0->1"\n'
        result=m.union_gate(base,self.addition())
        self.assertEqual(m.stable.semantic(base)[0],m.stable.semantic(result)[0])
    def test_whole_scope_ancestor_rejected(self):
        base='CHECKSUM: "1 2"\nINSTANCE: a\nANNOTATION: "fixture"\n'
        with self.assertRaises(ValueError):m.union_gate(base,self.addition())
    def test_strict_FSM_header_machine_and_fullmatch(self):
        header=('a','1 2','','Fsm state_q "2"')
        self.assertTrue(m.exact_fsm_header(header))
        for line in ('Fsm state_q "3"','Fsm state_q "2" junk','Fsm state_q','State A "1"'):
            self.assertFalse(m.exact_fsm_header(('a','1 2','',line)))
        headers={header}
        for line in ('State A "1"','Transition A->B "0->1"'):
            self.assertTrue(m.exact_fsm_record(('a','1 2',header[3],line),headers))
        for line in ('State A "1" junk','State malformed','Fsm unknown "2"','Branch 2 "1"','Line 1'):
            self.assertFalse(m.exact_fsm_record(('a','1 2',header[3],line),headers))
        self.assertFalse(m.exact_fsm_record(('a','1 2','Fsm foreign "2"','State A "1"'),headers))
    def test_wrong_direction_capacity_rejected(self):
        with self.assertRaises(ValueError):m.union_gate('',self.addition().replace('Toggle ','Toggle 0to1 '))
    def test_receipt_missing_prepare_no_output(self):
        with tempfile.TemporaryDirectory() as d,patch.object(m,'LOCAL',Path(d)/'absent'):
            out=Path(d)/'out'
            with self.assertRaises(ValueError):m.context('0'*64)[0](out,'ara-test.service')
            self.assertFalse(out.exists())
    def test_receipt_before_only_or_bad_terminal_rejected(self):
        q=dict(status='FPNEW_TIED90_LOCAL_NATIVE_QUALIFIED_NOT_APPLIED',config_seal=m.LOCAL_CONFIG_SHA,
               fields=90,directions=8520,terminal_returncode=0,stages=list(m.native.STAGES),population_application=False)
        m.receipt_gate(q)
        for key,value in [('status','BEFORE_PASS'),('terminal_returncode',1),('directions',8518),
                          ('population_application',True),('stages',['before']),('config_seal','0'*64)]:
            bad=dict(q);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.receipt_gate(bad)
    def test_private_reuse_exact_five_stage72_root_engine(self):
        frozen=(m.prior.SCHEMA,m.prior.BASE_SHA,m.prior.UNION_SHA)
        prepare,check,verify,run=m.context('a'*64)
        self.assertIs(check.__code__,m.prior.frozen.check.__code__)
        self.assertIs(verify.__code__,m.prior.frozen.verify.__code__)
        self.assertIs(run.__code__,m.prior.frozen.run.__code__)
        self.assertEqual(check.__globals__['metadata']()['additional_direction_count'],18220)
        self.assertEqual(frozen,(m.prior.SCHEMA,m.prior.BASE_SHA,m.prior.UNION_SHA))

    def test_actual_existing9700_and_native90_canonical_union(self):
        base=(m.life.OUT/'current-population781-plus9700-prepared-agent-20261008-01/combined.el').read_text()
        c=m.life.read_bound(m.LOCAL/'config.json',m.LOCAL_CONFIG_SHA)
        addition=(m.LOCAL/'first.el').read_text()
        self.assertEqual(len(m.native.el_gate(addition,c)),90)
        result=m.union_gate(base,addition)
        self.assertEqual(m.stable.semantic(base)[0],m.stable.semantic(result)[0])

    def test_source_zero_target_activation_rejected(self):
        with self.assertRaises(ValueError):
            m.prior.prior.zero_row(dict(width=4,checksum='1',bits='8'),4,'1',[0])


if __name__=='__main__':unittest.main()
