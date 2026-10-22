"""Scalar encoding negatives and fresh actual Spike preflight replay."""
from dataclasses import replace
import json
import unittest

import preflight_dtlb_permissions_scalar779 as pre

FIXTURE=pre.p.OUT/'dtlb-permissions-preflight779-agent-20261008-04'


class Encoding(unittest.TestCase):
    def test_scalar_and_compressed(self):
        result=pre.scalar_isa_evidence('80000000: 30051073 csrw mstatus,a0\n80000004: a001 j 80000004\n')
        self.assertEqual(result['decoded_instructions'],2)

    def test_disguised_op_v(self):
        with self.assertRaisesRegex(ValueError,'OP-V'):
            pre.scalar_isa_evidence('80000000: 00000057 unknown\n')

    def test_vector_memory_encodings(self):
        for opcode in (0x07,0x27):
            for funct3 in (0,4,5,6,7):
                with self.subTest(opcode=opcode,funct3=funct3), self.assertRaises(ValueError):
                    pre.scalar_isa_evidence(f'80000000: {opcode|(funct3<<12):08x} unknown\n')

    def test_scalar_fp_width_not_vector(self):
        for opcode in (0x07,0x27):
            for funct3 in (1,2,3):
                pre.scalar_isa_evidence(f'80000000: {opcode|(funct3<<12):08x} scalar\n')

    def test_mnemonic_and_empty_rejected(self):
        for text in ('','80000000: 00000013 vmv.v.i\n'):
            with self.assertRaises(ValueError): pre.scalar_isa_evidence(text)

    def test_truncated_encoding(self):
        with self.assertRaises(ValueError): pre.scalar_isa_evidence('80000000: 0057 unknown\n')


class Actual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=json.loads((FIXTURE/'preflight.json').read_bytes())
        pre.p.life.check(cls.report['input_pins']); pre.p.life.check(cls.report['output_pins'])
        cls.commits=pre.parse_spike_commits(FIXTURE/'spike.trace')
        cls.s=cls.report['symbols']

    def test_exact_preflight(self):
        self.assertEqual(pre.validate(self.commits,self.s),self.report['counts'])

    def test_command_and_encoding(self):
        command=json.loads((FIXTURE/'compile-command.json').read_bytes())
        self.assertEqual([x for x in command if x.startswith('-march=')],['-march=rv64gc_zfh'])
        self.assertEqual(command.count('-fno-vectorize'),1)
        self.assertEqual(command.count('-fno-slp-vectorize'),1)
        self.assertIn('-mabi=lp64d',command)
        spike=json.loads((FIXTURE/'spike-command.json').read_bytes())
        self.assertIn('--isa=rv64gcv_zfh_zvfh_zvl1024b',spike)
        self.assertEqual(pre.scalar_isa_evidence((FIXTURE/'disassembly.txt').read_text()),
                         self.report['scalar_isa_evidence'])

    def test_handler_clobbers_and_resume(self):
        handler=[c for c in self.commits if self.s['dpa_handler_begin']<=c.pc<self.s['dpa_handler_end']]
        self.assertTrue(handler)
        self.assertTrue(all(set(c.gpr_writes)<=set((5,6,7)) for c in handler))
        self.assertEqual([c.csr_writes[0x341] for c in handler if 0x341 in c.csr_writes],
            [self.s[x]+4 for x in ('dpa_load','dpa_load','dpa_store','dpa_load','dpa_store')])

    def test_corrupted_trap_golden(self):
        commits=list(self.commits); address=self.s['dpa_probe']+64+32
        i=max(i for i,c in enumerate(commits) if any(a==address and v is not None for a,v in c.memory_accesses))
        commits[i]=replace(commits[i],memory_accesses=tuple((a,v^1 if a==address else v)
                                                           for a,v in commits[i].memory_accesses))
        with self.assertRaises(ValueError): pre.validate(commits,self.s)

    def test_missing_mprv_restore(self):
        commits=list(self.commits)
        i=next(i for i,c in enumerate(commits) if c.pc==self.s['dpa_disable'])
        del commits[i]
        with self.assertRaises(ValueError): pre.validate(commits,self.s)


if __name__=='__main__': unittest.main()
