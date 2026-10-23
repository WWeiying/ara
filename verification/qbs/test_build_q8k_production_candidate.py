import unittest

from build_q8k_production_candidate import adapt_harness, adapt_production


class ProductionAdapterTests(unittest.TestCase):
    def test_changes_selection_not_generic(self):
        text = ("void generic_body() { unchanged(); }\n"
                "template <> void entry() {\n"
                "    ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row);\n"
                "}\n\ntemplate <int M, int N>\nnext();\n")
        new = adapt_production(text, "/private/helper.h")
        self.assertIn("void generic_body() { unchanged(); }", new)
        self.assertIn("qbs_m4_prepare_enabled()", new)
        self.assertIn("qbs_q8k_m4_prepare_vla_candidate::quantize(x, vy, n_per_row)", new)
        self.assertEqual(new.count("ggml_quantize_mat_q8_K_4x1_ara_generic(x, vy, n_per_row)"), 1)

    def test_reject_ambiguous_selection(self):
        with self.assertRaises(ValueError):
            adapt_production("not the production source", "/private/helper.h")

    def test_calls_real_entry_not_helper(self):
        text = ('#include "../ggml_q8k_m4_prepare_candidate.h"\n'
                '__attribute__((noinline)) static bool candidate(...) { old(); }\n'
                'static size_t cases = 0;\nint main(int argc, char ** argv) {\n}\n')
        new = adapt_harness(text)
        self.assertIn("ggml_quantize_mat_t<1, GGML_TYPE_Q8_K>(x, y, 4, k)", new)
        self.assertNotIn("prepare_candidate.h", new)
        self.assertNotIn("::quantize", new)
        self.assertIn("q8k_production_last_vector_path()", new)
        self.assertIn('setenv("GGML_RISCV_QBS_M4_PREPARE", "1", 1)', new)

    def test_reject_changed_harness_boundary(self):
        with self.assertRaises(ValueError):
            adapt_harness("int main() { return 0; }")


if __name__ == "__main__":
    unittest.main()
