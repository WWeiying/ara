#!/usr/bin/env python3
"""Regression test for production-path timing fields in QBS result CSVs."""

from __future__ import annotations

import csv
import subprocess
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SUMMARIZER = REPO / "hardware/scripts/qbs/summarize_qbs_run.py"


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        run_log = root / "run.log"
        perf_log = root / "perf.log"
        output = root / "result.csv"
        run_log.write_text(
            "QBS_REAL_BENCH case=probe result=PASS k=256 rows=32 inputs=1 "
            "outputs=32 tiles=1 timing_scope=production_command "
            "setup_included=1 timed_cycles=123 "
            "timed_cycles_per_output_x1000=3843 "
            "descriptor_setup_cycles=0 descriptor_setup_cycles_valid=0 "
            "compute_cycles=123 cycles_per_output_x1000=3843 "
            "quantize_cycles=20 pack_cycles=0 matmul_cycles=103 "
            "logical_read_bytes=4096 checksum=0x1 mismatches=0 "
            "max_abs_bits=0x0 max_rel_bits=0x0\n",
            encoding="ascii",
        )
        perf_log.write_text("[PERF] total_cycles : 130\n", encoding="ascii")
        subprocess.run(
            [
                str(SUMMARIZER),
                "--run-log",
                str(run_log),
                "--perf-log",
                str(perf_log),
                "--output",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        with output.open(newline="", encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        expected = {
            "timing_scope": "production_command",
            "setup_included": "1",
            "timed_cycles": "123",
            "timed_cycles_per_output_x1000": "3843",
            "descriptor_setup_cycles": "0",
            "descriptor_setup_cycles_valid": "0",
        }
        for field, value in expected.items():
            if row[field] != value:
                raise SystemExit(f"{field}: expected {value}, got {row[field]}")
    print("PASS: QBS production timing fields survive result summarization")


if __name__ == "__main__":
    main()
