import unittest
from run_packed_installed import check_selected, select_packed


class PackedInstalledTests(unittest.TestCase):
    def test_selector_preserves_original(self):
        source = '    env("GGML_RISCV_QBS_M4_CACHE", mode ? "1" : "0");\n'
        self.assertEqual(select_packed(source), source + source.replace('M4_CACHE', 'M4_PACKED'))
        with self.assertRaises(ValueError):
            select_packed(select_packed(source))

    def test_executed_identity_not_just_hits(self):
        text = ('Q8K_MODEL_BEGIN enabled=0\n'
                'GGML_RISCV_QBS_M4_SELECTED source=direct tag=1 path=rvv k=1536\n'
                'Q8K_MODEL_BEGIN enabled=1\n'
                'GGML_RISCV_QBS_M4_SELECTED source=cache tag=2 event=compute_rvv k=1536\n')
        self.assertEqual(check_selected(text, 'model'), {0: 1, 1: 1})
        for bad in (text.replace('tag=2', 'tag=1'), text.replace('compute_rvv', 'hit'),
                    text.replace('compute_rvv', 'compute_generic')):
            with self.assertRaises(ValueError):
                check_selected(bad, 'model')


if __name__ == '__main__':
    unittest.main()
