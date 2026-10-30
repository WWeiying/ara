import unittest
from check import check_log


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.golden = bytes(7008)
        signature = 14695981039346656037
        for byte in self.golden * 3:
            signature = ((signature ^ byte)*1099511628211) & ((1 << 64)-1)
        lines = []
        for i in range(4):
            c = int(i in (1, 2))
            lines.append(f'CACHE_COST_TRIAL id={i} reuse={c} total=100 first=30 second=20 third=20 '
                         f'producers={1 if c else 3} hits={2*c} misses={c} stores={c} '
                         f'compare_bytes={49152*c} copied_bytes={45600*c} fcsr=17 vcsr=5 '
                         f'errors=0 signature={signature:016x}')
        self.text = '\n'.join(lines + ['CACHE_COST_RESULT trials=4 errors=0'])

    def test_valid(self):
        self.assertEqual(check_log(self.text, self.golden)['speedup'], 1)

    def test_reject(self):
        for old, new in [('errors=0', 'errors=1'), ('fcsr=17', 'fcsr=16'),
                         ('hits=2', 'hits=1'), ('compare_bytes=49152', 'compare_bytes=0'),
                         ('total=100', 'total=1'), ('id=3', 'id=2'),
                         ('trials=4', 'trials=3')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_log(self.text.replace(old, new, 1), self.golden)
        with self.assertRaises(ValueError):
            check_log(self.text, bytes([1])*7008)
