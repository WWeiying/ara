import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('m4_cache_checker',Path(__file__).with_name('check.py'))
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class CheckTest(unittest.TestCase):
    def log(self):
        lines=[]
        for i in range(4):
            reuse=int(i in (1,2))
            lines.append(f'M4_CACHE_SOC_TRIAL id={i} reuse={reuse} first=100 second=100 third=100 total=300 '
                         f'hits={2*reuse} misses={reuse} stores={reuse} compare_requested={49152*reuse} '
                         f'copied={45600*reuse} errors=0')
        lines.append('M4_CACHE_SOC_RESULT errors=0 trials=4 calls=12 m=4 k=1536')
        return '\n'.join(lines)
    def test_accept(self):
        r=checker.check(self.log());self.assertEqual(r['speedup'],1)
    def test_reject(self):
        for a,b in [('id=0','id=1'),('hits=2','hits=3'),('misses=1','misses=0'),
                    ('copied=45600','copied=0'),('compare_requested=49152','compare_requested=1'),
                    ('total=300','total=301'),('first=100','first=0'),('errors=0','errors=1')]:
            with self.subTest(change=a),self.assertRaises(ValueError):
                checker.check(self.log().replace(a,b,1))
    def test_incomplete_or_duplicate(self):
        for log in [self.log().splitlines()[0],self.log()+'\n'+self.log()]:
            with self.assertRaises(ValueError):checker.check(log)


if __name__=='__main__':unittest.main()
