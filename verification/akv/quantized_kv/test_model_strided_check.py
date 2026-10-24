"""Synthetic protocol mutations, not actual-model correctness evidence."""

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from check_model_strided import check_log
from test_model_live_check import fixture as original_fixture


def fixture(prefill=True):
    lines = []
    kind, step = None, 0
    for line in original_fixture(prefill=prefill).splitlines():
        if line.startswith("QUANT_MODEL_BEGIN "):
            kind = line.split("kind=")[1].split()[0]
            step = 0
            lines.append("llama_context: n_ctx                 = 256")
        lines.append(line)
        if line.startswith("GGML_RISCV_QUANT_KV "):
            row = 136 if kind == "q8_0" else 72
            lines.append("GGML_RISCV_QUANT_KV_LAYOUT selection=0 "
                         f"key_panels={2 if step else 0} key_bytes={2 * (4 + step) * row if step else 0} "
                         f"workspace=13120 k_token_stride={2 * row} k_head_stride={row}")
        if line.startswith("QUANT_MODEL_TOKEN "):
            step = int(line.split("step=")[1].split()[0]) + 1
    return "\n".join(lines) + "\n"


class ModelStridedCheckTest(unittest.TestCase):
    def reject(self, *texts):
        for index, text in enumerate(texts):
            with self.subTest(index=index), self.assertRaises(ValueError):
                check_log(text)

    def test_complete_optional_prefill(self):
        for prefill in (False, True):
            result = check_log(fixture(prefill))
            self.assertEqual(result["native_command_attempts"], 448)
            self.assertEqual(result["key_panels"], 224)
            self.assertEqual(result["key_bytes"], 128128)
            self.assertEqual(result["effective_contexts"], [256] * 4)
            self.assertFalse(result["rtl_performance"])
        self.assertEqual(check_log(fixture().replace("\n", "\r\n"))["status"], "PASS")

    def test_wrong_layout_counters_stride_and_workspace(self):
        text = fixture()
        for old, new in (("selection=0", "selection=5"), ("key_panels=2", "key_panels=1"),
                         ("key_panels=2", "key_panels=4"), ("key_bytes=1360", "key_bytes=1632"),
                         ("key_bytes=1632", "key_bytes=1360"), ("key_bytes=720", "key_bytes=864"),
                         ("key_bytes=864", "key_bytes=720"), ("key_bytes=0", "key_bytes=72"),
                         ("workspace=13120", "workspace=8192"),
                         ("k_token_stride=272", "k_token_stride=136"),
                         ("k_token_stride=144", "k_token_stride=72"),
                         ("k_head_stride=136", "k_head_stride=34816"),
                         ("k_head_stride=72", "k_head_stride=18432")):
            self.reject(text.replace(old, new, 1))

    def test_layout_adjacency_and_unknown_records(self):
        text = fixture()
        line = next(line for line in text.splitlines() if line.startswith("GGML_RISCV_QUANT_KV_LAYOUT "))
        self.reject(text.replace(line + "\n", "", 1), text + line + "\n",
                    text.replace(line, line + "\n" + line, 1),
                    text.replace(line, "normal log\n" + line, 1))
        for replacement in (line + "BOGUS", line + " extra=1", "prefix " + line,
                            line + "\vignored", line.replace(" selection=0", ""),
                            "GGML_RISCV_QUANT_KV_LAYOUT_UNKNOWN x=1"):
            self.reject(text.replace(line, replacement, 1))

    def test_effective_context_is_not_requested_context(self):
        text = fixture()
        line = "llama_context: n_ctx                 = 256"
        self.reject(text.replace(line, "", 1), text.replace(line, line + "\n" + line, 1),
                    text.replace(line, line.replace("256", "128"), 1), text + line + "\n",
                    text.replace(line, line + " extra=1", 1))

    def test_original_acceptance_not_weakened(self):
        text = fixture()
        for old, new in (("command_attempts=4", "command_attempts=0"),
                         ("value_decodes=10", "value_decodes=12"),
                         ("token=10", "token=99"), ("max_abs=0.001", "max_abs=nan"),
                         ("GUEST_TEST_EXIT=0", "GUEST_TEST_EXIT=1"),
                         ("native_qbexec=20", "native_qbexec=0"),
                         ("performance=not_measured", "performance=not_measured_BOGUS")):
            self.reject(text.replace(old, new, 1))
        self.reject(text + "QUANT_MODEL_FAIL reason=synthetic\n",
                    text + "GGML_RISCV_QUANT_KV_UNKNOWN x=1\n")

    def test_prerequisite_requires_current_pass_and_raw_agreement(self):
        import run_model_strided as runner
        gate, llama = Path("/synthetic/gate"), Path("/synthetic/llama")
        pinned = {str(path): "synthetic-sha" for path in (
            runner.HERE / "check_strided_graph.py", runner.HERE / "run_strided_graph.py",
            runner.HERE / "ggml_strided/test.cpp", llama / "ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp",
            runner.ROOT / "software/akv/experimental/quantized_kv/runtime_strided.c",
            runner.ROOT / "software/akv/experimental/quantized_kv/ggml_entry_strided.h")}
        raw = dict(state="GRAPH_CHECKED", native_calls=16, native_command_attempts=160,
                   key_panels=40, key_bytes=110656, whole_model=False, rtl_performance=False)
        receipt = dict(raw, state="PASS", current_inputs_match=True,
                       log_sha256="synthetic-sha", source_pins_sha256="synthetic-sha")

        def attempt(changes=None, status="PASS", checked=None):
            documents = {"result.json": dict(receipt, **(changes or {})),
                         "status.json": {"state": status}, "source-pins.json": pinned}
            checker = SimpleNamespace(check_log=lambda _text: dict(raw if checked is None else checked))
            with patch.object(runner, "json_file", side_effect=lambda p: documents[p.name]), \
                 patch.object(runner, "digest", return_value="synthetic-sha"), \
                 patch.object(runner, "check_pins"), \
                 patch.object(runner.importlib, "import_module", return_value=checker), \
                 patch.object(Path, "read_bytes", return_value=b"synthetic raw"):
                return runner.prerequisite(gate, llama)

        self.assertEqual(attempt(), pinned)
        for changes in ({"state": "FAIL"}, {"current_inputs_match": False}, {"whole_model": True},
                        {"native_calls": 15}, {"log_sha256": "changed"},
                        {"source_pins_sha256": "changed"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                attempt(changes)
        with self.assertRaises(ValueError):
            attempt(status="RUNNING")
        with self.assertRaises(ValueError):
            attempt(checked=dict(raw, native_command_attempts=0))
        with self.assertRaises(ValueError):
            attempt(checked=dict(raw, key_bytes=0))


if __name__ == "__main__":
    unittest.main()
