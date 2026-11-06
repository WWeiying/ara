import struct
import unittest

from build_decode_rvv import custom_instructions, modified_recipe, upstream_warning_recipe


def elf(text, data=b''):
    result = bytearray(256+len(text)+len(data))
    struct.pack_into('<16sHHIQQQIHHHHHH', result, 0, b'\x7fELF\x02\x01'+bytes(10),
                     2, 243, 1, 0x80000000, 0, 64, 0, 64, 56, 0, 64, 3, 0)
    struct.pack_into('<IIQQQQIIQQ', result, 128, 0, 1, 6, 0x80000000, 256, len(text), 0, 0, 2, 0)
    struct.pack_into('<IIQQQQIIQQ', result, 192, 0, 1, 2, 0x80010000, 256+len(text), len(data), 0, 0, 1, 0)
    result[256:256+len(text)] = text; result[256+len(text):] = data
    return result


class BuildDecodeRVVTests(unittest.TestCase):
    def test_upstream_policy_changes_no_math_or_isa_option(self):
        command = ['/cc', '-O3', '-Wall', '-Wextra', '-Werror', '-fno-fast-math',
                   '-ffp-contract=off', '-march=rv64gcv_zfh_zvfh', '-c', 'upstream.cpp']
        actual = upstream_warning_recipe(command, '/cc -O3 -Wall -c upstream.cpp')
        self.assertEqual(actual, [word for word in command if word != '-Werror'])
        with self.assertRaises(ValueError): upstream_warning_recipe(command, '/cc -Werror -c upstream.cpp')
        scoped = upstream_warning_recipe(command, '/cc -Werror=implicit-int -Werror=implicit-function-declaration -c upstream.c')
        self.assertEqual(scoped, actual+['-Werror=implicit-int', '-Werror=implicit-function-declaration'])

    def test_recipe_preserves_isa_math_and_compile_flags(self):
        original = ['/cc', '-O3', '-ffp-contract=off', '-march=rv64gcv_zfh_zvfh', '-c', 'a.cpp', '-o', 'a.o']
        result = modified_recipe(original, 'b.cpp', 'b.o')
        self.assertEqual(result, original[:5]+['b.cpp', '-o', 'b.o'])
        self.assertEqual(original[5], 'a.cpp')
        for flag in ('-DGGML_CPU_GENERIC', '-DGGML_USE_RISCV_QBS=1'):
            with self.assertRaises(ValueError): modified_recipe([*original, flag], 'b.cpp', 'b.o')

    def test_scan_code_not_quantized_data_in_rwx_preload(self):
        nop = bytes.fromhex('010013000000')
        self.assertEqual(custom_instructions(elf(nop, bytes.fromhex('0b000000'))), [])
        self.assertEqual(custom_instructions(elf(nop+bytes.fromhex('0b000000'))), [0x80000006])
        for opcode in (0x2b, 0x5b, 0x7b):
            self.assertEqual(custom_instructions(elf(opcode.to_bytes(4, 'little'))), [0x80000000])

    def test_rejects_long_truncated_and_empty_executable(self):
        for text in (b'', b'\x13\x00', b'\x1f\x00\x00\x00'):
            with self.assertRaises(ValueError): custom_instructions(elf(text))


if __name__ == '__main__': unittest.main()
