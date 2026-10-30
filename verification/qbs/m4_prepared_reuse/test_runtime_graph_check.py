import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('m4_runtime_graph_checker',Path(__file__).with_name('run_runtime_graph.py'))
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class GraphCheckTest(unittest.TestCase):
    def log(self):
        lines=[]
        for m in range(2):
            for s in range(6):
                for e in range(2):
                    lines.append(f'M4_RUNTIME_GRAPH_BEGIN mode={m} scenario={s} epoch={e}')
                    if m==1 and s in (0,1):
                        for event in ('compute_rvv','hit'):
                            for group in range(3):
                                lines.append(f'GGML_RISCV_QBS_M4_CACHE epoch=1 group={group} event={event} fill=1')
                    lines.append(f'M4_RUNTIME_GRAPH_PASS mode={m} scenario={s} epoch={e} fc=17 vc=3')
        lines+=['M4_RUNTIME_GRAPH_SUITE_PASS graphs=24 paired_bytes=46272 performance=not_measured','GUEST_TEST_EXIT=0']
        return '\n'.join(lines)
    def test_complete(self):
        self.assertEqual(checker.check(self.log())['cache_hits'],12)
    def test_incomplete(self):
        with self.assertRaises(ValueError):checker.check(self.log().replace('GUEST_TEST_EXIT=0',''))
    def test_bad_work(self):
        for a,b in [('event=hit','event=compute_rvv'),('group=2','group=8'),
                    ('event=compute_rvv','event=compute_generic'),('scenario=0','scenario=2')]:
            with self.subTest(change=a),self.assertRaises(ValueError):checker.check(self.log().replace(a,b,1))
    def test_duplicate(self):
        with self.assertRaises(ValueError):checker.check(self.log()+'\n'+self.log())


if __name__=='__main__':unittest.main()
