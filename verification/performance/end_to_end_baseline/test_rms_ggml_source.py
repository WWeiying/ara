from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

import rms_ggml_source as source

FROZEN=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_output_graph_20261106_01/llama')


class RMSIntegrationSource(unittest.TestCase):
    def test_actual_full_ops_and_measured_helpers(self):
        old=(FROZEN/source.OPS).read_text();text,r=source.transform(old)
        self.assertEqual(text,(source.LIVE/source.OPS).read_text())
        self.assertTrue(r['original_group_reversible'])
        self.assertTrue(r['unrelated_source_text_unchanged'])
        self.assertFalse(r['default_enabled'])
        self.assertEqual(len(source.header_inventory()),3)

    def test_missing_or_duplicate_anchor_fails_closed(self):
        old=(FROZEN/source.OPS).read_text()
        for anchor in (source.SUM,source.OUTPUT):
            for replacement in ('',anchor+anchor):
                with self.subTest(anchor=anchor[:40]),self.assertRaises(ValueError):
                    source.transform(old.replace(anchor,replacement,1))

    def test_non_rvv_explicit_enable_does_not_execute_helpers(self):
        cc=shutil.which('c++');self.assertIsNotNone(cc)
        text=r'''
#include "rms-norm.h"
int main() {
    auto c=ggml_rvv_rms_begin(true,33,0,1);
    if(c.enabled || c.trace) return 1;
    double sum=123;float x[2]={1,2},w[2]={3,4},out[2]={5,6};
    if(ggml_rvv_rms_sum_row(&c,x,2,&sum) || sum!=123) return 2;
    if(ggml_rvv_rms_output_row(&c,out,x,w,1,2) || out[0]!=5 || out[1]!=6) return 3;
    ggml_rvv_rms_finish(&c);return 0;
}
'''
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'test.cpp';p.write_text(text)
            compiled=subprocess.run([cc,'-std=c++17','-O2','-Wall','-Wextra','-Werror',
                '-I'+str(source.LIVE/source.ARCH),p,'-o',root/'test'],capture_output=True,text=True,timeout=30)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([root/'test'],env=dict(os.environ,GGML_RISCV_ORDERED_RMS='1',
                GGML_RISCV_ORDERED_RMS_TRACE='1'),capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode,0,run.stderr);self.assertEqual(run.stdout+run.stderr,'')


if __name__=='__main__':unittest.main()
