import hashlib
from pathlib import Path
import unittest

from run_product_v2 import BASE_TB_SHA256, LOCAL, REFERENCE, bench, check_log


def fixture(exhaustive=False):
    rows = []
    for identity in range(27):
        shared, sew, pipes, bypass = ((identity // 12, 8 << ((identity % 12) // 3), identity % 3, 1)
                                      if identity < 24 else (1, 8, identity - 24, 0))
        retired = 200000 if exhaustive and sew == 8 else 5000
        flushed = int(pipes > 0 and (not shared or not bypass or sew != 8))
        rows.append(f'PRODUCT_CASE id={identity} shared={shared} sew={sew} pipes={pipes} bypass={bypass} '
                    f'accepted={retired + flushed} retired={retired} flushed={flushed} checks={retired + 50} stalled=50')
    rows.append(f'STAGE2_PRODUCT_V2_PASS configurations=24 shared_no_bypass=3 exhaustive={int(exhaustive)}')
    return '\n'.join(rows) + '\n'


class ProductSuccessorTest(unittest.TestCase):
    def test_reference_fixed_not_head(self):
        self.assertEqual(REFERENCE, 'b0156f8ab6b86db0de9b44f47d1de4afb052762d')
        self.assertNotIn('vmfpu_tb.sv', LOCAL)
        self.assertNotIn('run_vmfpu.py', LOCAL)

    def test_original_tb_and_oracle_unchanged(self):
        raw = (Path(__file__).parent / 'product_tb.sv').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), BASE_TB_SHA256)
        transformed = bench(raw)
        old_model = raw.decode().split('function automatic gold_t model(', 1)[1].split('endfunction', 1)[0]
        self.assertIn(old_model, transformed)
        self.assertIn('n<6000', transformed)
        self.assertIn('$test$plusargs("EXHAUSTIVE")', transformed)
        with self.assertRaises(ValueError):
            bench(raw + b'\n')

    def test_bounded_and_exhaustive_distinct(self):
        self.assertFalse(check_log(fixture())['byte_pair_exhaustive'])
        self.assertTrue(check_log(fixture(True), True)['byte_pair_exhaustive'])
        with self.assertRaises(ValueError):
            check_log(fixture(), True)
        with self.assertRaises(ValueError):
            check_log(fixture(True), False)

    def test_missing_duplicate_malformed_and_error(self):
        text = fixture()
        for bad in (text.replace('PRODUCT_CASE id=0 ', 'MISSING id=0 '), text + text.splitlines()[0] + '\n',
                    text + 'PRODUCT_CASE malformed\n', text + text.splitlines()[-1] + '\n', text + 'Fatal:'):
            with self.assertRaises(ValueError):
                check_log(bad)

    def test_geometry_accounting_and_coverage(self):
        text = fixture()
        for old, new in (('id=0 shared=0 sew=8', 'id=0 shared=0 sew=16'),
                         ('accepted=5000', 'accepted=5001'), ('retired=5000', 'retired=1'),
                         ('checks=5050', 'checks=1'), ('stalled=50', 'stalled=0'), ('flushed=1', 'flushed=0')):
            with self.assertRaises(ValueError):
                check_log(text.replace(old, new, 1))


if __name__ == '__main__':
    unittest.main()
