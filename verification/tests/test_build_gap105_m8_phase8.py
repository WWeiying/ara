import copy
import json
import unittest

import build_gap105_m8_phase8 as b


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.static = json.loads(b.STATIC.read_bytes())
        self.oracle = dict(scope='host-reference-only',independent_native_decode=True,
            m8_packing_checked=True,m=8,n=1,fflags=0,custom_instruction_execution_prechecked=False,
            expected_bits=self.static['expected_bits'],integer_dot=[256*c for c in range(1,9)],
            integer_correction=[0]*8,activation_hex='00'*2336)

    def test_oracle_contract(self):
        b.oracle_check(self.oracle,self.static)

    def test_wrong_output_dot_or_flags_rejected(self):
        for key,value in [('expected_bits',[0]*8),('integer_dot',[0]*8),('fflags',1),
                          ('m',4),('m8_packing_checked',False),('activation_hex','00'*1168)]:
            oracle = copy.deepcopy(self.oracle); oracle[key] = value
            with self.assertRaises(ValueError):
                b.oracle_check(oracle,self.static)

    def test_exact_two_phase_contract(self):
        contract = (b.APP/'contract.h').read_text()
        source = (b.APP/'main.c').read_text()
        asm = (b.APP/'execute.S').read_text()
        self.assertIn('#define GAP105_COMMANDS 2u',contract)
        self.assertIn('c->activation_skew == 4 + 4 * current',source)
        self.assertIn('((uintptr_t)ap & 15) == c->activation_skew',source)
        self.assertIn('c->m == 8 && c->n == 1',source)
        self.assertIn('MATRIX_EXEC 0, 1, 0x0eb5045b',asm)
        self.assertIn('MATRIX_EXEC 1, 1, 0x0eb5045b',asm)

    def test_full_inspection_and_preservation_contract(self):
        source = (b.APP/'main.c').read_text()
        for token in ('complete v0..v31 image','complete initial VRF source image',
                      'initial six CSRs','immediate six CSRs/flags','all weight/source guards',
                      'all activation/source guards','all descriptor/source guards',
                      'source_bytes == 6880','const unsigned required = 41'):
            self.assertIn(token,source)
        self.assertIn('if (c->m < QBS_WIDE_M_MIN)',source)


if __name__ == '__main__':
    unittest.main()
