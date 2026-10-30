import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('packed_checker',Path(__file__).with_name('check.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def log():
    return '\n'.join([f'M4_PACKED_TRIAL id={i} packed={mode} first=10 second=20 third=30 total=60 errors=0'
        for i,mode in enumerate((0,1,1,0))]+['M4_PACKED_RESULT errors=0 trials=4 calls=12 m=4 k=1536'])


class PackedChecker(unittest.TestCase):
    def test_complete(self):
        result=module.check(log());self.assertEqual(result['speedup'],1)
        self.assertEqual(result['baseline_cycles'],120)
    def test_schema_order_errors_and_cycle_partition(self):
        for old,new in (('errors=0','errors=1'),('total=60','total=59'),('id=2','id=1'),('packed=1','packed=0')):
            with self.subTest(old=old),self.assertRaises(ValueError):module.check(log().replace(old,new,1))
    def test_reject_segment_candidate_receipt_and_partial(self):
        with self.assertRaises(ValueError):module.check(log().replace('PACKED','TILED'))
        with self.assertRaises(ValueError):module.check('\n'.join(log().splitlines()[1:]))


if __name__=='__main__':unittest.main()
