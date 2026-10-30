import unittest
from model_check import check


class ModelCheck(unittest.TestCase):
    def setUp(self):
        lines=['GRAPH_CYCLES_MODEL_BEGIN enabled=0','GRAPH_CYCLES_MODEL_END enabled=0',
               'GRAPH_CYCLES_MODEL_BEGIN enabled=1']
        for gid in range(6):
            lines += [f'GGML_NODE_CYCLES graph={gid} valid=1 records=1 elapsed=50 node_sum=30 clock=rdcycle threads=1',
                      f'GGML_NODE_CYCLE graph={gid} first=0 last=2 op=26 cycles=30 ne=32,4,1,1']
        lines += ['GRAPH_CYCLES_MODEL_END enabled=1']
        lines += [f'GRAPH_CYCLES_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                  for k in range(2) for s in range(3)]
        lines += ['GRAPH_CYCLES_MODEL_SUITE_PASS comparisons=6 performance=not_measured','GUEST_TEST_EXIT=0']
        self.text='\n'.join(lines)

    def test_valid(self):
        result=check(self.text)
        self.assertEqual(result['records'],6)
        self.assertFalse(result['performance_measured'])

    def test_reject(self):
        for a,b in [('valid=1','valid=0'),('records=1','records=2'),
                    ('cycles=30','cycles=31'),('bitwise=1','bitwise=0'),
                    ('threads=1','threads=2'),('elapsed=50','elapsed=10'),
                    ('clock=rdcycle','clock=host'),('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1')]:
            with self.subTest(field=a), self.assertRaises(ValueError):
                check(self.text.replace(a,b,1))
