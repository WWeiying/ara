"""Actual frozen preflight/722/parent-command fixtures with modeled monitor rejection cases; no running logs."""
from copy import deepcopy
from types import SimpleNamespace
import json
import unittest

import collect_memory_emul_r2_strict as c


def row(event='retire',**kwargs):
    r=dict.fromkeys(c.common.COMMIT_FIELDS,'0')
    r.update(event=event,cycle='1',pc='0000000080000000',insn='00000013',rd_wdata='0000000000000000',
             mem_addr='0000000000000000',mem_wdata='0000000000000000',mem_rmask='00',mem_wmask='00')
    r.update({k:str(v) for k,v in kwargs.items()});return r


def control_fixture(s):
    operations=[*c.p.PAIRS[3:7],*c.p.PAIRS[:3],*c.p.PAIRS[7:]]
    rows,vectors=[],[]
    for seq,(name,word) in enumerate(operations):
        insn='%08x'%word;bad=name.startswith('gmr_bad')
        rows.extend([row('arch_start',order=seq,trans_id=seq,insn=insn),row('cvx_req',order=-1,trans_id=seq,insn=insn)])
        if not bad:
            rows.extend(row(e,order=seq,trans_id=seq,port=seq,insn=insn) for e in ('uop_alloc','uop_done'))
            v=dict.fromkeys(c.common.VECTOR_FIELDS,'0')
            v.update(cycle='1',arch_seq=str(seq),vid=str(seq),insn=insn,nr_lanes='4',vlen_bits='1024',
                     use_vd='1' if name.startswith('gmr_load') else '0',vd='8',vl='4',eew='0',vstart='0')
            vectors.extend(dict(v,event=e) for e in ('alloc','write','done'))
        rows.append(row('cvx_resp',order=-1,trans_id=seq,pc='0000000000000000',insn='00000000',trap=int(bad)))
        if not bad:rows.append(row(insn=insn,pc='%016x'%s[name]))
    return rows,vectors


