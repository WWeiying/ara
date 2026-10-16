import unittest
from pathlib import Path
from reduce_fp_compare import single_trial, with_data_detail, remaining_results, prefix_full_alias


class ComparisonReductionTests(unittest.TestCase):
    def test_exclusion_requires_original_identity(self):
        names=['rvv_fp_compare_one','rvv_fp_compare_two']
        report=dict(inputs=dict(cases=[dict(name=n,sha256=n) for n in names]),
                    results=[dict(name=n,status='failed') for n in names])
        excluded=dict(cases=[dict(original_name=names[0],original_elf_sha256=names[0])])
        self.assertEqual(remaining_results(report,[excluded]),report['results'][1:])
        self.assertEqual(remaining_results(report,[]),report['results'])
        excluded['cases'][0]['original_elf_sha256']='changed'
        with self.assertRaises(ValueError):remaining_results(report,[excluded])
        report['inputs']['cases'].append(report['inputs']['cases'][0])
        with self.assertRaises(ValueError):remaining_results(report,[])

    def setUp(self):
        self.source = (Path(__file__).resolve().parents[1]/'fp_compare_oracle.c').read_text()
        self.fields = dict(seed=0, op=4, vl=2, mask=3, sticky=1)

    def test_preserves_inputs_call_and_entire_oracle(self):
        reduced = single_trial(self.source, self.fields)
        marker = '        for(unsigned i=0;i<128;++i)'
        self.assertEqual(self.source[self.source.index(marker):], reduced[reduced.index(marker):])
        self.assertNotIn('for(unsigned seed=', reduced)
        self.assertEqual(reduced.count('functions[op]('), 1)
        self.assertIn('unsigned start=0;', reduced)
        self.assertIn('unsigned mode=3;', reduced)

    def test_restart_is_retained(self):
        self.assertIn('unsigned start=17;', single_trial(self.source, dict(self.fields, vstart=17)))

    def test_missing_stimulus_rejected(self):
        with self.assertRaises(ValueError):
            single_trial(self.source, {})

    def test_raw_diagnostics_preserve_call_and_oracle(self):
        reduced = single_trial(self.source, self.fields)
        detailed = with_data_detail(reduced)
        call = '        unsigned long status=functions[op](a,b,output+1,vl,cap,mask,start,sticky);\n'
        oracle = '        if((uint32_t)status)++errors;'
        self.assertEqual(detailed.count(call), 1)
        self.assertEqual(reduced[:reduced.index(call)+len(call)],
                         detailed[:detailed.index(call)+len(call)])
        self.assertEqual(reduced[reduced.index(oracle):], detailed[detailed.index(oracle):])
        self.assertIn('RVV_FP_COMPARE_RAW cap=', detailed)
        self.assertIn('d<bytes', detailed)
        self.assertIn('num(output[d+1])', detailed)

    def test_raw_diagnostics_reject_unknown_call(self):
        with self.assertRaises(ValueError):
            with_data_detail('unknown source')

    def test_measured_prefix_retains_loops(self):
        fields = dict(op=0, seed=0, vl=512, mask=0, sticky=1)
        reduced = prefix_full_alias(self.source, fields)
        start = '    unsigned lengths[]='
        end = '        unsigned long status='
        self.assertEqual(self.source[self.source.index(start):self.source.index(end)],
                         reduced[reduced.index(start):reduced.index(end)])
        self.assertIn('if(seed==0 && op==0 && l==6 && mode==0 && sticky==1)goto prefix_done;', reduced)
        self.assertEqual(reduced.count('functions[op]('), 1)
        for bad in (dict(fields, vl=256), dict(fields, sticky=0), dict(fields, vstart=0)):
            with self.assertRaises(ValueError):prefix_full_alias(self.source, bad)


if __name__ == '__main__':
    unittest.main()
