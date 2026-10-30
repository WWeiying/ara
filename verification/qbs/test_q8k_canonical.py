from pathlib import Path
import re
import unittest

ROOT=Path(__file__).resolve().parents[2]


def without_comments(text):
    return re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)


def body(text,name,kind="bool"):
    text=without_comments(text)
    start=text.index("inline "+kind+" "+name+"(")
    start=text.index("{",start)
    depth=1; end=start+1
    while depth:
        if text[end]=="{": depth+=1
        elif text[end]=="}": depth-=1
        end+=1
    return text[start+1:end-1]


def normalized(text):
    return re.sub(r"\s+","",without_comments(text))


class CanonicalTest(unittest.TestCase):
    def test_vector_function_is_the_accepted_candidate(self):
        current=(ROOT/"software/qbs/ggml/q8_K-m4.h").read_text()
        accepted=(ROOT/"verification/out/q8k-signed-max-compile-20261026-01/ggml/src/ggml-cpu/arch/riscv/q8_K-m4.h").read_text()
        accepted=accepted.replace("qbs_signed_max_candidate", "ggml_riscv_q8_K_signed_max")
        actual=body(current,"quantize")
        actual=actual.replace("#if GGML_RISCV_Q8_K_M4_VECTOR","")
        actual=actual.split("#else")[0]
        expected=body(accepted,"quantize").replace("#if GGML_RISCV_Q8_K_M4_VECTOR", "").split("#else")[0]
        self.assertEqual(normalized(actual),normalized(expected))

    def test_signed_max_matches_tested_candidate(self):
        current=(ROOT/"software/qbs/ggml/q8_K-signed-max.h").read_text()
        accepted=(ROOT/"verification/qbs/signed_max_candidate/signed_max.h").read_text()
        self.assertEqual(normalized(body(current,"ggml_riscv_q8_K_signed_max","float")),
                         normalized(body(accepted,"qbs_signed_max_candidate","float")))
        installed=Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/q8_K-signed-max.h")
        self.assertEqual(current,installed.read_text())

    def test_preflight_is_the_accepted_vla_algorithm(self):
        current=(ROOT/"software/qbs/ggml/q8_K-m4.h").read_text()
        accepted=(ROOT/"verification/qbs/q8k_m4_domain_vla.h").read_text()
        self.assertEqual(normalized(body(current,"vector_domain")),normalized(body(accepted,"check")))

    def test_installed_copy_matches_and_fallback_is_present(self):
        canonical=ROOT/"software/qbs/ggml/q8_K-m4.h"
        installed=Path("/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/arch/riscv/q8_K-m4.h")
        self.assertEqual(canonical.read_bytes(),installed.read_bytes())
        text=canonical.read_text()
        self.assertIn("!defined(__FAST_MATH__)",text)
        self.assertIn("#else\n    ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, k);\n    return false;",text)


if __name__=="__main__": unittest.main()
