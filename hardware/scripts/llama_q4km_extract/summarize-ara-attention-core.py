#!/usr/bin/env python3

import argparse
import csv
import re
from pathlib import Path


OPERATOR_RE = re.compile(
    r"LLAMA_OPERATOR\s+\S+\s+(PASS|FAIL)\s+cycles=(\d+)\s+mismatches=(\d+)"
)
PHASE_NAMES = {
    "total": "total",
    "quantize": "q_convert",
    "pack": "online_kv",
    "matmul": "output_norm",
}


def newest_complete_run(root: Path, implementation: str, effective_kv: int):
    candidates = list(
        root.glob(f"decode_attention_core_{implementation}_kv{effective_kv}_20*")
    )
    if effective_kv == 16:
        candidates.extend(root.glob(f"decode_attention_core_{implementation}_20*"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        ara_log = candidate / "ara.log"
        perf_logs = list(candidate.glob("llm_perf_report_*.log"))
        if (ara_log.is_file() and perf_logs and
                OPERATOR_RE.search(ara_log.read_text(errors="replace"))):
            return candidate, ara_log, perf_logs[0]
    return None


def parse_key_values(line: str):
    values = {}
    for token in line.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        values[key] = value
    return values


def parse_run(implementation: str, effective_kv: int, run, ara_log: Path, perf_log: Path):
    log_text = ara_log.read_text(errors="replace")
    run_config = {}
    config_path = run / "run.conf"
    if config_path.is_file():
        run_config = parse_key_values(config_path.read_text(errors="replace").replace("\n", " "))
    match = OPERATOR_RE.search(log_text)
    status = match.group(1) if match else "UNKNOWN"
    kernel_cycles = match.group(2) if match else ""
    mismatches = match.group(3) if match else ""
    rows = []
    for line in perf_log.read_text(errors="replace").splitlines():
        if not line.startswith("[LLM_PERF]"):
            continue
        values = parse_key_values(line)
        phase = PHASE_NAMES.get(values.pop("phase", ""), "unknown")
        values.pop("case", None)
        rows.append(
            {
                "implementation": implementation,
                "effective_kv": effective_kv,
                "capture_root": run_config.get("capture_root", ""),
                "run_dir": str(run),
                "status": status,
                "kernel_cycles": kernel_cycles,
                "mismatches": mismatches,
                "phase": phase,
                **values,
            }
        )
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "llama_attention_runs",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.run_root / "attention_core_summary.csv"

    rows = []
    for implementation in ("ref", "rvv", "tiled_rvv", "akv"):
        for effective_kv in (16, 128, 256):
            selected = newest_complete_run(args.run_root, implementation, effective_kv)
            if selected is not None:
                rows.extend(parse_run(implementation, effective_kv, *selected))
    if not rows:
        raise SystemExit("no completed Attention-core runs with LLM_PERF data")

    leading = [
        "implementation",
        "effective_kv",
        "capture_root",
        "run_dir",
        "status",
        "kernel_cycles",
        "mismatches",
        "phase",
    ]
    remaining = sorted({key for row in rows for key in row} - set(leading))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=leading + remaining)
        writer.writeheader()
        writer.writerows(rows)
    print(output)


if __name__ == "__main__":
    main()
