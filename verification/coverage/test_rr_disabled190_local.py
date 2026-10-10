import copy
import json
import unittest
from unittest.mock import patch
import rr_disabled190_local as r


class LocalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.q=json.loads(r.SOURCE.read_bytes())
        cls.ii=r.instances(cls.q)
        cls.c={'instances':cls.ii}

    def test_actual_source_partition(self):
        self.assertEqual(len(self.ii),30)
        self.assertEqual(sum(len(i['typed_objects'])-len(i['signals']) for i in self.ii),5160)

    def test_actual_candidate_roundtrip(self):
        self.assertEqual(len(r.el_gate(r.candidate(self.ii),self.c)),190)

    def test_actual_existing_qualified_el_disjoint(self):
        r.collision_gate(self.q,(r.source.POLICY/'combined.el').read_text())

    def test_existing_whole_or_partial_collision(self):
        text=r.candidate(self.ii)
        for changed in (text,text.replace('Toggle ','Toggle 0to1 ',1),
                        text.replace('[63:0]','[3:0]',1)):
            with self.assertRaises(Exception): r.collision_gate(self.q,changed)

    def test_changed_direction(self):
        text=r.candidate(self.ii).replace('Toggle ', 'Toggle 0to1 ',1)
        with self.assertRaises(Exception): r.el_gate(text,self.c)

    def test_partial_field(self):
        text=r.candidate(self.ii).replace('[63:0]','[62:0]',1)
        with self.assertRaises(Exception): r.el_gate(text,self.c)

    def test_foreign_annotation(self):
        with self.assertRaises(Exception): r.el_gate(r.candidate(self.ii).replace(r.ANNOTATION,'foreign'),self.c)

    def test_nonzero783_rejected(self):
        q=copy.deepcopy(self.q); q['candidates'][0]['raw_missing']-=1
        with self.assertRaises(Exception): r.source_gate(q)

    def test_active_format_rejected(self):
        q=copy.deepcopy(self.q); q['candidates'][0]['format_index']=0
        with self.assertRaises(Exception): r.source_gate(q)

    def test_source_role_rejected(self):
        q=copy.deepcopy(self.q); q['candidates'][0]['attributes']['portnode']='0'
        with self.assertRaises(Exception): r.source_gate(q)

    def test_complement_drop_rejected(self):
        q=copy.deepcopy(self.q); q['callers'][0]['protected_objects'].pop()
        with self.assertRaises(Exception): r.instances(q)

    def test_terminal_failure_rejected(self):
        with self.assertRaises(Exception): r.primitive.terminal_gate({'returncode':1,'timed_out':False},{},{})

    def test_relative_import_env_rejected(self):
        with patch.dict(r.os.environ,{'PYTHONPATH':'verification:relative'},clear=True):
            with self.assertRaises(Exception): r.run(r.life.OUT/'unused', 'unused','unused')

    def test_recursive_tcl_closure(self):
        pins=r.frozen.tcl_pins(r.TCL)
        self.assertIn(str(r.frozen.TCL),pins)
        self.assertIn(str(r.primitive.TCL),pins)


if __name__=='__main__': unittest.main()
