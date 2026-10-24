"""Synthetic protocol mutations only: these fixtures are NOT model evidence."""

import unittest

from check_model_live import check_log


SUITE = ("QUANT_MODEL_SUITE_PASS profiles=2 generations=4 tokens_each=3 "
         "common_greedy_trajectory=1 performance=not_measured")
PREFILL = ("GGML_RISCV_QUANT_KV status=1 mapping=5 memory=0 runtime_called=0 "
           "command_attempts=0 groups=0 value_decodes=0 executor_status=0")


def native(step, prompt=4):
    return ("GGML_RISCV_QUANT_KV status=0 mapping=0 memory=1 runtime_called=1 "
            f"command_attempts=4 groups=2 value_decodes={2 * (prompt + step)} "
            "executor_status=0")


def projection(kind):
    # Independent literal schema, not generated from the checker's field list.
    return (f"GGML_RISCV_QBS_EXEC type={kind} gemv_calls=4 gemm_calls=1 "
            "input_rows=8 output_rows=128 activation_elements=1024 "
            "output_elements=1024 dot_elements=131072 split_calls=0 "
            "commands_m1=16 commands_m2=0 commands_m3=0 commands_m4=4 "
            "commands_m5=0 commands_m6=0 commands_m7=0 commands_m8=0 "
            "native_qbexec=20 emulated_commands=0 command_dot_elements=131072 "
            "segmented_commands=0 context_fill=0 context_reuse=0 context_release=0")


def fixture(prefill=True, prompt=4):
    lines = ["Linux boot", "llama_model_loader: synthetic fixture, not a captured model"]
    for kind in ("q8_0", "q4_0"):
        for mode in ("baseline", "candidate"):
            lines.append(f"QUANT_MODEL_BEGIN kind={kind} mode={mode} layers=28 "
                         f"prompt_tokens={prompt} generated=3 context=128 threads=1")
            for step in range(3):
                if mode == "candidate":
                    if step == 0 and prefill:
                        lines.extend([PREFILL] * 28)
                    elif step:
                        lines.extend([native(step, prompt)] * 28)
                piece = ("", "20", "ff00")[step]
                lines.append(f"QUANT_MODEL_TOKEN kind={kind} mode={mode} step={step} "
                             f"token={10 + step} piece_hex={piece}")
            lines.append(f"QUANT_MODEL_END kind={kind} mode={mode} generated=3 vocab=100")
        for step in range(3):
            lines.append(f"QUANT_MODEL_COMPARE kind={kind} step={step} common_prefix=1 "
                         "top1_equal=1 max_abs=0.001 rmse=0.0001 kl=-1e-9")
    lines.extend([SUITE, "GGML_RISCV_QBS_LIFETIME_SUMMARY ordinary=ignored",
                  projection("Q4_K"), projection("Q6_K"), "GUEST_TEST_EXIT=0",
                  "reboot: Power down"])
    return "\n".join(lines) + "\n"


