import unittest
from run_graph_qemu import check_log


def fixture(native):
    lines=[]
    for k in ('q8_0','q4_0'):
        for h in (0,1):
            for e in (0,1):
                lines.append(f'PREFILL_GRAPH_BEGIN kind={k} hole={h} enabled={e}')
                if native and e:
                    lines.append('GGML_RISCV_QUANT_PREFILL mapping=0 memory=1 runtime_called=1 '+
                        ('status=1 selection=7 commands=0 groups=0 queries_quantized=0' if h else
                         'status=0 selection=0 commands=160 groups=40 value_decodes=480 queries_quantized=320'))
                lines.append(f'PREFILL_GRAPH_END kind={k} hole={h} enabled={e} outputs=40960 max_abs=0 fcsr=9 vcsr=5')
    return '\n'.join(lines+['PREFILL_GRAPH_SUITE_PASS profiles=2 calls=8 performance=not_measured','GUEST_TEST_EXIT=0'])


class GraphCheckTest(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(check_log(fixture(False),False)['calls'],8)
        self.assertEqual(check_log(fixture(True),True)['native_completed'],2)

    def test_mutations(self):
        text=fixture(True)
        for old,new in [('commands=160','commands=0'),('memory=1','memory=0'),
                        ('fcsr=9','fcsr=0'),('vcsr=5','vcsr=0'),
                        ('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1'),('selection=7','selection=0')]:
            with self.subTest(old=old),self.assertRaises(AssertionError):
                check_log(text.replace(old,new,1),True)
        with self.assertRaises(AssertionError):check_log(fixture(False),True)
        with self.assertRaises(AssertionError):check_log(text,False)


if __name__=='__main__':unittest.main()
