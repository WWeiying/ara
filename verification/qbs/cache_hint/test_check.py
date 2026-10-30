import unittest
from check import check_log


def log():
    lines=['CACHE_HINT_REFERENCE groups=3 errors=0']
    for i in range(4):
        hint=int(i in (1,2))
        lines.append(f'CACHE_HINT_TRIAL id={i} hint={hint} total=100 producers=3 hits=6 misses=3 '
                     f'stores=3 compare_bytes={294912 if hint else 442368} copied_bytes=136800 '
                     'fcsr=17 vcsr=5 errors=0 signature=1234')
    return '\n'.join(lines+['CACHE_HINT_RESULT trials=4 errors=0'])


class CheckerTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(check_log(log(),bytes(7008))['speedup'],1)

    def test_reject(self):
        for original,replacement in [('errors=0','errors=1'),('total=100','total=0'),
            ('hits=6','hits=5'),('fcsr=17','fcsr=0'),('signature=1234','signature=5678'),
            ('hint=0','hint=1'),('compare_bytes=442368','compare_bytes=294912'),
            ('CACHE_HINT_RESULT trials=4 errors=0','')]:
            with self.subTest(original=original):
                with self.assertRaises(ValueError):
                    check_log(log().replace(original,replacement,1),bytes(7008))
        with self.assertRaises(ValueError):check_log(log()+log(),bytes(7008))
        with self.assertRaises(ValueError):check_log(log()+'\nUVM_FATAL failure',bytes(7008))


if __name__=='__main__':unittest.main()
