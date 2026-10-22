import unittest
from build_masklogical_same_source_native import native_gate, sha, ORIGINAL, ORIGINAL_SHA


GOOD = '''00008000 <main>:
8000: jalr 0(ra) <printf_>

00008010 <printf_>:
8010: ret

00008020 <_putchar>:
8020: ret

00008030 <_eoc>:
8030: sd a0, 0(t0)
'''


class NativeGateTests(unittest.TestCase):
    def test_original_computation_is_sealed(self):
        self.assertEqual(sha(ORIGINAL), ORIGINAL_SHA)

    def test_native_output_passes(self):
        self.assertEqual(native_gate(GOOD)['status'], 'PASS')

    def test_newlib_target_rejected(self):
        with self.assertRaises(ValueError):
            native_gate(GOOD.replace('printf_', 'printf'))

    def test_dormant_syscall_rejected(self):
        with self.assertRaises(ValueError):
            native_gate(GOOD + '\n00008040 <_fstat>:\n8040: ecall\n')

    def test_anonymous_ecall_rejected(self):
        with self.assertRaises(ValueError):
            native_gate(GOOD + '\n8040: ecall\n')


if __name__ == '__main__':
    unittest.main()
