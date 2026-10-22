"""Read-only negatives against sealed agent software execution; no simulator."""
from dataclasses import replace
import json
import struct
import unittest
import build_narrow_clip_reject_preflight as m

FIXTURE=m.OUT/'narrow-clip-reject-preflight-737-agent-20261006-01'
SEAL='f0fc1ee53df6af7c7a1b78df9ff2aa5bb4655dc2c805268dcce32606a3b7576e'


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=m.life.read_bound(FIXTURE/'preflight-manifest.json',SEAL)
        cls.symbols=cls.pre['symbols'];cls.trace=(FIXTURE/'spike.trace').read_text()
        cls.commits=m.frozen.shared.parse_spike_commits(FIXTURE/'spike.trace')
        cls.blob=(FIXTURE/'input.elf').read_bytes()

    def validate(self,commits=None,trace=None):
        return m.validate(self.commits if commits is None else commits,self.symbols,self.trace if trace is None else trace)

    def corrupt(self,name,offset,value):
        extra=replace(self.commits[-1],instruction=0x0002b023,gpr_writes={},fpr_writes={},vector_writes={},csr_writes={},
                      memory_accesses=((self.symbols[name]+offset,value),))
        return self.commits+[extra]

    def test_actual_full_trace_and_ELF(self):
        self.assertEqual(self.validate(),self.pre['validation'])
        self.assertEqual(m.frozen.strict.reference_counts(self.commits,self.symbols),self.pre['reference_counts'])
        m.verify_elf(self.blob,self.symbols)

    def test_wrong_cause_or_extra_trap(self):
        with self.assertRaises(ValueError):self.validate(trace=self.trace.replace('trap_illegal_instruction','trap_load_page_fault',1))
        with self.assertRaises(ValueError):self.validate(trace=self.trace+'\nexception trap_illegal_instruction, epc 0x80000000\n')

    def test_missing_terminal(self):
        commits=[replace(c,memory_accesses=()) if (self.symbols['tohost'],1) in c.memory_accesses else c for c in self.commits]
        with self.assertRaises(ValueError):self.validate(commits)

    def test_wrong_tval_or_vstart_CSR(self):
        for name,offset in [('gnr_ledger',16),('gnr_ledger',40),('gnr_post',32)]:
            with self.subTest(name=name,offset=offset),self.assertRaises(ValueError):self.validate(self.corrupt(name,offset,0))

    def test_fullVRF_guard_corruption(self):
        for offset in [0,8,(32*18+16*18+1)*8]:
            with self.subTest(offset=offset),self.assertRaises(ValueError):self.validate(self.corrupt('gnr_dump',offset,0))

    def test_unexpected_vector_writer(self):
        commits=self.commits+[replace(self.commits[-1],gpr_writes={},fpr_writes={},memory_accesses=(),
                                       vector_writes={16:0})]
        with self.assertRaises(ValueError):self.validate(commits)

    def test_wrong_ELF_header_type_not_rewritten(self):
        blob=bytearray(self.blob);struct.pack_into('<H',blob,16,18)
        with self.assertRaises(ValueError):m.verify_elf(bytes(blob),self.symbols)

    def test_duplicate_faultPC(self):
        symbols=dict(self.symbols);symbols['gnr_bad_01']=symbols['gnr_bad_00']
        with self.assertRaises(ValueError):m.verify_elf(self.blob,symbols)


if __name__=='__main__':unittest.main()
