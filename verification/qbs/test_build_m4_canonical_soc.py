import unittest
from build_m4_canonical_soc import retarget, validate_oracle


class RetargetTest(unittest.TestCase):
    def test_generic_exact_body_required(self):
        body = '\nvoid ggml_quantize_mat_q8_0_4x1_generic() {}\n'
        repack = body + '\nvoid ggml_quantize_mat_q8_K_4x1_ara_generic() {}'
        archived = '#include "ggml_m4_prepare_candidate.h"\nextern "C" {\n' + body + '\n}\n'
        validate_oracle(repack, archived)
        with self.assertRaises(ValueError):
            validate_oracle(repack.replace('{}', '{ changed(); }'), archived)

    def test_only_helper_changes(self):
        text = '#include "ggml_m4_prepare_candidate.h"\nqbs_m4_prepare_candidate::quantize(x,y,k);\n'
        self.assertEqual(retarget(text),
            '#include "arch/riscv/q8_0-m4.h"\nggml_riscv_q8_0_m4::quantize(x,y,k);\n')

    def test_reject_ambiguous_or_missing_boundary(self):
        text = '#include "ggml_m4_prepare_candidate.h"\nqbs_m4_prepare_candidate::quantize(x,y,k);\n'
        for invalid in (text * 2, text.replace('::quantize', '::other'), ''):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                retarget(invalid)


if __name__ == "__main__":
    unittest.main()
