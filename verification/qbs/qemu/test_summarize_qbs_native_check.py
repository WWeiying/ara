#!/usr/bin/env python3
"""Regression test for the QBS QEMU machine-readable report."""

from __future__ import annotations

import csv
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "summarize_qbs_native_check.py"


def main() -> None:
    log = """\
QBS_TOKEN_RUN_EXIT=RVV:0
GGML_RISCV_QBS_EXEC type=Q4_K gemv_calls=2 gemm_calls=3 native_qbexec=5
QBS_TOKEN_RUN_EXIT=QBS_NATIVE:0
QBS_LOGITS_RECORDS=2 status=OK
QBS_MODEL_METRICS records=2 mean_kl=0.01 top1_agreement=1 top5_overlap=0.8 mean_rmse=0.02 max_abs=0.1
QBS_TOKEN_OUTPUT_EQUAL=1
LLAMA_GUEST_EXIT=0
"""
    with tempfile.TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        log_path = root / "run.log"
        csv_path = root / "run.csv"
        json_path = root / "run.json"
        log_path.write_text(log, encoding="ascii")
        subprocess.run(
            [
                "python3",
                str(SCRIPT),
                "--log",
                str(log_path),
                "--output",
                str(csv_path),
                "--json",
                str(json_path),
                "--require-pass",
            ],
            check=True,
        )
        with csv_path.open(newline="", encoding="utf-8") as stream:
            row = next(csv.DictReader(stream))
        assert row["native_qbexec_total"] == "5"
        assert row["native_gemv_calls"] == "2"
        assert row["native_gemm_calls"] == "3"
        assert row["pass"] == "True"
        report = json.loads(json_path.read_text(encoding="utf-8"))
        assert report["executions"][0]["type"] == "Q4_K"
        assert report["summary"]["top1_agreement"] == 1
    print("PASS: QBS QEMU report summarization")


if __name__ == "__main__":
    main()
