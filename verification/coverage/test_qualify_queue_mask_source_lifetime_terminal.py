import copy
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import qualify_queue_mask_source_lifetime_terminal as q

def writes(reg,value,seq,source,eew=0):
    out=[]
    for word in range(4):
        for lane in range(4):
            data=0
            for b in range(8):
                natural=word*32+q.vc._deshuffle_byte(lane*8+b,4,eew)
                data|=(value>>(8*natural)&255)<<(8*b)
            out.append(q.vc.VectorWrite(row=len(out)+seq*100,cycle=seq*100+len(out)+1,
                arch_seq=seq,vid=seq%8,lane=lane,source=source,instruction=0,eew=eew,
                addr=reg*4+word,be=255,data=data,known_be=255))
    return out

class IntegratedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols=q.json.loads((q.runner.PRE/'symbols.json').read_bytes())
        cls.reference=q.reference_prefix()
        cls.mapping={seq:i for seq,i in enumerate(i for i,c in enumerate(cls.reference)
                    if c.instruction&127 in (7,0x27,0x57))}
        cls.activities={};state={}
        for seq,i in cls.mapping.items():
            c=cls.reference[i];ws=[]
            if c.vector_writes:
                producer=4 if c.instruction&127==7 else 2 if c.instruction>>26==26 else 1
                for reg,value in c.vector_writes.items():
                    if producer==2:
                        n=next(n for n in range(8) if c.pc==cls.symbols['qv_pair_'+str(n)]+4)
                        context=q.tail.case_context(n)
                        value=context['active_gold'] | (q.tail.REGISTER_MASK^((1<<context['vl'])-1))
                    state[reg]=value;ws.extend(writes(reg,value,seq,producer))
            elif c.instruction&127==0x27 and c.instruction>>20&31==11:
                ws=writes(8,state[8],seq,3)
            if ws:
                cls.activities[seq]=q.vc.ArchActivity(instruction=c.instruction,allocations=1,completions=1,
                    use_vd=True,vd=c.instruction>>7&31,eew=0,vl=c.vector_vl,vstart=0,writes=ws)
        cls.rows=[]
        for i,c in enumerate(cls.reference):
            values={k:v for k,v in c.gpr_writes.items() if k};rd=next(iter(values),0)
            addr,rm,wm,data=0,0,0,0;access=q.common.scalar_memory(c.instruction)
            if access is not None:
                kind,size=access;addr,value=c.memory_accesses[0];mask=((1<<size)-1)<<(addr&7)
                if kind=='read':rm=mask
                else:wm=mask;data=value
            cls.rows.append(dict(event='retire',order=str(i),pc=hex(c.pc),insn=hex(c.instruction),trap='0',
                rd=str(rd),rd_wdata=hex(values.get(rd,0)),mem_addr=hex(addr),mem_rmask=hex(rm),
                mem_wmask=hex(wm),mem_wdata=hex(data)))
    def evaluate(self,activities=None):
        return q.native_state(self.reference,activities if activities is not None else self.activities,
                              self.mapping,self.symbols)
    def mask(self,a):return next(seq for seq,act in a.items() if act.instruction>>26==26)
    def test_real_reference_native_integration(self):
        r=self.evaluate();self.assertEqual(r['primary_writers'],32)
        self.assertEqual(r['identity_transport_requests'],8);self.assertEqual(r['active_bits_strict'],720)
        self.assertTrue(r['native_prestate_proved'])
    def test_reference_scalar_full_footprint_integration(self):
        r=q.observed(self.rows,self.symbols)
        self.assertEqual(r['strict_memory_bytes'],6912);self.assertEqual(r['csr_values'],24)
    def test_observed_missing_retirement(self):
        with self.assertRaises(ValueError):q.observed(self.rows[:-1],self.symbols)
    def test_observed_bad_opcode(self):
        rows=list(self.rows);rows[0]=dict(rows[0],insn='0x13')
        with self.assertRaises(ValueError):q.observed(rows,self.symbols)
    def test_missing_primary(self):
        a=copy.deepcopy(self.activities);a.pop(next(iter(a)))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_unknown_native_earlier_byte(self):
        a=copy.deepcopy(self.activities);seq=self.mask(a);w=a[seq].writes[0]
        a[seq].writes[0]=q.vc.VectorWrite(**dict(w.__dict__,known_be=0))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_active_corruption(self):
        a=copy.deepcopy(self.activities);seq=self.mask(a);w=a[seq].writes[0]
        a[seq].writes[0]=q.vc.VectorWrite(**dict(w.__dict__,data=w.data^1))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_v9_compare_corruption(self):
        a=copy.deepcopy(self.activities)
        seq=next(s for s,x in a.items() if x.instruction>>26==26 and x.vl==256)
        a[seq].writes.extend(writes(9,0,seq,2))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_native_tail_old1_clear(self):
        a=copy.deepcopy(self.activities);seq=self.mask(a);context=q.tail.case_context(0)
        bit=next(i for i in range(context['vl'],1024) if context['old8']>>i&1)
        value=context['active_gold'] | (q.tail.REGISTER_MASK^((1<<context['vl'])-1))
        a[seq].writes=writes(8,value&~(1<<bit),seq,2)
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_unknown_pc_mapping(self):
        a=copy.deepcopy(self.activities);a[999999]=copy.deepcopy(next(iter(a.values())))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_wrong_producer(self):
        a=copy.deepcopy(self.activities);seq=self.mask(a);w=a[seq].writes[0]
        a[seq].writes[0]=q.vc.VectorWrite(**dict(w.__dict__,source=1))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_missing_completion(self):
        a=copy.deepcopy(self.activities);a[self.mask(a)].completions=0
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_unclassified_transport(self):
        a=copy.deepcopy(self.activities);seq=next(s for s,x in a.items() if x.instruction&127==0x27)
        w=a[seq].writes[0];a[seq].writes[0]=q.vc.VectorWrite(**dict(w.__dict__,source=2))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_identity_transport_tail_corruption(self):
        a=copy.deepcopy(self.activities);seq=next(s for s,x in a.items() if x.instruction&127==0x27)
        w=a[seq].writes[-1];a[seq].writes[-1]=q.vc.VectorWrite(**dict(w.__dict__,data=w.data^1))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_transport_earlier_corruption_cannot_hide_under_final_write(self):
        a=copy.deepcopy(self.activities);seq=next(s for s,x in a.items() if x.instruction&127==0x27)
        w=a[seq].writes[0]
        a[seq].writes.insert(0,q.vc.VectorWrite(**dict(w.__dict__,cycle=w.cycle-1,row=w.row-1,data=w.data^1)))
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_actual_prestate_not_proved(self):
        a=copy.deepcopy(self.activities);seq=self.mask(a)
        a[seq].writes=[q.vc.VectorWrite(**dict(w.__dict__,cycle=0)) for w in a[seq].writes]
        with self.assertRaises(ValueError):self.evaluate(a)
    def test_existing_run_manifest_no_fresh_prepare(self):
        run=q.life.OUT/'queue-mask-source-lifetime-old-image-738-agent-20261006-01'
        record=q.life.read_bound(run.with_name(run.name+'.prepared.json'),
            'b45a190d4441fe9c4573aadad51dcd3a670679ff1281fd2bea76a930e4b31d7c')
        with patch.object(q.runner,'prepare',side_effect=AssertionError('fresh prepare forbidden')):
            self.assertEqual(q.runner.manifest(run),record)

