#!/usr/bin/env python3

import argparse
import csv
import hashlib
import json
import re
import struct
import subprocess
from pathlib import Path


PHASE_RE = re.compile(r"^\[LLM_PERF\] ")
TRACE_MNEMONICS = {
    "vle": re.compile(r"\bvle(?:8|16|32|64)\.v\b"),
    "whole_load": re.compile(r"\bvl(?:1|2|4|8)re8\.v\b"),
    "vse": re.compile(r"\bvse(?:8|16|32|64)\.v\b"),
    "whole_store": re.compile(r"\bvs(?:1|2|4|8)r\.v\b"),
    "fp_reduction": re.compile(r"\bvf(?:w)?red(?:u|o)?sum\.vs\b"),
    "vector_to_scalar": re.compile(r"\bvfmv\.f\.s\b"),
    "widen_mac": re.compile(r"\bvfwmacc\.vv\b"),
    "fp_scale": re.compile(r"\bvfmul\.vf\b"),
    "fp_vector_fma": re.compile(r"\bvfmadd\.vf\b"),
}


def load_json(path):
    return json.loads(path.read_text())


def parse_key_values(line):
    values = {}
    for token in line.split():
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def latest_perf(run_root, effective_kv):
    candidates = list(run_root.glob(f"decode_attention_core_rvv_kv{effective_kv}_20*"))
    if effective_kv == 16:
        candidates.extend(run_root.glob("decode_attention_core_rvv_20*"))
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for run in candidates:
        reports = list(run.glob("llm_perf_report_*.log"))
        ara_log = run / "ara.log"
        if reports and ara_log.is_file() and " PASS " in ara_log.read_text(errors="replace"):
            rows = {}
            for line in reports[0].read_text(errors="replace").splitlines():
                if PHASE_RE.match(line):
                    values = parse_key_values(line)
                    rows[values["phase"]] = values
            if "total" in rows and "pack" in rows:
                return run, rows
    return None, {}


def count_trace_lines(lines):
    counts = {name: 0 for name in TRACE_MNEMONICS}
    for line in lines:
        for name, pattern in TRACE_MNEMONICS.items():
            counts[name] += len(pattern.findall(line))
    return counts


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def latest_trace(run_root, effective_kv, spike):
    run_candidates = list(run_root.glob(f"decode_attention_core_rvv_kv{effective_kv}_20*"))
    run_candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    for run in run_candidates:
        traces = list(run.glob("spike.trace"))
        if traces:
            with traces[0].open(errors="replace") as stream:
                return count_trace_lines(stream)

        elfs = list(run.glob("*.rvv.spike"))
        if not elfs or not spike.is_file():
            continue
        elf = elfs[0]
        elf_hash = sha256(elf)
        cache = run / "spike_instruction_counts.json"
        if cache.is_file():
            payload = load_json(cache)
            if payload.get("elf_sha256") == elf_hash:
                return payload["counts"]

        command = [
            "timeout", "--foreground", "600", str(spike), "-l",
            "--isa=rv64gcv_zfh", "--varch=vlen:1024,elen:64", str(elf),
        ]
        process = subprocess.Popen(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            text=True, errors="replace",
        )
        assert process.stderr is not None
        counts = count_trace_lines(process.stderr)
        return_code = process.wait()
        if return_code != 0:
            raise RuntimeError(
                f"Spike instruction count failed for {elf} with status {return_code}"
            )
        cache.write_text(json.dumps({
            "elf": str(elf),
            "elf_sha256": elf_hash,
            "counts": counts,
        }, indent=2) + "\n")
        return counts
    return {}


def integer(values, key):
    return int(values[key]) if key in values else None


