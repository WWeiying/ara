import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('tiled_checker',Path(__file__).with_name('check.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def log():
    return '\n'.join([f'M4_TILED_TRIAL id={i} tiled={mode} first=10 second=20 third=30 total=60 errors=0'
                      for i,mode in enumerate((0,1,1,0))]+
                     ['M4_TILED_RESULT errors=0 trials=4 calls=12 m=4 k=1536'])


class TiledChecker(unittest.TestCase):
    def test_complete(self):
        result=module.check(log());self.assertEqual(result['speedup'],1)
        self.assertEqual(result['baseline_cycles'],120)
    def test_failure_and_wrong_timing(self):
        for old,new in (('errors=0','errors=1'),('total=60','total=59'),('id=2','id=1'),('tiled=1','tiled=0')):
            with self.subTest(old=old),self.assertRaises(ValueError):module.check(log().replace(old,new,1))
    def test_partial(self):
        with self.assertRaises(ValueError):module.check('\n'.join(log().splitlines()[1:]))


if __name__=='__main__':unittest.main()
