#!/usr/bin/env python3
"""Bounded host oracle/parser/mutation tests. Synthetic logs are not RTL evidence."""
import argparse
import copy
import io
import json
from pathlib import Path
import unittest
from contract import HERE,OUT,NARROW,WIDE,require,save,sha,verify
import prepare
import oracle
import generate
import check

ARCH=None


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.integer=oracle.integer_cases(ARCH)
        cls.floating,cls.module=oracle.float_cases(ARCH)
        cls.handoff=oracle.handoff_reference(cls.module)

    def test_fixed_integer_scope(self):
        self.assertEqual(len(self.integer),52)
        self.assertEqual({c['op'] for c in self.integer},set(NARROW+WIDE))
        self.assertEqual({c['sew'] for c in self.integer if c['op'] in WIDE},{8,16,32})
        self.assertEqual({c['sew'] for c in self.integer if c['op'] not in WIDE},{8,16,32,64})
        self.assertEqual(sum(c['masked'] for c in self.integer),2)

    def test_signed_high_boundaries(self):
        for w in (8,16,32,64):
            m=(1<<w)-1
            self.assertEqual(oracle.integer('vmulh',w,m,2,0),m)
            self.assertEqual(oracle.integer('vmulhu',w,m,2,0),1)
            self.assertEqual(oracle.integer('vmulhsu',w,m,2,0),m)
            self.assertEqual(oracle.integer('vmulh',w,1<<(w-1),m,0),0)

    def test_gold_is_independently_recomputed(self):
        for c in self.integer+self.floating[:3]:
            if not c['masked']:self.assertEqual(c['gold'],c['reviewed_gold'])

    def test_float_formats_flags_and_scope(self):
        self.assertEqual(len(self.floating),12)
        for w in (16,32,64):
            c=next(c for c in self.floating if c['sew']==w and c['provenance'].startswith('Directed') and not c['frm'])
            self.assertEqual(c['expected_fcsr']&31,31)
        self.assertEqual({c['frm'] for c in self.floating},{0,3})

    def test_mask_restart_tail_preservation(self):
        for c in self.integer+self.floating:
            if not c['masked']:continue
            for i in range(16):
                if i<c['restart'] or i>=c['vl'] or i%2==0:self.assertEqual(c['gold'][i],c['seed'][i])

    def test_changed_reviewed_macro_rejected(self):
        text=(ARCH/'apps/riscv-tests/isa/rv64uv/vmul.c').read_text()
        for a,b in (('VSET(16','VSET(15'),('vmul.vv','vadd.vv'),('0xb3','expression()')):
            with self.assertRaises(ValueError):oracle.reviewed(text.replace(a,b,1),'vmul')

    def test_handoff_math(self):
        self.assertEqual(len(self.handoff['qk']),6)
        self.assertEqual(len(self.handoff['pv']),128)
        self.assertEqual((self.handoff['qk_fmas'],self.handoff['pv_fmas']),(384,384))
        self.assertEqual(self.handoff['qbs'][:3],[0x43800000,0x44000000,0x44400000])

    def test_handoff_small_and_no_clear_inside_chain(self):
        text=(HERE/'handoff.c').read_text()
        self.assertNotIn('csrwi fflags',text)
        self.assertNotIn('SKIP',text)
        self.assertIn('issue_akvinfo(4)',text)
        self.assertNotIn('akv_v2_attention_rvv.S',(HERE/'prepare.py').read_text().split('names=')[1].split('raw=subprocess')[0])

    def fixture(self):
        c=copy.deepcopy(self.integer[0]);c.update(expected_vl=16,expected_vtype=0)
        return dict(kind='integer',cases=[c],data_bytes=1,data_hash=2)

    def log(self,f):
        c=f['cases'][0]
        return ('CO_CASE id=0 begin=1 end=2 initial_fcsr=8 initial_vcsr=5 initial_vstart=0 '
            f'fcsr={c["expected_fcsr"]} vcsr=5 vstart=0 vl=16 vtype=0 op_vstart=0 hash={c["output_hash"]:x} errors=0\n'
            'CO_DATA bytes=1 hash=2\nCO_DONE cases=1 errors=0\n')

    def test_numerical_accepts_complete_record(self):
        f=self.fixture();self.assertEqual(len(check.numerical(self.log(f),f)),1)

    def test_numerical_mutations(self):
        f=self.fixture();text=self.log(f)
        for a,b in (('vcsr=5','vcsr=0'),('op_vstart=0','op_vstart=1'),('errors=0','errors=1'),
                    ('vl=16','vl=15'),('fcsr=8','fcsr=0'),('hash=2','hash=3')):
            with self.subTest(mutation=a),self.assertRaises(ValueError):check.numerical(text.replace(a,b,1),f)
        with self.assertRaises(ValueError):check.numerical(text+'CO_DONE cases=1 errors=0\n',f)
        with self.assertRaises(ValueError):check.numerical(text.replace('CO_DONE','CO_REJECT'),f)

    def unit_log(self,native=0,qk=0,pv=0):
        result=[]
        for lane in range(4):
            q=128 if qk and lane<3 else 0;p=96 if pv else 0
            values=dict(cycles=100,native_requests=16,native_fma_requests=4 if native else 0,
                native_fma_elements=native//4,qk_requests=q//2,qk_elements=q,
                pv_requests=p//4,pv_elements=p,native_blocked=0,resident_blocked=0)
            result.append('OPERATOR_UNIT ara_tb.dut.gen_lanes[%d].i_operator_unit_activity '%lane+
                ' '.join(k+'='+str(v) for k,v in values.items()))
        return '\n'.join(result)

    def test_activity_semantics_and_rejects_missing(self):
        f=self.fixture();self.assertEqual(len(check.activity(self.unit_log(),f)),1)
        with self.assertRaises(ValueError):check.activity(self.unit_log(native=16),f)
        with self.assertRaises(ValueError):check.activity(self.unit_log().split('\n',1)[1],f)
        c=dict(f['cases'][0],op='resident',qk_elements=384)
        self.assertEqual(check.activity(self.unit_log(qk=384),dict(f,cases=[c]))[0]['totals']['qk_elements'],384)
        with self.assertRaises(ValueError):check.activity(self.unit_log(qk=384).replace('qk_elements=128','qk_elements=127',1),dict(f,cases=[c]))


def main():
    global ARCH
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.absolute()
    require(out==out.resolve() and out.parent==OUT.resolve() and
        out.name.startswith('operator_coexist_prepare_20261115_') and not out.exists(),'Fresh owned host test output')
    out.mkdir();ARCH=prepare.archive(out)
    pins={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
    pins.update({str(p):sha(p) for p in out.rglob('*') if p.is_file()})
    stream=io.StringIO();r=unittest.TextTestRunner(stream=stream,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    log=out/'host-tests.log';log.write_text(stream.getvalue());verify(pins)
    pins[str(Tests.module.LIB)]=sha(Tests.module.LIB)
    save(out/'source-pins.json',pins)
    report=dict(state='HOST_TEST_PASS_NOT_RTL' if r.wasSuccessful() else 'FAIL',
        tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),
        rtl_executed=False,source_pins_sha256=sha(out/'source-pins.json'),post_pins_match=True,
        log_sha256=sha(log),synthetic_records_not_target_acceptance=True)
    save(out/'result.json',report);print(stream.getvalue());print(json.dumps(report),flush=True)
    return not r.wasSuccessful()


if __name__=='__main__':raise SystemExit(main())
