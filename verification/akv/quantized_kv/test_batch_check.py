#!/usr/bin/env python3
"""Known host arithmetic plus batch transcript mutations, not native acceptance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from batch_spec import sequence
from check_batch_qk import CAP,SUITE,TERMINAL,schema,check_log
from check_rvv_qbs import HostOracle

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class BatchCheckTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='quant-batch-oracle-')
        library = Path(cls.temp.name)/'oracle.so'
        subprocess.run([shutil.which('gcc'),'-std=gnu11','-O2','-shared','-fPIC',
            '-fno-fast-math','-ffp-contract=off','-frounding-math','-I'+str(ROOT),
            str(HERE/'host_score.c'),str(ROOT/'verification/qbs/qbs_ref.c'),
            '-lm','-o',str(library)],check=True,timeout=120)
        cls.oracle = HostOracle(library)
        cls.query = (b'\x00\x3c'+bytes([1])*32)*4
        cls.keys = [(b'\x00\x3c'+bytes([1])*32)*4*512,
                    (b'\x00\x3c'+bytes([0x99])*16)*4*512]
        cls.previous = {(kind,head):cls.query for kind in range(2) for head in (0,6)}
        cls.rtl = (ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
        cls.fields = schema(cls.rtl)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def transcript(self):
        lines = [CAP]
        for kind in range(2):
            for head in range(12):
                lines.append(f'QUANT_QK_BATCH_QUERY kind={kind} head={head} bytes=136 fcsr=0 vcsr=5 hex={self.query.hex()}')
            for i,c in enumerate(sequence()):
                if c.kind != kind:
                    continue
                row = dict.fromkeys(self.fields,0)
                row.update(seq=i+1,id=1,m=c.m,n=c.n,vlen=1024,lanes=4,success=1,
                    read_ranges=c.read_ranges,payload_bytes=c.payload_bytes,
                    weight_bytes=c.weight_row_bytes*c.n,activation_bytes=136*c.m,
                    useful_pairs=128*c.outputs,busy_cycles=100,ar=c.read_ranges,
                    r_beats=c.read_ranges+4,read_outstanding_max=2,commit_groups=1)
                lines.append('[QBS_PERF] '+' '.join(f'{k}={row[k]}' for k in self.fields))
                lines.append(f'QUANT_QK_BATCH_SCORE seq={i+1} kind={kind} kv_head={c.kv_head} '
                    f'first_q={c.first_q} m={c.m} first_token={c.first_token} n={c.n} '
                    f'fcsr=0 vcsr=5 errors=0 hex='+('43000000'*c.outputs))
        return '\n'.join(lines+[SUITE,TERMINAL,'UVM_ERROR : 0','UVM_FATAL : 0'])

    def test_complete_host_replay(self):
        result = check_log(self.transcript(),self.keys,self.oracle,self.rtl,self.previous)
        self.assertEqual(result['expected']['outputs'],3336)
        self.assertEqual(len(result['hardware_records']),40)
        self.assertEqual(len(result['query_exports']),24)
        self.assertFalse(result['deployment_approved'])

    def test_mutations(self):
        text = self.transcript()
        first_perf = next(line for line in text.splitlines() if line.startswith('[QBS_PERF]'))
        changes = [text.replace(CAP,CAP+'\n'+CAP,1),
            text.replace('seq=1 ','seq=2 ',1),
            text.replace('hex=43000000','hex=43000001',1),
            text.replace('first_q=0 m=4','first_q=1 m=4',1),
            text.replace('first_token=32 n=31','first_token=33 n=31',1),
            text.replace('n=1 fcsr=0','n=2 fcsr=0',1),
            text.replace('payload_bytes=4912','payload_bytes=4911',1),
            text.replace('context_reuse_count=0','context_reuse_count=1',1),
            text.replace('success=1','success=0',1),
            text.replace('vcsr=5','vcsr=0',1),
            text.replace('fcsr=0 vcsr=5 errors=0','fcsr=1 vcsr=5 errors=0',1),
            text.replace(first_perf+'\n','',1),
            text.replace(first_perf,first_perf+'\n'+first_perf,1),
            text.replace(TERMINAL,''),text+'\n'+CAP,
            text.replace('UVM_ERROR : 0','UVM_ERROR : 1'),
            text.replace('kind=0 head=0','kind=0 head=1',1),
            text.replace(SUITE,SUITE+'\n'+SUITE,1)]
        for i,changed in enumerate(changes):
            with self.subTest(mutation=i),self.assertRaises(ValueError):
                check_log(changed,self.keys,self.oracle,self.rtl,self.previous)
        with self.assertRaises(ValueError):
            check_log(text,[bytes(len(x)) for x in self.keys],self.oracle,self.rtl,self.previous)
        with self.assertRaises(ValueError):
            check_log(text,self.keys,self.oracle,self.rtl,{})


if __name__ == '__main__':
    unittest.main()
