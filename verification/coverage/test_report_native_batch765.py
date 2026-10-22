import copy
import unittest
import report_native_batch765 as r


class Population765(unittest.TestCase):
    def test_actual_manifest_prefix_full6162_OR(self):
        b=r.life.read_bound(r.MANIFEST,r.MANIFEST_SHA)
        p=r.predecessor.prep.MANIFEST
        old=r.life.read_bound(p,r.predecessor.prep.MANIFEST_SHA)
        beforepath=p.parent/'combined-bits.json'
        before=r.life.read_bound(beforepath,old['output_pins'][str(beforepath)])
        def read(name):
            path=r.MANIFEST.parent/name;return r.life.read_bound(path,b['output_pins'][str(path)])
        bits,single=read('combined-bits.json'),read('single-bits.json')
        r.full_or(before,bits,single)
        wrong=copy.deepcopy(bits);wrong['tests'][0]='foreign'
        with self.assertRaises(Exception):r.full_or(before,wrong,single)
        wrong=copy.deepcopy(bits)
        metric=next(iter(wrong['metrics']));scope=next(iter(wrong['metrics'][metric]))
        wrong['metrics'][metric][scope]['checksum']='foreign'
        with self.assertRaises(Exception):r.full_or(before,wrong,single)

    def test_reviewed_native_scope_unchanged_and_runtime_bound(self):
        ns=r.namespace()
        self.assertEqual(ns['CAPTURES'],r.predecessor.CAPTURES)
        self.assertEqual(ns['TCL'],r.predecessor.TCL)
        self.assertIs(ns['records'],r.predecessor.records)
        self.assertIn('batch_scale',ns['verify'].__code__.co_consts)
        save=next(c for c in ns['verify'].__code__.co_consts
                  if hasattr(c,'co_name') and c.co_name=='save')
        self.assertIn('retained',save.co_consts)
        self.assertIs(ns['snapshot_stdout'],r.snapshot_stdout)
        self.assertIs(ns['run'].__globals__,ns)


if __name__=='__main__':unittest.main()
