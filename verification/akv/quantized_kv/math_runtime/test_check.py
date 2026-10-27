import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('math_replay_checker',Path(__file__).with_name('check.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def fixture():
    pairs=[dict(input_bits='bf800000',output_bits='3ebc5ab2') for _ in range(768)]
    lines=['EXP_REPLAY_CAP calls=768 library=linked_linux_libm performance=not_measured']
    lines.extend(f'EXP_REPLAY i={i} input=bf800000 result=3ebc5ab2 flags=1 errno=123' for i in range(768))
    lines+=['EXP_REPLAY_RESULT calls=768 differences=0 errors=0','GUEST_TEST_EXIT=0']
    return pairs,lines


class ReplayChecker(unittest.TestCase):
    def test_complete_nonperformance_receipt(self):
        pairs,lines=fixture();result=module.check('\n'.join(lines),pairs)
        self.assertFalse(result['performance_measured']);self.assertEqual(result['calls'],768)
        self.assertEqual(result['linux_newlib_bit_differences'],0)
    def test_missing_or_reordered(self):
        pairs,lines=fixture()
        for bad in (lines[:-1],lines[:5]+lines[6:],lines[:1]+[lines[2],lines[1]]+lines[3:]):
            with self.assertRaises(ValueError):module.check('\n'.join(bad),pairs)
    def test_changed_argument_flags_and_large_error(self):
        pairs,lines=fixture()
        for old,new in (('input=bf800000','input=c0000000'),('flags=1','flags=16'),
                        ('result=3ebc5ab2','result=3ebc5ab8')):
            bad=list(lines);bad[1]=bad[1].replace(old,new)
            with self.subTest(change=old),self.assertRaises(ValueError):module.check('\n'.join(bad),pairs)
    def test_negative_infinity(self):
        pairs,lines=fixture();pairs[0]=dict(input_bits='ff800000',output_bits='00000000')
        lines[1]='EXP_REPLAY i=0 input=ff800000 result=00000000 flags=0 errno=123'
        self.assertEqual(module.check('\n'.join(lines),pairs)['calls'],768)
        lines[1]=lines[1].replace('flags=0','flags=1')
        with self.assertRaises(ValueError):module.check('\n'.join(lines),pairs)


if __name__=='__main__':unittest.main()
