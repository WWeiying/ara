#!/usr/bin/env python3
"""Host FP-order model properties; no native matrix-equality claim."""
from pathlib import Path
import random
import struct
import subprocess
import tempfile
import unittest

from check_rvv_qbs import HostOracle

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


class RvvOrderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='quant-rvv-order-')
        libraries=[]
        for name in ('rvv_order_score','host_score'):
            path=Path(cls.tmp.name)/(name+'.so')
            subprocess.run(['/usr/bin/gcc','-std=gnu11','-O2','-shared','-fPIC',
                '-fno-fast-math','-ffp-contract=off','-frounding-math','-I'+str(ROOT),
                HERE/(name+'.c'),ROOT/'verification/qbs/qbs_ref.c','-lm','-o',path],check=True,timeout=120)
            libraries.append(HostOracle(path))
        cls.rvv,cls.qbs=libraries

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_known_scores(self):
        q=(b'\x00\x3c'+bytes([1])*32)*4
        for kind in (0,1):
            w=(b'\x00\x3c'+bytes([0x99 if kind else 1])*(16 if kind else 32))*4
            self.assertEqual(self.rvv(kind,w,q),(0x43000000,0))
            self.assertEqual(self.rvv(kind,w,q),self.qbs(kind,w,q))

    def test_q8_same_order_finite_random(self):
        rng=random.Random(77291)
        scales=[0,0x8000,1,0x03ff,0x0400,0x3555,0xb555,0x3c00,0x7bff,0xfbff]
        for case in range(256):
            def blocks():
                return b''.join(struct.pack('<H',rng.choice(scales))+bytes(rng.randrange(256) for _ in range(32))
                                for _ in range(4))
            w,q=blocks(),blocks()
            with self.subTest(case=case):
                self.assertEqual(self.rvv(0,w,q),self.qbs(0,w,q))

    def test_q4_not_universally_equivalent(self):
        scales=[0x3555,0x3556,0x37ff,0x3801,0x3bff,0x3c01,0x3d55,0x3fff]
        differences=[]
        for wd in scales:
            for qd in scales:
                # Canonical Q4_0-style negative d with mostly -8 and one -7;
                # Q8_0 Query uses legal production-range +127 values.
                w=struct.pack('<H',wd|0x8000)+b'\x01'+bytes(15)+bytes(54)
                q=struct.pack('<H',qd)+bytes([127])*32+bytes(102)
                a,b=self.rvv(1,w,q),self.qbs(1,w,q)
                if a!=b: differences.append((wd,qd,a,b))
        self.assertTrue(differences,'The model must expose the real two-rounding-versus-one distinction')


if __name__=='__main__':
    unittest.main()
