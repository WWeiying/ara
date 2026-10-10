"""721/frozen RTL/static arithmetic and full actual Spike rejection tests; no VCS."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import json
import os
from pathlib import Path
import unittest

import build_memory_emul_r2_preflight as p


class StaticTests(unittest.TestCase):
    def test_check_population(self):self.assertEqual(p.CHECKS,7*32*18+3*21+3*3+3*3+3*18*2+6+1+1)
    def test_original_three_words(self):
        report=p.life.read_bound(p.old.REVIEW,p.old.REVIEW_SEAL)
        self.assertEqual(p.BAD_WORDS,[int(t['word'],16) for t in report['candidates'][1]['tests']])
    def test_legal_vtypes_cannot_underflow(self):
        proof=p.emul_proof();self.assertEqual(len(proof['legal_vtype_memory_combinations']),88)
        self.assertTrue(all(Fraction(t['emul'])>=Fraction(1,8) for t in proof['legal_vtype_memory_combinations']))
    def test_boundaries(self):
        self.assertEqual(Fraction(1)*8/64,Fraction(1,8));self.assertEqual(Fraction(1)*64/8,8)
        self.assertEqual(Fraction(8)*64/8,64)
    def test_vill_not_legal_memory_proof(self):
        self.assertGreater(64,Fraction(1,8)*64)
        self.assertEqual(p.VTYPES,[1<<63,1<<63,3]);self.assertEqual(p.VLS,[0,0,4])
    def test_721_six_targets_and_four_hold(self):
        bits=json.loads((p.BASE/'combined-bits.json').read_text())
        report=p.life.read_bound(p.old.REVIEW,p.old.REVIEW_SEAL)
        targets=p.reconcile(bits,report['candidates'][1]['zero_targets'])
        self.assertEqual(len(targets),6)
        self.assertEqual([(t['metric'],t['point']['raw_index']) for t in targets if t['expected_case']==2],
                         [('line',1308),('branch',362)])
        self.assertEqual(sum(t['scope_status'].startswith('HOLD') for t in targets),4)
    def test_shape_drift_rejected(self):
        bits=json.loads((p.BASE/'combined-bits.json').read_text());targets=json.loads(p.old.REVIEW.read_text())['candidates'][1]['zero_targets']
        bits['metrics']['line'][targets[0]['scope']]['checksum']='bad'
        with self.assertRaises(ValueError):p.reconcile(bits,targets)
    def test_seed_and_recovery_all_bytes(self):
        for phase in range(7):
            for reg in range(32):
                data=p.expected_register(reg,phase)
                self.assertEqual(len(data),128)
                if reg!=8:self.assertEqual(data,p.old.expected_register(reg))
        self.assertEqual(p.expected_register(8,6)[4:32],p.input_bytes(1)[4:32])
        self.assertEqual(p.expected_register(8,6)[:4],p.input_bytes(2)[:4])
        self.assertEqual(p.expected_register(8,6)[32:],p.expected_register(8,0)[32:])
    def test_no_DUT_gold(self):
        text=p.APP.read_text();self.assertIn('gold[r][w]=r1_dump_word(0,r,w+1)',text)
        self.assertNotIn('gold[r][w]=gmr_dump',text)
    def test_no_ZCC(self):self.assertNotIn('ZCC',str(p.LLVM))


@unittest.skipUnless(os.environ.get('R2_PREFLIGHT'),'Set R2_PREFLIGHT for actual complete Spike fixture')
class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['R2_PREFLIGHT']).absolute()
        cls.pre=json.loads((cls.out/'preflight-manifest.json').read_text())
        cls.s=cls.pre['symbols'];cls.trace=(cls.out/'spike.trace').read_text()
        cls.commits=p.old.shared.parse_spike_commits(cls.out/'spike.trace')
    def validate(self,commits=None,trace=None):
        return p.validate(self.commits if commits is None else commits,self.s,self.trace if trace is None else trace)
    def corrupt(self,name,offset,value):
        c=replace(self.commits[-1],instruction=0x0002b023,vector_writes={},memory_accesses=((self.s[name]+offset,value),))
        with self.assertRaises(ValueError):self.validate(commits=[*self.commits,c])
    def test_actual_full_replay(self):self.assertEqual(self.validate(),self.pre['validation'])
    def test_actual_complete_scalar_counts(self):
        self.assertEqual(p.old.strict.reference_counts(self.commits,self.s),self.pre['reference_counts'])
    def test_first_context_vill_not_valid(self):self.corrupt('gmr_cfg',8,24)
    def test_second_context_vl_not_nonzero(self):self.corrupt('gmr_cfg',3*8,1)
    def test_upper_context_vtype(self):self.corrupt('gmr_cfg',7*8,1<<63)
    def test_trap_cause(self):self.corrupt('gmr_ledger',0,4)
    def test_last_trap_tval(self):self.corrupt('gmr_ledger',(2*12+2)*8,0)
    def test_last_trap_PC(self):self.corrupt('gmr_ledger',(2*12+1)*8,self.s['gmr_bad_00'])
    def test_post_vstart(self):self.corrupt('gmr_post',4*8,1)
    def test_handler_saved_t2(self):self.corrupt('gmr_post',2*8,2)
    def test_CSR_restore(self):self.corrupt('gmr_restore',3*8,1)
    def test_guard(self):self.corrupt('gmr_dump',0,0)
    def test_v31_tail_after_all_faults(self):self.corrupt('gmr_dump',((5*32+31)*18+16)*8,0)
    def test_recovery_v8_tail(self):self.corrupt('gmr_dump',((6*32+8)*18+16)*8,0)
    def test_store_guard(self):self.corrupt('gmr_output',(1*18+17)*8,0)
    def test_illegal_store_changed_source(self):self.corrupt('gmr_input',8,0)
    def test_check_count(self):self.corrupt('g75_result',0,0)
    def test_missing_trap(self):
        with self.assertRaises(ValueError):self.validate(trace='')
    def test_extra_trap(self):
        with self.assertRaises(ValueError):self.validate(trace=self.trace+'exception trap_illegal_instruction, epc 0x80000000\n')
    def test_fault_retirement(self):
        with self.assertRaises(ValueError):self.validate(commits=[*self.commits,replace(self.commits[-1],pc=self.s['gmr_bad_02'])])
    def test_illegal_vector_write(self):
        with self.assertRaises(ValueError):self.validate(commits=[*self.commits,replace(self.commits[-1],vector_writes={31:0})])
    def test_protected_handler_CSR(self):
        commits=[replace(c,csr_writes={8:0}) if c.pc==self.s['gmr_handler'] else c for c in self.commits]
        with self.assertRaises(ValueError):self.validate(commits=commits)
    def test_handler_store_footprint(self):
        c=replace(self.commits[-1],pc=self.s['gmr_handler']+4,instruction=0x0002b023,
                  memory_accesses=((self.s['gmr_input'],0),),vector_writes={})
        with self.assertRaises(ValueError):self.validate(commits=[*self.commits,c])
    def test_opcode_drift(self):
        blob=bytearray((self.out/'input.elf').read_bytes());pos=blob.find(bytes.fromhex('27740502'))
        self.assertGreaterEqual(pos,0);blob[pos]^=1
        with self.assertRaises(ValueError):p.verify_elf(blob,self.s)
    def test_host_byte_checksum_independent(self):
        checksum=sum(sum(p.expected_register(r,phase)) for phase in range(7) for r in range(32))
        for n in range(3):
            active=32 if n==1 else 4
            for body in (p.input_bytes(n),p.input_bytes(n)[:active]+b'\xcc'*(128-active)):
                full=b'\xa5'*8+body+b'\xa5'*8
                for word in range(18):checksum^=int.from_bytes(full[word*8:word*8+8],'little')
        self.assertIn('checksum=%d\n'%checksum,(self.out/'host.log').read_text())


if __name__=='__main__':unittest.main()
