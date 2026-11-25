import unittest
from audit import preguard


DIS = """
00000000 <portal>:
   0: 00000013 beqz a0,20 <legacy>
   4: 00000013 auipc ra,0
   4: R_RISCV_CALL_PLT ara_resident_linux_admit
   8: 00000013 jalr ra
   c: 00000013 csrr a0,vstart
  10: 00000013 vadd.vv v1,v2,v3
  14: 00000013 ret
  20: 00000013 auipc ra,0
  20: R_RISCV_CALL_PLT ara_resident_linux_open
  24: 00000013 jalr ra
  28: 00000013 csrr a0,vstart
  2c: 00000013 ret
  40: 00000013 addi a0,a0,1
  44: 00000013 ret
"""
SYM = "00000000 00000030 T portal\n00000040 00000008 t tensor_span\n"


class AuditTests(unittest.TestCase):
    def test_both_guards(self):
        self.assertEqual(len(preguard(DIS, SYM)["guards"]), 2)

    def test_vector_before_either_guard(self):
        for address in ("8", "24"):
            with self.assertRaises(AssertionError):
                preguard(DIS.replace(f"{address}: 00000013 jalr ra", f"{address}: 00000013 vadd.vv v1,v2,v3"), SYM)

    def test_fp_before_guard(self):
        with self.assertRaises(AssertionError):
            preguard(DIS.replace("8: 00000013 jalr ra", "8: 00000013 fadd.s fa0,fa1,fa2"), SYM)

    def test_lp64d_stack_save_only(self):
        allowed = DIS.replace("8: 00000013 jalr ra", "8: 00000013 fsd fs0,24(sp)")
        self.assertEqual(preguard(allowed, SYM)["guards"][0]["lp64d_prologue_fp_saves"], ["0x8"])
        for args in ("fs0,0(a0)", "fa0,24(sp)"):
            with self.assertRaises(AssertionError):
                preguard(DIS.replace("8: 00000013 jalr ra", "8: 00000013 fsd " + args), SYM)

    def test_tls_before_guard(self):
        with self.assertRaises(AssertionError):
            preguard(DIS.replace("ara_resident_linux_admit", "__cxa_thread_atexit"), SYM)

    def test_missing_admission(self):
        with self.assertRaises(AssertionError):
            preguard(DIS.replace("ara_resident_linux_open", "other_function"), SYM)

    def test_helper_vector(self):
        with self.assertRaises(AssertionError):
            preguard(DIS.replace("40: 00000013 addi a0,a0,1", "40: 00000013 vle16.v v1,(a0)"), SYM)


if __name__ == "__main__":
    unittest.main()
