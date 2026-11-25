#!/usr/bin/env python3
"""Host-only checker mutations. Synthetic records are never target evidence."""
import argparse
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.dont_write_bytecode = True
import check
import check_activity
from contract import HERE, OUT, GEOMETRY, cases, load, resident_commands, require, save, sha


def fixture():
    c = cases()[0]
    return dict(case=c,order=[0,1,2],result=dict(bits=[0]*(2*128),expected_fcsr=11,
        stages=[dict(head=h,tile=t,mode=mode,fflags=0) for h in range(2)
                for t in (0,64,128) for mode in ('QK','PV')]),
        memory=dict(query_hash=1,guard_hash=2,guard_bytes=10344),data_bytes=133632,data_hash=3)


def numerical_log(f):
    c, lines = f['case'], []
    def record(tag, fields):
        lines.append('OP_ATTN_'+tag+' '+' '.join(k+'='+format(v,'x' if k in check.HEX else 'd')
                                                for k,v in fields.items()))
    for trial,mode in enumerate(f['order']):
        record('CALL',dict(trial=trial,mode=mode,d=c['dimension'],heads=c['heads'],kvheads=c['kv_heads'],
            tokens=c['tokens'],begin=trial*100+1,returned=trial*100+50,end=trial*100+60,
            initial_fcsr=c['initial_flags'],initial_vcsr=0,initial_vstart=0,fcsr=f['result']['expected_fcsr'],
            vcsr=0,vstart=0,groups=c['kv_heads'],errors=0))
        for g in range(c['kv_heads']):
            record('GROUP',dict(trial=trial,group=g,first_head=g*c['heads']//c['kv_heads'],
                rows=c['heads']//c['kv_heads'],q=0x80001000+g*512,k=0x80002000+g*c['capacity']*256,
                v=0x80020000+g*c['capacity']*256,output=0x80040000+g*1024))
        record('MEMORY',dict(trial=trial,**f['memory']))
        for i,bits in enumerate(f['result']['bits']): record('OUT',dict(trial=trial,index=i,bits=bits))
    record('DATA',dict(bytes=f['data_bytes'],hash=f['data_hash']))
    record('DONE',dict(calls=len(f['order']),errors=0))
    return '\n'.join(lines)+'\n'


def resident_log(f):
    g, lines = load(GEOMETRY,'test_attention_geometry'), []
    for i,c in enumerate(resident_commands(f['case'],f['order'])):
        shape = g.geometry(c)
        def record(kind, fields):
            lines.append('[RESIDENT_'+c['mode']+'_'+kind+'] '+' '.join(
                k+'='+format(v,'b' if k == 'active' else 'd') for k,v in fields.items()))
        for lane in range(4):
            if not shape['writes'][lane]: continue
            values = dict(lane=lane,vid=0,tokens=c['tokens'],elements=shape['elements'][lane],heads=c['heads'],
                issued=shape['fma'][lane],returned=shape['fma'][lane],writes=len(shape['writes'][lane]),flags=0,error=0)
            if c['mode'] == 'QK': values['dimensions'] = c['dimension']
            record('LANE',values)
        record('PERF',dict(shape['counts'],seq=i+1,vid=0,cycles=20,flags=0,error=0))
    return '\n'.join(lines)+'\n'


