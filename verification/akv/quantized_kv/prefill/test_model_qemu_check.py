import unittest
from run_model_qemu import check


def fixture():
    lines=[]
    for mode in (0,1):
        lines.append(f'PREFILL_MODEL_BEGIN enabled={mode}')
        if mode:
            lines.extend(['GGML_RISCV_QUANT_PREFILL status=0 mapping=0 selection=0 commands=8 groups=6']*56)
        lines.extend(['GGML_RISCV_QUANT_KV status=0 command_attempts=12 groups=2 value_decodes=5']*112)
        lines.append(f'PREFILL_MODEL_END enabled={mode}')
    lines.extend(f'PREFILL_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
                 for k in range(2) for s in range(3))
    lines.extend(['PREFILL_MODEL_SUITE_PASS comparisons=6 performance=not_measured','GUEST_TEST_EXIT=0'])
    return '\n'.join(lines)


class ModelCheckerTest(unittest.TestCase):
    def test_complete(self):
        result=check(fixture())
        self.assertEqual(result['prefill_completed'],56)
        self.assertEqual(result['logits_compared'],911616)

    def test_reject_mutations(self):
        text=fixture()
        for old,new in [('commands=8','commands=0'),('selection=0','selection=6'),
                        ('bitwise=1','bitwise=0'),('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1'),
                        ('command_attempts=12','command_attempts=11'),
                        ('PREFILL_MODEL_BEGIN enabled=1','PREFILL_MODEL_BEGIN enabled=0')]:
            with self.subTest(old=old),self.assertRaises(AssertionError):
                check(text.replace(old,new,1))
        for marker in ('GGML_RISCV_QUANT_PREFILL ', 'GGML_RISCV_QUANT_KV '):
            lines=text.splitlines();index=next(i for i,l in enumerate(lines) if l.startswith(marker))
            del lines[index]
            with self.subTest(missing=marker),self.assertRaises(AssertionError):
                check('\n'.join(lines))


if __name__=='__main__':unittest.main()
