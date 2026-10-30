import unittest
from analyze_prepare_reuse import analyze


def example():
    text=[]
    for mode in (0,1):
        text.append(f'Q8K_MODEL_BEGIN enabled={mode}')
        for seq in (1,2):
            text.append(f'GGML_RISCV_QBS_LIFETIME seq={seq} graph_epoch=1 source_id=0xab activation_type=q8_K m=4 k=1536 bytes=7008 digest=1234 same_tensor={seq-1} reusable={seq-1} match_seq={seq-1}')
        text.append('GGML_RISCV_QBS_CROSS_OP quantization_skipped=1')
        text.append(f'Q8K_MODEL_END enabled={mode}')
        text.append('GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=2 exact_reuse_candidates=1 quantized_bytes=14016 reusable_quantized_bytes=7008 cross_op_quantization_skips=1')
    return '\n'.join(text)


class AnalyzeTest(unittest.TestCase):
    def test_complete(self):
        result=analyze(example())
        self.assertEqual(result['1']['totals']['exact_reuse_candidates'],1)
        self.assertEqual(result['1']['duplicate_sequence_gaps'],{1:1})

    def test_reject(self):
        for text in (example().replace('quantizations=2','quantizations=3',1),
                     example().replace('seq=2','seq=3',1),
                     example().replace('match_seq=1','match_seq=9',1),
                     example().replace('Q8K_MODEL_END enabled=1',''),
                     example().replace('source_id=0xab','source_id=0xcd',1)):
            with self.subTest(text=text),self.assertRaises(ValueError): analyze(text)


if __name__=='__main__': unittest.main()
