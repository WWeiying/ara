import copy
import csv
import json
from pathlib import Path
import tempfile
import tkinter
import unittest
from unittest.mock import patch
import capture_cast168_native_v2 as m


def fixture():return copy.deepcopy(m.origin)


def el(c):
    lines=[]
    for i in c['instances']:
        lines += ['CHECKSUM: "1144939760 400336858"','INSTANCE: '+i['scope']]
        lines += ['Toggle '+t['name']+' "logic '+t['native_name']+'"'for t in i['targets']]
    return '\n'.join(lines)+'\n'


class Successor(unittest.TestCase):
    def setUp(self):self.c=fixture()

    def test_actual279_fixture_keeps_all21plus258(self):
        self.assertEqual(len(m.inventory(m.ORIGIN,self.c,'before',0)),279)
        self.assertEqual(len(self.c['instances'][0]['protected']),258)
        self.assertEqual(len(self.c['instances'][0]['protected_compiled']),258)

    def mutate_rows(self,change):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            with (m.ORIGIN/'native_before_0.tsv').open() as f:rows=list(csv.reader(f,delimiter='\t'))
            original=copy.deepcopy(rows);change(rows)
            self.assertNotEqual(rows,original)
            with (out/'native_before_0.tsv').open('w',newline='') as f:csv.writer(f,delimiter='\t').writerows(rows)
            with self.assertRaises(ValueError):m.inventory(out,self.c,'before',0)

    def test_alias_missing_rejected(self):
        self.mutate_rows(lambda rows:rows.pop(next(i for i,r in enumerate(rows)if r[-1]=='out_pipe_ready')))

    def test_alias_path_drift_rejected(self):
        self.mutate_rows(lambda rows:rows[next(i for i,r in enumerate(rows)if r[-1]=='out_pipe_ready')].__setitem__(1,'out_pipe_ready[1]'))

    def test_alias_meta_drift_rejected(self):
        self.mutate_rows(lambda rows:rows[next(i for i,r in enumerate(rows)if r[-1]=='out_pipe_ready')].__setitem__(2,'wrong_meta'))

    def test_alias_duplicate_handle_rejected(self):
        self.mutate_rows(lambda rows:rows[-1].__setitem__(0,rows[1][0]))

    def test_alias_wrong_element_rejected(self):
        self.mutate_rows(lambda rows:rows[next(i for i,r in enumerate(rows)if r[-1]=='out_pipe_aux_q[0][7:0]')].__setitem__(3,'out_pipe_aux_q[1][7:0]'))

    def test_nonzero_output_stages_rejected(self):
        altered=copy.deepcopy(m.source)
        for i in altered['instances']:i['compiled_definition']=i['compiled_definition'].replace('NUM_OUT_REGS=0','NUM_OUT_REGS=1')
        with patch.object(m,'source',altered):
            with self.assertRaises(ValueError):m.contract(self.c)

    def test_wrong_singleton_compiled_bounds_rejected(self):
        altered=copy.deepcopy(m.source)
        for i in altered['instances']:
            for n in i['protected']:
                if n['native_name']=='out_pipe_aux_q[0:0][7:0]':n['dimensions']=[[0,1],[7,0]]
        with patch.object(m,'source',altered):
            with self.assertRaises(ValueError):m.contract(self.c)

    def test_target_unchanged_no_extra_aliases(self):
        old=[t for i in self.c['instances']for t in i['targets']]
        m.contract(self.c)
        self.assertEqual(old,[t for i in self.c['instances']for t in i['targets']])
        self.assertEqual(len(m.ALIASES),6)
        self.c['instances'][0]['protected'][0]='unauthorized'
        with self.assertRaises(ValueError):m.contract(self.c)

    def test_bare_identity_and_typed_EL_separate(self):
        meta={(i['scope'],t['name']):t['native_name']for i in self.c['instances']for t in i['targets']}
        self.assertEqual(len(m.parse_el(el(self.c),self.c,meta)),168)
        key=next(iter(meta));meta[key]='logic '+meta[key]
        with self.assertRaises(ValueError):m.parse_el(el(self.c),self.c,meta)

    def test_EL_wrong_type_bounds_extra_missing_duplicate_rejected(self):
        text=el(self.c)
        bad=[text.replace('"logic ','"integer ',1),text.replace('[63:0]','[62:0]',1),
             text+'Toggle status_d "logic status_d[4:0]"\n',
             '\n'.join(text.splitlines()[:-1]),text+'\n'+text.splitlines()[-1],
             text.replace('Toggle operands_q ','Toggle 0to1 operands_q ',1)]
        for value in bad:
            with self.assertRaises(ValueError):m.parse_el(value,self.c)

    def test_actual_Tcl_successor_body_loads_without_launch(self):
        t=tkinter.Tcl();t.eval('set ::cast_v2_test_only 1')
        t.call('source',str(m.HERE/'capture_cast168_native_v2.tcl'))
        self.assertEqual(t.eval('info args cast_session'),'')
        self.assertEqual(t.eval('info args cast_bind'),'stage instance')


if __name__=='__main__':unittest.main()
