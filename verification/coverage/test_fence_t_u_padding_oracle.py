import copy
from pathlib import Path
import unittest
import fence_t_u_padding_oracle as s


class PaddingTests(unittest.TestCase):
    def trace(self, trap=1, pc=0x80001000):
        return ','.join(s.frozen.FIELDS)+'\n'+f'1,retire,0,0,-1,{pc:016x},00000073,0,0000000000000000,0000000000000000,00,00,0000000000000000,{trap}\n'

    def test_exact_ecall_trap_one_is_preserved(self):
        rows=s.parse_padding_trace(self.trace(),0x80001000)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['trap'],1)
        with self.assertRaises(ValueError):s.frozen.parse_trace(self.trace())

    def test_missing_wrong_duplicate_trap_rejected(self):
        for text in (self.trace(0),self.trace(pc=0x80002000),self.trace()+self.trace().splitlines()[1]+'\n'):
            with self.assertRaises(ValueError):s.parse_padding_trace(text,0x80001000)

    def log(self, ceiling):
        return ('fence_t_gap36_smoke rounds=2 checks=458 failures=0\n'
                f'fence_t_u_padding_successor ceiling={ceiling} padding_witness={int(ceiling>0)}\n'
                'fence_t_u_padding_successor legacy_checks=458 extra_checks=241 failures=0\n'
                'PASSED: fence_t_u_padding_successor\n')

    def test_functional_zero_ceiling_not_cycle_or_native_qualification(self):
        result=s.uart(self.log(0),0x80001000)
        self.assertFalse(result['exact_cycle_proof']);self.assertFalse(result['nonzero_ceil_observed'])
        self.assertTrue(result['native_bitmap_review_required'])

    def test_full_counts_duplicate_pass_and_range_rejection(self):
        s.uart(self.log(100),0x80001000)
        for text in (self.log(100).replace('458','457'),self.log(100).replace('241','240'),
                     self.log(100)+self.log(100),self.log(s.PAD+1)):
            with self.assertRaises(ValueError):s.uart(text,0x80001000)

    def window(self):
        rows=[];q=0
        for cycle in range(s.PAD+8):
            priv=0 if cycle==1 else 3
            priv_q=0 if cycle==2 else 3
            load=int(cycle==2)
            state=2 if cycle==5 else 3 if 6<=cycle<=s.PAD+3 else 4 if cycle==s.PAD+4 else 0
            ceil=s.PAD-q if state==2 and q else 0
            rows.append(dict(cycle=cycle,rst_n=1,priv_q=priv_q,priv=priv,sel=1,pad=s.PAD,
                             q=q,load=load,state=state,drain=15,ceil=ceil))
            q=s.PAD if load else max(0,q-1)
        return rows

    def test_synthetic_model_only_complete_window_and_mutations(self):
        rows=self.window();result=s.counter(rows,2)
        self.assertTrue(result['counter_parity'])
        for mutation in ('missing','q','load','ceil','unknown'):
            bad=copy.deepcopy(rows)
            if mutation=='missing':del bad[4]
            elif mutation=='unknown':bad[4]['q']='X'
            else:bad[5][mutation]+=1
            with self.assertRaises(ValueError):s.counter(bad,2)

    def test_literal_reuse_of_frozen_458_and_third_probe(self):
        root=Path(__file__).resolve().parents[2]
        c=(root/'apps/fence_t_u_padding_successor/main.c').read_text()
        asm=(root/'apps/fence_t_u_padding_successor/probe.S').read_text()
        self.assertIn('#include "../fence_t_gap36_smoke/main.c"',c)
        self.assertIn('#include "../fence_t_gap36_smoke/probe.S"',asm)
        self.assertIn('checks != 458',c);self.assertIn('PROBE 2',asm)
        self.assertEqual(asm.count('    ecall\n'),1)
        self.assertIn('UINT64_C(65536)',c)


if __name__=='__main__':unittest.main()
