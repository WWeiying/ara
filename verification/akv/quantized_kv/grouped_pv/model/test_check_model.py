"""Synthetic protocol mutations only, not actual-model evidence."""
import unittest

from check_model import check_log, SUITE


def fixture(prefill=True):
    lines = []
    for kind, row in (('q8_0', 136), ('q4_0', 72)):
        for grouped, mode in enumerate(('baseline', 'candidate')):
            lines.extend(['llama_context: n_ctx                 = 256',
                          f'GROUPED_MODEL_BEGIN kind={kind} mode={mode} layers=28 '
                          'prompt_tokens=4 generated=3 context=128 threads=1'])
            for step in range(3):
                for projection in ('q4_K', 'q6_K'):
                    lines.append(f'GGML_RISCV_QBS_CALL type={projection} mode={"gemm" if step == 0 else "gemv"} '
                                 f'k=32 input_rows={4 if step == 0 else 1} output_rows=128 split_k=0')
                if step or prefill:
                    for _ in range(28):
                        lines.append('GGML_RISCV_QUANT_KV ' +
                                     ('status=0 mapping=0 memory=1 runtime_called=1 command_attempts=4 '
                                      f'groups=2 value_decodes={2 * (4 + step)} executor_status=0' if step else
                                      'status=1 mapping=5 memory=0 runtime_called=0 command_attempts=0 '
                                      'groups=0 value_decodes=0 executor_status=0'))
                        lines.append(f'GGML_RISCV_QUANT_KV_LAYOUT selection=0 key_panels={2 if step else 0} '
                                     f'key_bytes={2 * (4 + step) * row if step else 0} workspace=13120 '
                                     f'k_token_stride={2 * row} k_head_stride={row}')
                        lines.append(f'GGML_RISCV_QUANT_KV_PV grouped={grouped} completed_groups={2 if step else 0}')
                lines.extend([f'GROUPED_MODEL_CSR kind={kind} mode={mode} step={step} flags=9 vcsr=5',
                              f'GROUPED_MODEL_TOKEN kind={kind} mode={mode} step={step} token={10 + step} piece_hex=20'])
            lines.append(f'GROUPED_MODEL_END kind={kind} mode={mode} generated=3 vocab=100')
        for step in range(3):
            lines.append(f'GROUPED_MODEL_COMPARE kind={kind} step={step} common_prefix=1 top1_equal=1 '
                         'outputs=100 bitwise=1 csr_equal=1 max_abs=0 rmse=0 kl=0')
    lines.append(SUITE)
    for kind in ('Q4_K', 'Q6_K'):
        lines.append(f'GGML_RISCV_QBS_EXEC type={kind} gemv_calls=8 gemm_calls=4 input_rows=24 '
                     'output_rows=1536 activation_elements=768 output_elements=3072 dot_elements=98304 '
                     'split_calls=0 commands_m1=16 commands_m2=0 commands_m3=0 commands_m4=8 '
                     'commands_m5=0 commands_m6=0 commands_m7=0 commands_m8=0 native_qbexec=24 '
                     'emulated_commands=0 command_dot_elements=98304 segmented_commands=0 '
                     'context_fill=0 context_reuse=0 context_release=0')
    lines.append('GUEST_TEST_EXIT=0')
    return '\n'.join(lines) + '\n'


class ModelAcceptance(unittest.TestCase):
    def reject(self, old, new):
        text = fixture()
        self.assertIn(old, text)
        with self.assertRaises(ValueError):
            check_log(text.replace(old, new, 1))

    def test_complete_and_optional_prefill(self):
        for prefill in (False, True):
            checked = check_log(fixture(prefill))
            self.assertEqual(checked['native_calls'], 224)
            self.assertEqual(checked['native_command_attempts'], 896)
            self.assertEqual(checked['key_bytes'], 256256)
            self.assertEqual(checked['value_decodes'], 2464)
            self.assertEqual(checked['projection_calls'], 24)
            self.assertEqual(checked['baseline'], 'qbs_attention_grouped_default_off')
            self.assertFalse(checked['rtl_performance'])
        self.assertEqual(check_log(fixture().replace('\n', '\r\n'))['status'], 'PASS')

    def test_exact_grouped_selection_and_native_work(self):
        for old, new in (('PV grouped=0 completed_groups=2', 'PV grouped=1 completed_groups=2'),
                         ('PV grouped=1 completed_groups=2', 'PV grouped=0 completed_groups=2'),
                         ('completed_groups=2', 'completed_groups=0'),
                         ('command_attempts=4', 'command_attempts=0'),
                         ('value_decodes=10', 'value_decodes=12'), ('key_bytes=1360', 'key_bytes=0'),
                         ('k_token_stride=272', 'k_token_stride=136')):
            with self.subTest(new=new):
                self.reject(old, new)

    def test_complete_logits_and_greedy(self):
        for old, new in (('outputs=100', 'outputs=99'), ('bitwise=1', 'bitwise=0'),
                         ('max_abs=0 ', 'max_abs=0.001 '), ('rmse=0 ', 'rmse=nan '),
                         ('kl=0', 'kl=1e999'), ('token=10', 'token=99'),
                         ('csr_equal=1', 'csr_equal=0')):
            with self.subTest(new=new):
                self.reject(old, new)

    def test_exact_caller_csr(self):
        for old, new in (('flags=9', 'flags=11'), ('flags=9', 'flags=1'),
                         ('flags=9', 'flags=41'), ('vcsr=5', 'vcsr=4')):
            with self.subTest(new=new):
                self.reject(old, new)

    def test_projections_are_same_and_native(self):
        for old, new in (('k=32 input_rows=4', 'k=64 input_rows=4'),
                         ('gemv_calls=8', 'gemv_calls=7'),
                         ('dot_elements=98304', 'dot_elements=98305'),
                         ('native_qbexec=24', 'native_qbexec=0'),
                         ('emulated_commands=0', 'emulated_commands=1')):
            with self.subTest(new=new):
                self.reject(old, new)

    def test_context_adjacency_failures_and_extra_records(self):
        self.reject('n_ctx                 = 256', 'n_ctx                 = 128')
        self.reject('GGML_RISCV_QUANT_KV_LAYOUT selection=0', 'ordinary chatter\nGGML_RISCV_QUANT_KV_LAYOUT selection=0')
        for text in (fixture().replace('GUEST_TEST_EXIT=0', ''), fixture() + 'GUEST_TEST_EXIT=0\n',
                     fixture() + 'GROUPED_MODEL_FAIL reason=synthetic\n',
                     fixture() + 'GGML_RISCV_QUANT_KV_UNKNOWN x=1\n'):
            with self.assertRaises(ValueError):
                check_log(text)


if __name__ == '__main__':
    unittest.main()
