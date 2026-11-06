import unittest
from check_output_model import check


def fixture():
    lines=[]
    for mode in range(2):
        lines += [f'OUTPUT_MODEL_BEGIN enabled={mode}',
                  'OUTPUT_MODEL_SHAPE model=qwen3_1p7b prompt_tokens=41 n_ctx=128 n_batch=64']
        for kind in range(2):
            for step in range(3):
                for layer in range(28):
                    if not step:
                        lines.append('GGML_RISCV_QUANT_PREFILL status=0 mapping=0 memory=1 runtime_called=1 selection=0 commands=32 groups=8 value_decodes=160 queries_quantized=16 key_bytes=1024 workspace=13120')
                    else:
                        lines += ['GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts=8 groups=8 value_decodes=160 executor_status=0',
                                  f'GGML_RISCV_QUANT_KV_OUTPUT_TILE enabled={mode} status=0 completed_groups=8',
                                  f'GGML_RISCV_QUANT_KV_REGISTER_PV enabled={1-mode} status=0 completed_groups=8']
                lines.append(f'OUTPUT_MODEL_STEP enabled={mode} kind={kind} step={step} token=42 fcsr=9 vcsr=5 outputs=151936')
        lines.append(f'OUTPUT_MODEL_END enabled={mode}')
    lines += [f'OUTPUT_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1' for k in range(2) for s in range(3)]
    return '\n'.join(lines+['OUTPUT_MODEL_SUITE_PASS comparisons=6 performance=not_measured','GUEST_TEST_EXIT=0'])


class ModelAuditTests(unittest.TestCase):
    def test_complete(self):self.assertEqual(check(fixture())['logits_compared'],911616)
    def test_missing_or_wrong_route(self):
        for old,new in (('OUTPUT_TILE enabled=1','OUTPUT_TILE enabled=0'),('command_attempts=8','command_attempts=0'),
                        ('outputs=151936 bitwise=1','outputs=151936 bitwise=0'),('token=42','token=43'),
                        ('memory=1','memory=0'),('prompt_tokens=41','prompt_tokens=32'),('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1')):
            with self.subTest(old=old),self.assertRaises(ValueError):check(fixture().replace(old,new,1))
    def test_missing_decode(self):
        text=fixture();line=next(l for l in text.splitlines() if l.startswith('GGML_RISCV_QUANT_KV status='))
        with self.assertRaises(ValueError):check(text.replace(line+'\n','',1))
