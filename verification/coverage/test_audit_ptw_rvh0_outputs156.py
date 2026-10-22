import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import audit_ptw_rvh0_outputs156 as a
life = a.life


class AffirmativeNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p = a.life.OUT/'ptw-rvh0-outputs156-local-prepared794-agent-20261008-01/source-proof.json'
        a.need(a.life.digest(p) == 'f979b42b792c9e92d204b7e2e96cda54991da5e463d8db42eeb4bb2a821a0404', 'Frozen proof')
        cls.proof = json.loads(p.read_bytes()); cls.i = cls.proof['instance']
        rows = ['handle\tpath\tmeta\tname\ttype\tcoverage\tdisplay']
        for j,n in enumerate(cls.i['typed_objects']):
            dims = a.original.primitive.indexed.previous.frozen.dimensions(n)
            label = n['name']+''.join('[%d:%d]'%d for d in dims)
            role = 'MDA' if n['kind']=='arrays' else 'port' if n['portnode'] in ('2','3') else 'signal'
            rows.append('\t'.join([str(j),label,label,label,role,'0.00%','']))
        cls.before = a.original.bind(cls.i,'\n'.join(rows)+'\n')

    def stages(self):
        stages = {s: copy.deepcopy(self.before) for s in a.original.STAGES}
        for s in ('applied','reloaded'):
            for name in a.original.labels(self.i): stages[s][name]['display']='Excluded'
        return stages

    def test_explicit_synthetic_positive_not_native_evidence(self):
        self.assertEqual(a.stages_gate(self.i,self.stages())['native_flag_observation'],'UNOBSERVED')

    def flags(self):
        return [dict(stage=s,scope=self.i['scope'],label=n,excluded='1' if s in ('applied','reloaded') else '0')
                for s in a.original.STAGES for n in a.original.labels(self.i)]

    def test_identical_noop_targets_rejected(self):
        rows=self.flags()
        for r in rows:r['excluded']='0'
        with self.assertRaises(ValueError):a.affirmative(self.i,rows)
        self.assertEqual(a.stages_gate(self.i,{s:copy.deepcopy(self.before) for s in a.original.STAGES})
                         ['native_flag_observation'],'UNOBSERVED')

    def test_any_one_target_noop_or_false_label_rejected(self):
        for stage in ('applied','reloaded'):
            for label in a.original.labels(self.i):
                for flag in ('','0','true','Excluded'):
                    rows=self.flags()
                    next(r for r in rows if r['stage']==stage and r['label']==label)['excluded']=flag
                    with self.assertRaises(ValueError):a.affirmative(self.i,rows)

    def test_bad_target_coverage_rejected(self):
        v=self.stages();v['reset'][a.original.labels(self.i)[0]]['coverage']='100.00%'
        with self.assertRaises(ValueError):a.stages_gate(self.i,v)

    def test_protected_internal_or_reset_target_mutation_rejected(self):
        for stage,label in [('applied','gpaddr_q[40:0]'), ('reloaded','ptw_stage_q[1:0]'),
                            ('reset',a.original.labels(self.i)[0]), ('final',a.original.labels(self.i)[0])]:
            v=self.stages();v[stage][label]['display']='Excluded'
            with self.assertRaises(ValueError):a.stages_gate(self.i,v)

    def test_missing_stage_or_target_rejected(self):
        v=self.stages();del v['final']
        with self.assertRaises(ValueError):a.stages_gate(self.i,v)
        v=self.stages();del v['applied'][a.original.labels(self.i)[0]]
        with self.assertRaises(ValueError):a.stages_gate(self.i,v)

    def test_actual_qualified_soc_blank_display_is_not_affirmative(self):
        root=a.life.OUT/'soc-constants61-native-parent-20261008-03'
        q=json.loads((root/'capture-result.json').read_bytes())
        p=root/'native_applied_10.tsv'
        a.need(a.life.digest(p)==q['pins'][str(p)],'Actual qualified historical rows')
        rows=a.original.primitive.old.frozen.pack.native.native_rows(p.read_text())
        label='req_port_o.data_wdata[63:0]'
        self.assertEqual((rows[label]['coverage'],rows[label]['display']),('0.00%',''))
        self.assertFalse(rows[label]['display'])
        with self.assertRaises(ValueError):a.affirmative(self.i,[])

    def test_readonly_verify_intercepts_only_own_result(self):
        run=Path('/host/run')
        def fake(out,seal):
            life.save(out/'capture-result.json',{'status':'host'})
            return {'status':'host'}
        with patch.object(a.original,'verify',fake):
            self.assertEqual(a.original_readonly_verify(run,'host'),{'status':'host'})
        def foreign(out,seal):
            life.save(out/'foreign.json',{})
        with patch.object(a.original,'verify',foreign):
            with self.assertRaises(ValueError):a.original_readonly_verify(run,'host')


if __name__ == '__main__':unittest.main()
