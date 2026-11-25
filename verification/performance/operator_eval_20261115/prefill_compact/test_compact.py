"""Host unit tests. All artificial cycle/record fixtures are mocks, not timing evidence."""
import csv
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

from contract import HERE, OUT, ORDER, CONST_FIELDS, real_fixture, hash64, work, constant_bytes
from prepare import budget
from check import numerical, activity, roi, RAW_FIELDS, AGGREGATES


def mock_numerical(c):
    lines = [f'PFC_CAP first=72 queries={c["queries"]} d=128 heads=2 kvheads=1 capacity=256 '
             f'outputs={c["outputs"]} printed=64 trials=4 pair_pv=1 atol=3b83126f rtol=3b03126f']
    for t,m in enumerate(ORDER):
        lines += [f'PFC_BEGIN trial={t} mode={m}',
            f'PFC_RESULT trial={t} mode={m} begin={t*100+10} end={t*100+20} checked={c["outputs"]} '
            f'nonfinite=0 tolerance_errors=0 fcsr=1 vcsr=5 vstart=0 guards=128 input_bytes={c["input_bytes"]} '
            f'input_hash={c["input_hash"]:016x} output_hash=0123456789abcdef repeat_errors=0 errors=0 hex='+'3f800000'*64]
    return '\n'.join(lines+['PFC_DONE calls=4 errors=0'])


class CompactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data,cls.c = real_fixture(16)
        cls.output = Path(tempfile.mkdtemp(prefix='operator_prefill_compact_prepare_20261115_host_',dir=OUT))

    def test_real_q64_complete_k_and_coordinates(self):
        full,c = real_fixture(64)
        self.assertEqual(c['first'],72)
        self.assertEqual(c['outputs'],16384)
        self.assertEqual(len(full['key']),65536)
        self.assertEqual(len(full['mask']),64*512)
        self.assertEqual(struct.unpack_from('<256H',full['mask'],63*512),tuple([0]*136+[0xfc00]*120))
        self.assertEqual(self.data['query'][:8192],full['query'][:8192])
        self.assertEqual(self.data['query'][8192:],full['query'][64*512:80*512])
        self.assertEqual(self.data['golden'],full['golden'][:16*1024])
        self.assertEqual(self.c['input_hash'],hash64(b''.join(self.data.values())))
        self.assertEqual(len(constant_bytes(c)),len(CONST_FIELDS)*8)

    def test_original_budget_and_threshold(self):
        small,large = budget(16),budget(64)
        self.assertEqual(small['state'],'CLEARED_FOR_BOUNDED_PARENT_RUN')
        self.assertEqual(large['state'],'HOLD_EXCEEDS_BUDGET_ENVELOPE')
        self.assertFalse(small['query_threshold_covered'])
        self.assertTrue(large['query_threshold_covered'])
        self.assertLess(small['conservative_seconds'],10800)
        self.assertGreater(large['conservative_seconds'],10800)

    def test_numerical_mutations(self):
        text = mock_numerical(self.c)
        gold = struct.pack('<64f',*([1.0]*64))
        self.assertEqual(len(numerical(text,gold,self.c)),4)
        for old,new in (('checked=4096','checked=64'),('nonfinite=0','nonfinite=1'),
            ('tolerance_errors=0','tolerance_errors=1'),('atol=3b83126f','atol=3c23d70a'),
            ('input_hash=','input_hash=0'),('vstart=0','vstart=1'),('guards=128','guards=127'),
            ('fcsr=1','fcsr=32'),('3f800000','7fc00000'),('PFC_DONE calls=4 errors=0',''),
            ('queries=16','queries=64'),('output_hash=0123456789abcdef','output_hash=1123456789abcdef')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                numerical(text.replace(old,new,1),gold,self.c)
        with self.assertRaises(ValueError): numerical(text,gold[:-4],self.c)

    def test_workload_full_prefixes_and_mutations(self):
        expected = work(self.c)
        lines,rows = [],[]
        for trial,mode in enumerate(ORDER):
            lines.append(f'PFC_BEGIN trial={trial} mode={mode}')
            for want in expected if mode else ():
                cmd = want['command']; r = dict.fromkeys(RAW_FIELDS,0)
                r.update(want,seq=len(rows)+1,id=0,success=1,busy_cycles=1,context_ready=int(cmd != 3),
                    load=int(cmd == 2),release=int(cmd == 3),v2_full=int(cmd == 4),v2_refill=int(cmd == 5),
                    v2_row_load=int(cmd == 2),v2_column_load=int(cmd == 6),v2_column_panel=int(cmd == 6),
                    v2_logical_column=4*int(cmd == 6),read_payload_bytes=want['q_external_bytes']+
                    want['kv_external_bytes']+64*int(cmd == 4))
                rows.append(r); lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in r.items()))
            lines.append(f'PFC_RESULT trial={trial} mode={mode}')
        total = {k:sum(r[k] for r in rows) for k in AGGREGATES}
        total.update(records=len(rows),success_records=len(rows),fault_records=0,validation_fault_records=0)
        text = '\n'.join(lines+['[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in total.items())])
        self.assertEqual(activity(text,self.c)['records_per_trial'],[0,2315,2315,0])
        for old,new in (('seq=1 ','seq=2 '),('command=4','command=5'),('success=1','success=0'),
                        ('v2_column_panel=1','v2_column_panel=0'),('q_external_bytes=512','q_external_bytes=256')):
            with self.subTest(old=old),self.assertRaises(ValueError): activity(text.replace(old,new,1),self.c)
        _,large = real_fixture(64)
        self.assertEqual(len(work(large)),11044)

    def test_all_output_scalar_oracle(self):
        binary = self.output/'validate'
        commands = [['gcc','-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-I'+str(HERE),
                     str(HERE/'test_validate.c'),'-lm','-o',str(binary)],[str(binary)]]
        for command in commands:
            r = subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            self.assertEqual(r.returncode,0,r.stdout.decode())

    def test_roi_binding_and_outside_audit(self):
        report = dict(elf_ranges=dict(main=[100,120],compact_full_prefill=[200,204],
            akv_attention_execute_v2_prefill_native=[300,304],compact_audit_all=[400,404],compact_validate_all=[500,504]),
            roi_marker_pcs=[100,112],roi_read_pcs=[104,108])
        parsed = dict(words={200:0x13,300:0x13,400:0x13,500:0x13,104:0xc00022f3,108:0xc0002373})
        rows = numerical(mock_numerical(self.c),struct.pack('<64f',*([1.0]*64)),self.c)
        commits = []
        def emit(pc,insn,value=0):
            commits.append(dict(cycle=len(commits)+1,event='retire',pc=f'{pc:x}',insn=f'{insn:x}',rd_wdata=f'{value:x}',trap='0'))
        for trial,mode in enumerate(ORDER):
            emit(100,0xc0002073); emit(104,parsed['words'][104],rows[trial]['begin']); emit(200,0x13)
            if mode: emit(300,0x13)
            emit(108,parsed['words'][108],rows[trial]['end']); emit(112,0xc0002073)
            emit(400,0x13); emit(500,0x13)
        path = self.output/'mock-commit.csv'
        def write():
            with path.open('w',newline='') as stream:
                w = csv.DictWriter(stream,fieldnames=list(commits[0])); w.writeheader(); w.writerows(commits)
        write()
        self.assertEqual(roi(path,report,rows,parsed)['markers'],8)
        commits[1]['rd_wdata'] = 'deadbeef'; write()
        with self.assertRaises(ValueError): roi(path,report,rows,parsed)


if __name__ == '__main__':
    unittest.main()
