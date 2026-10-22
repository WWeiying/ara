"""Strict case-only fault proof; no simulation or global checker mutation."""
from copy import deepcopy
from dataclasses import replace
import unittest

import qualify_sv39_masked_unit_fault_terminal_v2 as m
from ara_verify.spike_trace import SpikeCommit


def fixture():
    insn=m.p.WORDS['smuf_masked_load']
    writes=[]
    for word in range(4):
        for lane in range(4):
            # E8 VRF byte positions use three-bit reversal within each lane.
            data=0
            for byte in range(8):
                reverse=((byte&1)<<2)|(byte&2)|((byte&4)>>2)
                logical=word*32+reverse*4+lane
                value=(m.p.word(1,logical//4,False)>>(8*(logical%4)))&255
                data|=value<<(8*byte)
            writes.append(m.vc.VectorWrite(len(writes),12+word,243,0,lane,3,insn,0,32+word,255,data,255))
    for lane in range(4):
        writes.append(m.vc.VectorWrite(len(writes),22,243,0,lane,4,insn,0,0,0,0,255))
    activity=m.vc.ArchActivity(insn,2,2,True,8,0,17,0,writes)
    def row(event,cycle,vl):
        return dict(event=event,cycle=str(cycle),vl=str(vl),arch_seq='243',vid='0',
                    insn='%08x'%insn,use_vd='1',vd='8',eew='0',vstart='0',nr_lanes='4',vlen_bits='1024')
    rows=[row('alloc',10,128),row('done',16,128),row('alloc',20,17),row('done',24,17)]
    rows += [row('write',w.cycle,128 if w.source==3 else 17) for w in writes]
    return activity,rows


class ProofTests(unittest.TestCase):
    def test_complete_identity(self):
        a,r=fixture(); proof=m.native_identity(a,r)
        self.assertEqual(proof['maintenance_known_bytes'],128)
        self.assertEqual(proof['load_accepted_bytes'],0)
        self.assertIs(proof['zero_write_fault_claimed'],False)

    def reject_write(self,index,**changes):
        a,r=fixture(); a.writes[index]=replace(a.writes[index],**changes)
        with self.assertRaises(ValueError):m.native_identity(a,r)

    def test_accepted_load_byte(self):self.reject_write(16,be=1)
    def test_wrong_identity(self):self.reject_write(0,data=0)
    def test_unknown_identity_byte(self):self.reject_write(0,known_be=254)
    def test_duplicate_byte(self):self.reject_write(1,lane=0)
    def test_extra_source(self):self.reject_write(16,source=5)
    def test_wrong_owner(self):self.reject_write(0,arch_seq=244)
    def test_wrong_register(self):self.reject_write(0,addr=36)
    def test_outside_interval(self):self.reject_write(0,cycle=19)
    def test_missing_write(self):
        a,r=fixture();a.writes.pop()
        with self.assertRaises(ValueError):m.native_identity(a,r)
    def test_extra_native_row(self):
        a,r=fixture();r.append(deepcopy(r[-1]))
        with self.assertRaises(ValueError):m.native_identity(a,r)
    def test_wrong_geometry(self):
        a,r=fixture();r[0]['nr_lanes']='8'
        with self.assertRaises(ValueError):m.native_identity(a,r)
    def test_wrong_uop_vl(self):
        a,r=fixture();r[0]['vl']='17'
        with self.assertRaises(ValueError):m.native_identity(a,r)

    def fault_fixture(self):
        a,r=fixture();proof=m.native_identity(a,r);proof['fault_pc']=0x80002268
        c=SpikeCommit(proof['fault_pc'],a.instruction,{},{},{},{8:0},(),8,'m1',17,0,0,False,False)
        f=dict(pc='0x%016x'%c.pc,instruction='0x%08x'%c.instruction,fault_handler_returned=True,
               invalidated_fault_csrs=[],matched_fault_csrs={'0x341':c.pc,'0x342':13,'0x343':0x40000300})
        return a,c,f,proof

    def test_exact_fault(self):self.assertTrue(m.authorized_fault(*self.fault_fixture()))
    def test_wrong_csr_faults(self):
        for csr,value in [('0x341',0),('0x342',4),('0x343',0)]:
            with self.subTest(csr=csr):
                a,c,f,p=self.fault_fixture();f['matched_fault_csrs'][csr]=value
                self.assertFalse(m.authorized_fault(a,c,f,p))
    def test_wrong_metadata_or_side_effect(self):
        for change in [dict(vector_lmul='m2'),dict(vector_vtype=64),dict(vector_tail_agnostic=True),
                       dict(vector_mask_agnostic=True),dict(vector_vstart=1),dict(vector_vl=16),
                       dict(gpr_writes={1:1}),dict(memory_accesses=((0x1000,0),)),dict(csr_writes={8:1})]:
            with self.subTest(change=change):
                a,c,f,p=self.fault_fixture()
                self.assertFalse(m.authorized_fault(a,replace(c,**change),f,p))
    def test_no_handler_return(self):
        a,c,f,p=self.fault_fixture();f['fault_handler_returned']=False
        self.assertFalse(m.authorized_fault(a,c,f,p))
    def test_activity_tamper(self):
        a,c,f,p=self.fault_fixture();a.writes[0]=replace(a.writes[0],data=0)
        self.assertFalse(m.authorized_fault(a,c,f,p))
    def test_global_predicate_still_cause4_only(self):
        a,c,f,p=self.fault_fixture()
        self.assertFalse(m.vc._known_identity_load_fault(a,c,f))
    def test_seed_default_explicit_equivalence(self):
        for w in range(32):self.assertEqual(m.p.word(1,w),m.p.word(1,w,False))


if __name__=='__main__':unittest.main()
