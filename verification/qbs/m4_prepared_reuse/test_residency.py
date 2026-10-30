import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('m4_residency',Path(__file__).with_name('analyze_capture_residency.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ResidencyTest(unittest.TestCase):
    def ops(self):
        data=b''.join(bytes([i])*4096 for i in range(3))
        return [(name,256,12,data) for name in ('q','v','k')]
    def test_thrash(self):
        r=module.replay(self.ops(),2)['totals']
        self.assertEqual((r['hits'],r['misses'],r['evictions']),(0,9,7))
    def test_fit(self):
        r=module.replay(self.ops(),3)['totals']
        self.assertEqual((r['hits'],r['misses'],r['evictions']),(6,3,0))
    def test_tail_and_limit(self):
        ops=[('q',256,15,b'\x01'*(256*15*4))]
        r=module.replay(ops,8,max_entry=1)['totals']
        self.assertEqual((r['hits'],r['misses'],r['uncached'],r['tail_rows']),(0,0,3,3))
    def test_changed_value(self):
        ops=[('q',256,4,b'a'*4096),('v',256,4,b'b'*4096)]
        self.assertEqual(module.replay(ops,8)['totals']['hits'],0)
    def test_prefix_does_not_thrash(self):
        r=module.replay(self.ops(),2,policy='prefix')['totals']
        self.assertEqual((r['hits'],r['misses'],r['uncached'],r['evictions']),(4,2,3,0))
    def test_larger_batch_prefix(self):
        data=b''.join(bytes([i])*4096 for i in range(9))
        ops=[(name,256,36,data) for name in ('q','v','k')]
        self.assertEqual(module.replay(ops,8)['totals']['hits'],0)
        r=module.replay(ops,8,policy='prefix')['totals']
        self.assertEqual((r['hits'],r['misses'],r['uncached']),(16,8,3))
    def test_geometry(self):
        with self.assertRaises(ValueError):module.replay([('q',256,4,b'')],8)


if __name__=='__main__':unittest.main()
