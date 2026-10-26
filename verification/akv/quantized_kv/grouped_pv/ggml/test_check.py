import unittest

from check import check_log


def valid_log():
    lines = []

    def trace(row, layout, visible, grouped, selection=0):
        accepted = not selection
        tiles = (visible + 31) // 32
        ts, hs = (row, row * 256) if layout == 'contiguous' else (2 * row, row)
        panels = 2 * tiles if accepted and layout == 'token_major' else 0
        lines.extend([
            f'GGML_RISCV_QUANT_KV status={0 if accepted else 1} mapping=0 memory=1 runtime_called=1 '
            f'command_attempts={4 * tiles if accepted else 0} groups={2 if accepted else 0} '
            f'value_decodes={2 * visible if accepted else 0} executor_status=0',
            f'GGML_RISCV_QUANT_KV_LAYOUT selection={selection} key_panels={panels} '
            f'key_bytes={2 * visible * row if panels else 0} workspace=13120 k_token_stride={ts} k_head_stride={hs}',
            f'GGML_RISCV_QUANT_KV_PV grouped={grouped} completed_groups={2 if accepted else 0}'])

    for kind, row in (('q8_0', 136), ('q4_0', 72)):
        for layout in ('contiguous', 'token_major'):
            for visible in (128, 5):
                for repeat in range(2):
                    for grouped in range(2):
                        prefix = (f'kind={kind} layout={layout} mode=native visible={visible} '
                                  f'repeat={repeat} grouped={grouped}')
                        lines.append('GROUPED_GGML_BEGIN ' + prefix)
                        trace(row, layout, visible, grouped)
                        lines.append('GROUPED_GGML_END ' + prefix +
                                     f' outputs=1536 flags=9 ref_flags=9 vcsr=5 max_abs=0.000001 exact_pair={grouped}')
        for mode in ('mask', 'thread', 'memory', 'rounding', 'reference'):
            for grouped in range(2):
                prefix = f'kind={kind} layout=token_major mode={mode} grouped={grouped}'
                lines.append('GROUPED_GGML_BEGIN ' + prefix)
                if mode in ('mask', 'rounding'):
                    trace(row, 'token_major', 128, grouped, 6 if mode == 'mask' else 2)
                flags = 41 if mode == 'rounding' else 9
                if mode == 'thread':
                    lines.append(f'GROUPED_GGML_THREAD_CSR kind={kind} mode=thread grouped={grouped} '
                                 'actual_fcsr=9 ref_fcsr=9 actual_vcsr=5 ref_vcsr=5 '
                                 'actual_new_flags=1 ref_new_flags=1 aggregate=0')
                lines.append('GROUPED_GGML_END ' + prefix +
                             f' outputs=1536 flags={flags} ref_flags={flags} vcsr=5 exact=1')
        lines.append(f'GROUPED_GGML_PROFILE_PASS kind={kind} outputs=1536 native_calls=16 fallback_calls=10 inputs_unchanged=1')
    lines.extend(['GROUPED_GGML_SUITE_PASS profiles=2 layouts=2 native_calls=32 fallback_calls=20 '
                  'executor=native_qbs performance=not_measured', 'GUEST_TEST_EXIT=0'])
    return '\n'.join(lines) + '\n'


