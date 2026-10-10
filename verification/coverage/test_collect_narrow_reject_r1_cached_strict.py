"""Frozen real Spike/719 fixtures plus modeled monitor events; no running DUT log reads."""
from copy import deepcopy
from types import SimpleNamespace
import json
import re
import unittest

import collect_narrow_reject_r1_cached_strict as c


def row(event='retire', **kwargs):
    r = dict.fromkeys(c.common.COMMIT_FIELDS, '0')
    r.update(event=event, cycle='1', pc='0000000080000000', insn='00000013',
             rd_wdata='0000000000000000', mem_addr='0000000000000000',
             mem_wdata='0000000000000000', mem_rmask='00', mem_wmask='00')
    r.update({k: str(v) for k, v in kwargs.items()})
    return r


def control_fixture(symbols):
    rows = []
    for seq, word in enumerate([*c.WORDS, c.oracle.RECOVERY]):
        insn = '%08x' % word
        rows += [row('arch_start', order=seq, trans_id=seq, insn=insn),
                 row('cvx_req', order=-1, trans_id=seq, insn=insn)]
        if seq == 24:
            rows += [row(e, order=seq, trans_id=seq, insn=insn, port=1) for e in ('uop_alloc', 'uop_done')]
        rows.append(row('cvx_resp', order=-1, trans_id=seq, insn='00000000', pc='0000000000000000', trap=int(seq < 24)))
    rows.append(row(order=0, insn='%08x' % c.oracle.RECOVERY, pc='%016x' % symbols['gnr_recovery']))
    v = dict.fromkeys(c.common.VECTOR_FIELDS, '0')
    v.update(cycle='1', arch_seq='24', vid='1', insn='%08x' % c.oracle.RECOVERY,
             nr_lanes='4', vlen_bits='1024', use_vd='1', vd='16', vl='4', vstart='0')
    return rows, [dict(v, event=e) for e in ('alloc', 'write', 'done')]


def signature_fixture(s):
    rows = []
    def store(name, offset, value, width=8, handler=False, entry=False):
        addr = s[name]+offset
        rows.append(row(insn='0002b023' if width == 8 else '0002a023',
            pc='%016x' % (s['gnr_handler']+(0 if entry else 4) if handler else 0x80000000),
            mem_addr='%016x' % addr, mem_wdata='%016x' % value, mem_wmask='%02x' % (((1<<width)-1) << (addr&7))))
    sp = 0x80110000
    for n, case in enumerate(c.oracle.CASES):
        ledger = [2,s['gnr_bad_%02d'%n],int(case['word'],16),4,c.oracle.vtype(case),1,5,n+1,0x2222,1,117,sp]
        for i, value in enumerate(ledger): store('gnr_ledger', (n*12+i)*8, value, handler=True, entry=i==0)
        store('gnr_traps', 0, n+1, handler=True)
        for i, value in enumerate([0x1111,0x2222,1,sp,1,4,c.oracle.vtype(case),5,117]):
            store('gnr_post', (n*9+i)*8, value)
    for i, v in enumerate([s['trap_fail'],s['trap_fail'],0,0,sp,sp,0,0,0,0,0,0]): store('gnr_restore',i*8,v)
    store('g75_result',0,15489,4); store('g75_result',4,0,4); store('num_failed',0,0,4)
    for phase in range(26):
        for reg in range(32):
            expected = b'\xa5'*8+c.oracle.expected_register(reg,phase==25)+b'\xa5'*8
            for word in range(18):
                address = s['gnr_dump']+((phase*32+reg)*18+word)*8
                rows.append(row(insn='0002b283',rd=5,mem_addr='%016x'%address,mem_rmask='ff',
                                rd_wdata='%016x'%int.from_bytes(expected[word*8:word*8+8],'little')))
    store('tohost',0,1)
    for i, r in enumerate(rows): r['order'] = str(i)
    return rows


class StrictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = c.life.read_bound(c.runner.PRE/'preflight-manifest.json', c.PRE_SEAL)
        cls.s = cls.pre['symbols']
        cls.rows, cls.vectors = control_fixture(cls.s)
        cls.sig = signature_fixture(cls.s)
        cls.before = json.loads((c.BASE/'combined-bits.json').read_text())

    def reject_control(self, rows=None, vectors=None):
        with self.assertRaises(ValueError): c.lifecycle(self.rows if rows is None else rows,
                                                        self.vectors if vectors is None else vectors, self.s)

    def test_modeled_lifecycle_pass(self):
        r = c.lifecycle(self.rows,self.vectors,self.s)
        self.assertEqual((r['requests'],r['responses'],r['exceptions']),(25,25,24))

    def test_illegal_backend(self):
        rows=deepcopy(self.rows)
        rows[2:2]=[row(e,order=0,insn='%08x'%c.WORDS[0],port=1) for e in ('uop_alloc','uop_done')]
        self.reject_control(rows)

    def test_illegal_vector_config(self):
        self.reject_control(vectors=[*self.vectors,dict(self.vectors[0],event='config',arch_seq='0')])

    def test_missing_response(self): self.reject_control([r for i,r in enumerate(self.rows) if i!=2])
    def test_duplicate_start(self): self.reject_control([*self.rows,self.rows[0]])
    def test_duplicate_request(self): self.reject_control([self.rows[0],self.rows[1],self.rows[1],*self.rows[2:]])
    def test_wrong_request_opcode(self):
        rows=deepcopy(self.rows); rows[1]['insn']='00000013'; self.reject_control(rows)
    def test_wrong_rejection_order(self):
        rows=deepcopy(self.rows); rows[0]['insn'],rows[3]['insn']=rows[3]['insn'],rows[0]['insn']; self.reject_control(rows)
    def test_response_opcode_is_not_identity(self):
        rows=deepcopy(self.rows); rows[2]['insn']='00000013'; self.reject_control(rows)
    def test_missing_exception(self):
        rows=deepcopy(self.rows); rows[2]['trap']='0'; self.reject_control(rows)
    def test_recovery_exception(self):
        rows=deepcopy(self.rows); rows[-2]['trap']='1'; self.reject_control(rows)
    def test_missing_backend_completion(self): self.reject_control([r for r in self.rows if r['event']!='uop_done'])
    def test_missing_vector_completion(self): self.reject_control(vectors=self.vectors[:-1])
    def test_unallocated_vector_write(self): self.reject_control(vectors=self.vectors[1:])
    def test_vector_write_metadata(self):
        v=deepcopy(self.vectors); v[1]['vstart']='1'; self.reject_control(vectors=v)

    def test_modeled_full_signatures_pass(self):
        r=c.observed(self.sig,self.s); self.assertEqual((r['snapshots'],r['checks'],r['explicit_dump_read_bytes']),(26,15489,119808))

    def corrupt(self,name,offset,value,load=False):
        rows=deepcopy(self.sig); address=self.s[name]+offset
        match=[r for r in rows if int(r['mem_addr'],16)==address and int(r['mem_rmask' if load else 'mem_wmask'],16)]
        self.assertTrue(match); match[-1]['rd_wdata' if load else 'mem_wdata']='%016x'%value
        with self.assertRaises(ValueError): c.observed(rows,self.s)

    def test_trap_cause(self): self.corrupt('gnr_ledger',0,4)
    def test_last_tval(self): self.corrupt('gnr_ledger',(23*12+2)*8,0)
    def test_vstart(self): self.corrupt('gnr_ledger',40,0)
    def test_post_vstart(self): self.corrupt('gnr_post',23*9*8+32,0)
    def test_post_t2(self): self.corrupt('gnr_post',16,2)
    def test_CSR_restore(self): self.corrupt('gnr_restore',24,1)
    def test_check_count(self): self.corrupt('g75_result',0,15488)
    def test_guard(self): self.corrupt('gnr_dump',0,0,True)
    def test_phase24_v31_tail(self): self.corrupt('gnr_dump',((24*32+31)*18+16)*8,0,True)
    def test_recovery_word(self): self.corrupt('gnr_dump',((25*32+16)*18+1)*8,0,True)
    def test_missing_readback(self):
        rows=deepcopy(self.sig); next(r for r in rows if int(r['mem_rmask'],16))['mem_addr']='0000000090000000'
        with self.assertRaises(ValueError): c.observed(rows,self.s)
    def test_handler_register(self):
        rows=deepcopy(self.sig); rows[0]['rd']='8'
        with self.assertRaises(ValueError): c.observed(rows,self.s)
    def test_handler_CSR(self):
        rows=deepcopy(self.sig); rows[0]['insn']='00829073';rows[0]['mem_wmask']='00'
        with self.assertRaises(ValueError): c.observed(rows,self.s)
    def test_postterminal(self):
        with self.assertRaises(ValueError): c.observed([*self.sig,row(order=len(self.sig))],self.s)
    def test_scalar_unknown_skip(self):
        with self.assertRaises(ValueError): c.common.scalar_exact({'skipped_unobservable_register_values':1},self.pre['reference_counts'])
    def test_terminal_and_manifest(self):
        s=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,case=c.preflight.NAME,coverage_admitted=False,admission_performed=False)
        c.terminal(s,{'command':['sealed']},{'command':['sealed']})
        for changed in (dict(s,returncode=1),dict(s,status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED'),dict(s,coverage_admitted=True)):
            with self.assertRaises(ValueError):c.terminal(changed,{}, {})
        with self.assertRaises(ValueError): c.terminal(s,{'command':['wrong']},{'command':['sealed']})
    def test_targets_actual719_fixture(self):
        single=deepcopy(self.before);single['tests']=[str(c.RUN/'code.vdb')]
        hits=c.target_hits(self.before,single,self.pre['targets'])
        self.assertEqual(len(hits),45);self.assertFalse(any(h['hit_single'] for h in hits))
    def test_target_shape_drift(self):
        single=deepcopy(self.before);single['tests']=[str(c.RUN/'code.vdb')]
        t=self.pre['targets'][0];single['metrics'][t['metric']][t['scope']]['checksum']='wrong'
        with self.assertRaises(ValueError):c.target_hits(self.before,single,self.pre['targets'])
    def test_duplicate_vdb(self):
        with self.assertRaises(ValueError):c.target_hits(self.before,self.before,self.pre['targets'])


class VectorTests(unittest.TestCase):
    def setUp(self):
        self.ref=[SimpleNamespace(pc=0x80000000+i*4,instruction=i,vector_writes={i%32:0}) for i in range(33)]
        records=[dict(pc=hex(r.pc),instruction=hex(r.instruction),status='PASS',compared_bytes=128,
                      skipped_unknown_bytes=0,unknown_write_bytes=0,mismatch_count=0,first_mismatch=None) for r in self.ref]
        self.result=dict(status='PASS',compared_instructions=33,skipped_unknown_bytes=0,non_bit_exact_instructions=0,
                         nr_lanes=4,vlen_bits=1024,selected_index=None,stopped_at_spike_index=None,
                         trapped_requests=list(range(24)),first_mismatch=None,unobservable_instructions=0,
                         incomplete_requests=[],unretired_requests=[],instructions=records,compared_bytes=4224)
    def test_full_vector(self):c.vector_exact(self.result,list(range(24)),self.ref)
    def test_vector_missing_trap(self):
        self.result['trapped_requests'].pop()
        with self.assertRaises(ValueError):c.vector_exact(self.result,list(range(24)),self.ref)
    def test_vector_unknown(self):
        self.result['instructions'][0]['unknown_write_bytes']=1
        with self.assertRaises(ValueError):c.vector_exact(self.result,list(range(24)),self.ref)
    def test_vector_missing_init_byte(self):
        self.result['instructions'][31]['compared_bytes']=127
        with self.assertRaises(ValueError):c.vector_exact(self.result,list(range(24)),self.ref)
    def test_vector_wrong_PC(self):
        self.result['instructions'][-1]['pc']='0x0'
        with self.assertRaises(ValueError):c.vector_exact(self.result,list(range(24)),self.ref)


class TracerTests(unittest.TestCase):
    def setUp(self):
        self.s=json.loads((c.runner.PRE/'preflight-manifest.json').read_text())['symbols']
        self.rows=[row(cycle=1)]
        self.text='1ns 1 M 0000000080000000 0 00000013\n'+''.join(
            'Exception @ 51870000, PC: %016x, Cause: Illegal Instruction\ntval: %016x\n'%
            (self.s['gnr_bad_%02d'%n],word) for n,word in enumerate(c.WORDS))
    def test_exact24(self):self.assertEqual(c.tracer_exact(self.text,self.rows,self.s)['illegal_exceptions'],24)
    def test_real_frozen_tracer_time_is_not_PC(self):
        actual=c.TRACER_FIXTURE.read_text()
        events=re.findall(r'Exception @\s*([0-9a-fA-F]+), PC: ([0-9a-fA-F]+), Cause: ([^,\n]+)',actual)
        self.assertEqual(len(events),1)
        self.assertEqual(events[0],('51870000','0000000080002394','Illegal Instruction'))
        self.assertNotEqual(int(events[0][0],16),int(events[0][1],16))
    def test_time_cannot_substitute_PC(self):
        changed=self.text.replace('PC: %016x'%self.s['gnr_bad_00'],'PC: 0000000051870000')
        with self.assertRaises(ValueError):c.tracer_exact(changed,self.rows,self.s)
    def test_missing_exception(self):
        with self.assertRaises(ValueError):c.tracer_exact(self.text.split('Exception @')[0],self.rows,self.s)
    def test_wrong_tval(self):
        with self.assertRaises(ValueError):c.tracer_exact(self.text.replace('%016x'%c.WORDS[-1],'0000000000000000'),self.rows,self.s)
    def test_unknown_tail(self):
        with self.assertRaises(ValueError):c.tracer_exact(self.text+'2ns 2 M 0000000080000004 0 00000013\n',self.rows,self.s)


if __name__=='__main__':unittest.main()
