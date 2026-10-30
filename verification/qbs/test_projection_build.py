import importlib.util
from pathlib import Path
import unittest


path = Path(__file__).resolve().parents[2] / "apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py"
spec = importlib.util.spec_from_file_location("projection_builder", path)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class LibcBuildTests(unittest.TestCase):
    def test_non_recursive_bodies(self):
        builder.check_libc_calls("0000 <memcpy>:\n  0: 8082 ret\n0000 <memset>:\n  0: 8082 ret\n")

    def test_recursive_relocations_rejected(self):
        for function in ("memcpy", "memset"):
            for relocation in ("CALL", "CALL_PLT", "JAL"):
                with self.subTest(function=function, relocation=relocation), self.assertRaises(ValueError):
                    builder.check_libc_calls(
                        "0000 <memcpy>:\n0000 <memset>:\n0000 <" + function + ">:\n"
                        "  1c: R_RISCV_" + relocation + " " + function + "\n")

    def test_missing_bodies_rejected(self):
        with self.assertRaises(ValueError):
            builder.check_libc_calls("")


if __name__ == "__main__":
    unittest.main()
