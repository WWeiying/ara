import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import gap107_static_contract as c

APP=c.ROOT/'apps/qbs_gap107_invalid_nan'
DRIVER=r'''
#include <stdio.h>
#include <string.h>
#include "contract.h"
#include "gap107_data.h"
#include "ieee_native.h"
int main(int argc,char **argv) {
  uint32_t flags=0, total=0, bits=0; int ok=1;
  if (argc!=2) return 9;
  if (!strcmp(argv[1],"priority")) {
    bits=gap107_fma(0x7f800000,0,0x7fc02000,&flags,&ok);total|=flags;
    bits=gap107_fma(0,0x7f800000,bits,&flags,&ok);total|=flags;
    bits=gap107_fma(0xffc00000,0,bits,&flags,&ok);total|=flags;
  } else if (!strcmp(argv[1],"same-inf")) {
    bits=gap107_fma(0x7f800000,0x3f800000,0x7f800000,&flags,&ok);total=flags;
  } else if (!strcmp(argv[1],"opposite-inf")) {
    bits=gap107_fma(0x7f800000,0x3f800000,0xff800000,&flags,&ok);total=flags;
  } else if (!strcmp(argv[1],"unsupported")) {
    bits=gap107_fma(0x40000000,0x40000000,0,&flags,&ok);total=flags;
  } else if (!strcmp(argv[1],"half-snan")) {
    bits=gap107_half(0x7c01);
  } else if (!strcmp(argv[1],"fp32-snan")) {
    bits=gap107_fma(0x7f800001,0x3f800000,0,&flags,&ok);total=flags;
  } else {
    uint8_t w[176], a[292];gap107_result_t r={0};
    memcpy(w,(const uint8_t *)gap107_weights1+64,176);
    memcpy(a,(const uint8_t *)gap107_activation1+64,292);
    if (!strcmp(argv[1],"bsum-cancel")) { a[260]++;a[262]--; }
    else if (!strcmp(argv[1],"quant")) w[48]^=1;
    else if (!strcmp(argv[1],"size")) return gap107_native_evaluate(w,175,a,292,&r) ? 1 : 0;
    else return 8;
    return gap107_native_evaluate(w,176,a,292,&r) ? 1 : 0;
  }
  printf("%u %u %d\n",bits,total,ok);return 0;
}
'''