class GateTests(unittest.TestCase):
    def test_collect_rejects_no_terminal_before_trace_reads(self):
        plan=dict(status=q.STATUS,run=str(q.life.OUT/'not-a-live-run-unit'),pins={'test':'sha'},
                  coverage_admitted=False,simulation_started=False)
        with patch.object(q.life,'read_bound',return_value=plan),patch.object(q.life,'check'):
            with self.assertRaises(ValueError):q.collect(Path('/unused'), 'a'*64,q.life.OUT/'not-created')
    def test_terminal_failure(self):
        with self.assertRaises(ValueError):q.terminal(dict(status='SIMULATION_FAILED_OR_TIMEOUT_NOT_ADMITTED'),{}, {}, {})
    def test_uvm_error_rejected(self):
        with self.assertRaises(ValueError):q.logs('UVM_ERROR bad', 'Core Test *** SUCCESS ***',{'requests':1})
    def test_primary_writer_count_cannot_drop(self):
        with self.assertRaises(ValueError):q.native_state([],{}, {},{})
    def lifecycle_fixture(self):
        word=0x8282e857
        def row(event,cycle,seq=0):
            return dict(event=event,cycle=str(cycle),order=str(seq),trans_id='0',port='0',pc='0x80002000',
                        insn=hex(word),trap='0')
        rows=[row('arch_start',1),row('cvx_req',2),row('uop_alloc',3),
              dict(row('cvx_resp',4,-1),pc='0',insn='0'),row('uop_done',5),row('retire',6)]
        def vector(event,cycle):
            return dict(event=event,cycle=str(cycle),arch_seq='0',vid='0',insn=hex(word),nr_lanes='4',
                        vlen_bits='1024',use_vd='1',vd='16',eew='0',vl='16',vstart='0',lane='0')
        vectors=[dict(vector('config',0),arch_seq='-1',vid='-1'),vector('alloc',3),vector('write',4),vector('done',5)]
        return rows,vectors
    def test_complete_SID_lifecycle(self):
        rows,vectors=self.lifecycle_fixture();result=q.lifecycle(rows,vectors)
        self.assertEqual(result['exceptions'],0);self.assertEqual(result['backend_uops'],1)
    def test_native_write_wrong_owner(self):
        rows,vectors=self.lifecycle_fixture();vectors[2]['vid']='1'
        with self.assertRaises(ValueError):q.lifecycle(rows,vectors)
    def test_native_metadata_drift(self):
        rows,vectors=self.lifecycle_fixture();vectors[2]['eew']='1'
        with self.assertRaises(ValueError):q.lifecycle(rows,vectors)

if __name__=='__main__':unittest.main()
