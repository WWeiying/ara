#!/usr/bin/env python3
import argparse
from pathlib import Path
import unittest

import oracle as o
import prepare as p


class ContractTests(unittest.TestCase):
    def test_sample_set_is_exact(self):
        request = {('expf',0)}
        good = [dict(function='expf',input=0,output=o.ONE,fflags=0)]
        self.assertEqual(o.sample_table(request,good),{('expf',0):(o.ONE,0)})
        bad = [[],good*2,[{**good[0],'extra':0}], [{**good[0],'input':1}],
               [{**good[0],'function':'sin'}],[{**good[0],'fflags':32}],
               [{**good[0],'input':False}],[{**good[0],'output':-1}]]
        for rows in bad:
            with self.assertRaises(ValueError): o.sample_table(request,rows)

    def test_strict_json(self):
        for raw in ('{"a":1,"a":2}','{"a":NaN}','{"a":Infinity}','{"a":-Infinity}','{'):
            with self.assertRaises(ValueError): p.strict_json(raw)

    def test_probe_store_protocol(self):
        trace = 'mem 0x1000 0x3f800000\nmem 0x1004 0x00000000\n'
        self.assertEqual(p.parse_results(trace,0x1000,1),[(o.ONE,0)])
        for bad in (trace.splitlines()[0],trace+trace,trace.replace('1004','1005'),
                    trace.replace('3f800000','100000000')):
            with self.assertRaises(ValueError): p.parse_results(bad,0x1000,1)

    def test_early_returns_and_flags(self):
        for row,flags in zip(o.directed()[-3:],(0,5,0)):
            a = o.Arithmetic(CTX)
            value = o.transform(a,row['dot'],row['scale'],row['mask'],row['head'],row['index'],row['features'])
            self.assertEqual((value,a.flags),(o.NEG_INF,flags))
            self.assertFalse(a.used)

    def test_missing_sample_fails_closed(self):
        with self.assertRaisesRegex(ValueError,'Missing target libm'):
            o.Arithmetic(CTX).libm('expf',0)

    def test_exact_f64_tree_f32_halfway(self):
        a = o.Arithmetic(CTX)
        result = a.sum_scores([0x3eb1a29c,0x3e27c38c,0x3f212774,0x3f800000,0x3e982017],0x3edb9a73)
        self.assertEqual(result,0x403771ba)
        self.assertEqual(a.flags,1)  # Final F32 tie rounds; no seeded NX masks it.

    def test_group_local_mapping(self):
        for h in range(6):
            f,local = o.local_features(o.GROUPED,h)
            self.assertEqual(local,h%3)
            self.assertEqual(f,o.GROUPED['features'][h//3])
        self.assertNotEqual(o.GROUPED['features'][0],o.GROUPED['features'][1])
        self.assertEqual([(g,base,min(2,3-base)) for g in range(2) for base in (0,2)],
                         [(0,0,2),(0,2,1),(1,0,2),(1,2,1)])

    def test_finite_tail_controls(self):
        for case in o.TAILS:
            scores = [o.transform(o.Arithmetic(CTX),o.ONE,o.ONE,0,0,t,case['features']) for t in range(65)]
            if 'excluded_first' in case['name']:
                self.assertTrue(all(v == o.NEG_INF for v in scores[:64]))
                self.assertNotEqual(scores[64],o.NEG_INF)
            else:
                self.assertTrue(all(v != o.NEG_INF for v in scores[:64]))
                self.assertEqual(scores[64],o.NEG_INF)

    def test_clean_target_samples_and_directed(self):
        receipt = p.strict_json((RECEIPT/'target-libm.json').read_text())
        rows = receipt['samples']
        table = o.sample_table({(r['function'],r['input']) for r in rows},rows)
        self.assertEqual(table[('expf',0)],(o.ONE,0))
        self.assertTrue(any(name == 'expf' and arg != 0 for name,arg in table))
        self.assertFalse(receipt['host_libm_used'])
        self.assertTrue(all(probe['clean_fcsr'] for probe in receipt['probes']))

    def test_fixture_contract(self):
        record = p.strict_json((RECEIPT/'oracle.json').read_text())
        self.assertEqual([r['case'] for r in record['cases']],list(o.CASES))
        self.assertTrue(record['query_conversion_outside_roi'])
        self.assertEqual(record['initial_fflags_cases'],[0,8])
        self.assertFalse(record['full_call_target_executed'])
        for row in record['cases']:
            self.assertEqual(len(row['expected']['bits']),row['case']['heads']*row['case']['dimension'])
            self.assertLessEqual(row['expected']['fflags'],31)
        grouped = record['cases'][-1]['expected']
        self.assertEqual(sum(x['phase'][0] == 'PV' for x in grouped['phases']),6)

    def test_baseline_build_contract(self):
        contract = p.strict_json((RECEIPT/'build-contract.json').read_text())
        self.assertEqual(contract['performance_order'],[0,1,1,0])
        self.assertEqual(contract['getenv'],{'AKV_PAIR_HEADS':'1'})
        self.assertEqual(contract['rotation_selected'],1)
        self.assertTrue(contract['requires_retired_rotation_body'])
        self.assertTrue(contract['requires_candidate_wrapper_bypass'])
        self.assertEqual(contract['fallback_case']['actual_frm'],1)
        self.assertEqual(contract['fallback_case']['options_frm'],0)
        self.assertEqual(contract['link_flags'],['-Wl,--wrap=akv_experimental_pv_f16_pair'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--receipt',type=Path,required=True)
    args = parser.parse_args()
    CTX, RECEIPT = o.Context(args.inputs), args.receipt
    unittest.main(argv=['test_oracle.py'],verbosity=2)
