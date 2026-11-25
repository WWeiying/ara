#!/usr/bin/env python3
"""Bounded host proofs for one real D256 point; synthetic logs are never RTL evidence."""
import argparse
import copy
import io
import json
from pathlib import Path
import unittest
from contract import HERE,OUT,require,save,sha,verify,load
import prepare
import oracle
from arithmetic import Arithmetic,bits
import check

ARCH=None
ROOT_OUT=None


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data,cls.capture_pins=oracle.capture()
        cls.module=load(ARCH/'verification/fpnew_upstream_20261009/oracle.py','d256_test_softfloat')
        cls.ref=oracle.reference(cls.data,cls.module.SoftFloat())

    def test_archive_compatibility_is_numerical_not_rtl(self):
        report=json.loads((ROOT_OUT/'compatibility.json').read_text())
        self.assertEqual(report['state'],'NUMERICAL_SOURCE_IDENTICAL_NOT_RTL_ACCEPTED')
        self.assertEqual(len(report['comparisons']),3)
        self.assertTrue(all(c['identical'] for c in report['comparisons']))
        self.assertFalse(report['old_rtl_pass_reused'])

    def test_one_real_full_shape_original_tolerance(self):
        self.assertEqual(len(self.ref['bits']),1024)
        self.assertEqual(len(bytes.fromhex(self.ref['query_half'])),2048)
        comparison=self.ref['model_comparison']
        self.assertEqual((comparison['atol'],comparison['rtol']),(0.004,0.002))
        self.assertEqual(comparison['failures'],[])
        self.assertLess(comparison['max_tolerance_ratio'],1)
        self.assertEqual((len(self.data['key']),len(self.data['value']),len(self.data['mask'])),(131072,131072,512))

    def test_flags_are_independently_accumulated(self):
        self.assertEqual(self.ref['natural_flags'],3)
        self.assertEqual(self.ref['expected_fcsr'],self.ref['natural_flags']|8)
        self.assertEqual(self.ref['max_update_tokens'],[[0,15],[0],[0],[0,16]])
        self.assertEqual(sum(s['input']==0xff800000 for s in self.ref['expf_samples']),4)
        self.assertEqual(len(self.ref['expf_samples']),6)

    def test_complete_work_no_zero_weight_shortcut(self):
        self.assertEqual((self.ref['qk_fmas'],self.ref['pv_fmas'],self.ref['vector_exp_fmas']),(17408,17408,544))
        self.assertTrue(all(s.get('weight_zero_tokens',0)==0 for s in self.ref['stages']))
        self.assertEqual(len(check.CUSTOM),101)
        self.assertEqual(check.CUSTOM.count(0x0205745b),64)
        self.assertEqual(check.CUSTOM.count(0x0205345b),34)
        self.assertNotIn(0x0605705b,check.CUSTOM)

    def test_scalar_exp_domain_and_flags(self):
        a=Arithmetic(self.module.SoftFloat())
        self.assertEqual(a.expf(0xff800000),0)
        self.assertEqual(a.expf(0),0x3f800000)
        self.assertEqual(a.flags,0)
        for x in (1,-90,float('nan')):
            with self.assertRaises(ValueError):Arithmetic(self.module.SoftFloat()).expf(bits(x))

    def test_modified_mask_is_rejected(self):
        for position in (0,16,17,255):
            d=dict(self.data);raw=bytearray(d['mask']);raw[2*position:2*position+2]=b'\x00\x3c';d['mask']=bytes(raw)
            with self.assertRaises(ValueError):oracle.reference(d,self.module.SoftFloat())

    def test_never_relabel_invalid_model_gold(self):
        d=dict(self.data,model=bytes(4096))
        with self.assertRaisesRegex(ValueError,'original model tolerance'):oracle.reference(d,self.module.SoftFloat())

    def fixture(self):
        return dict(reference=dict(result=self.ref),memory=dict(query_hash=123,data_bytes=1,data_hash=2),
                    modes=['same_schedule_memory_rvv','current_sdk_segmented_akv'])

    def log(self,m):
        lines=[];ref=m['reference']['result']
        for t in range(2):
            lines.append(f'D256_CALL trial={t} begin={100*t+1} end={100*t+2} groups=1 status=0 initial_fcsr=8 initial_vcsr=5 initial_vstart=0 fcsr={ref["expected_fcsr"]} vcsr=5 vstart=0 errors=0 model_errors=0 hash={ref["output_hash"]:x} query_hash=7b guards=0')
            lines.append(f'D256_PLAN trial={t} segments=2 logical=256 physical=128 offset=0 count=128 rows=4 tokens=17 q=1000 qh=1100 k=2000 kh=2100 v=3000 vh=3100 qs=512 ks=512 vs=512')
            lines += [f'D256_OUT trial={t} index={i} bits={b:08x}' for i,b in enumerate(ref['bits'][:64])]
        lines+=['D256_DATA bytes=1 hash=2','D256_DONE calls=2 errors=0']
        return '\n'.join(lines)

    def test_numerical_full_records(self):
        m=self.fixture();self.assertEqual(len(check.numerical(self.log(m),m)),2)

    def test_numerical_state_mapping_mutations(self):
        m=self.fixture();text=self.log(m)
        for a,b in (('logical=256','logical=128'),('qh=1100','qh=1200'),('segments=2','segments=1'),
            ('tokens=17','tokens=16'),('vcsr=5','vcsr=0'),('vstart=0','vstart=1'),
            ('model_errors=0','model_errors=1'),('guards=0','guards=1'),('fcsr=11','fcsr=3'),
            ('query_hash=7b','query_hash=7c'),('errors=0','errors=1')):
            with self.subTest(mutation=a),self.assertRaises(ValueError):check.numerical(text.replace(a,b,1),m)
        with self.assertRaises(ValueError):check.numerical(text+'\nD256_DONE calls=2 errors=0',m)

    def test_native_activity_complete_and_no_resident(self):
        rows=[]
        for t in range(2):
            for lane in range(4):
                count=9632 if lane==0 else 8576
                r=dict(cycles=10000,native_requests=count,native_fma_requests=count//2,
                    native_fma_elements=count,qk_requests=0,qk_elements=0,pv_requests=0,pv_elements=0,
                    native_blocked=0,resident_blocked=0)
                rows.append('OPERATOR_UNIT ara_tb.dut.gen_lanes[%d].i_operator_unit_activity '%lane+
                    ' '.join(k+'='+str(v) for k,v in r.items()))
        text='\n'.join(rows);self.assertEqual([r['native_fma_elements'] for r in check.activity(text)],[35360,35360])
        for a,b in (('native_fma_elements=9632','native_fma_elements=9631'),('pv_elements=0','pv_elements=1'),
                    ('gen_lanes[1]','gen_lanes[0]')):
            with self.assertRaises(ValueError):check.activity(text.replace(a,b,1))
        with self.assertRaises(ValueError):check.activity('\n'.join(rows[1:]))


