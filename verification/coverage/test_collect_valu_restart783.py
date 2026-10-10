import copy
import unittest
from types import SimpleNamespace

import collect_valu_restart783 as c


def target(n):
    return dict(vd='8',eew='0',vl='1024',use_vd='1',vstart=str(c.gold.STARTS[n]))


def actual(n):
    state=c.gold.gold()[n][1]
    return {(8+i//128,i%128):((state[(8+i//128)*16+(i%128)//8]>>(8*(i%8)))&255,None)
        for i in range(c.gold.STARTS[n],1024)}


def lifecycle_fixture():
    rows=[];vectors=[]
    for n in range(12):
        base=10*n;insn=hex(c.gold.OPCODE)
        common=dict(order=str(n),trans_id='0',pc='80000000',insn=insn,trap='0',port='0')
        for event,offset in [('arch_start',0),('cvx_req',1),('uop_alloc',2),('uop_done',4),('cvx_resp',5)]:
            r=dict(common,event=event,cycle=str(base+offset))
            if event=='cvx_resp':r.update(order='-1',pc='0',insn='0')
            rows.append(r)
        v=dict(target(n),nr_lanes='4',vlen_bits='1024',arch_seq=str(n),vid='0',insn=insn,lane='0',source='0')
        for event,offset in [('alloc',2),('write',3),('done',4)]:vectors.append(dict(v,event=event,cycle=str(base+offset)))
    return rows,vectors


class CollectorTests(unittest.TestCase):
    def test_actual783_target_gain_deduplicates_suffix(self):
        pre=c.life.read_bound(c.run.PRE,c.run.PRE_SHA)
        native=next((c.Path(pre['baseline']['appended_vdb'])/'snps/coverage/db/testdata').iterdir())
        gain,pins=c.target_gain(native,pre)
        self.assertEqual(gain['actual_new_target_coordinates'],0)
        self.assertEqual(len(gain['targets']),45)
        self.assertFalse(gain['official_percentage'])
        c.life.check(pins)

    def test_full_scalar_CSR_memory_negatives(self):
        instructions=[0x00000097,0xc2002173,0x0020b023]
        regs=[{1:0x80001000},{2:1},{}]
        reference=[SimpleNamespace(pc=0x80001000+4*n,instruction=word,gpr_writes=regs[n],
            fpr_writes={},memory_accesses=((0x80001000,1),) if n==2 else ())
            for n,word in enumerate(instructions)]
        rows=[dict(event='retire',order=str(n),trap='0',pc=hex(ref.pc),insn=hex(ref.instruction),
            rd=str(next(iter(ref.gpr_writes),0)),rd_wdata=hex(next(iter(ref.gpr_writes.values()),0)),
            mem_addr=hex(0x80001000 if n==2 else 0),mem_wmask='ff' if n==2 else '0',
            mem_rmask='0',mem_wdata='1' if n==2 else '0') for n,ref in enumerate(reference)]
        c.mature.scalar_check(rows,reference,{'tohost':0x80001000})
        for n,key,value in [(1,'rd_wdata','2'),(2,'mem_addr','80001008'),(2,'mem_wmask','f'),
            (2,'mem_wdata','2'),(1,'trap','1'),(1,'pc','80002000')]:
            q=copy.deepcopy(rows);q[n][key]=value
            with self.subTest(key=key),self.assertRaises(Exception):c.mature.scalar_check(q,reference,{'tohost':0x80001000})

    def test_lastdrain_exact_negatives(self):
        text='\n'.join((
            '[ARA_CONTRACT_TRACE] sample=pre_edge cycle=15 req=1/1 fire=1 id=2 insn=030c0457 resp=0/1 fire=0 id=0 exc=0 pending=00 stalled=00 errors=0000000',
            '[ARA_CONTRACT_TRACE] sample=pre_edge cycle=25 req=0/1 fire=0 id=0 insn=00000000 resp=1/1 fire=1 id=2 exc=0 pending=04 stalled=00 errors=0000000'))
        req=[(10,2,c.gold.OPCODE)];resp=[(20,2)]
        self.assertEqual(c.mature.protocol(text,req,resp,30)['last']['after'],0)
        for bad in (text.replace('pending=04','pending=00'),text.replace('errors=0000000','errors=0000001'),
            text.splitlines()[0],text.replace('cycle=25','cycle=24'),text.replace('id=2 insn','id=3 insn')):
            with self.assertRaises(Exception):c.mature.protocol(bad,req,resp,30)

    def test_terminal_strict(self):
        s=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False);c.terminal(s)
        for key,value in [('returncode',False),('returncode','0'),('returncode',1),('timeout',True)]:
            q=dict(s);q[key]=value
            with self.assertRaises(Exception):c.terminal(q)

    def test_metadata(self):
        targets=[target(n) for n in range(12)];c.target_metadata(targets)
        for key,value in [('vd','16'),('eew','1'),('vl','1020'),('vstart','0'),('use_vd','0')]:
            q=copy.deepcopy(targets);q[0][key]=value
            with self.subTest(key=key),self.assertRaises(Exception):c.target_metadata(q)
        with self.assertRaises(Exception):c.target_metadata(targets[:-1])

    def test_independent_bytes_all12(self):
        self.assertEqual([c.target_bytes(actual(n),n)['defined_bytes'] for n in range(12)],
            [4]*4+[1024]*4+[4]*4)

    def test_wrong_byte_extent_and_data(self):
        for change in ('missing','prefix','foreign','data','unknown'):
            q=actual(0);key=next(iter(q))
            if change=='missing':q.pop(key)
            elif change=='prefix':q[8,0]=(0,None)
            elif change=='foreign':q[16,0]=(0,None)
            elif change=='data':q[key]=(q[key][0]^1,None)
            else:q[key]=(None,None)
            with self.subTest(change=change),self.assertRaises(Exception):c.target_bytes(q,0)

    def test_lifetimes(self):
        rows,vectors=lifecycle_fixture();control,req,resp=c.lifecycle(rows,vectors)
        self.assertEqual(control,dict(requests=12,responses=12,backend_uops=12))
        self.assertEqual(len(req),len(resp))

    def test_lifetime_negatives(self):
        for change in ('missing_done','duplicate_alloc','write_after_done','wrong_owner','metadata','unknown_event'):
            rows,vectors=lifecycle_fixture()
            if change=='missing_done':rows=[r for r in rows if not(r['event']=='uop_done' and r['order']=='0')]
            elif change=='duplicate_alloc':vectors.insert(1,dict(vectors[0]))
            elif change=='write_after_done':vectors[1]['cycle']='5'
            elif change=='wrong_owner':vectors[1]['arch_seq']='1'
            elif change=='metadata':vectors[1]['eew']='2'
            else:rows[0]['event']='foreign'
            with self.subTest(change=change),self.assertRaises(Exception):c.lifecycle(rows,vectors)

    def test_vector_unknown_gate(self):
        q=dict(status='PASS',skipped_unknown_bytes=0,non_bit_exact_instructions=0,
            unobservable_instructions=0,incomplete_requests=[],unretired_requests=[],trapped_requests=[],instructions=[])
        c.vector_gate(q)
        for key,value in [('skipped_unknown_bytes',1),('unobservable_instructions',1),
            ('non_bit_exact_instructions',False),('trapped_requests',[1])]:
            v=dict(q);v[key]=value
            with self.assertRaises(Exception):c.vector_gate(v)

    def test_actual_spike_snapshot_memory_oracle(self):
        pre=c.life.read_bound(c.run.PRE,c.run.PRE_SHA)
        commits=c.shared.spike_trace.parse_spike_commits(c.gold.OUT/'spike.trace')
        memory,audit=c.gold.memory_bytes(commits,pre['symbols'])
        self.assertEqual(audit['whole_register_store_bytes'],98304)
        reads=set(memory)
        c.memory_oracle(memory,reads,pre['symbols'])
        address=pre['symbols']['vr_snap']+64
        for change in ('wrong_data','missing_byte','missing_read','source','CSR'):
            m=dict(memory);r=set(reads)
            if change=='wrong_data':m[address]^=1
            elif change=='missing_byte':m.pop(address)
            elif change=='missing_read':r.remove(address)
            elif change=='source':m[pre['symbols']['vr_source']+64]^=1
            else:m[pre['symbols']['vr_csr']]^=1
            with self.subTest(change=change),self.assertRaises(Exception):c.memory_oracle(m,r,pre['symbols'])


if __name__=='__main__':unittest.main()
