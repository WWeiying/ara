#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("analyze-v2-token-probe.py")
SPEC = importlib.util.spec_from_file_location("analyze_v2_token_probe", SCRIPT)
assert SPEC and SPEC.loader
PROBE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PROBE
SPEC.loader.exec_module(PROBE)


class AnalyzeV2TokenProbeTest(unittest.TestCase):
    def analyze(self, lines: list[str]) -> dict[str, object]:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "ara.log"
            log.write_text("\n".join(lines) + "\n", encoding="utf-8")
            return PROBE.analyze(PROBE.parse_log(log))

    def base_lines(self, dim1_value: str = "2222") -> list[str]:
        return [
            "[AKV_V2_CONTEXT_PROBE] t=1 q=8000 k=9000 v=a000 "
            "rows=4 dim=2 kv=6 tile_start=0 tile_count=0",
            # This is a held column result from the preceding context. It is
            # emitted before the new FULL completes and must not be compared.
            "[AKV_V2_TOKEN_GATHER] t=2 stream=1 dim=1 count=6 token5=dead",
            "[AKV_V2_TOKEN_WRITE] t=3 stream=1 token=5 offset=0 strb=000f "
            "data=00000000000000000000000022221111",
            "[AKV_PERF] seq=0 success=1 fault=0 v2_full=1",
            "[AKV_V2_TOKEN_GATHER] t=4 stream=1 dim=0 count=6 token5=1111",
            f"[AKV_V2_TOKEN_GATHER] t=5 stream=1 dim=1 count=6 token5={dim1_value}",
        ]

    def test_ignores_stale_sample_and_checks_every_dimension(self):
        result = self.analyze(self.base_lines())
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["contexts_with_token5"], 1)
        self.assertEqual(result["checked_k_dimensions"], 2)
        self.assertEqual(result["ignored_prefill_gathers"], 1)
        self.assertEqual(result["stale_reported_tile_counts"], 1)
        self.assertEqual(result["mismatch_count"], 0)

    def test_reports_written_vs_gathered_data_mismatch(self):
        result = self.analyze(self.base_lines("3333"))
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["mismatch_count"], 1)
        self.assertEqual(result["first_mismatch"]["kind"], "data_mismatch")
        self.assertEqual(result["first_mismatch"]["expected"], 0x2222)
        self.assertEqual(result["first_mismatch"]["observed"], 0x3333)


if __name__ == "__main__":
    unittest.main()