def signatures_fixture(s):
    rows=[]
    def store(name,offset,value,width=8,handler=False,entry=False):
        addr=s[name]+offset
        rows.append(row(insn='0002b023' if width==8 else '0002a023',mem_addr='%016x'%addr,mem_wdata='%016x'%value,
                        mem_wmask='%02x'%(((1<<width)-1)<<(addr&7)),
                        pc='%016x'%(s['gmr_handler']+(0 if entry else 4) if handler else 0x80000000)))
    def load_body(name,offset,body):
        for word in range(len(body)//8):
            rows.append(row(insn='0002b283',rd=5,mem_addr='%016x'%(s[name]+offset+word*8),mem_rmask='ff',
                            rd_wdata='%016x'%int.from_bytes(body[word*8:word*8+8],'little')))
    sp=0x80110000
    for n,w in enumerate(c.p.BAD_WORDS):
        values=[2,s['gmr_bad_%02d'%n],w,c.p.VLS[n],c.p.VTYPES[n],0,5,n+1,0x2222,1,117,sp]
        for i,v in enumerate(values):store('gmr_ledger',(n*12+i)*8,v,handler=True,entry=i==0)
        store('gmr_traps',0,n+1,handler=True)
        for i,v in enumerate([0x1111,0x2222,1,sp,0,c.p.VLS[n],c.p.VTYPES[n],5,117]):store('gmr_post',(n*9+i)*8,v)
        for i,v in enumerate([c.p.VLS[n],c.p.VTYPES[n],0]):store('gmr_cfg',(n*3+i)*8,v)
        for i,v in enumerate([4,24 if n==0 else 0,0]):store('gmr_legal',(n*3+i)*8,v)
        active=32 if n==1 else 4
        load_body('gmr_input',n*18*8,b'\xa5'*8+c.p.input_bytes(n)+b'\xa5'*8)
        load_body('gmr_output',n*18*8,b'\xa5'*8+c.p.input_bytes(n)[:active]+b'\xcc'*(128-active)+b'\xa5'*8)
    for i,v in enumerate([s['trap_fail'],s['trap_fail'],0,0,sp,sp,0,0,0,0,0,0]):store('gmr_restore',i*8,v)
    store('g75_result',0,4229,4);store('g75_result',4,0,4);store('num_failed',0,0,4)
    for phase in range(7):
        for reg in range(32):load_body('gmr_dump',(phase*32+reg)*18*8,b'\xa5'*8+c.p.expected_register(reg,phase)+b'\xa5'*8)
    store('tohost',0,1)
    for i,r in enumerate(rows):r['order']=str(i)
    return rows


class StrictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=c.life.read_bound(c.runner.PRE/'preflight-manifest.json',c.PRE_SEAL);cls.s=cls.pre['symbols']
        cls.rows,cls.vectors=control_fixture(cls.s);cls.sig=signatures_fixture(cls.s)
        cls.before=json.loads((c.BASE/'combined-bits.json').read_text())
    def reject(self,rows=None,vectors=None):
        with self.assertRaises(ValueError):c.lifecycle(self.rows if rows is None else rows,self.vectors if vectors is None else vectors,self.s)
    def test_actual_parent_prepared_binding(self):
        path=c.RUN.with_name(c.RUN.name+'.prepared.json');m=c.life.read_bound(path,c.RUN_SEAL)
        self.assertEqual(m['command'],c.runner.command(c.RUN));self.assertEqual(m['timeout_s'],1200)
    def test_modeled_shared_opcode_population(self):
        x=c.lifecycle(self.rows,self.vectors,self.s);self.assertEqual(x['rejected_arch_seqs'],[4,5,6]);self.assertEqual(len(x['legal_operations']),6)
    def test_illegal_backend(self):
        rows=deepcopy(self.rows);position=next(i for i,r in enumerate(rows) if r['event']=='cvx_req' and r['trans_id']=='4')+1
        rows[position:position]=[row(e,order=4,port=4,insn='%08x'%c.p.BAD_WORDS[0]) for e in ('uop_alloc','uop_done')];self.reject(rows)
    def test_illegal_vector_config(self):self.reject(vectors=[*self.vectors,dict(self.vectors[0],event='config',arch_seq='4')])
    def test_missing_response(self):self.reject([r for r in self.rows if not(r['event']=='cvx_resp' and r['trans_id']=='4')])
    def test_duplicate_request(self):
        rows=deepcopy(self.rows);rows.insert(2,rows[1]);self.reject(rows)
    def test_response_placeholder_not_identity(self):
        rows=deepcopy(self.rows);next(r for r in rows if r['event']=='cvx_resp')['insn']='02050407';self.reject(rows)
    def test_missing_exception(self):
        rows=deepcopy(self.rows);next(r for r in rows if r['event']=='cvx_resp' and r['trans_id']=='4')['trap']='0';self.reject(rows)
    def test_legal_shared_opcode_falsely_rejected(self):
        rows=deepcopy(self.rows);next(r for r in rows if r['event']=='cvx_resp' and r['trans_id']=='0')['trap']='1';self.reject(rows)
    def test_wrong_legal_PC(self):
        rows=deepcopy(self.rows);next(r for r in rows if r['event']=='retire')['pc']='0000000080000000';self.reject(rows)
    def test_missing_vector_done(self):self.reject(vectors=[r for r in self.vectors if not(r['event']=='done' and r['arch_seq']=='7')])
    def test_unallocated_write(self):self.reject(vectors=self.vectors[1:])
    def test_wrong_vector_vstart(self):
        vectors=deepcopy(self.vectors);vectors[1]['vstart']='1';self.reject(vectors=vectors)
    def test_full_modeled_signatures(self):
        r=c.observed(self.sig,self.s);self.assertEqual((r['checks'],r['snapshots'],r['explicit_read_bytes']),(4229,7,33120))
    def corrupt(self,name,offset,value,load=False):
        rows=deepcopy(self.sig);addr=self.s[name]+offset
        match=[r for r in rows if int(r['mem_addr'],16)==addr and int(r['mem_rmask' if load else 'mem_wmask'],16)]
        self.assertTrue(match);match[-1]['rd_wdata' if load else 'mem_wdata']='%016x'%value
        with self.assertRaises(ValueError):c.observed(rows,self.s)
    def test_trap_cause(self):self.corrupt('gmr_ledger',0,4)
    def test_last_tval(self):self.corrupt('gmr_ledger',(2*12+2)*8,0)
    def test_trap_vstart(self):self.corrupt('gmr_ledger',5*8,1)
    def test_prefault_vill(self):self.corrupt('gmr_cfg',8,24)
    def test_post_t2(self):self.corrupt('gmr_post',16,2)
    def test_CSR_restore(self):self.corrupt('gmr_restore',24,1)
    def test_check_count(self):self.corrupt('g75_result',0,4228)
    def test_VRF_guard(self):self.corrupt('gmr_dump',0,0,True)
    def test_v31_tail_after_faults(self):self.corrupt('gmr_dump',((5*32+31)*18+16)*8,0,True)
    def test_recovery(self):self.corrupt('gmr_dump',((6*32+8)*18+1)*8,0,True)
    def test_source_guard(self):self.corrupt('gmr_input',0,0,True)
    def test_output_tail(self):self.corrupt('gmr_output',(1*18+16)*8,0,True)
    def test_missing_readback(self):
        rows=deepcopy(self.sig);next(r for r in rows if int(r['mem_rmask'],16))['mem_addr']='0000000090000000'
        with self.assertRaises(ValueError):c.observed(rows,self.s)
    def test_protected_handler_register(self):
        rows=deepcopy(self.sig);rows[0]['rd']='8'
        with self.assertRaises(ValueError):c.observed(rows,self.s)
    def test_terminal_drift(self):
        s=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=c.p.NAME,coverage_admitted=False,admission_performed=False)
        c.terminal(s,{}, {})
        for changed in (dict(s,returncode=1),dict(s,status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED'),dict(s,coverage_admitted=True)):
            with self.assertRaises(ValueError):c.terminal(changed,{}, {})
        with self.assertRaises(ValueError):c.terminal(s,{'command':['wrong']},{'command':['sealed']})
    def test_722_upper_targets(self):
        single=deepcopy(self.before);single['tests']=[str(c.RUN/'code.vdb')]
        for t in self.pre['targets']:
            r=single['metrics'][t['metric']][t['scope']]
            r['bits']=hex(int(r['bits'],16)&~(1<<(r['width']-1-t['point']['raw_index'])))
            if t['expected_case']==2:r['bits']=hex(int(r['bits'],16)|(1<<(r['width']-1-t['point']['raw_index'])))
        hits,qualified=c.target_hits(self.before,single,self.pre['targets']);self.assertTrue(qualified)
        self.assertEqual(sum(h['hit_single'] for h in hits),2)
    def test_zero_gain_hold(self):
        single=deepcopy(self.before);single['tests']=[str(c.RUN/'code.vdb')]
        self.assertFalse(c.target_hits(self.before,single,self.pre['targets'])[1])
    def test_target_shape_drift(self):
        single=deepcopy(self.before);single['tests']=[str(c.RUN/'code.vdb')];t=self.pre['targets'][0]
        single['metrics'][t['metric']][t['scope']]['checksum']='bad'
        with self.assertRaises(ValueError):c.target_hits(self.before,single,self.pre['targets'])


class VectorTracerTests(unittest.TestCase):
    def setUp(self):
        self.s=c.life.read_bound(c.runner.PRE/'preflight-manifest.json',c.PRE_SEAL)['symbols']
        rows,vectors=control_fixture(self.s);self.control=c.lifecycle(rows,vectors,self.s)
        self.ref=[SimpleNamespace(pc=0x80000000+i*4,instruction=i,vector_writes={i:0}) for i in range(32)]
        self.ref += [SimpleNamespace(pc=self.s['gmr_load_%d'%n],instruction=(0x02057407 if n==1 else 0x02050407),vector_writes={8:0}) for n in range(3)]
        records=[dict(pc=hex(r.pc),instruction=hex(r.instruction),arch_seq=100+i,status='PASS',compared_bytes=128,
                      skipped_unknown_bytes=0,unknown_write_bytes=0,mismatch_count=0,first_mismatch=None) for i,r in enumerate(self.ref)]
        for n,r in enumerate(records[-3:]):r['arch_seq']=(0,2,7)[n];r['compared_bytes']=(4,32,4)[n]
        self.vector=dict(status='PASS',compared_instructions=35,skipped_unknown_bytes=0,non_bit_exact_instructions=0,
            nr_lanes=4,vlen_bits=1024,selected_index=None,stopped_at_spike_index=None,trapped_requests=[4,5,6],
            first_mismatch=None,unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],instructions=records,compared_bytes=4136)
        self.rows=[row(cycle=1)]
        self.text='1ns 1 M 0000000080000000 0 00000013\n'+''.join('Exception @ 51870000, PC: %016x, Cause: Illegal Instruction\ntval: %016x\n'%
                                                              (self.s['gmr_bad_%02d'%n],w) for n,w in enumerate(c.p.BAD_WORDS))
    def test_full35_vector(self):c.vector_exact(self.vector,self.control,self.ref,self.s)
    def test_missing_vector_byte(self):
        self.vector['instructions'][31]['compared_bytes']=127
        with self.assertRaises(ValueError):c.vector_exact(self.vector,self.control,self.ref,self.s)
    def test_wrong_recovery_arch(self):
        self.vector['instructions'][-1]['arch_seq']=4
        with self.assertRaises(ValueError):c.vector_exact(self.vector,self.control,self.ref,self.s)
    def test_unknown_byte(self):
        self.vector['instructions'][0]['unknown_write_bytes']=1
        with self.assertRaises(ValueError):c.vector_exact(self.vector,self.control,self.ref,self.s)
    def test_wrong_trap_arch(self):
        self.vector['trapped_requests']=[0,5,6]
        with self.assertRaises(ValueError):c.vector_exact(self.vector,self.control,self.ref,self.s)
    def test_precise3_tracer(self):self.assertEqual(c.tracer_exact(self.text,self.rows,self.s)['illegal_exceptions'],3)
    def test_wrong_tval(self):
        with self.assertRaises(ValueError):c.tracer_exact(self.text.replace('0000000002057427','0000000000000000'),self.rows,self.s)
    def test_time_not_PC(self):
        with self.assertRaises(ValueError):c.tracer_exact(self.text.replace('PC: %016x'%self.s['gmr_bad_00'],'PC: 0000000051870000'),self.rows,self.s)


if __name__=='__main__':unittest.main()
