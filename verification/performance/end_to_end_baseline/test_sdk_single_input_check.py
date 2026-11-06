import re
import unittest

from test_decode_native import fixture as decode_fixture
from check_sdk_single_input import check,SUITE,ORDER


def fixture():
    text,*oracle=decode_fixture();lines=[]
    for trial,candidate in enumerate(ORDER):
        lines.append(f'SDK_SINGLE_INPUT_TRIAL_BEGIN trial={trial} candidate={candidate}')
        sequence=0
        for line in text.splitlines():
            if line.startswith('[QBS_PERF] '):
                sequence+=1
                line=re.sub(r'(?<!\S)seq=\d+(?=\s|$)',f'seq={trial*28+sequence}',line,count=1)
            lines.append(line)
        lines.append(f'SDK_SINGLE_INPUT_TRIAL_END trial={trial} candidate={candidate} status=0')
    return '\n'.join(lines+[SUITE]),oracle


class SDKSingleInputCheckTests(unittest.TestCase):
    def test_complete_pair_does_not_require_speedup(self):
        text,oracle=fixture();r=check(text,*oracle)
        self.assertEqual(r['execution_ratio'],1)
        self.assertEqual(r['region_ratio'],1)
        self.assertFalse(r['candidate_accepted_for_production'])

    def test_reject_order_scope_csr_and_service_mismatch(self):
        text,oracle=fixture()
        for old,new in (('trial=1 candidate=1','trial=1 candidate=0'),('seq=29 ','seq=1 '),
            ('vcsr=3','vcsr=5'),('outputs=896','outputs=895'),('status=0','status=1'),
            ('order=ABBA','order=AABB')):
            with self.subTest(old=old),self.assertRaises(ValueError):check(text.replace(old,new,1),*oracle)

    def test_reject_extra_command_outside_trials(self):
        text,oracle=fixture();line=next(s for s in text.splitlines() if s.startswith('[QBS_PERF] '))
        with self.assertRaises(ValueError):check(text+'\n'+line,*oracle)


if __name__=='__main__':unittest.main()
