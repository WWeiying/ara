import unittest

from check_flags import check_log


def fixture(flags=None):
    flags = flags or [9, 11] * 8
    rows = ['THREAD_FLAGS_BEGIN kind=q4_0 layout=token_major visible=128 threads=2 calls=16 '
            'quant_kv=0 grouped=unset initial_fcsr=8 initial_vcsr=5']
    rows.extend(f'THREAD_FLAGS_CALL call={i} outputs=1536 fcsr={value} vcsr=5 digest=0123456789abcdef exact=1'
                for i, value in enumerate(flags))
    rows.extend(['THREAD_FLAGS_COMPLETE calls=16 outputs_each=1536 all_bits_equal=1 quant_kv=0 '
                 'grouped=unset performance=not_measured', 'GUEST_TEST_EXIT=0'])
    return '\n'.join(rows) + '\n'


class DiagnosticCheck(unittest.TestCase):
    def test_variation_supports_hypothesis(self):
        result = check_log(fixture())
        self.assertEqual(result['observed_fcsr'], [9, 11])
        self.assertTrue(result['hypothesis_supported'])

    def test_constant_is_inconclusive(self):
        result = check_log(fixture([11] * 16))
        self.assertFalse(result['hypothesis_supported'])
        self.assertEqual(result['interpretation'], 'inconclusive')

    def test_no_dispatch_truncation_and_failure(self):
        for text in (fixture() + 'GGML_RISCV_QUANT_KV status=0\n',
                     fixture().replace('GUEST_TEST_EXIT=0', ''),
                     fixture().replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1'),
                     fixture() + 'GROUPED_GGML_FAIL reason=numerical\n',
                     fixture().replace('call=2 ', 'call=1 ', 1)):
            with self.assertRaises(ValueError):
                check_log(text)

    def test_full_outputs_and_csr_preservation(self):
        for old, new in (('outputs=1536', 'outputs=1535'), ('exact=1', 'exact=0'),
                         ('fcsr=9', 'fcsr=1'), ('fcsr=9', 'fcsr=41'),
                         ('vcsr=5 digest', 'vcsr=4 digest'),
                         ('digest=0123456789abcdef', 'digest=1123456789abcdef')):
            with self.subTest(new=new), self.assertRaises(ValueError):
                check_log(fixture().replace(old, new, 1))


if __name__ == '__main__':
    unittest.main()
