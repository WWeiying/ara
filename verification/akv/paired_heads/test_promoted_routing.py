#!/usr/bin/env python3
"""Recheck unchanged pure admission and routing implementations after promotion."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


class PromotedRoutingTests(unittest.TestCase):
    def test_normal_and_d256_test_builds_export_shared_leaves(self):
        source = ROOT/'software/akv/src/akv_v2_attention_rvv.S'
        for flags in ([],['-DAKV_D256_TEST_REFERENCE=1']):
            text = subprocess.check_output([shutil.which('gcc'),'-E','-P','-x',
                'assembler-with-cpp',*flags,source],text=True,timeout=120)
            for name in ('akv_experimental_qk_f16_pair_panel4','akv_experimental_pv_f16_pair',
                         'akv_experimental_pv_f32_pair'):
                self.assertEqual(text.count(name+':'),1)
            self.assertEqual('akv_d256_scores_reference:' in text,bool(flags))

    def test_host_capability_and_odd_tail_routing(self):
        cases = [(HERE/'test_admission.c','PAIR_ADMISSION_PASS'),
                 (HERE/'test_dispatch.c','PAIR_DISPATCH_PASS'),
                 (HERE/'f32_pv/test_runtime.c','F32_PAIR_RUNTIME_HOST_PASS')]
        with tempfile.TemporaryDirectory(prefix='akv-promoted-routing-') as temp:
            for index,(source,marker) in enumerate(cases):
                with self.subTest(source=source.name):
                    binary = Path(temp)/str(index)
                    subprocess.run([shutil.which('gcc'),'-std=c11','-Wall','-Wextra','-Werror','-O2',
                        '-I'+str(ROOT),'-I'+str(ROOT/'software/akv/include'),source,'-o',binary],
                        check=True,timeout=120)
                    result = subprocess.run([binary],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                            text=True,check=True,timeout=120)
                    self.assertIn(marker,result.stdout)


if __name__ == '__main__':
    unittest.main()
