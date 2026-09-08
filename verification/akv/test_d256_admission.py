import unittest

from run_d256_admission import decode_evidence, plans, require_admission


def log(body):
    return "AKV_TOKEN_RUN_BEGIN=QBS_AKV_V2\n" + body + "\nAKV_TOKEN_RUN_EXIT=QBS_AKV_V2:0\n"


class AdmissionEvidenceTest(unittest.TestCase):
    def test_existing_and_new_cases(self):
        cohort = plans()
        self.assertEqual(len(cohort), 4)
        d256 = "GGML_RISCV_AKV_EXEC mode=decode kernel=v2 head_dim=256 active_kv=17 d256=1 execution=functional"
        result = require_admission(log(d256), cohort[0])
        self.assertEqual(result["active_kv"], [17])
        qwen = d256.replace("head_dim=256", "head_dim=128").replace("d256=1", "d256=0")
        self.assertEqual(require_admission(log(qwen), cohort[2])["decode_executed"], 1)
        default = log("GGML_RISCV_AKV_FALLBACK mode=decode reason=shape portable=1")
        self.assertEqual(require_admission(default, cohort[1])["decode_fallback"], 1)

    def test_no_acceptance_of_missing_or_wrong_execution(self):
        for body in ("", "GGML_RISCV_AKV_FALLBACK mode=decode reason=shape",
                     "GGML_RISCV_AKV_EXEC mode=decode kernel=v2 head_dim=256 active_kv=17 d256=1 execution=native"):
            with self.assertRaises(RuntimeError):
                require_admission(log(body), plans()[0])

    def test_not_other_variants_or_prefill(self):
        text = "AKV_TOKEN_RUN_BEGIN=QBS_ONLY\nGGML_RISCV_AKV_FALLBACK mode=decode reason=runtime\n"
        text += log("GGML_RISCV_AKV_FALLBACK mode=prefill reason=shape portable=1")
        self.assertEqual(decode_evidence(text), ([], []))


if __name__ == "__main__":
    unittest.main()
