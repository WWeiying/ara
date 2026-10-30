from pathlib import Path
import unittest
from build_q8k_vla_native import check_core,adapt_harness
from build_q8k_vla_soc import replace_one


class TestSuccessor(unittest.TestCase):
    def test_quantizer_unchanged(self):
        root=Path(__file__).parent
        old=(root/"ggml_q8k_m4_prepare_candidate.h").read_text()
        new=(root/"ggml_q8k_m4_prepare_vla_candidate.h").read_text()
        check_core(old,new)
        with self.assertRaises(ValueError):check_core(old,new.replace("-127.0f","-126.0f"))

    def test_harness_only_redirected(self):
        root=Path(__file__).parent
        text=(root/"ggml_q8k_m4_prepare_native/native.cpp").read_text()
        adapted=adapt_harness(text,Path("/candidate.h"))
        restored=adapted.replace('#include "/candidate.h"','#include "../ggml_q8k_m4_prepare_candidate.h"').replace(
            "qbs_q8k_m4_prepare_vla_candidate::","qbs_q8k_m4_prepare_candidate::")
        self.assertEqual(text,restored)
        with self.assertRaises(ValueError):adapt_harness(text+text,Path("/candidate.h"))

    def test_unique_build_argument(self):
        self.assertEqual(replace_one(["cc","old","-o","result"],"old","new"),["cc","new","-o","result"])
        for args in (["cc","other"],["old","old"]):
            with self.assertRaises(ValueError):replace_one(args,"old","new")


if __name__=="__main__":unittest.main()
