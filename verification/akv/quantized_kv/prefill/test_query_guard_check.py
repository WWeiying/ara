import unittest
from query_guard_check import check_log


def example(q4):
    lines=['QUERY_GUARD_SCOPE whole_call=1 admission=1 scatter=1 baseline=grouped_qbs_query_guard',
           'QUERY_GUARD_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0',
           f'QUERY_GUARD_CAP q4={q4} rows=8 d=128 first_query=16 tokens=20 trials=4']
    for i,mode in enumerate((0,1,1,0)):
        lines += [f'QUERY_GUARD_BEGIN trial={i} shared={mode}',
                  f'QUERY_GUARD_PANEL trial={i} panels=1 key_bytes={20*(72 if q4 else 136)}',
                  f'QUERY_GUARD_RESULT trial={i} shared={mode} cycles=100 commands=4 values=20 '
                  'fcsr=1 vcsr=5 errors=0 hex='+'00000000'*1024]
    return '\n'.join(lines+['QUERY_GUARD_SUITE_PASS'])


class CheckerTest(unittest.TestCase):
    def test_valid(self):
        for q4 in (0,1):self.assertEqual(check_log(example(q4),bytes(163840),q4)['speedup'],1)

    def test_mutations(self):
        for a,b in [('values=20','values=74'),('commands=4','commands=3'),
                    ('cycles=100','cycles=0'),('panels=1','panels=2'),
                    ('fcsr=1','fcsr=0'),('errors=0','errors=1'),
                    ('baseline=grouped_qbs_query_guard','baseline=per_query_qbs'),
                    ('hex=00000000','hex=7fc00000'),('QUERY_GUARD_SUITE_PASS','')]:
            with self.subTest(a=a):
                with self.assertRaises(ValueError):check_log(example(1).replace(a,b,1),bytes(163840),1)
        with self.assertRaises(ValueError):check_log(example(1)*2,bytes(163840),1)


if __name__=='__main__':unittest.main()