def unit_log(f):
    c, lines = f['case'], []
    for trial,mode in enumerate(f['order']):
        for lane in range(4):
            qk = c['dimension']*c['heads']*sum(max(0,(min(64,c['tokens']-s)+3-lane)//4)
                for s in range(0,c['tokens'],64)) if mode == 2 else 0
            pv = c['dimension']//4*c['heads']*c['tokens'] if mode == 2 else 0
            r = dict(cycles=50000,native_requests=200,native_fma_requests=100,native_fma_elements=200,
                qk_requests=(qk+1)//2,qk_elements=qk,pv_requests=(pv+3)//4,pv_elements=pv,
                native_blocked=1,resident_blocked=1)
            lines.append('OPERATOR_UNIT ara_tb.dut.gen_lanes[%d].i_lane.i_vmfpu.i_operator_unit_activity ' % lane+
                         ' '.join(k+'='+str(v) for k,v in r.items()))
    return '\n'.join(lines)+'\n'


VECTOR_FIELDS = 'cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split()


def vector_rows(f):
    g = load(GEOMETRY,'test_attention_vector_geometry')
    result, cycle, resident = [], 0, iter(resident_commands(f['case'],f['order']))
    def row(event, insn=0, **values):
        nonlocal cycle
        value = dict.fromkeys(VECTOR_FIELDS,'0')
        value.update(cycle=str(cycle),event=event,insn='%08x' % insn,nr_lanes='4',vlen_bits='1024')
        value.update({k:str(v) for k,v in values.items()})
        result.append(value)
        cycle += 1
    row('config')
    for seq,insn in enumerate(check.expected_work(f)[1],1):
        if insn not in (0x0605705b,0x0485705b):
            row('alloc',insn,arch_seq=seq)
            continue
        shape = g.geometry(next(resident))
        meta = dict(arch_seq=seq,vid=0,use_vd=1,vd=0,eew=shape['eew'],vl=shape['vl'],vstart=0)
        row('alloc',insn,**meta)
        for lane in range(4):
            for addr,be in shape['writes'][lane].items():
                row('write',insn,**meta,lane=lane,addr=addr,source=4,be='%x' % be,wdata='0000000000000000')
        row('done',insn,**meta)
    return result


def check_vector(rows, f):
    with tempfile.TemporaryDirectory(dir=OUT,prefix='operator_attention_prepare_20261115_vector_test_') as directory:
        p = Path(directory)/'synthetic.csv'
        with p.open('w',newline='') as stream:
            writer = csv.DictWriter(stream,fieldnames=VECTOR_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        return check.vector_work(p,f)


class CheckTests(unittest.TestCase):
    def setUp(self): self.f = fixture()
    def test_numerical_pass(self): self.assertEqual(len(check.numerical(numerical_log(self.f),self.f)),3)
    def test_raw_output(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace('bits=0','bits=1',1),self.f)
    def test_flags_preserved(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace(' fcsr=11 ',' fcsr=3 ',1),self.f)
    def test_guard_mutation(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace('guard_hash=2','guard_hash=3',1),self.f)
    def test_query_mutation(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace('query_hash=1','query_hash=0',1),self.f)
    def test_missing_terminal(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).rsplit('OP_ATTN_DONE',1)[0],self.f)
    def test_duplicate_terminal(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f)+'OP_ATTN_DONE calls=3 errors=0\n',self.f)
    def test_wrong_mode(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace('mode=2','mode=1',1),self.f)
    def test_unknown_field(self):
        with self.assertRaises(ValueError): check.numerical(numerical_log(self.f).replace(' fcsr=11',' bogus=0 fcsr=11',1),self.f)
    def test_work_counts(self):
        legacy, sig = check.expected_work(self.f)
        self.assertEqual(len(legacy),241)
        self.assertEqual(Counter(r['command'] for r in legacy),{4:2,5:4,6:96,2:137,3:2})
        self.assertEqual(len(sig),239)
    def test_rvv_no_custom(self):
        self.f['order'] = [0]
        self.assertEqual(check.expected_work(self.f),([],[]))
    def test_resident_commands(self):
        self.assertEqual(len(resident_commands(self.f['case'],self.f['order'])),6)
        self.assertEqual(len(check.resident_work(resident_log(self.f),self.f)),6)
    def test_resident_missing_lane(self):
        with self.assertRaises(ValueError): check.resident_work(resident_log(self.f).split('\n',1)[1],self.f)
    def test_resident_wrong_work(self):
        text = resident_log(self.f).replace('issued=2048','issued=2047',1)
        self.assertNotEqual(text,resident_log(self.f))
        with self.assertRaises(ValueError): check.resident_work(text,self.f)
    def test_resident_wrong_flags(self):
        with self.assertRaises(ValueError): check.resident_work(resident_log(self.f).replace('flags=0','flags=1',1),self.f)
    def test_unit_pass(self):
        rows = check_activity.unit_activity(unit_log(self.f),self.f)
        self.assertEqual(rows[2]['sums']['qk_elements'],35072)
        self.assertEqual(rows[2]['sums']['pv_elements'],35072)
    def test_unit_inactive_native_private(self):
        with self.assertRaises(ValueError): check_activity.unit_activity(unit_log(self.f).replace('qk_elements=0','qk_elements=1',1),self.f)
    def test_unit_missing(self):
        with self.assertRaises(ValueError): check_activity.unit_activity(unit_log(self.f).split('\n',1)[1],self.f)
    def test_unit_duplicate_lane(self):
        with self.assertRaises(ValueError): check_activity.unit_activity(unit_log(self.f).replace('gen_lanes[1]','gen_lanes[0]',1),self.f)
    def test_unit_underreported(self):
        with self.assertRaises(ValueError): check_activity.unit_activity(unit_log(self.f).replace('qk_elements=8960','qk_elements=8959',1),self.f)
    def test_matrix(self):
        all_cases = cases()
        self.assertEqual(len({c['id'] for c in all_cases}),len(all_cases))
        self.assertTrue({64,96,128} <= {c['dimension'] for c in all_cases})
        self.assertTrue({64,128,256,512,1024} <= {c['tokens'] for c in all_cases})
        for c in all_cases:
            self.assertEqual(c['heads'] % c['kv_heads'],0)
            if c['tokens'] > 137: self.assertIn('derived',c['provenance'])
    def test_vector_pass(self):
        self.assertEqual(len(check_vector(vector_rows(self.f),self.f)),6)
    def test_vector_missing_write(self):
        rows = vector_rows(self.f)
        del rows[next(i for i,r in enumerate(rows) if r['event'] == 'write')]
        with self.assertRaises(ValueError): check_vector(rows,self.f)
    def test_vector_wrong_mask(self):
        rows = vector_rows(self.f)
        next(r for r in rows if r['event'] == 'write')['be'] = '1'
        with self.assertRaises(ValueError): check_vector(rows,self.f)
    def test_vector_duplicate_write(self):
        rows = vector_rows(self.f)
        i = next(i for i,r in enumerate(rows) if r['event'] == 'write')
        rows.insert(i,dict(rows[i]))
        with self.assertRaises(ValueError): check_vector(rows,self.f)
    def test_vector_opcode_mismatch(self):
        rows = vector_rows(self.f)
        rows[1]['insn'] = '0005745b'
        with self.assertRaises(ValueError): check_vector(rows,self.f)
    def test_vector_wrong_config(self):
        rows = vector_rows(self.f)
        rows[0]['vlen_bits'] = '512'
        with self.assertRaises(ValueError): check_vector(rows,self.f)
    def test_unit_multiple_groups_tail(self):
        self.f['case'] = cases()[2]
        rows = check_activity.unit_activity(unit_log(self.f),self.f)
        self.assertEqual(rows[2]['sums']['qk_elements'],6*65*96)
        self.assertEqual(rows[2]['sums']['pv_elements'],6*65*96)
    def test_resident_fallback_rejected(self):
        with self.assertRaises(ValueError): check.resident_work('',self.f)
    def test_markers(self):
        self.assertEqual((HERE/'main.c').read_text().count('__asm__ volatile("csrr zero,cycle"'),2)


from collections import Counter


def main():
    p = argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--output',type=Path,required=True)
    args = p.parse_args()
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT.resolve() and
            out.name.startswith('operator_attention_prepare_20261115_') and not out.exists(), 'Fresh owned host-test output required')
    out.mkdir()
    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(CheckTests)
    result = unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    (out/'host-tests.log').write_text(log.getvalue())
    save(out/'result.json',dict(state='HOST_TEST_PASS_NOT_RTL' if result.wasSuccessful() else 'FAIL',
        tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        rtl_executed=False,synthetic_records_not_acceptance=True,
        source_sha256={str(HERE/n):sha(HERE/n) for n in ('test_attention.py','check.py','check_activity.py','contract.py')}))
    print(log.getvalue())
    return not result.wasSuccessful()


if __name__ == '__main__':
    raise SystemExit(main())
