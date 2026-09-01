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
RUN_CONFIG_FIELDS = (
    "capture_root",
    "source_commit",
    "source_dirty",
    "capture_manifest_sha256",
    "simv",
    "simv_sha256",
    "spike_elf_sha256",
    "ara_elf_sha256",
)
AKV_PERF_SUM_FIELDS = (
    "busy_cycles",
    "v2_full",
    "v2_refill",
    "v2_row_load",
    "v2_column_load",
    "v2_k_view_bank_cycles",
    "v2_bank_conflict_cycles",
    "v2_rejected",
    "q_external_bytes",
    "kv_external_bytes",
    "replay_bytes",
    "replay_backpressure_cycles",
)


def newest_complete_run(roots: list[Path], implementation: str, effective_kv: int):
    candidates = []
    for root in roots:
        candidates.extend(
            root.glob(f"decode_attention_core_{implementation}_kv{effective_kv}_20*")
        )
        if effective_kv == 16:
            candidates.extend(root.glob(f"decode_attention_core_{implementation}_20*"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        ara_log = candidate / "ara.log"
        config_path = candidate / "run.conf"
        perf_logs = list(candidate.glob("llm_perf_report_*.log"))
        if (not (candidate / "complete").is_file() or not config_path.is_file() or
                not ara_log.is_file() or not perf_logs or not perf_logs[0].stat().st_size):
            continue
        run_config = parse_key_values(config_path.read_text(errors="replace").replace("\n", " "))
        if (run_config.get("implementation") != implementation or
                int(run_config.get("effective_kv", -1)) != effective_kv):
            continue
        log_text = ara_log.read_text(errors="replace")
        match = OPERATOR_RE.search(log_text)
        if (match and match.group(1) == "PASS" and int(match.group(3)) == 0 and
                "Core Test *** SUCCESS" in log_text):
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
    akv_perf = {f"akv_{key}": 0 for key in AKV_PERF_SUM_FIELDS}
    akv_perf["akv_command_count"] = 0
    for line in log_text.splitlines():
        if not line.startswith("[AKV_PERF]"):
            continue
        values = parse_key_values(line)
        akv_perf["akv_command_count"] += 1
        for key in AKV_PERF_SUM_FIELDS:
            akv_perf[f"akv_{key}"] += int(values.get(key, "0"))
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
                **{key: run_config.get(key, "") for key in RUN_CONFIG_FIELDS},
                "run_dir": str(run),
                "status": status,
                "kernel_cycles": kernel_cycles,
                "mismatches": mismatches,
                **akv_perf,
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
        action="append",
        help="Attention run root; repeat to combine independent run directories",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    run_roots = args.run_root or [
        Path(__file__).resolve().parents[2] / "llama_attention_runs"
    ]
    output = args.output or run_roots[0] / "attention_core_summary.csv"

    rows = []
    for implementation in (
        "ref",
        "rvv",
        "tiled_rvv",
        "q64_rvv",
        "akv",
        "akv_v2",
        "akv_v2_prefill",
    ):
        for effective_kv in (16, 128, 256):
            selected = newest_complete_run(run_roots, implementation, effective_kv)
            if selected is not None:
                rows.extend(parse_run(implementation, effective_kv, *selected))
    if not rows:
        raise SystemExit("no completed Attention-core runs with LLM_PERF data")

    leading = [
        "implementation",
        "effective_kv",
        *RUN_CONFIG_FIELDS,
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
