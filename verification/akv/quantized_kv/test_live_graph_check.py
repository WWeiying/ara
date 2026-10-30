"""Fail-closed acceptance of native-dispatch and ordinary-fallback evidence."""
import unittest

from run_live_graph import check_log

NATIVE = 'GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 command_attempts=16 groups=2 value_decodes=256 executor_status=0'
REJECT = 'GGML_RISCV_QUANT_KV status=1 mapping=0 memory=1 runtime_called=1 command_attempts=0 groups=0 value_decodes=0 executor_status=0'


def fixture():
    lines = []
    for kind in ('q8_0', 'q4_0'):
        for repeat in range(2):
            lines.extend([f'QUANT_LIVE_BEGIN kind={kind} mode=native repeat={repeat}', NATIVE,
                f'QUANT_LIVE_END kind={kind} mode=native repeat={repeat} flags=1 max_abs=0.00001'])
        for mode in ('mask_fallback', 'thread_fallback', 'memory_fallback'):
            lines.append(f'QUANT_LIVE_BEGIN kind={kind} mode={mode}')
            if mode == 'mask_fallback':
                lines.append(REJECT)
            lines.append(f'QUANT_LIVE_END kind={kind} mode={mode}' + (' exact=1' if mode == 'mask_fallback' else ''))
        lines.append(f'QUANT_LIVE_PROFILE_PASS kind={kind} heads=12 kv_heads=2 outputs=1536 native_calls=2 ordinary_gold_max=0.00001 inputs_unchanged=1')
    lines.extend(['QUANT_LIVE_SUITE_PASS profiles=2 executor=native_qbs performance=not_measured', 'GUEST_TEST_EXIT=0'])
    return '\n'.join(lines) + '\n'


class LiveGraphCheckTest(unittest.TestCase):
    def test_complete(self):
        result = check_log(fixture())
        self.assertEqual(result['native_command_attempts'], 64)
        self.assertEqual(result['fallback_cases'], 6)
        self.assertFalse(result['rtl_performance'])
        self.assertFalse(result['whole_model'])

    def test_native_work_not_inferred_from_output_marker(self):
        for replacement in ('', REJECT, NATIVE.replace('command_attempts=16', 'command_attempts=0'),
                            NATIVE.replace('groups=2', 'groups=1')):
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                check_log(fixture().replace(NATIVE, replacement, 1))

    def test_fallback_cannot_execute_native(self):
        with self.assertRaises(ValueError):
            check_log(fixture().replace(REJECT, NATIVE, 1))
        with self.assertRaises(ValueError):
            check_log(fixture().replace('mode=thread_fallback\n', 'mode=thread_fallback\n' + NATIVE + '\n', 1))

    def test_missing_duplicate_or_nonfinite_records(self):
        text = fixture()
        for broken in (text.replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=1'),
                       text.replace('max_abs=0.00001', 'max_abs=nan', 1),
                       text.replace('mode=native repeat=1 flags=', 'mode=native repeat=0 flags=', 1),
                       text + NATIVE + '\n',
                       text + 'GGML_RISCV_QUANT_KV unknown=1\n',
                       text.replace('performance=not_measured', 'performance=not_measured_BOGUS'),
                       text.replace('inputs_unchanged=1', 'inputs_unchanged=1_BOGUS', 1),
                       text.replace('GUEST_TEST_EXIT=0', 'GUEST_TEST_EXIT=0\nGUEST_TEST_EXIT=1'),
                       text + 'Assertion failed\n',
                       text.replace('inputs_unchanged=1', 'inputs_unchanged=0', 1)):
            with self.subTest(broken=broken[-100:]), self.assertRaises(ValueError):
                check_log(broken)


if __name__ == '__main__':
    unittest.main()