def analyze_capture(capture_root, run_root, spike, expected_kv):
    block = capture_root / "decode/block"
    qmeta = load_json(block / "attn_q_input-0.json")
    kmeta = load_json(block / "attn_k_input-0.json")
    mask = (block / "attn_mask_input-0.bin").read_bytes()
    mask_values = struct.unpack(f"<{len(mask) // 2}H", mask)
    active_kv = sum(value != 0xFC00 for value in mask_values)
    if active_kv != expected_kv:
        raise RuntimeError(f"{capture_root}: expected {expected_kv} active KV entries, got {active_kv}")

    dim, tokens, qheads, _ = map(int, qmeta["shape"])
    _, capacity, kvheads, _ = map(int, kmeta["shape"])
    queries = tokens * qheads
    dot_products = queries * active_kv
    element_bytes = 2
    vector_bytes = dim * element_bytes

    q_stream_bytes = dot_products * vector_bytes
    q_resident_bytes = queries * vector_bytes
    kv_stream_bytes = 2 * dot_products * vector_bytes
    kv_gqa_reuse_bytes = 2 * kvheads * active_kv * vector_bytes
    accum_rmw_bytes = 2 * dot_products * vector_bytes
    current_target_bytes = q_stream_bytes + kv_stream_bytes + accum_rmw_bytes
    resident_target_bytes = q_resident_bytes + kv_gqa_reuse_bytes

    run, phases = latest_perf(run_root, expected_kv)
    total = phases.get("total", {})
    online = phases.get("pack", {})
    trace = latest_trace(run_root, expected_kv, spike)
    # The current binary performs one final vector scale per query. Remaining
    # vfmul.vf instructions are data-dependent online-Softmax accumulator
    # rescales. Keep this compiled-code fact separate from the algorithmic
    # lower bound so a future implementation may change the instruction mix.
    observed_rescales = None
    if "fp_scale" in trace and trace["fp_scale"] >= queries:
        observed_rescales = trace["fp_scale"] - queries
    observed_accum_rmw = (
        2 * (dot_products + observed_rescales) * vector_bytes
        if observed_rescales is not None else None
    )
    observed_accum_one_way = (
        observed_accum_rmw // 2 if observed_accum_rmw is not None else None
    )
    observed_current_target = (
        q_stream_bytes + kv_stream_bytes + observed_accum_rmw
        if observed_accum_rmw is not None else None
    )
    observed_scratch_load = (
        trace["whole_load"] * vector_bytes if "whole_load" in trace else None
    )
    observed_logical_read = (
        q_stream_bytes + kv_stream_bytes + observed_accum_one_way +
        observed_scratch_load
        if observed_accum_one_way is not None and observed_scratch_load is not None
        else None
    )
    observed_logical_write = observed_accum_one_way
    online_cycles = integer(online, "cycles")
    total_cycles = integer(total, "cycles")
    reductions = integer(online, "fp_reduction_count")
    reduction_cycles = integer(online, "fp_reduction_active_cycles")
    scalar_inst = integer(online, "retired_scalar_inst_count")
    retired_inst = integer(online, "retired_inst_count")

    return {
        "effective_kv": active_kv,
        "kv_capacity": capacity,
        "head_dim": dim,
        "q_heads": qheads,
        "kv_heads": kvheads,
        "gqa_group": qheads // kvheads,
        "queries": queries,
        "dot_products": dot_products,
        "masked_probe_iterations": queries * (capacity - active_kv),
        "q_stream_bytes": q_stream_bytes,
        "q_resident_bytes": q_resident_bytes,
        "q_avoidable_bytes": q_stream_bytes - q_resident_bytes,
        "kv_stream_bytes": kv_stream_bytes,
        "kv_gqa_reuse_bytes": kv_gqa_reuse_bytes,
        "kv_avoidable_bytes": kv_stream_bytes - kv_gqa_reuse_bytes,
        "accum_rmw_bytes_lower_bound": accum_rmw_bytes,
        "observed_accum_rescale_count": observed_rescales,
        "observed_accum_rmw_bytes": observed_accum_rmw,
        "current_target_bytes_lower_bound": current_target_bytes,
        "observed_current_target_bytes": observed_current_target,
        "observed_dot_scratch_load_bytes": observed_scratch_load,
        "observed_logical_read_bytes": observed_logical_read,
        "observed_logical_write_bytes": observed_logical_write,
        "resident_target_bytes_lower_bound": resident_target_bytes,
        "target_traffic_reduction_bound": current_target_bytes / resident_target_bytes,
        "observed_target_traffic_reduction": (
            observed_current_target / resident_target_bytes
            if observed_current_target is not None else None
        ),
        "rtl_run": str(run) if run else "",
        "rtl_total_cycles": total_cycles,
        "rtl_online_cycles": online_cycles,
        "rtl_online_fraction": online_cycles / total_cycles if online_cycles and total_cycles else None,
        "rtl_backend_busy_fraction": (
            integer(online, "backend_busy_cycles") / online_cycles
            if online_cycles and integer(online, "backend_busy_cycles") is not None
            else None
        ),
        "rtl_lane_active_fraction": (
            integer(online, "lane_active_cycles") / online_cycles
            if online_cycles and integer(online, "lane_active_cycles") is not None
            else None
        ),
        "rtl_compute_active_fraction": (
            integer(online, "compute_active_cycles") / online_cycles
            if online_cycles and integer(online, "compute_active_cycles") is not None
            else None
        ),
        "rtl_mfpu_active_fraction": (
            integer(online, "mfpu_exec_active_cycles") / online_cycles
            if online_cycles and integer(online, "mfpu_exec_active_cycles") is not None
            else None
        ),
        "rtl_reduction_count": reductions,
        "rtl_reduction_active_cycles": reduction_cycles,
        "rtl_cycles_per_reduction": reduction_cycles / reductions if reductions and reduction_cycles is not None else None,
        "rtl_online_scalar_fraction": scalar_inst / retired_inst if scalar_inst is not None and retired_inst else None,
        "rtl_req_blocked_cycles": integer(online, "req_blocked_cycles"),
        "rtl_req_blocked_fraction": (
            integer(online, "req_blocked_cycles") / online_cycles
            if online_cycles and integer(online, "req_blocked_cycles") is not None
            else None
        ),
        "rtl_queue_full_cycles": integer(online, "queue_full_cycles"),
        "rtl_hazard_block_cycles": integer(online, "hazard_block_cycles"),
        "rtl_scalar_result_wait_cycles": integer(online, "scalar_result_wait_cycles"),
        "rtl_unit_load_span_bytes_diagnostic": integer(online, "unit_load_span_bytes"),
        "rtl_axi_ar_bytes": integer(online, "axi_ar_bytes"),
        "rtl_axi_aw_bytes": integer(online, "axi_aw_bytes"),
        "rtl_axi_read_amplification": (
            integer(online, "axi_ar_bytes") / observed_logical_read
            if observed_logical_read and integer(online, "axi_ar_bytes") is not None
            else None
        ),
        **{f"spike_{name}_count": value for name, value in trace.items()},
    }


