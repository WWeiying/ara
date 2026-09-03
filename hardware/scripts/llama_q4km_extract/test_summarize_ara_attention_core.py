#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("summarize-ara-attention-core.py")
SPEC = importlib.util.spec_from_file_location("summarize_attention", MODULE_PATH)
summarize = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(summarize)


class SummarizeAraAttentionCoreTest(unittest.TestCase):
    def make_run(self, root: Path, aggregate: bool) -> Path:
        run = root / "decode_attention_core_akv_v2_prefill_kv15_20260903_120000"
        run.mkdir(parents=True)
        (run / "complete").write_text("", encoding="ascii")
        (run / "run.conf").write_text(
            "implementation=akv_v2_prefill\neffective_kv=15\n",
            encoding="utf-8",
        )
        perf = (
            "[AKV_PERF_SUMMARY] records=3 busy_cycles=17 v2_full=1 "
            "v2_column_load=2 v2_column_panel=2 v2_logical_column=8\n"
            if aggregate else
            "[AKV_PERF] busy_cycles=7 v2_full=1 v2_column_load=0\n"
            "[AKV_PERF] busy_cycles=10 v2_full=0 v2_column_load=2\n"
        )
        (run / "ara.log").write_text(
            "LLAMA_OPERATOR case PASS cycles=123 mismatches=0\n"
            "Core Test *** SUCCESS\n" + perf,
            encoding="utf-8",
        )
        (run / "llm_perf_report_case.log").write_text(
            "[LLM_PERF] case=case phase=total cycles=125\n",
            encoding="utf-8",
        )
        return run

    def test_discovers_nonstandard_kv_and_parses_summary_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = self.make_run(root, aggregate=True)
            selected = summarize.newest_complete_run(
                [root], "akv_v2_prefill", 15
            )
            self.assertIsNotNone(selected)
            rows = summarize.parse_run(
                "akv_v2_prefill", 15, *selected
            )
        self.assertEqual(rows[0]["akv_command_count"], 3)
        self.assertEqual(rows[0]["akv_busy_cycles"], 17)
        self.assertEqual(rows[0]["akv_v2_column_panel"], 2)
        self.assertEqual(rows[0]["akv_v2_logical_column"], 8)

    def test_sums_detail_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.make_run(root, aggregate=False)
            selected = summarize.newest_complete_run(
                [root], "akv_v2_prefill", 15
            )
            self.assertIsNotNone(selected)
            rows = summarize.parse_run(
                "akv_v2_prefill", 15, *selected
            )
        self.assertEqual(rows[0]["akv_command_count"], 2)
        self.assertEqual(rows[0]["akv_busy_cycles"], 17)
        self.assertEqual(rows[0]["akv_v2_full"], 1)
        self.assertEqual(rows[0]["akv_v2_column_load"], 2)


if __name__ == "__main__":
    unittest.main()
