#!/usr/bin/env python3
"""Reject unsupported or implicit compile contracts before deployment."""
import unittest
from build_ggml_candidate import check_compile_policy


class CompilePolicyTest(unittest.TestCase):
    def test_explicit_policy_and_identical_cmake_arch_flags(self):
        command = 'cc -march=rv64gcv_zfh_zvfh -fno-fast-math -ffp-contract=off -c a.c'
        check_compile_policy([dict(file='a.c',command=command)])
        check_compile_policy([dict(file='a.cpp',command=command+' -march=rv64gcv_zfh_zvfh')])
        check_compile_policy([dict(file='a.S',command='cc -march=rv64gcv_zfh_zvfh -c a.S')])
        for changed in (command.replace(' -march=rv64gcv_zfh_zvfh',''),
                        command.replace('rv64gcv_zfh_zvfh','rv64gcv_zfh_zvfh_zicbop'),
                        command.replace('-ffp-contract=off','-ffp-contract=fast'),
                        command.replace('-fno-fast-math',''),
                        command+' -ffast-math',command+' -march=rv64gcv'):
            with self.subTest(command=changed),self.assertRaises(ValueError):
                check_compile_policy([dict(file='a.c',command=changed)])


if __name__ == '__main__':
    unittest.main()
