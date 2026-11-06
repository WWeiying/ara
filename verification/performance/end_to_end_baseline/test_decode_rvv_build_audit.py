import unittest

from collect_decode_rvv_build import symbols


TEXT = '''0000000080000000 <ggml_gemv_q4_K_32x1_q8_K>:
  80000000: 00000013 nop
0000000080000010 <quantize_row_q8_K>:
  80000010: 00000013 nop
0000000080000020 <ggml_vec_dot_q6_K_q8_K>:
  80000020: c2202373 csrr t1,vlenb
  80000024: 40000693 li a3,1024
  80000028: 00000067 jr t1 # 80000030 <ggml_vec_dot_q6_K_q8_K_vl1024.isra.0>
0000000080000030 <ggml_vec_dot_q6_K_q8_K_vl1024.isra.0>:
  80000030: 0cf7f057 \tvsetvli zero,a5,e16,mf2,ta,ma
  80000034: 02050107 \tvle8.v v2,(a0)
  80000038: ee000057 \tvwmul.vv v1,v2,v3
'''


class RVVBuildAuditTests(unittest.TestCase):
    def test_only_exact_reviewed_clone_with_real_dispatch_is_accepted(self):
        self.assertTrue(symbols(TEXT)['dispatcher_reference_checked'])
        for old, new in (('vl1024.isra.0', 'vl1024.constprop.0'), ('vlenb', 'vl'),
                         ('li a3,1024', 'li a3,512'), ('\tvwmul.vv', '\tmul'),
                         ('jr t1 # 80000030 <ggml_vec_dot_q6_K_q8_K_vl1024.isra.0>', 'jr t1')):
            with self.subTest(old=old), self.assertRaises(ValueError): symbols(TEXT.replace(old, new))

    def test_custom_reference_executor_duplicate_or_missing_kernel_rejected(self):
        for name in ('qbs_native_execute_command', 'qbs_ref_execute', 'ggml_gemv_q4_K_32x1_q8_K',
                     'ggml_vec_dot_q6_K_q8_K_vl1024.isra.1'):
            with self.assertRaises(ValueError): symbols(TEXT+'0000000080000040 <'+name+'>:\n')
        with self.assertRaises(ValueError): symbols(TEXT.replace('ggml_gemv_q4_K_32x1_q8_K', 'unrelated'))


if __name__ == '__main__': unittest.main()
