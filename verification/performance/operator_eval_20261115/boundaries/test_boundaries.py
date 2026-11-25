import copy
import unittest
import check
import prepare

def fixture(m,segment):
    case=next(c for c in prepare.catalog()['cases'] if c['m']==m)
    commands=[]; snapshot=0
    for k0 in range(0,8,segment or 8):
        kb=min(segment or 8,8-k0)
        for col,n in ((0,32),(32,3)):
            commands.append(dict(m=m,n=n,kb=kb,k0=k0,col=col,
                wo=((k0*36+col*kb) if segment else col*8)*144,
                snapshot=snapshot,snapshot_bytes=m*kb*292)); snapshot+=m*kb*292
    ws=m*32*4+m*3*292 if segment else 0
    rejects=dict(context=13,short_weight=3,short_ws=3 if ws else 0,ws_tested=int(bool(ws)),bad_k=12,bad_segment=11)
    plan=dict(commands=commands,flags=1,snapshot_bytes=snapshot,workspace_bytes=ws,reject=rejects)
    b=dict(case=case,plan=plan,build_id='test'); lines=[]
    for t in range(2):
        for i,c in enumerate(commands):
            n,kb=c['n'],c['kb']; kper=4 if m==2 else 2
            dot=kb*((n+3)//4)*256//kper
            p=dict(seq=t*len(commands)+i+1,m=m,n=n,lanes=4,vlen=1024,success=1,
                fault=0,validation_fault=0,validation_error=0,read_fault=0,context_validation_fault_count=0,
                busy_cycles=dot,dot_active_cycles=dot,probe_compute_without_dot_issue_cycles=0,
                weight_bytes=n*kb*144,activation_bytes=m*kb*292,tiles=kb*((n+3)//4),
                useful_pairs=m*n*kb*256,pair_capacity=n*kb*256*8//kper,
                activation_access=0,context_fill_count=0,context_reuse_count=0,activation_axi_bytes_saved=0)
            p.update({k:0 for k in check.PHASES}); p['phase_compute_cycles']=dot
            lines.append('[QBS_PERF] '+' '.join(f'{k}={v}' for k,v in p.items()))
    lines.append(f'QBB_META id=test m={m} n=35 k=2048 stride=38 segment={segment} trials=2')
    for t in range(2):
        timing=dict(trial=t,status=0,fallback=t,**{f't{i}':t*10000000+i*1000000 for i in range(6)})
        csr=dict(trial=t,before_f=0,before_v=0,before_s=0,quant_f=1,quant_v=2,quant_s=0,
            pack_f=1,pack_v=2,pack_s=0,after_f=1|(8 if t else 0),after_v=2,after_s=0)
        work=dict(trial=t,planned=len(commands),actual=len(commands),eligible=0,split=int(bool(segment)),
            gather=int(bool(segment)),workspace=ws,snapshots=snapshot,coop=1)
        lengths=dict(out=m*38,q8=m*8*292,act=m*8*292,input=m*8192,weight=36*8*144,
            ws=max(ws,4),snap=snapshot,guard=768)
        proof=dict(trial=t,work_bad=0,csr_bad=0)
        for k,v in lengths.items(): proof[k+'_n']=v; proof[k+'_bad']=0
        for kind,r in (('TIME',timing),('CSR',csr),('WORK',work),('PROOF',proof)):
            lines.append('QBB_'+kind+' '+' '.join(f'{k}={v}' for k,v in r.items()))
    rejection=dict(rejects,calls=0,bytes=m*38*4+2*m*8*292+m*8192+36*8*144+max(ws,4)+768,
        bad=0,fcsr=8,vcsr=2,vstart=0,csr_bad=0)
    lines+=['QBB_REJECT '+' '.join(f'{k}={v}' for k,v in rejection.items()),
            'QBB_DONE errors=0 trials=2','Core Test *** SUCCESS ***']
    return '\n'.join(lines),b

class BoundaryTests(unittest.TestCase):
    def test_two_small_cases(self):
        for m,segment in ((2,0),(3,3)):
            f=fixture(m,segment); self.assertEqual(check.check_text(*f)['state'],'PASS')
            self.assertEqual(sum(c['kb']*c['n'] for c in f[1]['plan']['commands']),8*35)

    def test_m3_capacity_is_not_equal_useful_pairs(self):
        text,b=fixture(3,3)
        self.assertIn('pair_capacity=98304',text)
        with self.assertRaises(ValueError): check.check_text(text.replace('pair_capacity=98304','pair_capacity=73728',1),b)

    def test_full_memory_flags_and_snapshot_gates(self):
        text,b=fixture(3,3)
        for old,new in (('out_bad=0','out_bad=1'),('out_n=114','out_n=105'),
            ('ws_bad=0','ws_bad=1'),('snap_bad=0','snap_bad=1'),('q8_bad=0','q8_bad=1'),
            ('guard_bad=0','guard_bad=1'),('after_v=2','after_v=0'),('after_f=1 ','after_f=0 '),
            ('after_f=9 ','after_f=1 '),('fallback=1','fallback=0'),('actual=6','actual=5')):
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError): check.check_text(text.replace(old,new,1),b)

    def test_rejection_must_never_reach_executor_or_change_state(self):
        text,b=fixture(2,0)
        for old,new in (('context=13','context=0'),('calls=0','calls=1'),('bad=0 fcsr=8','bad=1 fcsr=8'),
            ('fcsr=8','fcsr=0'),('bad_k=12','bad_k=0'),('short_weight=3','short_weight=0')):
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError): check.check_text(text.replace(old,new,1),b)

    def test_tail_and_truncation(self):
        text,b=fixture(2,0)
        for old,new in (('m=2 n=3 lanes','m=2 n=4 lanes'),('weight_bytes=3456','weight_bytes=4608'),
                        ('QBB_PROOF trial=1','IGNORED trial=1'),('t2=2000000','t2=1000000')):
            self.assertIn(old,text)
            with self.subTest(old=old),self.assertRaises(ValueError): check.check_text(text.replace(old,new,1),b)

    def test_scope_stays_bounded_and_d256_is_explicit_gap(self):
        cat=prepare.catalog(); self.assertEqual(len(cat['cases']),2)
        self.assertTrue(all(c['k']==2048 and c['n']==35 and c['trials']==2 for c in cat['cases']))
        self.assertEqual(cat['sdk_commit'],'dbe2b78817ef45b912444afcb85ad6e01a2be135')
        self.assertEqual(cat['d256']['state'],'GAP_NOT_RUNNABLE')

if __name__=='__main__': unittest.main()
