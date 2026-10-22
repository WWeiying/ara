"""Software mutations for the exact725 singleton proposal; no raw collect/admit."""
from copy import deepcopy
import json
import unittest

import prepare_vnclipu_admission726 as c


def bit(width, index): return hex(1 << (width-1-index))


def bitmaps():
    before=dict(design={'shape':'fixed'},tests=['/fixture/%s/code.vdb'%i for i in range(725)],
                input_hashes={},metrics={})
    for metric,width,checksum in [('line',1718,'1316526434'),('cond',1140,'1370170966'),
                                  ('branch',1215,'1558979345'),('fsm',8,'7')]:
        before['metrics'][metric]={c.old.p.SCOPE:dict(width=width,checksum=checksum,bits='0x0')}
    single=deepcopy(before);single['tests']=[str(c.VDB)]
    single['input_hashes']={str(c.VDB/'snps/coverage/db/testdata'/c.old.p.NAME/(m+'.verilog.data.xml')):'a'*64
                          for m in c.bitmap.METRICS}
    for m,i in c.TARGETS:
        row=single['metrics'][m][c.old.p.SCOPE]
        row['bits']=hex(int(row['bits'],16)|int(bit(row['width'],i),16))
    targets=[dict(metric=m,raw_index=i,scope=c.old.p.SCOPE,
        width=before['metrics'][m][c.old.p.SCOPE]['width'],
        checksum=before['metrics'][m][c.old.p.SCOPE]['checksum']) for m,i in sorted(c.TARGETS)]
    return before,single,targets


class AdmissionTests(unittest.TestCase):
    def setUp(self): self.before,self.single,self.targets=bitmaps()
    def rejected_population(self):
        with self.assertRaises(ValueError): c.population(self.before,self.single)
    def test_exact_prefix(self):
        result,delta=c.population(self.before,self.single)
        self.assertEqual(result['tests'][:-1],self.before['tests'])
        self.assertEqual(delta['metrics'],dict(line=2,cond=1,branch=2,fsm=0))
    def test_missing_prefix(self): self.before['tests'].pop(); self.rejected_population()
    def test_duplicate_prefix(self): self.before['tests'][0]=self.before['tests'][1]; self.rejected_population()
    def test_duplicate_candidate(self): self.before['tests'][0]=str(c.VDB); self.rejected_population()
    def test_foreign_candidate(self): self.single['tests']=['/wrong/code.vdb']; self.rejected_population()
    def test_two_candidates(self): self.single['tests'].append('/other/code.vdb'); self.rejected_population()
    def test_design_drift(self): self.single['design']['shape']='drift'; self.rejected_population()
    def test_checksum_drift(self): self.single['metrics']['line'][c.old.p.SCOPE]['checksum']='0'; self.rejected_population()
    def test_width_drift(self): self.single['metrics']['line'][c.old.p.SCOPE]['width']+=1; self.rejected_population()
    def test_metric_missing(self): del self.single['metrics']['fsm']; self.rejected_population()
    def test_universe_drift(self): self.single['metrics']['line']['wrong']=self.single['metrics']['line'][c.old.p.SCOPE]; self.rejected_population()
    def test_hash_conflict(self):
        self.before['input_hashes']={'/fixture/hash':'a'*64};self.single['input_hashes']={'/fixture/hash':'b'*64};self.rejected_population()
    def reconcile(self):
        proposed,_=c.population(self.before,self.single)
        return c.reconcile(self.before,self.single,proposed,self.targets)
    def test_five_expected(self): self.assertEqual(sum(t['sample_hit'] for t in self.reconcile()),5)
    def test_missing_target_not_fabricated(self):
        self.single['metrics']['cond'][c.old.p.SCOPE]['bits']='0x0'
        self.assertEqual(sum(t['sample_hit'] for t in self.reconcile()),4)
    def test_wrong_scope(self):
        self.targets[0]['scope']='wrong'
        with self.assertRaises(ValueError): self.reconcile()
    def test_wrong_identity(self):
        self.targets[0]['raw_index']+=1
        with self.assertRaises(ValueError): self.reconcile()
    def test_target_already_hit(self):
        self.before['metrics']['cond'][c.old.p.SCOPE]['bits']=bit(1140,265)
        with self.assertRaises(ValueError): self.reconcile()
    def test_positive_measured(self):
        proposed,delta=c.population(self.before,self.single)
        points=[dict(scope=c.old.p.SCOPE,metric=m,point={'raw_index':i},baseline_hit=False,sample_hit=True,
            proposed_hit=True,source_sha256='known',native_GUI_ID_qualification=False) for m,i in c.TARGETS]
        c.positive(delta,points)
        for mutation in ('zero','duplicate','unproved','native','count'):
            d=deepcopy(delta);p=deepcopy(points)
            if mutation=='zero': d['metrics']=dict.fromkeys(c.bitmap.METRICS,0)
            if mutation=='duplicate': p.append(p[0])
            if mutation=='unproved': p[0]['source_sha256']=''
            if mutation=='native': p[0]['native_GUI_ID_qualification']=True
            if mutation=='count': d['metrics']['line']+=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):c.positive(d,p)
    def test_incomplete_metric_pins(self):
        self.single['input_hashes'].pop(next(iter(self.single['input_hashes'])))
        with self.assertRaises(ValueError):c.evaluate(self.before,self.single,{'targets':self.targets},{})
    def test_qualification_exact_seal(self):
        with self.assertRaises(ValueError):c.context('0'*64)
    def test_parent_qualification_gate(self):
        with self.assertRaises(ValueError):c.prepare(c.life.OUT/'never-created',c.life.OUT/'never-formal',c.QUAL_SEAL,False)
    def test_admit_authorization(self):
        with self.assertRaises(ValueError):c.admit(None,None,None,'USER_REPORTED')
    def test_real_parent_qualification_fixed(self):
        self.assertEqual(c.life.digest(c.QUAL/'qualification.json'),c.QUAL_SEAL)
        q=c.life.read_bound(c.QUAL/'qualification.json',c.QUAL_SEAL)
        pre=c.life.read_bound(c.old.p.PRE/'preflight-manifest.json',c.old.PRE_SEAL)
        proof=json.loads((c.QUAL/'maintenance-proof.json').read_text())
        scalar=json.loads((c.QUAL/'scalar-comparison.json').read_text())
        vector=json.loads((c.QUAL/'vector-comparison-unmodified.json').read_text())
        c.eligibility(q,proof,scalar,vector,pre)
        for mutation in ('fail','admitted','unknown','maintenance','scalar','vector','skip'):
            a,b,s,v=deepcopy(q),deepcopy(proof),deepcopy(scalar),deepcopy(vector)
            if mutation=='fail':a['status']='FAIL'
            if mutation=='admitted':a['coverage_admitted']=True
            if mutation=='unknown':a['genuinely_unknown_bytes']=1
            if mutation=='maintenance':b['known_source_maintenance_bytes']=127
            if mutation=='scalar':s['mismatch']={'bad':1}
            if mutation=='vector':v['instructions'][0]['unknown_write_bytes']=1
            if mutation=='skip':v['instructions'][0]['skipped_unknown_bytes']=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):c.eligibility(a,b,s,v,pre)


if __name__=='__main__':unittest.main()
