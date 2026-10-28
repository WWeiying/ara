import unittest
from run_canonical import compare_codegen


class CodegenTest(unittest.TestCase):
    def fixtures(self):
        common = """0000000000000000 <body>:
 0: 12345678 vadd.vv v1,v2,v3
00000000000004f4 <.L2>:
 4f4: 00000697 auipc a3,0x0
"""
        old = common + " 4fc: 4669 li a2,26\n 4fe: 00000597 auipc a1,0x0\n 502: 000080e7 jalr ra\n"
        new = common + " 4fc: 03100613 li a2,49\n 500: 00000597 auipc a1,0x0\n 504: 000080e7 jalr ra\n"
        return [old,new],["00000000000004fe R_RISCV_CALL_PLT __assert_fail\n",
                          "0000000000000500 R_RISCV_CALL_PLT __assert_fail\n"], ["\n"*25+"assert(k);", "\n"*48+"assert(k);"]

    def test_diagnostic_only(self):
        result = compare_codegen(*self.fixtures())
        self.assertFalse(result["object_instructions_equal"])
        self.assertTrue(result["assertion_line_only_difference"])

    def test_reject_arithmetic(self):
        asm,reloc,headers = self.fixtures()
        asm[1] = asm[1].replace("12345678","12345679")
        with self.assertRaises(ValueError): compare_codegen(asm,reloc,headers)

    def test_reject_other_argument(self):
        asm,reloc,headers = self.fixtures()
        asm[1] = asm[1].replace("li a2,49","li a2,50")
        with self.assertRaises(ValueError): compare_codegen(asm,reloc,headers)

    def test_reject_other_call(self):
        asm,reloc,headers = self.fixtures()
        reloc[1] = reloc[1].replace("__assert_fail","run_quantizer")
        with self.assertRaises(ValueError): compare_codegen(asm,reloc,headers)

    def test_reject_nonterminal(self):
        asm,reloc,headers = self.fixtures()
        asm[0] += " 506: 00000513 addi a0,zero,0\n"
        asm[1] += " 508: 00000513 addi a0,zero,0\n"
        with self.assertRaises(ValueError): compare_codegen(asm,reloc,headers)


if __name__ == "__main__": unittest.main()
