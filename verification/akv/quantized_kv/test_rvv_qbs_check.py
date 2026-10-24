#!/usr/bin/env python3
"""Host arithmetic sanity and transcript rejection tests; no RTL acceptance."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import check_rvv_qbs as c

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class ReplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='quant-kv-oracle-')
        cls.library = Path(cls.temp.name)/'oracle.so'
        subprocess.run([shutil.which('gcc'), '-std=gnu11', '-O2', '-shared', '-fPIC',
            '-fno-fast-math', '-ffp-contract=off', '-frounding-math', '-I'+str(ROOT),
            str(HERE/'host_score.c'), str(ROOT/'verification/qbs/qbs_ref.c'),
            '-lm', '-o', str(cls.library)], check=True, timeout=120)
        cls.oracle = c.HostOracle(cls.library)
        cls.query = (b'\x00\x3c'+bytes([1])*32)*4
        cls.keys = [(b'\x00\x3c'+bytes([1])*32)*4*512,
                    (b'\x00\x3c'+bytes([0x99])*16)*4*512]

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def transcript(self, different=False):
        lines = [c.CAP]
        for kind in range(2):
            for head in range(2):
                lines.append(f'QUANT_KV_QUERY kind={kind} head={head} bytes=136 fcsr=0 vcsr=5 hex={self.query.hex()}')
                for token in c.TOKENS:
                    rvv = '43000001' if different and kind else '43000000'
                    lines.append(f'QUANT_KV_SCORE kind={kind} head={head} token={token} rvv={rvv} '
                        f'qbs=43000000 ref=43000000 rvv_flags=0 qbs_flags=0 ref_flags=0 equal={int(rvv == "43000000")} errors=0')
        lines.extend([f'QUANT_KV_SUITE_PASS comparisons=16 q8_differences=0 q4_differences={8 if different else 0} '
            'hardware_reference_exact=1 deployment_accepted=0',
            'Core Test *** SUCCESS *** (tohost = 0)', 'UVM_ERROR : 0', 'UVM_FATAL : 0'])
        return '\n'.join(lines)

    def test_host_known_exact_arithmetic(self):
        for kind, width in ((0,136),(1,72)):
            self.assertEqual(self.oracle(kind,self.keys[kind][:width],self.query),(0x43000000,0))
            self.assertEqual(self.oracle(kind,self.keys[kind][:width],bytes(136)),(0,0))

    def test_accepted_exact_and_reported_difference(self):
        for differs in (False,True):
            result = c.check_transcript(self.transcript(differs),self.keys,self.oracle)
            self.assertEqual(result['differences'],dict(q8_0=0,q4_0=8 if differs else 0))
            self.assertEqual(len(result['scores']),16)
            self.assertFalse(result['deployment_approved'])

    def test_mutations_rejected(self):
        text = self.transcript()
        mutations = [text.replace(c.CAP,c.CAP+'\n'+c.CAP,1),
            text.replace('qbs=43000000','qbs=43000001',1),
            text.replace('ref_flags=0','ref_flags=1',1),
            text.replace('rvv_flags=0','rvv_flags=32',1),
            text.replace('equal=1','equal=0',1),
            text.replace('token=63','token=62',1),
            text.replace('q8_differences=0','q8_differences=1',1),
            text.replace('vcsr=5','vcsr=0',1),
            text.replace('errors=0','errors=1',1),
            text.replace('UVM_ERROR : 0','UVM_ERROR : 1'),
            text.replace('Core Test *** SUCCESS *** (tohost = 0)',''),
            text.replace('qbs=43000000','qbs=7fc00000',1),
            text+'\n'+c.CAP,
            '\n'.join(x for x in text.splitlines() if 'token=127' not in x)]
        for index, changed in enumerate(mutations):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                c.check_transcript(changed,self.keys,self.oracle)
        with self.assertRaises(ValueError):
            c.check_transcript(text,[bytes(len(x)) for x in self.keys],self.oracle)


if __name__ == '__main__':
    unittest.main()