class ModelLiveCheckTest(unittest.TestCase):
    def reject(self, *logs):
        for index, log in enumerate(logs):
            with self.subTest(mutation=index), self.assertRaises(ValueError):
                check_log(log)

    def test_valid_optional_prefill_and_prompt_boundaries(self):
        for prefill in (False, True):
            for prompt in (2, 4, 32):
                with self.subTest(prefill=prefill, prompt=prompt):
                    result = check_log(fixture(prefill, prompt))
                    self.assertEqual(result["native_calls"], 112)
                    self.assertEqual(result["native_command_attempts"], 448)
                    self.assertEqual(result["prefill_fallback_reports"], 56 if prefill else 0)
                    self.assertEqual(len(result["generations"]), 4)
                    self.assertEqual(len(result["comparisons"]), 6)
                    self.assertFalse(result["rtl_performance"])
        self.assertEqual(check_log(fixture().replace("\n", "\r\n"))["status"], "PASS")

    def test_missing_extra_fallback_and_wrong_native_work(self):
        text, report = fixture(), native(1)
        self.reject(text.replace(report + "\n", "", 1),
                    text.replace(report, report + "\n" + report, 1),
                    text.replace(report, PREFILL, 1),
                    text.replace(PREFILL + "\n", "", 1),
                    text.replace(PREFILL, report, 1),
                    text.replace(report + "\n", ""))
        for field, replacement in (("status=0", "status=1"), ("mapping=0", "mapping=5"),
                                   ("memory=1", "memory=0"),
                                   ("runtime_called=1", "runtime_called=0"),
                                   ("command_attempts=4", "command_attempts=0"),
                                   ("groups=2", "groups=1"),
                                   ("value_decodes=10", "value_decodes=12"),
                                   ("executor_status=0", "executor_status=1")):
            self.reject(text.replace(report, report.replace(field, replacement), 1))
        marker = "QUANT_MODEL_TOKEN kind=q8_0 mode=baseline step=0"
        self.reject(text.replace(marker, report + "\n" + marker, 1))

    def test_full_line_namespaces_and_failure_text(self):
        text = fixture()
        for line in ("QUANT_MODEL_UNKNOWN x=1", "GGML_RISCV_QUANT_KV_BOGUS x=1",
                     "GGML_RISCV_QBS_EXEC_UNKNOWN x=1", "GUEST_TEST_EXIT_UNKNOWN=0",
                     "QUANT_MODEL_FAIL reason=synthetic", "Assertion failed",
                     "terminate called after throwing", "Illegal instruction"):
            self.reject(text + line + "\n")
        # Every record family rejects suffixes, extra fields, prefixes, duplicates.
        lines = [line for line in text.splitlines() if line.startswith(
            ("QUANT_MODEL_", "GGML_RISCV_QUANT_KV", "GGML_RISCV_QBS_EXEC", "GUEST_TEST_EXIT"))]
        representatives = {line.split(" ")[0]: line for line in lines}
        for line in representatives.values():
            for replacement in (line + "_BOGUS", line + " unknown=1", "noise " + line,
                                " " + line, line + "\n" + line,
                                line + "\vignored", line + "\rignored"):
                self.reject(text.replace(line, replacement, 1))
        self.reject(text.replace(" executor_status=0", "", 1),
                    text.replace(" top1_equal=1", "", 1),
                    text.replace(" context_release=0", "", 1))

    def test_order_missing_and_guest_exit(self):
        text = fixture()
        for prefix in ("QUANT_MODEL_BEGIN", "QUANT_MODEL_TOKEN", "QUANT_MODEL_END",
                       "QUANT_MODEL_COMPARE", "QUANT_MODEL_SUITE_PASS", "GUEST_TEST_EXIT"):
            line = next(line for line in text.splitlines() if line.startswith(prefix))
            self.reject(text.replace(line + "\n", "", 1))
        self.reject(text.replace("kind=q8_0", "kind=q4_0", 1),
                    text.replace("mode=baseline", "mode=candidate", 1),
                    text.replace("step=0", "step=1", 1),
                    text.replace("GUEST_TEST_EXIT=0", "GUEST_TEST_EXIT=1"),
                    text + "GUEST_TEST_EXIT=1\n",
                    "GUEST_TEST_EXIT=0\n" + text,
                    text.replace(SUITE, projection("Q4_K") + "\n" + SUITE),
                    text + projection("Q8_0") + "\n")

    def test_caps_vocabulary_tokens_and_piece(self):
        text = fixture()
        for old, new in (("layers=28", "layers=27"), ("context=128", "context=256"),
                         ("threads=1", "threads=3"), ("generated=3", "generated=2"),
                         ("prompt_tokens=4", "prompt_tokens=1"),
                         ("prompt_tokens=4", "prompt_tokens=33"),
                         ("prompt_tokens=4", "prompt_tokens=5"),
                         ("vocab=100", "vocab=101"), ("vocab=100", "vocab=1"),
                         ("token=10", "token=99"), ("token=10", "token=100"),
                         ("token=10", "token=-1"), ("piece_hex=20", "piece_hex=f"),
                         ("piece_hex=20", "piece_hex=gg"),
                         ("piece_hex=20", "piece_hex=" + "00" * 513)):
            self.reject(text.replace(old, new, 1))

    def test_comparison_finite_metrics_and_claims(self):
        text = fixture()
        for old, values in (("max_abs=0.001", ("-1", "nan", "inf", "1e999")),
                            ("rmse=0.0001", ("-0.01", "NaN", "-inf")),
                            ("kl=-1e-9", ("-1.01e-8", "nan", "1e999"))):
            key = old.split("=")[0]
            for value in values:
                self.reject(text.replace(old, f"{key}={value}", 1))
        self.reject(text.replace("common_prefix=1", "common_prefix=0", 1),
                    text.replace("top1_equal=1", "top1_equal=0", 1))
        self.assertEqual(check_log(text.replace("kl=-1e-9", "kl=-1e-8"))["status"], "PASS")

    def test_projection_requires_native_both_profiles_and_no_emulation(self):
        text = fixture()
        for kind in ("Q4_K", "Q6_K"):
            report = projection(kind)
            self.reject(text.replace(report + "\n", ""),
                        text.replace(report, report.replace("native_qbexec=20", "native_qbexec=0")),
                        text.replace(report, report.replace("emulated_commands=0", "emulated_commands=1")),
                        text.replace(report, report.replace("type=" + kind, "type=UNKNOWN")),
                        text.replace(report, report.replace("gemv_calls=4 gemm_calls=1",
                                                            "gemv_calls=0 gemm_calls=0")),
                        text.replace(report, report + "\n" + report),
                        text.replace(report, report.replace("native_qbexec=20",
                                                            "native_qbexec=18446744073709551616")))
        extra = projection("Q8_0").replace("emulated_commands=0", "emulated_commands=1")
        self.reject(text.replace("GUEST_TEST_EXIT=0", extra + "\nGUEST_TEST_EXIT=0"))


if __name__ == "__main__":
    unittest.main()
