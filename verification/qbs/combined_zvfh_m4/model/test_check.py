import unittest
from check import check


def fixture():
    rows = []
    for mode in range(2):
        rows.append(f'Q8K_MODEL_BEGIN enabled={mode}')
        rows.append(f'GGML_RISCV_QBS_Q8K_M4_PREPARE enabled={mode} path={"rvv" if mode else "generic"} k=1536')
        rows.append('GGML_RISCV_QBS_CALL type=q4_K mode=gemm k=1536 input_rows=4 output_rows=1536 split_k=0')
        for kind in range(2):
            for step in range(3):
                rows.append(f'Q8K_MODEL_STEP enabled={mode} kind={kind} step={step} token=42 fcsr=9 vcsr=3 outputs=151936')
        rows.append(f'Q8K_MODEL_END enabled={mode}')
    for kind in range(2):
        for step in range(3):
            rows.append(f'Q8K_MODEL_COMPARE kind={kind} step={step} outputs=151936 bitwise=1 csr_equal=1 token_equal=1')
    rows.append('Q8K_MODEL_SUITE_PASS comparisons=6 performance=not_measured')
    rows.append('GUEST_TEST_EXIT=0')
    return '\n'.join(rows)


class ModelChecker(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(check(fixture())['comparisons'], 6)

    def test_mutations(self):
        for old, new in [('path=rvv', 'path=generic'), ('token=42', 'token=43'),
                         ('vcsr=3', 'vcsr=8'), ('fcsr=9', 'fcsr=1'),
                         ('bitwise=1', 'bitwise=0'), ('outputs=151936', 'outputs=1'),
                         ('k=1536', 'k=8960'), ('enabled=1 path=rvv', 'enabled=0 path=rvv')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check(fixture().replace(old, new, 1))

    def test_truncation(self):
        lines = fixture().splitlines()
        for i in range(len(lines)):
            with self.assertRaises(ValueError):
                check('\n'.join(lines[:i]))

    def test_guest_error(self):
        with self.assertRaises(ValueError):
            check(fixture()+'\nQ8K_MODEL_FAIL reason=child')


if __name__ == '__main__':
    unittest.main()
