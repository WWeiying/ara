"""Independent rejection-matrix model and actual Spike-log negative tests."""
from dataclasses import replace
import json
import os
from pathlib import Path
import re
import unittest

import build_narrow_reject_r1_preflight as p


class StaticTests(unittest.TestCase):
    def test_matrix24(self):
        self.assertEqual(len(p.CASES),24)
        self.assertEqual(len({c['word'] for c in p.CASES}),24)
        self.assertEqual([p.vtype(c) for c in p.CASES],[24,0,1,2]*6)

    def test_exact_integer_fields(self):
        for c in p.CASES:
            w=int(c['word'],16)
            self.assertIn(w>>26,(44,45));self.assertEqual(w&127,87)
            self.assertEqual((w>>25)&1,1);self.assertEqual((w>>7)&31,16)
            self.assertIn((w>>12)&7,(0,3,4));self.assertEqual(c['vstart'],1)

    def test_each_case_architecturally_invalid(self):
        for c in p.CASES:
            emul=2*int(c['lmul'][1:]);vs2=(int(c['word'],16)>>20)&31
            self.assertTrue(c['sew']==64 or vs2%emul!=0)
            self.assertEqual(16%int(c['lmul'][1:]),0)

    def test_independent_recovery(self):
        self.assertEqual(p.expected_register(16,True)[:4],bytes((0x56,0x63,0x70,0x7d)))
        self.assertEqual(p.expected_register(16,True)[4:],p.expected_register(16)[4:])
        for r in range(32):
            if r!=16:self.assertEqual(p.expected_register(r,True),p.expected_register(r))

    def test_complete_check_count(self):
        self.assertEqual(p.CHECKS,26*32*18+24*(12+9)+9)

    def test_sealed719_targets(self):
        report=p.life.read_bound(p.REVIEW,p.REVIEW_SEAL)
        self.assertEqual(report['baseline'],719)
        self.assertEqual(len(report['candidates'][0]['zero_targets']),45)

    def test_NO_VCS_interface(self):
        self.assertNotIn('VCS',p.NAME.upper())
        self.assertNotIn('prefix',p.NAME)
        self.assertNotIn('ZCC',str(p.LLVM))


@unittest.skipUnless(os.environ.get('R1_PREFLIGHT'),'Set R1_PREFLIGHT for actual Spike fixture')
class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['R1_PREFLIGHT']).absolute()
        cls.pre=json.loads((cls.out/'preflight-manifest.json').read_text())
        cls.commits=p.shared.parse_spike_commits(cls.out/'spike.trace')
        cls.symbols=cls.pre['symbols'];cls.trace=(cls.out/'spike.trace').read_text()

    def validate(self,commits=None,trace=None):
        return p.validate(self.commits if commits is None else commits,self.symbols,
                          self.trace if trace is None else trace)

    def corrupt(self,name,offset,value):
        c=replace(self.commits[-1],instruction=0x0002b023,vector_writes={},
                  memory_accesses=((self.symbols[name]+offset,value),))
        with self.assertRaises(ValueError):self.validate(commits=self.commits+[c])

    def test_actual_full_replay(self):
        self.assertEqual(self.validate(),self.pre['validation'])

    def test_missing_traps(self):
        with self.assertRaises(ValueError):self.validate(trace='')

    def test_extra_trap(self):
        with self.assertRaises(ValueError):self.validate(trace=self.trace+'exception trap_illegal_instruction, epc 0x80000000\n')

    def test_wrong_trap_PC(self):
        changed=re.sub(r'epc (0x[0-9a-fA-F]+)',lambda m:'epc 0x80000000'
            if int(m[1],16)==self.symbols['gnr_bad_00'] else m[0],self.trace)
        self.assertNotEqual(changed,self.trace)
        with self.assertRaises(ValueError):self.validate(trace=changed)

    def test_fault_retired(self):
        with self.assertRaises(ValueError):self.validate(commits=self.commits+[replace(self.commits[-1],pc=self.symbols['gnr_bad_23'])])

    def test_vrf_extra_write(self):
        with self.assertRaises(ValueError):self.validate(commits=self.commits+[replace(self.commits[-1],vector_writes={31:0})])

    def test_recovery_wrong(self):
        commits=[replace(c,vector_writes={16:0}) if c.pc==self.symbols['gnr_recovery'] else c for c in self.commits]
        with self.assertRaises(ValueError):self.validate(commits=commits)

    def test_trap_vstart(self):self.corrupt('gnr_ledger',40,0)
    def test_post_vstart(self):self.corrupt('gnr_post',23*9*8+32,0)
    def test_handler_saved_t2(self):self.corrupt('gnr_post',16,2)
    def test_sp_preservation(self):self.corrupt('gnr_post',24,0)
    def test_CSR_vtype(self):self.corrupt('gnr_post',48,0)
    def test_last_case_tval(self):self.corrupt('gnr_ledger',(23*12+2)*8,0)
    def test_wrong_guard(self):self.corrupt('gnr_dump',0,0)
    def test_untouched_v31_tail(self):self.corrupt('gnr_dump',((24*32+31)*18+16)*8,0)
    def test_context_restore(self):self.corrupt('gnr_restore',24,1)
    def test_wrong_check_count(self):self.corrupt('g75_result',0,0)

    def test_protected_handler_CSR(self):
        commits=[replace(c,csr_writes={8:0}) if c.pc==self.symbols['gnr_handler'] else c for c in self.commits]
        with self.assertRaises(ValueError):self.validate(commits=commits)

    def test_protected_handler_store(self):
        c=replace(self.commits[-1],pc=self.symbols['gnr_handler']+4,instruction=0x0002b023,
                  memory_accesses=((self.symbols['gnr_post'],0),),vector_writes={})
        with self.assertRaises(ValueError):self.validate(commits=self.commits+[c])

    def test_ELF_word_drift(self):
        blob=bytearray((self.out/'input.elf').read_bytes());pos=blob.find(bytes.fromhex('57088cb2'))
        self.assertGreaterEqual(pos,0);blob[pos]^=1
        with self.assertRaises(ValueError):p.verify_elf(blob,self.symbols)


if __name__=='__main__':unittest.main()