def format_value(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--capture-set",
        type=Path,
        default=Path("/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-latest"),
    )
    parser.add_argument(
        "--run-root",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "llama_attention_runs",
    )
    parser.add_argument(
        "--spike",
        type=Path,
        default=Path(__file__).resolve().parents[3] / "install/riscv-isa-sim/bin/spike",
    )
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()
    rows = [
        analyze_capture(
            args.capture_set / f"kv{effective_kv}", args.run_root, args.spike,
            effective_kv,
        )
        for effective_kv in (16, 128, 256)
    ]

    csv_path = args.csv or args.run_root / "attention_baseline_analysis.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    markdown_path = args.markdown or args.run_root / "attention_baseline_analysis.md"
    columns = [
        "effective_kv", "dot_products", "masked_probe_iterations",
        "current_target_bytes_lower_bound", "resident_target_bytes_lower_bound",
        "target_traffic_reduction_bound", "observed_accum_rescale_count",
        "observed_current_target_bytes", "observed_dot_scratch_load_bytes",
        "rtl_total_cycles", "rtl_online_cycles",
        "rtl_online_fraction", "rtl_compute_active_fraction",
        "rtl_cycles_per_reduction", "rtl_online_scalar_fraction",
    ]
    with markdown_path.open("w") as stream:
        stream.write("| " + " | ".join(columns) + " |\n")
        stream.write("|" + "|".join("---:" for _ in columns) + "|\n")
        for row in rows:
            stream.write("| " + " | ".join(format_value(row[column]) for column in columns) + " |\n")
        stream.write("\n`*_lower_bound` excludes data-dependent accumulator rescale traffic. ")
        stream.write("`rtl_unit_load_span_bytes_diagnostic` is not a strict byte count for whole-register transfers.\n")

    print(csv_path)
    print(markdown_path)


if __name__ == "__main__":
    main()
