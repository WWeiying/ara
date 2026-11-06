#!/usr/bin/env python3
"""Host source-contract tests only; no kernel build or numerical acceptance."""
from pathlib import Path
import math
import re
import struct
import unittest

SOURCE = Path(__file__).with_name('decode_rvv.cpp')


def initializer(source, name):
    match = re.search(r'\b'+name+r'\[Parts\]\s*=\s*\{([^}]+)\}', source)
    if not match:
        raise ValueError('Missing schedule initializer')
    return tuple(int(v) for v in match[1].split(','))


def float_bits(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def ordered(value):
    return (~value & 0xffffffff) if value & 0x80000000 else value | 0x80000000


class DecodeRVVSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text()

    def test_actual_decode_schedule_and_shapes(self):
        self.assertEqual(initializer(self.source,'PartK'), (2048,2048,2048,2048,2048,6144,2048))
        self.assertEqual(initializer(self.source,'PartStage'), (0,0,0,1,1,2,3))
        profiles = initializer(self.source,'Profiles')
        self.assertEqual(profiles,(1,2,1,1,1,2,2))
        self.assertEqual((profiles.count(1), profiles.count(2)*128), (4,384))
        self.assertIn('part==0 || part==3 || part==5 || part==6',self.source)
        self.assertIn('N=128, Parts=7, Stages=4',self.source)
        self.assertIn('vlenb!=128',self.source)

    def test_genuine_abi_calls_and_no_custom_accelerator(self):
        self.assertIn('extern "C" {',self.source)
        self.assertIn('void ggml_gemv_q4_K_32x1_q8_K(int, float *, size_t, const void *, const void *, int, int);',self.source)
        self.assertIn('void ggml_vec_dot_q6_K_q8_K(int, float *, size_t, const void *, size_t, const void *, size_t, int);',self.source)
        execute = self.source.split('void execute_dispatch(',1)[1].split('static __attribute__((noinline)) Metrics compare',1)[0]
        self.assertEqual(execute.count('ggml_gemv_q4_K_32x1_q8_K('),1)
        self.assertIn('d->weights, d->activation, 1, N)',execute)
        self.assertIn('for (unsigned row=0; row<N; ++row)',execute)
        self.assertEqual(execute.count('ggml_vec_dot_q6_K_q8_K('),1)
        self.assertIn('weights+row*d->row_bytes, 0, d->activation, 0, 1)',execute)
        for forbidden in ('.word', '.insn', 'qbs_native_', 'qbs_device_', '#include "qbs', '#include <qbs'):
            self.assertNotIn(forbidden,self.source)
        self.assertIn('q4_layout=r32 q6_layout=row_major',self.source)

    def test_original_quantizer_reuse_and_guarded_buffers(self):
        self.assertEqual(self.source.count('quantize_row_q8_K('),2)  # declaration and one actual call site
        self.assertIn('quantize_row_q8_K(inputs[stage],activation[stage]+64,PartK[part])',self.source)
        self.assertIn('activation[Stages][MaxActivation+128]',self.source)
        self.assertIn('output[Parts][N+32]',self.source)
        self.assertIn('out->activation=activation[PartStage[part]]+64',self.source)
        self.assertIn('std::memcmp(activation[stage]+64,packed[stage],bytes)',self.source)
        self.assertIn('raw[64+N*sizeof(float)+i]!=0xa5',self.source)
        self.assertIn('i<sizeof(activation[stage])',self.source)

    def test_timing_excludes_validation_and_all_output_words(self):
        begin = self.source.index('const uint64_t begin=cycle();')
        end = self.source.index('const uint64_t end=cycle();')
        timed = self.source[begin:end]
        self.assertNotIn('printf(',timed)
        self.assertNotIn('compare(',timed)
        self.assertNotIn('memcmp(',timed)
        for token in ('prep[stage]=cycle()-start','prepare_dispatch(part, weights[part], &d)',
                      'execute_dispatch(&d)', 'dispatch[part]=d1-d0; execution[part]=e1-e0'):
            self.assertIn(token,timed)
        self.assertGreater(self.source.index('RVV_DECODE_OUTPUT'),end)
        self.assertIn('for (unsigned idx=0; idx<N; ++idx)',self.source[end:])
        self.assertIn('bits(output[part][16+idx])',self.source[end:])
        self.assertIn('outputs=896',self.source)
        self.assertIn('end-begin<prep_sum+dispatch_sum+execute_sum',self.source)

    def test_numeric_contract_is_tolerance_not_bit_exact(self):
        self.assertIn('Atol=2.0e-3f, Rtol=2.0e-3f',self.source)
        self.assertIn('absolute>Atol+Rtol*magnitude',self.source)
        self.assertIn('!finite_bits(a) || !finite_bits(b)',self.source)
        self.assertIn('independent_rvv_oracle=0',self.source)
        self.assertNotIn('std::memcmp(output',self.source)
        for field in ('bit_differences=%u', 'max_abs_bits=%u','max_rel_bits=%u','max_ulp=%u','mismatches=%u'):
            self.assertIn(field,self.source)

    def test_fp_and_vector_state_are_captured_without_flag_reset(self):
        self.assertEqual(self.source.count('csrwi fcsr,8;csrwi vcsr,5;csrwi vstart,0'),1)
        self.assertIn('((after.fc & 31u) & (before.fc & 31u))==(before.fc & 31u)',self.source)
        self.assertIn('(before.fc & ~31u)==0 && (after.fc & ~31u)==0',self.source)
        self.assertIn('before.vs==0 && after.vs==0',self.source)
        self.assertIn('prep_after[stage].vc!=3u',self.source)
        self.assertIn('before[part].vc!=3u || after[part].vc!=3u',self.source)
        self.assertIn('!same_state(dispatch_before[part],before[part])',self.source)
        for before in range(32):
            for after in range(32):
                preserved = after & before == before
                self.assertEqual(preserved, before | after == after)

    def test_ulp_ordering_including_signed_zero(self):
        values = (-100.,-1.,-0.5,0.5,1.,100.)
        self.assertEqual(sorted(values,key=lambda x:ordered(float_bits(x))),list(values))
        self.assertEqual(ordered(0x3f800001)-ordered(0x3f800000),1)
        self.assertEqual(ordered(0xbf800000)-ordered(0xbf800001),1)
        self.assertIn('actual == 0.0f && expected == 0.0f',self.source)
        for value in (float('inf'),float('-inf'),float('nan')):
            self.assertFalse(math.isfinite(value))
            self.assertEqual(float_bits(value) & 0x7f800000,0x7f800000)


if __name__=='__main__':
    unittest.main()