def main():
    global ARCH,ROOT_OUT
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.absolute()
    require(out==out.resolve() and out.parent==OUT.resolve() and
        out.name.startswith('operator_d256_prepare_20261115_') and not out.exists(),'Fresh owned host-test output')
    out.mkdir();ROOT_OUT=out;ARCH=prepare.sources(out)
    pins={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
    pins.update({str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    stream=io.StringIO();r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    (out/'host-tests.log').write_text(stream.getvalue());verify(pins)
    pins.update(Tests.capture_pins);pins[str(Tests.module.LIB)]=sha(Tests.module.LIB)
    save(out/'source-pins.json',pins)
    report=dict(state='HOST_TEST_PASS_NOT_RTL' if r.wasSuccessful() else 'FAIL',tests_run=r.testsRun,
        failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),post_pins_match=True,
        source_pins_sha256=sha(out/'source-pins.json'),log_sha256=sha(out/'host-tests.log'),
        rtl_executed=False,original_model_tolerance=Tests.ref['model_comparison'],
        natural_flags=Tests.ref['natural_flags'],expected_fcsr=Tests.ref['expected_fcsr'])
    save(out/'result.json',report);print(stream.getvalue());print(json.dumps(report),flush=True)
    return not r.wasSuccessful()


if __name__=='__main__':raise SystemExit(main())
