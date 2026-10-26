import unittest
from native_audit import native_accounting


def fixture():
    result = []
    for mode in (0, 1):
        result += [f'Q8K_MODEL_BEGIN enabled={mode}', f'Q8K_MODEL_END enabled={mode}']
        for kind in ('Q4_K', 'Q6_K'):
            fields = dict(gemv_calls=1, gemm_calls=1, input_rows=5, output_rows=64,
                          activation_elements=1280, output_elements=160, dot_elements=40960,
                          split_calls=0, native_qbexec=2, emulated_commands=0,
                          command_dot_elements=40960, segmented_commands=0,
                          context_fill=1, context_reuse=1, context_release=1)
            fields.update({f'commands_m{i}': int(i in (1, 4)) for i in range(1, 9)})
            result.append('GGML_RISCV_QBS_EXEC type='+kind+' '+
                          ' '.join(f'{key}={value}' for key, value in fields.items()))
    return '\n'.join(result)


class NativeAccounting(unittest.TestCase):
    def test_complete(self):
        self.assertEqual(set(native_accounting(fixture())), {'Q4_K', 'Q6_K'})

    def test_reject_mutations(self):
        text = fixture()
        bad = [text.replace('emulated_commands=0', 'emulated_commands=1', 1),
               text.replace('native_qbexec=2', 'native_qbexec=0', 1),
               text.replace('commands_m4=1', 'commands_m4=0', 1),
               text.replace('command_dot_elements=40960', 'command_dot_elements=40959', 1),
               text.replace('context_release=1', 'context_release=0', 1),
               text.replace('input_rows=5', 'input_rows=6', 1),
               text.replace('gemv_calls=1', 'gemv_calls=1 gemv_calls=1', 1),
               '\n'.join(text.splitlines()[:-1]), text+'\n'+text.splitlines()[-1]]
        for candidate in bad:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    native_accounting(candidate)


if __name__ == '__main__':
    unittest.main()
