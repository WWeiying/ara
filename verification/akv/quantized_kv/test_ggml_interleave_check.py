"""Numerical completion alone must not satisfy context-interleaving acceptance."""
import unittest
from run_ggml_interleave import check_log


def fixture():
    lines = []
    for kind in ('q8_0', 'q4_0'):
        for run in range(3):
            native = bool(run)
            mode = 'native' if native else 'baseline'
            lines.append(f'QUANT_INTERLEAVE_BEGIN kind={kind} run={run} mode={mode} context={int(native)} cross_op={int(native)} quant_kv={int(native)} threads=1')
            command = ('GGML_RISCV_QBS_COMMAND seq=1 graph_epoch=1 activation_seq=2 linked=1 weight_type=q4_K '
                       'weight_profile=1 activation_profile=1 m=1 n=32 k_blocks=1 access={} context_id=0 '
                       'context_generation=3 segmented=0 emulated=0')
            if native:
                lines.append('GGML_RISCV_QBS_CROSS_OP graph_epoch=1 action=fill_keep source_id=0x1234 activation_profile=1 m=1 k=256 generation=3 activation_seq=0 quantization_skipped=0 activation_bytes_saved=0 next_same=1')
                lines.append(command.format(1))
                lines.append(command.format(2))
                lines.append('GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts=16 groups=2 value_decodes=256 executor_status=0')
                lines.append('GGML_RISCV_QBS_CROSS_OP graph_epoch=1 action=reuse_release source_id=0x1234 activation_profile=1 m=1 k=256 generation=3 activation_seq=2 quantization_skipped=1 activation_bytes_saved=292 next_same=0')
                lines.extend([command.format(2), command.format(3)])
            else:
                lines.extend([command.format(0)] * 4)
            lines.append(f'QUANT_INTERLEAVE_END kind={kind} run={run} mode={mode} projection_outputs=128 attention_outputs=1536 projection_digest=0123456789abcdef attention_digest=1111111111111111 fcsr=1 vcsr=3 gold_max_abs=0.00001 ordinary_max_abs=0.00001 inputs_unchanged=1')
    lines.extend(['QUANT_INTERLEAVE_SUITE_NUMERICAL_PASS profiles=2 runs=6 native_runs=4 trace_validation_required=1 performance=not_measured', 'GUEST_TEST_EXIT=0'])
    return '\n'.join(lines) + '\n'


class InterleaveCheckTest(unittest.TestCase):
    def test_complete(self):
        result = check_log(fixture())
        self.assertEqual(result['native_lifetimes'], 4)
        self.assertEqual(result['quantized_attention_command_attempts'], 64)
        self.assertFalse(result['whole_model'])

    def test_false_lifetime_rejected(self):
        for old, new in [('action=reuse_release', 'action=reuse_keep'),
                         ('activation_bytes_saved=292', 'activation_bytes_saved=0'),
                         ('access=1 context_id=0 context_generation=3', 'access=1 context_id=0 context_generation=4'),
                         ('quantization_skipped=1', 'quantization_skipped=0'),
                         ('access=1 ', 'access=0 '), ('emulated=0', 'emulated=1'),
                         ('command_attempts=16', 'command_attempts=0'), ('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1')]:
            with self.subTest(old=old), self.assertRaises(ValueError):
                check_log(fixture().replace(old, new, 1))

    def test_missing_or_extra_work_rejected(self):
        text = fixture()
        for broken in (text.replace('vcsr=3', 'vcsr=0', 1),
                       text + 'GGML_RISCV_QUANT_KV extra=1\n',
                       text.replace('mode=baseline context=0', 'mode=native context=0', 1),
                       text + 'QUANT_INTERLEAVE_FAIL reason=wrong\n'):
            with self.subTest(broken=broken[-80:]), self.assertRaises(ValueError):
                check_log(broken)


if __name__ == '__main__':
    unittest.main()
