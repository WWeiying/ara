import copy
import json
from pathlib import Path
import sys
import unittest
import run_qbs_payload_matrix4_uart as m
sys.path.insert(0,str(m.life.ROOT/'verification/tests'))
import build_qbs_payload_matrix4_uart as builder


class UARTSuccessor(unittest.TestCase):
    def setUp(self):
        self.pre=json.loads((m.PRE/'preflight-manifest.json').read_bytes())

    def test_actual_preflight_and_elf(self):
        m.validate(self.pre)
        self.assertEqual(m.life.digest(m.PRE/'preflight-manifest.json'),m.SEAL)
        meta=json.loads((m.PRE/'dut.metadata.log').read_bytes())[0]
        proof=builder.printf_gate(meta,(m.PRE/(m.NAME+'.elf')).read_bytes())
        self.assertEqual(proof,json.loads((m.PRE/'uart-binding-proof.json').read_bytes()))

    def test_missing_or_tampered_uart_call(self):
        meta=json.loads((m.PRE/'dut.metadata.log').read_bytes())[0]
        elf=(m.PRE/(m.NAME+'.elf')).read_bytes()
        for case in ('symbol','bytes','newlib'):
            bad=copy.deepcopy(meta)
            if case=='symbol':
                for r in bad['Symbols']:
                    if r['Symbol']['Name']['Name']=='printf_':r['Symbol']['Value']+=4
            elif case=='newlib':
                row=copy.deepcopy(bad['Symbols'][0]);row['Symbol']['Name']['Name']='_fstat';bad['Symbols'].append(row)
            with self.assertRaises(ValueError):builder.printf_gate(bad,b'\x00'*len(elf) if case=='bytes' else elf)

    def test_scope_not_reduced(self):
        for key in ('commands','dut_checks','full_vrf_bytes','csr_values','source_readback_bytes','budget_s'):
            bad=copy.deepcopy(self.pre);bad[key]-=1
            with self.assertRaises(ValueError):m.validate(bad)

    def test_original_failed_binary_not_accepted(self):
        with self.assertRaises(ValueError):m.validate(json.loads((m.base.PRE/'preflight-manifest.json').read_bytes()))


if __name__=='__main__':unittest.main()
