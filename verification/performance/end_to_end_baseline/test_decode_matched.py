import unittest
from pathlib import Path

from check_decode_matched import check, SCOPE, ORDER
from check_decode_rvv import K, PROFILE
from check_projection_native import checksum


def fixture(slower=False):
    native=[bytes([i+1])*256 for i in range(7)]
    rvv=[bytes([i+11])*256 for i in range(7)]
    packed=[bytes(n) for n in (2336,2336,7008,2336)];flags=[0]*7
    lines=[SCOPE]
    for trial,backend in enumerate(ORDER):
        for stage in range(4):
            lines.append(f'MATCHED_DECODE_PREP trial={trial} backend={backend} stage={stage} cycles=10 '
                         f'fcsr=9 vcsr=3 vstart=0 checksum={checksum(packed[stage])} errors=0')
        execution=80 if backend else 100
        if slower and backend: execution=150
        for part in range(7):
            lines.append(f'MATCHED_DECODE_PART trial={trial} backend={backend} part={part} profile={PROFILE[part]} '
                         f'k={K[part]} admission=10 execution={execution} fcsr=9 vcsr=3 vstart=0 '
                         f'checksum={checksum((native if backend else rvv)[part])} errors=0')
        lines.append(f'MATCHED_DECODE_TRIAL trial={trial} backend={backend} preparation=40 admission=70 '
                     f'execution={execution*7} region={120+execution*7} commands={14 if backend else 0} '
                     f'q4_calls={0 if backend else 4} q6_calls={0 if backend else 192} outputs=448 errors=0')
    lines.append('MATCHED_DECODE_RESULT trials=4 native_commands=28 outputs_checked=1792 errors=0')
    return '\n'.join(lines),native,rvv,packed,flags


class MatchedDecodeTests(unittest.TestCase):
    def test_actual_oracle_family_and_all_work_required(self):
        result=check(*fixture())
        self.assertTrue(result['matched_csr_completion'])
        self.assertFalse(result['whole_model'])
        self.assertGreater(result['speedups']['region'],1)
        text,native,rvv,packed,flags=fixture()
        for a,b in (('backend=1 part=1','backend=0 part=1'),('vcsr=3','vcsr=5'),
                    ('outputs_checked=1792','outputs_checked=896'),('execution=80','execution=0'),
                    ('q6_calls=192','q6_calls=128'),('errors=0','errors=1')):
            with self.subTest(a=a),self.assertRaises(ValueError):
                check(text.replace(a,b,1),native,rvv,packed,flags)
        with self.assertRaises(ValueError): check(text,rvv,native,packed,flags)

    def test_a_slower_native_path_is_still_functional(self):
        self.assertLess(check(*fixture(True))['speedups']['region'],1)

    def test_bad_conservation_duplicate_or_incomplete_work_rejects(self):
        text,*oracle=fixture()
        for changed in (text.replace('region=820','region=100',1),
                        text+'\nMATCHED_DECODE_RESULT trials=4 native_commands=28 outputs_checked=1792 errors=0',
                        text.replace('MATCHED_DECODE_PREP trial=0','OTHER trial=0',1)):
            with self.assertRaises(ValueError): check(changed,*oracle)

    def test_source_has_same_completion_before_both_timer_ends(self):
        text=(Path(__file__).parent/'decode_matched.cpp').read_text()
        self.assertLess(text.index('prepared[s]=completed_state();'),text.index('prep[s]=cycle()-start;'))
        self.assertLess(text.index('finished[p]=completed_state();'),text.index('const uint64_t c=cycle();'))
        self.assertNotIn('before_fcsr=',text)
        self.assertIn('const unsigned order[]={0,1,1,0};',text)
        self.assertNotIn('qbs_ref_execute',text)


if __name__=='__main__':unittest.main()
