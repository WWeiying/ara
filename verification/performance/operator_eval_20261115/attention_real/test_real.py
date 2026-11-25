#!/usr/bin/env python3
"""Bounded host contracts, mutation checks, and genuine capture oracle gates."""
import json
import math
from pathlib import Path
import struct
import unittest

import capture
import check
import check_activity
from contract import HERE, MODES, load, sha
import oracle
import prepare


class RealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets = [capture.read_capture(p) for p in
            (capture.ORIGINAL,*(capture.LONG/x for x in ('qwen3_512','qwen3_1024','llama32_128')))]

    def test_ancestors_stable(self):
        d = json.loads((HERE/'DERIVATION.json').read_text())
        for rel,digest in d['snapshots'].items():
            self.assertEqual(sha(HERE/rel),digest)
        self.assertEqual(sha(HERE/'replay_rotation.S'),d['replay_rotation_sha256'])

    def test_real_context_and_scale(self):
        for (case,data,pins),tokens,d,scale in zip(self.datasets,
                (137,513,1025,129),(128,128,128,64),
                (0x3db504f3,0x3db504f3,0x3db504f3,0x3e000000)):
            self.assertEqual((case['tokens'],case['dimension'],case['scale_bits']),(tokens,d,scale))
            self.assertFalse(case['provenance']['kv_repetition'])
            self.assertEqual(len(data['mask']),2*case['capacity'])
            self.assertEqual(len(data['query']),1024)
            self.assertEqual(len(data['model_golden']),2*d*4)
            self.assertFalse(any('/operator_eval_20261115/attention/' in p for p in pins))
        self.assertEqual(self.datasets[-1][0]['provenance']['captured_gqa'],4)

    def test_exact_full_kv_mapping(self):
        for case,data,_ in self.datasets:
            block = Path(case['provenance']['capture'])/'capture/decode/block'
            d,capacity = case['dimension'],case['capacity']
            for dest,role in (('key','attn_k_input'),('value','attn_v_input')):
                meta = json.loads((block/(role+'-0.json')).read_text())
                raw = (block/(role+'-0.bin')).read_bytes()
                for t in range(capacity):
                    self.assertEqual(data[dest][t*256:t*256+d*2],
                        raw[t*meta['strides'][1]:t*meta['strides'][1]+d*2])
            rawq = (block/'attn_q_input-0.bin').read_bytes()
            meta = json.loads((block/'attn_q_input-0.json').read_text())
            for head in range(2):
                self.assertEqual(data['query'][head*512:head*512+d*4],
                    rawq[head*meta['strides'][2]:head*meta['strides'][2]+d*4])

    def test_all_independent_oracles_and_model_tolerance(self):
        for case,data,_ in self.datasets:
            with self.subTest(case=case['id']):
                result = oracle.reference(case,data)
                comparison = capture.model_error(result['bits'],data['model_golden'])
                self.assertTrue(comparison['all_outputs_within_tolerance'],(case['id'],comparison))
                self.assertEqual(result['expected_fcsr'],result['natural_flags'] | 8)
                self.assertEqual(result['reduction_order_checks'],2*((case['tokens']+63)//64))
                self.assertTrue(all(s['fflags'] in range(32) for s in result['stages']))

    def test_tolerance_rejects_nan_and_bad_values(self):
        self.assertFalse(capture.model_error([0x7fc00000],struct.pack('<f',0.0))['all_outputs_within_tolerance'])
        self.assertFalse(capture.model_error([0x3f800000],struct.pack('<f',0.0))['all_outputs_within_tolerance'])

    def test_scalar_expf_newlib(self):
        for x in (0.0,-0.01,-0.5,-1.0,-3.0,-10.0,-50.0):
            a = oracle.Arithmetic()
            raw = a.expf(oracle.raw32(x))
            self.assertLessEqual(abs(oracle.float32(raw)-math.exp(x)),math.exp(x)*2e-7)
            if x == 0:
                self.assertEqual((raw,a.flags),(0x3f800000,0))
        with self.assertRaisesRegex(ValueError,'outside audited'):
            oracle.Arithmetic().expf(oracle.raw32(-100))

    def test_memory_and_established_distinct(self):
        memory = (HERE/'memory.S').read_text()
        self.assertNotIn('.word',memory)
        self.assertIn('ROW 10',memory)
        self.assertIn('COLUMN v11',memory)
        self.assertIn('ATTN_SCALE',(HERE/'main.c').read_text())
        self.assertNotIn('.scale=0x1.6a09e6p-4f',(HERE/'main.c').read_text())
        self.assertEqual(len(MODES),5)

    def test_native_default_and_replay_signatures(self):
        c = self.datasets[0][0]
        base = dict(case=c,order=[1])
        native,sig = check.expected_work(base)
        default,dsig = check.expected_work(dict(base,order=[3]))
        replay,rsig = check.expected_work(dict(base,order=[4]))
        self.assertEqual(native,default)
        self.assertEqual(sig,dsig)
        self.assertEqual(native,replay)
        self.assertNotEqual(sig,rsig)
        self.assertEqual(rsig.count(0x0205355b),68)
        resident,rs = check.expected_work(dict(base,order=[2]))
        self.assertEqual(len(rs),6)
        self.assertEqual([r['command'] for r in resident],[4,5,5,3])

    def test_all_output_records_mutations(self):
        case = dict(self.datasets[0][0])
        fixture = dict(case=case,order=[0],result=dict(bits=list(range(256)),expected_fcsr=9),
            memory=dict(query_hash=11,guard_hash=12,guard_bytes=13),
            output_hash=14,printed_values=64,data_bytes=15,data_hash=16)
        text = ('OP_ATTN_CALL trial=0 mode=0 d=128 heads=2 kvheads=1 tokens=137 begin=1 returned=2 end=3 '
                'initial_fcsr=8 initial_vcsr=0 initial_vstart=0 fcsr=9 vcsr=0 vstart=0 groups=1 errors=0\n'
                'OP_ATTN_GROUP trial=0 group=0 first_head=0 rows=2 q=40 k=80 v=c0 output=100\n'
                'OP_ATTN_MEMORY trial=0 query_hash=b guard_hash=c guard_bytes=13\n'
                'OP_ATTN_CHECK trial=0 values=256 output_hash=e model_errors=0\n')
        text += ''.join('OP_ATTN_OUT trial=0 index=%d bits=%08x\n' % (i,i) for i in range(64))
        text += 'OP_ATTN_DATA bytes=15 hash=10\nOP_ATTN_DONE calls=1 errors=0\n'
        self.assertEqual(len(check.numerical(text,fixture)),1)
        for before,after in (('output_hash=e','output_hash=f'),('model_errors=0','model_errors=1'),
                ('values=256','values=64'),('bits=00000000','bits=00000001'),
                ('fcsr=9','fcsr=8'),('heads=2','heads=1')):
            with self.assertRaises(ValueError):
                check.numerical(text.replace(before,after),fixture)
        with self.assertRaises(ValueError):
            check.numerical(text+'OP_ATTN_DONE calls=1 errors=0\n',fixture)


if __name__ == '__main__':
    unittest.main()
