"""Successor host mutations for five-arm paths, counters and architectural work."""
from collections import Counter
import csv
import json
from pathlib import Path
import tempfile
import unittest

import check
import check_activity
from contract import HERE, OUT, ELF, LEGACY, load
from expf_audit import signature, function

GENERATORS = load(HERE/'ancestor/evidence_generators.py','real_evidence_generators')


def fixture():
    return dict(case=dict(dimension=128,heads=2,kv_heads=1,tokens=137,capacity=256,
            initial_flags=8), order=[0,1,4,2,3],
        result=dict(bits=[0]*256,expected_fcsr=11,
            stages=[dict(head=h,tile=t,mode=m,fflags=0) for h in range(2)
                    for t in (0,64,128) for m in ('QK','PV')]),
        memory=dict(query_hash=1,guard_hash=2,guard_bytes=10344),
        data_bytes=133632,data_hash=3,output_hash=4,printed_values=64)


def legacy_log(f):
    old = load(LEGACY,'real_legacy_schema')
    commands = check.expected_work(f)[0]
    lines,totals = [],Counter()
    for i,c in enumerate(commands):
        r = dict.fromkeys(old.PERF_FIELDS,0)
        r.update(c,seq=i+1,success=1,busy_cycles=1,context_ready=int(c['command'] != 3),
            read_payload_bytes=c['q_external_bytes']+c['kv_external_bytes']+64*c['v2_full'])
        lines.append('[AKV_PERF] '+' '.join(k+'='+str(v) for k,v in r.items()))
        for k in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
            totals[k] = max(totals[k],r[k]) if k == 'read_outstanding_max' else totals[k]+r[k]
    totals.update(records=len(commands),success_records=len(commands),fault_records=0,validation_fault_records=0)
    lines.append('[AKV_PERF_SUMMARY] '+' '.join(k+'='+str(v) for k,v in totals.items()))
    return '\n'.join(lines)+'\n'


