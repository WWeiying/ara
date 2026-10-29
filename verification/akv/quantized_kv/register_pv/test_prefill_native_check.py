import unittest
from check_prefill_native import check_log


def fixture(q4):
    lines=['REGISTER_PREFILL_SCOPE whole_call=1 admission=1 scatter=1 baseline=grouped_shared_rvv',
           'REGISTER_PREFILL_LAYOUT token_major=1 physical_kv_heads=8 selected_head=0',
           f'REGISTER_PREFILL_CAP q4={q4} rows=8 d=128 first_query=16 tokens=20 trials=4']
    for i,shared in enumerate((0,1,1,0)):
        lines += [f'REGISTER_PREFILL_BEGIN trial={i} shared={shared}',
                  f'REGISTER_PREFILL_PANEL trial={i} panels=1 key_bytes={1440 if q4 else 2720}',
                  f'REGISTER_PREFILL_RESULT trial={i} shared={shared} cycles={100 if shared else 200} commands=4 values=20 fcsr=1 vcsr=5 errors=0 hex='+('00000000'*1024)]
    return '\n'.join(lines+['REGISTER_PREFILL_SUITE_PASS'])


class PairCheck(unittest.TestCase):
    def test_valid(self):
        for q4 in (0,1):
            self.assertEqual(check_log(fixture(q4),bytes(163840),q4)['speedup'],2)

    def test_reject(self):
        text=fixture(1)
        variants=[text.replace('values=20','values=74',1),
                  text.replace('panels=1','panels=4',1),
                  text.replace('errors=0','errors=1',1),
                  text.replace('hex=00000000','hex=3f800000',1),
                  text.replace('trial=1 shared=1','trial=1 shared=0'),
                  text.replace('baseline=grouped_shared_rvv','baseline=per_query_qbs'),
                  text.replace('REGISTER_PREFILL_SUITE_PASS','')]
        for value in variants:
            with self.assertRaises(ValueError):check_log(value,bytes(163840),1)


if __name__=='__main__':unittest.main()
