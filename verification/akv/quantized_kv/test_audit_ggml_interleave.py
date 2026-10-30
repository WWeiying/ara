"""Additional epoch/context and independently emitted quantization checks."""
import unittest
from audit_ggml_interleave import check_identity
from test_ggml_interleave_check import fixture


def identity_fixture():
    lines = []
    native = False
    count = 0
    for line in fixture().splitlines():
        if line.startswith('QUANT_INTERLEAVE_BEGIN '):
            native = 'mode=native ' in line
            count = 0
        if line.startswith('GGML_RISCV_QBS_COMMAND '):
            sequence = 2 if native else 10 + count // 2
            if count == 0 or (not native and count == 2):
                lines.append(f'GGML_RISCV_QBS_LIFETIME seq={sequence} graph_epoch=1 activation_type=q8_K bytes=292 quantize_time_valid=1 source_id=0x1234')
            line = line.replace('activation_seq=2 ', f'activation_seq={sequence} ')
            count += 1
        if line == 'GUEST_TEST_EXIT=0':
            lines.append('GGML_RISCV_QBS_LIFETIME_SUMMARY quantizations=8 quantized_bytes=2336 cross_op_fill=4 cross_op_reuse=4 cross_op_release=4 cross_op_quantization_skips=4 cross_op_activation_bytes_saved=1168')
        lines.append(line)
    return '\n'.join(lines) + '\n'


class IdentityAuditTest(unittest.TestCase):
    def test_complete(self):
        result = check_identity(identity_fixture())
        self.assertEqual(result['quantization_skips'], 4)
        self.assertEqual(result['quantized_bytes_saved'], 1168)

    def test_wrong_command_identity(self):
        for old, new in [('context_id=0', 'context_id=1'),
                         ('seq=1 graph_epoch=1', 'seq=1 graph_epoch=9'),
                         ('activation_seq=10 ', 'activation_seq=77 ')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_identity(identity_fixture().replace(old, new, 1))

    def test_quantization_evidence_not_optional(self):
        text = identity_fixture()
        for old, new in [('quantizations=8 ', 'quantizations=9 '),
                         ('cross_op_quantization_skips=4 ', 'cross_op_quantization_skips=0 '),
                         ('quantize_time_valid=1 ', 'quantize_time_valid=0 '),
                         ('GGML_RISCV_QBS_LIFETIME seq=10 ', 'IGNORED_QUANTIZATION seq=10 ')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_identity(text.replace(old, new, 1))


if __name__ == '__main__': unittest.main()