class EvidenceTests(unittest.TestCase):
    def setUp(self): self.f = fixture()

    def test_legacy_and_dma(self):
        rows,sig = check.expected_work(self.f)
        self.assertEqual(len(rows),715)
        self.assertEqual(Counter(r['command'] for r in rows),{4:4,5:8,6:288,2:411,3:4})
        self.assertEqual(sum(r['q_external_bytes'] for r in rows),2048)
        self.assertEqual(sum(r['kv_external_bytes'] for r in rows),4*137*128*4)
        self.assertEqual(check.legacy_work(legacy_log(self.f),self.f)['commands'],715)

    def test_legacy_mutations(self):
        text = legacy_log(self.f)
        for before,after in (('success=1','success=0'),('kv_external_bytes=32768','kv_external_bytes=32766'),
                ('context_ready=1','context_ready=0'),('v2_full=1','v2_full=0'),('busy_cycles=1','busy_cycles=0')):
            with self.subTest(mutation=before),self.assertRaises(ValueError):
                check.legacy_work(text.replace(before,after,1),self.f)
        with self.assertRaises(ValueError):
            check.legacy_work(text.split('\n',1)[1],self.f)

    def test_resident_lanes_and_flags(self):
        text = GENERATORS.resident_log(self.f)
        self.assertEqual(len(check.resident_work(text,self.f)),6)
        for before,after in (('issued=2048','issued=2047'),('flags=0','flags=1'),
                              ('error=0','error=1'),('writes=16','writes=15')):
            mutated = text.replace(before,after,1)
            self.assertNotEqual(mutated,text)
            with self.assertRaises(ValueError): check.resident_work(mutated,self.f)
        with self.assertRaises(ValueError): check.resident_work(text.split('\n',1)[1],self.f)

    def test_activity_default_not_resident(self):
        text = GENERATORS.unit_log(self.f)
        results = check_activity.unit_activity(text,self.f)
        self.assertEqual(len(results),5)
        self.assertEqual(results[3]['sums']['qk_elements'],35072)
        self.assertEqual(results[3]['sums']['pv_elements'],35072)
        self.assertEqual(results[4]['sums']['qk_elements'],0)
        self.assertEqual(results[4]['sums']['pv_elements'],0)
        for before,after in (('qk_elements=0','qk_elements=1'),
                ('gen_lanes[1]','gen_lanes[0]'),('qk_elements=8960','qk_elements=8959')):
            with self.assertRaises(ValueError):
                check_activity.unit_activity(text.replace(before,after,1),self.f)
        with self.assertRaises(ValueError):
            check_activity.unit_activity(text.split('\n',1)[1],self.f)

    def vector(self,rows):
        with tempfile.TemporaryDirectory(dir=HERE,prefix='evidence_tmp_') as directory:
            path = Path(directory)/'synthetic.csv'
            with path.open('w',newline='') as stream:
                writer = csv.DictWriter(stream,fieldnames=GENERATORS.VECTOR_FIELDS)
                writer.writeheader();writer.writerows(rows)
            return check.vector_work(path,self.f)

    def test_vector_geometry_and_signatures(self):
        rows = GENERATORS.vector_rows(self.f)
        self.assertEqual(len(self.vector(rows)),6)
        for kind in ('mask','opcode','write','config'):
            with self.subTest(mutation=kind):
                mutated = [dict(r) for r in rows]
                i = next(i for i,r in enumerate(mutated) if r['event'] == 'write')
                if kind == 'mask': mutated[i]['be'] = '1'
                if kind == 'opcode': mutated[1]['insn'] = '0005745b'
                if kind == 'write': del mutated[i]
                if kind == 'config': mutated[0]['vlen_bits'] = '512'
                with self.assertRaises(ValueError): self.vector(mutated)

    def test_real_elf_entry_counts(self):
        build = OUT/'operator_attention_real_prepare_20261115_t137_01'
        m = json.loads((build/'build.json').read_text())
        parsed = load(ELF,'real_entry_reader').contract(Path(m['elf']).read_bytes())
        counts = dict(attention_full_call=5,akv_decode_execute=10,
            attention_rvv_group=1,attention_rvv_pack=3,
            attention_memory_qk_panel4=3,attention_memory_pv_rotation=3,
            attention_replay_pv_rotation=3,akv_experimental_qk_f16_pair_panel4=9,
            akv_attention_execute_v2_native_auto=2,akv_experimental_attention_execute_v2_native=2,
            akv_experimental_resident_qk_prepared=3,akv_experimental_resident_pv_compact=3)
        rows = []
        for name,count in counts.items():
            pc = m['elf_ranges'][name][0]
            word = parsed['words'][pc]
            word = word if word & 3 == 3 else word & 0xffff
            rows += [dict(cycle=len(rows)+i,event='retire',pc=format(pc,'x'),
                          insn=format(word,'x'),trap=0) for i in range(count)]
        rows += [dict(cycle=len(rows)+i,event='retire',pc='0',insn='c0002073',trap=0) for i in range(10)]
        def run(values):
            with tempfile.TemporaryDirectory(dir=HERE,prefix='evidence_tmp_') as directory:
                path = Path(directory)/'synthetic-commit.csv'
                with path.open('w',newline='') as stream:
                    writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
                    writer.writeheader();writer.writerows(values)
                return check.entries(path,m)
        self.assertEqual(run(rows)['counts'],counts)
        with self.assertRaises(ValueError): run(rows[1:])
        mutated = [dict(r) for r in rows];mutated[0]['trap'] = 1
        with self.assertRaises(ValueError): run(mutated)
        mutated = [dict(r) for r in rows];mutated[0]['insn'] = '13'
        with self.assertRaises(ValueError): run(mutated)
        with self.assertRaises(ValueError): run(rows[:-1])

    def test_target_expf_schedule(self):
        b = OUT/'operator_attention_real_prepare_20261115_t137_01'
        d = json.loads((HERE/'DERIVATION.json').read_text())
        text,raw = (b/'objdump.log').read_text(),(b/'attention.elf').read_bytes()
        oldtext,oldraw = Path(d['expf_anchor']).read_text(),Path(d['expf_elf']).read_bytes()
        self.assertEqual(signature(text,raw),signature(oldtext,oldraw))
        body = function(text,'__ieee754_expf')
        mutated = text.replace(body,body.replace('fmadd.s','fadd.s',1))
        self.assertNotEqual(signature(mutated,raw),signature(text,raw))

    def test_midpoint_reduction_is_proven_exact(self):
        import oracle
        a = oracle.Arithmetic();a.flags = 1
        # Exact positive F64 sum lies on an F32 midpoint. A loose error bound
        # straddles the midpoint, but every possible F64 tree is exact here.
        result = a.sum_scores([oracle.raw32(1.0),oracle.raw32(2**-24)],0)
        self.assertEqual(result,oracle.raw32(1.0))


if __name__ == '__main__': unittest.main()
