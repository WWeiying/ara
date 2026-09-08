import unittest

from run_d256_admission import plans
from summarize_d256_admission import validate_log


def fixture():
    lines = []
    for mode in ("RVV", "QBS_ONLY", "QBS_AKV_V2"):
        lines += [f"AKV_TOKEN_RUN_BEGIN={mode}", "prompt eval time = 1 ms / 4 tokens"]
        if mode == "QBS_AKV_V2":
            lines += [
                "GGML_RISCV_AKV_EXEC mode=decode kernel=v2 head_dim=256 active_kv=5 d256=1 execution=functional",
                "GGML_RISCV_AKV_FALLBACK mode=prefill reason=size",
                "GGML_RISCV_AKV_COVERAGE candidate_ops=2 executed_ops=1 executed_v1=0 "
                "executed_v2=1 executed_decode=1 executed_prefill=0 fallback_size=1",
                "GGML_RISCV_QBS_COVERAGE type=Q4_K candidate_tensors=1 selected_tensors=1 "
                "candidate_elements=256 selected_elements=256 fallback_shape=0",
                "GGML_RISCV_QBS_EXEC type=Q4_K native_qbexec=1 emulated_commands=0",
            ]
        lines += [f"AKV_TOKEN_RUN_EXIT={mode}:0"]
    for prefix in ("QBS_RVV", "AKV"):
        for suffix, value in (("RECORDS", 3), ("COMPARABLE_RECORDS", 3),
                              ("MAX_ABS", 0), ("MAX_KL", 0), ("MIN_COSINE", 1),
                              ("MIN_TOP5_OVERLAP", 1), ("TOP1_EQUAL", 1)):
            lines += [f"{prefix}_LOGITS_{suffix}={value}"]
        lines += [f"{prefix}_TOKEN_OUTPUT_EQUAL=1"]
    lines += ["LLAMA_GUEST_EXIT=0", "MODEL_NUMERICAL_CONTRACT=decision-preserving-v1",
              "MODEL_LOGITS_MAX_KL_TOLERANCE=0.02", "MODEL_LOGITS_MIN_COSINE_TOLERANCE=0.98",
              "MODEL_LOGITS_MIN_TOP5_OVERLAP_TOLERANCE=0.8"]
    return "\n".join(lines) + "\n"


class SummaryTest(unittest.TestCase):
    def test_complete_and_crlf(self):
        for text in (fixture(), fixture().replace("\n", "\r\n")):
            summary, records = validate_log(text, plans()[0])
            self.assertEqual(summary["prompt_tokens"], 4)
            self.assertEqual(summary["decode_executed"], 1)
            self.assertEqual(summary["prefill_fallback"], 1)
            self.assertEqual(summary["native_qbexec"], 1)
            self.assertEqual(records["fallback_by_phase"], {"prefill:size": 1})

    def test_reject_incomplete_or_inconsistent_logs(self):
        changes = (
            ("AKV_TOKEN_RUN_EXIT=RVV:0", "AKV_TOKEN_RUN_EXIT=RVV:1"),
            ("LLAMA_GUEST_EXIT=0", ""),
            ("AKV_LOGITS_RECORDS=3", "AKV_LOGITS_RECORDS=2"),
            ("AKV_LOGITS_MAX_KL=0", "AKV_LOGITS_MAX_KL=nan"),
            ("QBS_RVV_LOGITS_MAX_KL=0", "QBS_RVV_LOGITS_MAX_KL=0.021"),
            ("AKV_TOKEN_OUTPUT_EQUAL=1", "AKV_TOKEN_OUTPUT_EQUAL=0"),
            ("MODEL_LOGITS_MAX_KL_TOLERANCE=0.02", "MODEL_LOGITS_MAX_KL_TOLERANCE=0.03"),
            ("candidate_ops=2", "candidate_ops=3"),
            ("executed_v2=1", "executed_v2=0"),
            ("fallback_size=1", "fallback_size=2"),
            ("selected_tensors=1", "selected_tensors=0"),
            ("selected_elements=256", "selected_elements=255"),
            ("native_qbexec=1", "native_qbexec=0"),
            ("emulated_commands=0", "emulated_commands=1"),
            ("prompt eval time = 1 ms / 4 tokens", "prompt eval time = 1 ms / 5 tokens"),
            ("AKV_LOGITS_MAX_ABS=0", "AKV_LOGITS_MAX_ABS=0\nAKV_LOGITS_MAX_ABS=0"),
        )
        for old, new in changes:
            with self.subTest(change=old), self.assertRaises(ValueError):
                validate_log(fixture().replace(old, new, 1), plans()[0])


if __name__ == "__main__":
    unittest.main()
