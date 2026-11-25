import copy
from pathlib import Path
import unittest

import check
import prepare


def fixture(case,coop=0):
    c=copy.deepcopy(case); m,n,tile=c['m'],c['n'],c['tile']; native=c['backend']=='native'
    tn=16 if tile==8 else 32
    commands=[dict(m=tile,n=tn,row=r,col=col,layout={1:1,4:2,8:3}[tile])
        for r in range(0,m,tile) for col in range(0,n,tn)]
    b=dict(case=c,plan=dict(commands=commands,flags=1),build_id='fixture')
    lines=[]
    count=len(commands) if native else n//32*(1 if m==1 else m//4)
    if native:
        for trial in range(2):
            for i,cmd in enumerate(commands):
                cm,cn=cmd['m'],cmd['n']; pairs=cm*cn*2048
                cap=64 if coop and cm==8 else 32
                access=0
                if c['reuse']=='operation': access=1 if i==0 else (3 if i==count-1 else 2)
                elif c['reuse']=='cross_call': access=(1 if i==0 else 2) if trial==0 else (3 if i==count-1 else 2)
                p=dict(seq=trial*count+i+1,m=cm,n=cn,lanes=4,vlen=1024,success=1,
                    fault=0,validation_fault=0,validation_error=0,read_fault=0,context_validation_fault_count=0,
                    busy_cycles=pairs//cap,dot_active_cycles=pairs//cap,probe_compute_without_dot_issue_cycles=0,
                    weight_bytes=cn*8*144,activation_bytes=cm*8*292,useful_pairs=pairs,pair_capacity=pairs,
                    tiles=8*(cn//4)*(2 if cm>4 else 1),activation_access=access,
                    context_fill_count=int(access==1),context_reuse_count=int(access in (2,3)),
                    activation_axi_bytes_saved=cm*8*292 if access in (2,3) else 0)
                p.update({k:0 for k in check.PHASES}); p['phase_compute_cycles']=p['busy_cycles']
                lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in p.items()))
    reuse=dict(direct=0,operation=1,cross_call=2)[c['reuse']]
    lines.append(f'QBR_META id=fixture m={m} n={n} k=2048 tile={tile} rvv={int(not native)} reuse={reuse} trials=2')
    for t in range(2):
        timing=dict(trial=t,status=0,**{f't{i}':t*10000000+i*1000000 for i in range(6)})
        csr=dict(trial=t,before_f=0,before_v=0,before_s=0,quant_f=1,quant_v=2,quant_s=0,
                 pack_f=1,pack_v=2,pack_s=0,after_f=1|(8 if t else 0),after_v=2,after_s=0)
        work=dict(trial=t,quant=m,pack=m//4 if tile==4 else 1,query=int(native),plan=int(native),execute=1,
                  planned=count if native else 0,actual=count,eligible=int(native and m==1),
                  context=int(native and c['reuse']!='direct'),coop=coop if native else 0,caps5=coop if native else 0,
                  ctx_bytes=4672 if native else 0,ctx_count=int(native),ctx_m=8 if native else 0,ctx_k=32 if native else 0)
        sizes=dict(out=m*n,q8=m*8*292,pack=m*8*292,input=m*8192,weight=n*8*144,guard=640,
                   identity=m*8192+n*8*144+(2*m*8*292 if c['reuse']=='cross_call' and t else 0),work=count)
        proof=dict(trial=t,csr_bad=0,first_output_bad=2**32-1)
        for k,v in sizes.items(): proof[k+'_n']=v; proof[k+'_bad']=0
        for kind,record in (('TIME',timing),('CSR',csr),('WORK',work),('PROOF',proof)):
            lines.append('QBR_'+kind+' '+' '.join(f'{k}={v}' for k,v in record.items()))
    lines+=['QBR_DONE errors=0 trials=2','Core Test *** SUCCESS ***']
    return '\n'.join(lines),b


class ReuseTests(unittest.TestCase):
    def test_all_declared_modes_cooperation_on_and_off(self):
        for c in prepare.catalog()['cases']:
            for coop in (0,1):
                with self.subTest(case=c['id'],coop=coop):
                    self.assertEqual(check.check_text(*fixture(c,coop))['state'],'PASS')

    def test_full_comparison_counts_not_hash(self):
        c=prepare.catalog()['cases'][1]; text,b=fixture(c)
        for before,after in (('out_n=512','out_n=511'),('out_bad=0','out_bad=1'),
            ('q8_bad=0','q8_bad=1'),('pack_bad=0','pack_bad=1'),('input_bad=0','input_bad=1'),
            ('weight_bad=0','weight_bad=1'),('guard_bad=0','guard_bad=1'),('work_bad=0','work_bad=1'),
            ('csr_bad=0','csr_bad=1'),('quant_v=2','quant_v=0'),('after_v=2','after_v=3'),
            ('after_f=1 ','after_f=0 '),('after_f=9 ','after_f=1 '),('status=0','status=1')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                check.check_text(text.replace(before,after,1),b)

    def test_cross_call_identity_and_hardware_lifecycle(self):
        c=next(c for c in prepare.catalog()['cases'] if c['reuse']=='cross_call')
        text,b=fixture(c)
        for before,after in (('identity_bad=0','identity_bad=1'),('activation_access=2','activation_access=1'),
                             ('eligible=1','eligible=0'),('context=1','context=0'),('identity_n=160320','identity_n=1')):
            self.assertIn(before,text)
            with self.subTest(before=before),self.assertRaises(ValueError):
                check.check_text(text.replace(before,after,1),b)

    def test_no_assumed_coop_or_weakened_pair_rates(self):
        c=prepare.catalog()['cases'][1]; text,b=fixture(c,1)
        with self.assertRaises(ValueError): check.check_text(text.replace('coop=1','coop=0'),b)
        with self.assertRaises(ValueError): check.check_text(text.replace('dot_active_cycles=4096','dot_active_cycles=8192',1),b)

    def test_incomplete_duplicate_and_phase_evidence(self):
        text,b=fixture(prepare.catalog()['cases'][0])
        with self.assertRaises(ValueError): check.check_text(text.replace('QBR_PROOF trial=1','IGNORED trial=1'),b)
        with self.assertRaises(ValueError): check.check_text(text.replace('QBR_DONE','QBR_TIME trial=0 status=0\nQBR_DONE'),b)
        with self.assertRaises(ValueError): check.check_text(text.replace('t2=2000000','t2=1000000',1),b)

    def test_cases_and_source_policy(self):
        cat=prepare.catalog(); cs=cat['cases']
        self.assertEqual(len(cs),9); self.assertEqual(sum(c['backend']=='native' for c in cs),6)
        self.assertEqual(len({c['id'] for c in cs}),9)
        self.assertEqual(cat['sdk_commit'],'dbe2b78817ef45b912444afcb85ad6e01a2be135')
        self.assertTrue(all(c['k']==2048 and c['trials']==2 for c in cs))
        source=(Path(prepare.__file__).parent/'main.c').read_text()
        self.assertNotIn('printf("QBR_Q8',source)
        self.assertIn('if (identity.errors)',source)
        self.assertIn('reuse_check_bytes(q8.data,reuse_expected_q8,AB)',source)
        self.assertIn('if (errors) break;',source)


if __name__=='__main__': unittest.main()
