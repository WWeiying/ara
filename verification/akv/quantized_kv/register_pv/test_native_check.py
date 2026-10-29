import unittest
from check_native import check_log
from test_selector_native_check import fixture


def example(q4=1):
    return (fixture(q4).replace('SELECTOR_', 'REGISTER_PV_').replace('aligned=', 'candidate=') +
            '\nREGISTER_PV_BINDINGS value=shared_rvv_q8_0 baseline=current_shared candidate=register_pv')


class NativeCheck(unittest.TestCase):
    def test_valid(self):
        for q4 in (0, 1):
            self.assertEqual(check_log(example(q4), bytes(163840), q4)['speedup'], 2)

    def test_invalid(self):
        text = example()
        for old, new in [('candidate=register_pv', 'candidate=block_max'),
                         ('commands=1', 'commands=0'), ('values=20', 'values=0'),
                         ('errors=0', 'errors=1'), ('fcsr=1', 'fcsr=2'),
                         ('panels=1', 'panels=2'), ('key_bytes=1440', 'key_bytes=0'),
                         ('trial=1 candidate=1', 'trial=1 candidate=0'),
                         ('REGISTER_PV_SUITE_PASS', ''),
                         ('00000000'*256, '7fc00000'+'00000000'*255)]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_log(text.replace(old, new, 1), bytes(163840), 1)
        with self.assertRaises(ValueError):
            check_log(text+'\nSELECTOR_SUITE_PASS', bytes(163840), 1)


if __name__ == '__main__':
    unittest.main()
