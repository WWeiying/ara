import copy
import tempfile
from pathlib import Path
import unittest

import pmp_constants816_native as p


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof=p.life.read_bound(p.SOURCE,p.SOURCE_SHA)
        cls.ii=p.instances(cls.proof)
        cls.c=dict(instances=cls.ii,design='host',vdb='host',test='host')
        cls.el=p.candidate(cls.ii)

    def test_actual_registry(self):
        fields=[s for i in self.ii for s in i['signals']]
        self.assertEqual((len(self.ii),len(fields)),(8,816))
        self.assertEqual(sum(s['kind']=='node' for s in fields),544)
        self.assertEqual(sum(s['kind']=='vectornode' for s in fields),272)
        self.assertEqual(len(self.proof['HOLD']),13)
        self.assertTrue(p.el_gate(self.el,self.c))

    def test_actual_host_five_phase_complete_inventory(self):
        q=p.host_hook(self.c,p.selection(self.c),self.el)
        self.assertEqual(q['scope_inventories'],40)
        self.assertEqual(q['per_object_GUI_select_calls'],0)

    def test_unknown_scope_checksum_or_annotation(self):
        for text in (self.el+'CHECKSUM: "0 0"\n',self.el.replace('INSTANCE: ','INSTANCE: foreign',1),
                     self.el.replace(p.ANNOTATION,'foreign',1)):
            with self.assertRaises(Exception):p.el_gate(text,self.c)

    def test_scalar_range_net_and_partial_rejected(self):
        i=self.ii[0];s=next(s for s in i['signals'] if s['kind']=='node');name=s['name']
        for text in (self.el.replace('"logic '+name+'"','"logic '+name+'[0:0]"',1),
                     self.el.replace('"logic '+name+'"','"net '+name+'"',1),
                     self.el.replace('[1:0]"','[0:0]"',1)):
            with self.assertRaises(Exception):p.el_gate(text,self.c)

    def test_paired_directions_exact(self):
        line=next(line for line in self.el.splitlines() if line.startswith('Toggle '))
        paired=self.el.replace(line,line.replace('Toggle ','Toggle 0to1 ')+'\n'+line.replace('Toggle ','Toggle 1to0 '),1)
        self.assertEqual(p.el_gate(self.el,self.c),p.el_gate(paired,self.c))
        with self.assertRaises(Exception):p.el_gate(self.el.replace(line,line.replace('Toggle ','Toggle 0to1 '),1),self.c)
        with self.assertRaises(Exception):p.el_gate(paired.replace(line.replace('Toggle ','Toggle 1to0 '),line.replace('Toggle ','Toggle 0to1 ')),self.c)

    def test_whole_scope_unknown_object_rejected(self):
        for extra in ('Toggle\n','Toggle foreign "logic foreign"\n','State 1\n'):
            with self.assertRaises(Exception):p.el_gate(self.el+extra,self.c)

    def test_source_kind_role_range_x_claim_rejected(self):
        for key,value in (('type','3'),('portnode','9'),('left','99')):
            q=copy.deepcopy(self.proof);q['fresh_candidates'][0]['compiled'][key]=value
            with self.assertRaises(Exception):p.instances(q)
        q=copy.deepcopy(self.proof);q['fresh_candidates'][0]['initial_X_qualified']=True
        with self.assertRaises(Exception):p.instances(q)

    def test_old_owner_and_duplicate_target_rejected(self):
        q=copy.deepcopy(self.proof);q['already_owned'].append(q['fresh_candidates'][0])
        with self.assertRaises(Exception):p.instances(q)
        q=copy.deepcopy(self.proof);q['fresh_candidates'][1]=q['fresh_candidates'][0]
        with self.assertRaises(Exception):p.instances(q)

    def test_dynamic_d_and_mda_never_targets(self):
        for i in self.ii:
            for s in i['signals']:
                self.assertNotIn('pmpcfg_d',s['name'])
                self.assertNotIn('pmpaddr_d',s['name'])
                self.assertNotEqual(s['kind'],'arrays')
        self.assertTrue(any(n['kind']=='arrays' for i in self.ii for n in i['typed_objects']))
        q=copy.deepcopy(self.proof);q['fresh_candidates'][0]['compiled']['name']='pmpaddr_o'
        with self.assertRaises(Exception):p.instances(q)

    def test_protected_changed_or_missing_identity_rejected(self):
        i=self.ii[0];label=p.labels(i)[0]
        before={label:dict(name=label,type='port',coverage='0%',display='0%',handle='1'),
                'protected':dict(name='protected',type='signal',coverage='0%',display='0%',handle='2')}
        for change in ('coverage','display','type','name'):
            actual=copy.deepcopy(before);actual['protected'][change]='changed'
            with self.assertRaises(Exception):p.stage_gate(i,before,actual,'applied')
        actual=copy.deepcopy(before);actual.pop('protected')
        with self.assertRaises(Exception):p.stage_gate(i,before,actual,'applied')
        actual=copy.deepcopy(before);actual[label]['display']='excluded'
        with self.assertRaises(Exception):p.stage_gate(i,before,actual,'reset')

    def test_tcl_dependency_closure(self):
        pins=p.old.frozen.tcl_pins(p.TCL)
        self.assertIn(str(p.TCL),pins)
        self.assertIn(str(p.HERE/'soc_constants61_native.tcl'),pins)
        self.assertIn(str(p.HERE/'mfpu272_five_phase.tcl'),pins)

    def test_actual_fresh_prepare_and_check_missing_terminal(self):
        with tempfile.TemporaryDirectory(dir=p.life.OUT,prefix='pmp816-host-test-') as tmp:
            out=Path(tmp);out.rmdir()
            try:
                p.prepare(out);seal=p.life.digest(out/'config.json');c=p.check(out,seal)
                self.assertEqual((c['target_scalars'],c['target_vectors'],c['target_MDA']),(544,272,0))
                self.assertIn(str(p.TCL),c['pins'])
                with self.assertRaises(Exception):p.verify(out,seal)
            finally:
                import shutil
                shutil.rmtree(out,ignore_errors=True)


if __name__=='__main__':unittest.main()
