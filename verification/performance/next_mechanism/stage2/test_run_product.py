import unittest

from run_product import DEPENDENCIES, HEADERS, LOCAL, MULTIPLIERS, PACKAGES, check_log, reference_copy


def fixture():
    rows = []
    for identity in range(27):
        shared, sew, pipes, bypass = ((identity // 12, 8 << ((identity % 12) // 3), identity % 3, 1)
                                      if identity < 24 else (1, 8, identity - 24, 0))
        flushed = int(pipes > 0 and (not shared or not bypass or sew != 8))
        retired = 210000
        rows.append(f'PRODUCT_CASE id={identity} shared={shared} sew={sew} pipes={pipes} bypass={bypass} '
                    f'accepted={retired + flushed} retired={retired} flushed={flushed} checks=220000 stalled=50')
    return '\n'.join(rows + ['STAGE2_PRODUCT_PASS configurations=24 shared_no_bypass=3']) + '\n'


class ProductHostTest(unittest.TestCase):
    def test_reference_named_endmodule(self):
        original = b'module simd_mul;\nendmodule : simd_mul\n'
        self.assertEqual(reference_copy(original, 'simd_mul'),
                         b'module simd_mul_before;\nendmodule : simd_mul_before\n')
        with self.assertRaises(ValueError):
            reference_copy(b'module simd_mul; output logic [127:0] product_o; endmodule', 'simd_mul')

    def test_complete(self):
        self.assertEqual(check_log(fixture())['configurations'], 24)

    def test_missing_duplicate_and_completion(self):
        text = fixture()
        for bad in (text.replace('PRODUCT_CASE id=0 ', 'OMITTED id=0 '),
                    text + text.splitlines()[0] + '\n', text + text.splitlines()[-1] + '\n',
                    text.replace('STAGE2_PRODUCT_PASS', 'MISSING')):
            with self.assertRaises(ValueError):
                check_log(bad)

    def test_failures_not_hidden_by_pass(self):
        for failure in ('Error:', 'Fatal:', 'Assertion failed', 'timeout'):
            with self.assertRaises(ValueError):
                check_log(fixture() + failure)

    def test_geometry_accounting_and_coverage(self):
        text = fixture()
        for bad in (text.replace('id=0 shared=0 sew=8', 'id=0 shared=0 sew=16'),
                    text.replace('accepted=210000', 'accepted=210001', 1),
                    text.replace('retired=210000', 'retired=1', 1),
                    text.replace('checks=220000', 'checks=1', 1),
                    text.replace('stalled=50', 'stalled=0', 1),
                    text.replace('flushed=1', 'flushed=0', 1)):
            with self.assertRaises(ValueError):
                check_log(bad)

    def test_narrow_explicit_inventory(self):
        self.assertEqual(len(MULTIPLIERS), 2)
        self.assertEqual(len(DEPENDENCIES), 2)
        self.assertEqual(len(PACKAGES), 8)
        self.assertEqual(len(HEADERS), 1)
        self.assertEqual(len(LOCAL), 3)
        self.assertFalse(any('vmfpu' in p or 'fpu_div' in p for p in (*MULTIPLIERS, *DEPENDENCIES, *PACKAGES)))


if __name__ == '__main__':
    unittest.main()
