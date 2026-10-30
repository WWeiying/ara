import unittest
from run_sums_model_qemu import check


def fixture():
    lines=[]
    for mode in (0,1):
        lines.append(f'M4_SUMS_MODEL_BEGIN enabled={mode}')
        lines.append(f'GGML_RISCV_QBS_M4_SELECTED source=cache tag={2+mode} event=compute_rvv k=1536')
        lines += ['GGML_RISCV_QUANT_PREFILL status=0 mapping=0 selection=0 commands=4 groups=1']*56
        for _ in range(112):
            lines.append('GGML_RISCV_QUANT_KV status=0 command_attempts=2')
            lines.append(f'GGML_RISCV_QUANT_KV_REGISTER_PV enabled=1 status=0 completed_groups=8')
        lines.append(f'M4_SUMS_MODEL_END enabled={mode}')
    lines += [f'M4_SUMS_MODEL_COMPARE kind={k} step={s} outputs=151936 bitwise=1 csr_equal=1 token_equal=1'
              for k in range(2) for s in range(3)]
    lines += ['M4_SUMS_MODEL_SUITE_PASS comparisons=6 performance=not_measured','GUEST_TEST_EXIT=0']
    return '\n'.join(lines)


class CheckTest(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(check(fixture())['logits_compared'],911616)

    def test_missing_dispatch_and_mismatch(self):
        text=fixture()
        mutations=[text.replace('tag=3','tag=2'),text.replace('enabled=1 status=0','enabled=0 status=0'),
                   text.replace('REGISTER_PV enabled=1','REGISTER_OTHER enabled=1'),
                   text.replace('bitwise=1','bitwise=0',1),
                   text.replace('GUEST_TEST_EXIT=0','GUEST_TEST_EXIT=1'),
                   text.replace('REGISTER_PV enabled=1 status=0','REGISTER_PV enabled=1 status=1')]
        for value in mutations:
            with self.assertRaises(AssertionError):check(value)


if __name__=='__main__':unittest.main()