class Host(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.out=Path(cls.tmp.name);cc=shutil.which('cc')
        if not cc:raise RuntimeError('Host C compiler required')
        def compile(source,name,extra=(),stdin=None):
            command=[cc,'-std=gnu11','-O0','-Wall','-Wextra','-I'+str(APP),*extra,
                     *source,'-o',str(cls.out/name)]
            result=subprocess.run(command,input=stdin,text=True,capture_output=True,timeout=30)
            if result.returncode:raise AssertionError(result.stderr)
        compile([str(APP/'main.c')],'host-app',['-DGAP107_HOST=1'])
        compile([str(APP/'host_reference.c')],'oracle')
        compile(['-x','c','-'],'driver',stdin=DRIVER)

    def run_host(self,name,*args):
        return subprocess.run([str(self.out/name),*args],text=True,capture_output=True,timeout=10)

    def test_independent_stage_by_stage_ieee_results(self):
        result=self.run_host('oracle');self.assertEqual(result.returncode,0,result.stderr)
        rows=[json.loads(s) for s in result.stdout.splitlines()]
        self.assertEqual([r['dot'] for r in rows],[0,256])
        self.assertEqual([r['correction'] for r in rows],[0,0])
        self.assertEqual(rows[0]['stage_bits'],[0,0,0x7f800000,0,0x7fc00000,0x7fc00000])
        self.assertEqual(rows[1]['stage_bits'],[0x43800000,0,0x7fc00000,0x7fc00000,0x7fc00000,0x7fc00000])
        self.assertEqual(rows[0]['stage_flags'],[0,0,0,0,16,0])
        self.assertEqual(rows[1]['stage_flags'],[0,0,0,16,0,0])
        self.assertTrue(all(r['bits']==0x7fc00000 and r['flags']==16 and r['csr_flags']==24 for r in rows))

    def test_host_full_vrf_csr_guards(self):
        r=self.run_host('host-app');self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        self.assertIn('PASSED: qbs_gap107_invalid_nan checks=44 errors=0',r.stdout)
        self.assertIn('vrf_words=2048 initial_words=2048 source_bytes=6880 csr_words=24',r.stdout)
        self.assertEqual(r.stdout.count('checks=18 errors=0'),2)

    def test_full_contract_mutations_rejected_both_phases(self):
        for phase in ('0','1'):
            for mutation in ('dest','tail','register','initial','source','activation','descriptor','guard',
                'sourceguard','csrguard','vl','vtype','vstart','frm','flags','vcsr','skip',
                'byte:weights:799','byte:activation:2495','byte:descriptor:143',
                'byte:initial:4223','byte:actual:4223','byte:csr:159'):
                with self.subTest(phase=phase,mutation=mutation):
                    r=self.run_host('host-app',mutation,phase)
                    self.assertNotEqual(r.returncode,0,r.stdout)

    def driver(self,mode):
        r=self.run_host('driver',mode);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        return [int(x) for x in r.stdout.split()]

    def test_two_invalids_then_quiet_nan_keep_nv_or_not_add(self):
        self.assertEqual(self.driver('priority'),[0x7fc00000,16,1])

    def test_infinity_addition_signs(self):
        self.assertEqual(self.driver('same-inf'),[0x7f800000,0,1])
        self.assertEqual(self.driver('opposite-inf'),[0x7fc00000,16,1])

    def test_fp16_quieting_is_not_fp32_signalling_nv(self):
        self.assertEqual(self.driver('half-snan'),[0x7fc02000,0,1])
        self.assertEqual(self.driver('fp32-snan'),[0x7fc00000,16,1])

    def test_unsupported_finite_arithmetic_rejected(self):
        self.assertEqual(self.driver('unsupported')[2],0)

    def test_individual_bsums_quant_and_size_rejected(self):
        for mode in ('bsum-cancel','quant','size'):
            self.driver(mode)


class Static(unittest.TestCase):
    def test_real727_sources_compiled20_zeros_no_coverage_claim(self):
        result=c.contract()
        self.assertEqual(len(result['targets']),20)
        self.assertEqual(len({(t['scope'],t['point']['raw_index']) for t in result['targets']}),20)
        self.assertTrue(all(not t['before_hit'] and t['measured_hit'] is None for t in result['targets']))
        self.assertFalse(result['coverage_increment_measured']);self.assertFalse(result['simulations_started'])
        self.assertFalse(result['coverage_admitted']);self.assertEqual(result['expected_csr_fflags'],[24,24])

    def test_target_already_hit_rejected(self):
        with patch.object(c.mapping,'bit',return_value=True):
            with self.assertRaises(ValueError):c.contract()

    def test_old_source_pin_drift_rejected(self):
        with patch.object(c.mapping.life,'check',side_effect=ValueError('source drift')):
            with self.assertRaises(ValueError):c.contract()

    def test_two_opcodes_csr_capture_precedes_snapshot(self):
        asm=(APP/'execute.S').read_text()
        self.assertEqual(asm.count('MATRIX_EXEC '),3)
        self.assertIn('MATRIX_EXEC 0, 1, 0x00b5045b',asm)
        self.assertIn('MATRIX_EXEC 1, 1, 0x00b5045b',asm)
        tail=asm.split('.word \\word',1)[1]
        self.assertLess(tail.index('sd t0, 88(a4)'),tail.index('vsetvli zero, t0, e32, m8'))
        self.assertIn('csrwi fflags, 8',asm)


if __name__=='__main__':unittest.main()