class Acceptance(unittest.TestCase):
    def test_complete(self):
        result = check_log(valid_log())
        self.assertEqual(result['native_command_attempts'], 320)
        self.assertEqual(result['key_panels'], 80)
        self.assertEqual(result['key_bytes'], 221312)
        self.assertEqual(result['value_decodes'], 4256)
        self.assertEqual(result['native_pairs'], 16)
        self.assertFalse(result['rtl_performance'])

    def reject(self, old, new):
        text = valid_log()
        self.assertIn(old, text)
        with self.assertRaises(ValueError):
            check_log(text.replace(old, new, 1))

    def test_work_counts(self):
        for old, new in [('command_attempts=16', 'command_attempts=0'),
                         ('groups=2', 'groups=1'), ('value_decodes=256', 'value_decodes=128'),
                         ('key_panels=8', 'key_panels=16'), ('key_bytes=34816', 'key_bytes=0'),
                         ('k_token_stride=272', 'k_token_stride=136'),
                         ('workspace=13120', 'workspace=16384')]:
            with self.subTest(old=old):
                self.reject(old, new)

    def test_selection_and_completion(self):
        for old, new in [('PV grouped=1 completed_groups=2', 'PV grouped=0 completed_groups=2'),
                         ('PV grouped=1 completed_groups=2', 'PV grouped=1 completed_groups=0'),
                         ('selection=6', 'selection=0'), ('selection=2', 'selection=0'),
                         ('executor_status=0', 'executor_status=1')]:
            with self.subTest(old=old):
                self.reject(old, new)

    def test_outputs_and_exactness(self):
        self.reject('outputs=1536', 'outputs=1535')
        self.reject('exact_pair=1', 'exact_pair=0')
        self.reject('exact=1', 'exact=0')

    def test_csr(self):
        for old, new in [('flags=9 ref_flags=9', 'flags=25 ref_flags=9'),
                         ('flags=9 ref_flags=9', 'flags=1 ref_flags=1'),
                         ('vcsr=5', 'vcsr=4'),
                         ('flags=41 ref_flags=41', 'flags=9 ref_flags=9')]:
            with self.subTest(new=new):
                self.reject(old, new)
        self.reject('repeat=1 grouped=0 outputs=1536 flags=9 ref_flags=9',
                    'repeat=1 grouped=0 outputs=1536 flags=25 ref_flags=25')

    def test_only_thread_may_differ_in_new_flags(self):
        text = valid_log().replace('actual_fcsr=9 ref_fcsr=9', 'actual_fcsr=9 ref_fcsr=11', 1)
        text = text.replace('actual_new_flags=1 ref_new_flags=1', 'actual_new_flags=1 ref_new_flags=3', 1)
        text = text.replace('mode=thread grouped=0 outputs=1536 flags=9 ref_flags=9',
                            'mode=thread grouped=0 outputs=1536 flags=9 ref_flags=11', 1)
        checked = check_log(text)
        self.assertEqual(checked['thread_csr_observations'][0]['reference_new_flags'], 3)
        self.assertFalse(checked['thread_csr_observations'][0]['aggregate'])
        for mode, flags in (('mask', 9), ('memory', 9), ('rounding', 41), ('reference', 9)):
            old = f'mode={mode} grouped=0 outputs=1536 flags={flags} ref_flags={flags}'
            with self.subTest(mode=mode):
                self.reject(old, old.replace(f'ref_flags={flags}', f'ref_flags={flags | 2}'))
        self.reject('mode=native visible=128 repeat=0 grouped=0 outputs=1536 flags=9 ref_flags=9',
                    'mode=native visible=128 repeat=0 grouped=0 outputs=1536 flags=9 ref_flags=11')

    def test_thread_observations_remain_strict(self):
        for old, new in (('ref_vcsr=5', 'ref_vcsr=4'), ('aggregate=0', 'aggregate=1'),
                         ('actual_new_flags=1', 'actual_new_flags=3'),
                         ('actual_fcsr=9', 'actual_fcsr=1'), ('ref_fcsr=9 actual_vcsr', 'ref_fcsr=41 actual_vcsr')):
            with self.subTest(new=new):
                self.reject(old, new)

    def test_numerical_summary(self):
        for value in ('nan', 'inf', '-0.1', '1e999'):
            with self.subTest(value=value):
                self.reject('max_abs=0.000001', 'max_abs=' + value)

    def test_truncated_duplicate_and_failure(self):
        for text in (valid_log().replace('GUEST_TEST_EXIT=0', ''),
                     valid_log() + 'GUEST_TEST_EXIT=0\n',
                     valid_log() + 'GGML_RISCV_QUANT_KV_PV grouped=1 completed_groups=2\n',
                     valid_log() + 'GROUPED_GGML_FAIL reason=numerical\n',
                     valid_log() + 'Kernel panic\n',
                     valid_log().replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1')):
            with self.subTest(text=text[-70:]), self.assertRaises(ValueError):
                check_log(text)

    def test_no_fallback_commands(self):
        self.reject('status=1 mapping=0 memory=1 runtime_called=1 command_attempts=0',
                    'status=1 mapping=0 memory=1 runtime_called=1 command_attempts=1')


if __name__ == '__main__':
    unittest.main()
