import unittest
from build_masklogical_restart8_nativefix import check_native


class RuntimeGuard(unittest.TestCase):
    def test_common_printf(self):
        self.assertEqual(check_native('80000000 <printf_>:\n  ret\n',
                                      '/tmp/native-printf.c.o\n')['status'], 'PASS')

    def test_reject_syscall_and_newlib(self):
        cases = [
            ('80000000 <printf_>:\n  ecall\n', ''),
            ('80000000 <printf>:\n  ret\n', ''),
            ('80000000 <printf_>:\n80000004 <_fstat>:\n', ''),
            ('80000000 <printf_>:\n', '/lib/libc.a(libc_a-printf.o)\n'),
            ('80000000 <printf_>:\n', '/lib/libgloss.a(sys_fstat.o)\n'),
        ]
        for dis, link in cases:
            with self.subTest(dis=dis, link=link), self.assertRaises(ValueError):
                check_native(dis, link)


if __name__ == '__main__':
    unittest.main()
