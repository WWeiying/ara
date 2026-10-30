import unittest

from check_strided_graph import check_log


def valid_log():
    lines = []
    for kind, row in (('q8_0', 136), ('q4_0', 72)):
        for layout in ('contiguous', 'token_major'):
            ts, hs = (row, 256 * row) if layout == 'contiguous' else (2 * row, row)
            for visible in (128, 5):
                for repeat in range(2):
                    prefix = f'kind={kind} layout={layout} mode=native visible={visible} repeat={repeat}'
                    tiles = (visible + 31) // 32
                    panels, copied = (0, 0) if layout == 'contiguous' else (2 * tiles, 2 * visible * row)
                    lines.extend(['QUANT_STRIDED_BEGIN ' + prefix,
                        'GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 '
                        f'command_attempts={4 * tiles} groups=2 value_decodes={2 * visible} executor_status=0',
                        f'GGML_RISCV_QUANT_KV_LAYOUT selection=0 key_panels={panels} key_bytes={copied} '
                        f'workspace=13120 k_token_stride={ts} k_head_stride={hs}',
                        'QUANT_STRIDED_END ' + prefix + ' flags=1 vcsr=5 max_abs=0.000001'])
        for mode in ('mask_fallback', 'thread_fallback', 'memory_fallback'):
            prefix = f'kind={kind} layout=token_major mode={mode}'
            lines.append('QUANT_STRIDED_BEGIN ' + prefix)
            if mode == 'mask_fallback':
                lines.extend(['GGML_RISCV_QUANT_KV status=1 mapping=0 memory=1 runtime_called=1 '
                    'command_attempts=0 groups=0 value_decodes=0 executor_status=0',
                    'GGML_RISCV_QUANT_KV_LAYOUT selection=6 key_panels=0 key_bytes=0 workspace=13120 '
                    f'k_token_stride={2 * row} k_head_stride={row}'])
            lines.append('QUANT_STRIDED_END ' + prefix + ' exact=1')
        lines.append(f'QUANT_STRIDED_PROFILE_PASS kind={kind} outputs=1536 native_calls=8 fallback_cases=3 inputs_unchanged=1')
    lines.extend(['QUANT_STRIDED_SUITE_PASS profiles=2 layouts=2 native_calls=16 fallback_cases=6 '
                  'executor=native_qbs performance=not_measured', 'GUEST_TEST_EXIT=0'])
    return '\n'.join(lines) + '\n'


class GraphAcceptance(unittest.TestCase):
    def test_complete(self):
        result = check_log(valid_log())
        self.assertEqual(result['native_command_attempts'], 160)
        self.assertEqual(result['key_panels'], 40)
        self.assertEqual(result['key_bytes'], 110656)
        self.assertEqual(result['value_decodes'], 2128)
        self.assertFalse(result['rtl_performance'])

    def test_bad_work_or_layout(self):
        for old, new in [('key_panels=8', 'key_panels=16'),
                         ('key_bytes=34816', 'key_bytes=69632'),
                         ('k_token_stride=272', 'k_token_stride=136'),
                         ('command_attempts=16', 'command_attempts=0'),
                         ('selection=6', 'selection=0'),
                         ('workspace=13120', 'workspace=8192')]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                check_log(valid_log().replace(old, new, 1))

    def test_incomplete_or_extra(self):
        for text in (valid_log().replace('GUEST_TEST_EXIT=0', ''),
                     valid_log() + 'GGML_RISCV_QUANT_KV status=0\n',
                     valid_log().replace('native_calls=16', 'native_calls=8', 1),
                     valid_log() + 'Assertion failed\n'):
            with self.assertRaises(ValueError):
                check_log(text)

    def test_nonfinite_or_changed_csr(self):
        for replacement in ('flags=32 vcsr=5 max_abs=0.1',
                            'flags=1 vcsr=8 max_abs=0.1',
                            'flags=1 vcsr=5 max_abs=nan',
                            'flags=1 vcsr=5 max_abs=-0.1'):
            with self.assertRaises(ValueError):
                check_log(valid_log().replace('flags=1 vcsr=5 max_abs=0.000001', replacement, 1))
        text = valid_log().replace('repeat=1 flags=1', 'repeat=1 flags=3', 1)
        with self.assertRaises(ValueError):
            check_log(text)


if __name__ == '__main__':
    unittest.main()
