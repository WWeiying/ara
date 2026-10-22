import json
from pathlib import Path
import tempfile
import unittest

import ptw_rvh0_outputs156_local_v2 as v


class AnnotationOrder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=v.FIRST.parent/'config.json'
        cls.c=v.old.life.read_bound(p,'e9441de43157a0afd9074205e9f9b88925a0c2cc9fd4b4ed5dff42a050471830')
        v.old.need(v.old.life.digest(v.FIRST)==v.FIRST_SHA,'Actual first EL')
        cls.actual=v.FIRST.read_text()
        cls.annotation='ANNOTATION: "'+v.old.ANNOTATION+'"'

    def test_actual_saved_first_el_exact_complete_membership(self):
        self.assertEqual(v.el_gate(self.actual,self.c),v.old.el_gate(v.old.candidate(self.c['instances']),self.c))
        with self.assertRaises(ValueError):v.old.el_gate(self.actual,self.c)

    def test_annotation_first_middle_last_only_same_block(self):
        ls=[l for l in self.actual.splitlines() if not l.startswith('ANNOTATION:')]
        for index in (2,5,len(ls)):
            candidate=ls[:index]+[self.annotation]+ls[index:]
            self.assertEqual(len(v.el_gate('\n'.join(candidate)+'\n',self.c)),12)

    def test_before_instance_duplicate_wrong_missing_annotation(self):
        ls=[l for l in self.actual.splitlines() if not l.startswith('ANNOTATION:')]
        for text in ['\n'.join([ls[0],self.annotation]+ls[1:]),
                     self.actual+self.annotation+'\n',self.actual.replace(v.old.ANNOTATION,'foreign'),
                     '\n'.join(ls)]:
            with self.assertRaises(ValueError):v.el_gate(text,self.c)

    def test_foreign_checksum_scope_extra_block_rejected(self):
        for text in [self.actual.replace('313685876','313685877'),
                     self.actual.replace(v.old.SCOPE,v.old.SCOPE+'.sibling'),
                     self.actual+'CHECKSUM: "4218964517 313685876"\n',
                     self.actual+'INSTANCE: '+v.old.SCOPE+'\n']:
            with self.assertRaises(ValueError):v.el_gate(text,self.c)

    def test_missing_duplicate_partial_and_unknown_fields(self):
        line='Toggle shared_tlb_update_o.g_content.v "logic shared_tlb_update_o.g_content.v"'
        for text in [self.actual.replace(line,''),self.actual+line+'\n',
                     self.actual.replace('ppn[43:0]','ppn[42:0]'),
                     self.actual+'Toggle gpte_q "logic gpte_q[63:0]"\n']:
            with self.assertRaises(ValueError):v.el_gate(text,self.c)

    def test_full_sourced_five_stage_mock_uses_successor_without_original_edit(self):
        e=v.context();self.assertIs(e['el_gate'],v.el_gate)
        c=self.c
        text=e['selection'](c)
        self.assertIn(str(Path(v.__file__).resolve()),text)
        self.assertFalse(e['host_hook'](c,text,v.old.candidate(c['instances']))['EDA_started'])
        self.assertEqual(v.old.life.digest(v.old.__file__),v.OLD_SHA)

    def test_actual_complete_paired_directions_but_missing_direction_rejected(self):
        lines=self.actual.splitlines()
        split='\n'.join(l if not l.startswith('Toggle ') else
                         '\n'.join(l.replace('Toggle ','Toggle '+d+' ',1) for d in ('0to1','1to0'))
                         for l in lines)+'\n'
        self.assertEqual(v.el_gate(split,self.c),v.el_gate(self.actual,self.c))
        bad=split.replace('Toggle 1to0 shared_tlb_update_o.g_content.v "logic shared_tlb_update_o.g_content.v"','')
        with self.assertRaises(ValueError):v.el_gate(bad,self.c)

    def test_fresh_output_only(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):v.prepare(Path(d))


if __name__=='__main__':unittest.main()
