#!/usr/bin/env python3
"""Compare baseline/candidate Ara PERF logs for optimization validation.

The comparison is deliberately workload-aware: it refuses a closed-loop
speedup claim when opcode counts, requested work, mask mix, or SEW/LMUL shape
changed.  This prevents a faster but smaller/different ROI from being reported
as an RTL optimization.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from analyze_perf_bottleneck import build_diagnosis, parse_perf_log, _to_float, _to_int


OP_WORK_RE = re.compile(
    r"^op_(?P<op>.+?)_(?P<field>arch_insns|backend_uops|requested_elements|"
    r"nominal_element_ops|masked_uops|sew_encoding_[0-3]_uops|"
    r"lmul_encoding_[0-7]_uops)$"
)

# A positive normalized delta always means improvement.
CORE_METRICS = {
    "total_cycles": "lower",
    "IPC": "higher",
    "global_dispatch_blocked_ratio": "lower",
    "global_issue_progress_ratio": "higher",
    "global_no_issue_progress_ratio": "lower",
    "load_axi_useful_bytes_per_cycle": "higher",
    "store_axi_useful_bytes_per_cycle": "higher",
    "load_axi_avg_request_to_response_latency": "lower",
    "store_axi_avg_request_to_response_latency": "lower",
    "load_axi_avg_outstanding": "higher",
    "store_axi_avg_outstanding": "higher",
}


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("baseline")
    p.add_argument("candidate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--json-out", default="")
    p.add_argument("--top-n", type=int, default=15)
    p.add_argument("--require-ready", action="store_true",
                   help="fail unless both inputs pass single-log attribution gates")
    p.add_argument("--require-equivalent", action="store_true",
                   help="fail when the architectural/backend workload fingerprints differ")
    p.add_argument("--fail-regression-pct", type=float, default=None,
                   help="exit 2 if total_cycles regresses by more than this percentage")
    return p.parse_args()


def number(metrics: dict[str, str], key: str) -> float | None:
    return _to_float(metrics.get(key))


def fingerprint(metrics: dict[str, str]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in metrics.items():
        if OP_WORK_RE.match(key):
            result[key] = _to_int(value) or 0
    # Configuration and architectural memory subtypes are part of workload
    # identity even when no opcode-specific field distinguishes them.
    for key, value in metrics.items():
        if (
            key.startswith("vset_sew")
            or key.startswith("vset_lmul_encoding_")
            or "_arch_unit_stride_insns" in key
            or "_arch_strided_insns" in key
            or "_arch_indexed_" in key
            or "_arch_segment_insns" in key
            or "_arch_whole_register_insns" in key
            or "_arch_mask_memory_insns" in key
            or key == "load_fault_only_first_insns"
        ):
            result[key] = _to_int(value) or 0
    return result


def workload_diff(base: dict[str, int], cand: dict[str, int]) -> list[dict[str, object]]:
    changes = []
    for key in sorted(set(base) | set(cand)):
        b, c = base.get(key, 0), cand.get(key, 0)
        if b != c:
            changes.append({"metric": key, "baseline": b, "candidate": c, "delta": c - b})
    return changes


def metric_change(key: str, direction: str, b: float, c: float) -> dict[str, object]:
    delta = c - b
    pct = (delta / abs(b) * 100.0) if b else None
    improvement_pct = None if pct is None else (pct if direction == "higher" else -pct)
    return {
        "metric": key,
        "direction": direction,
        "baseline": b,
        "candidate": c,
        "delta": delta,
        "delta_pct": pct,
        "improvement_pct": improvement_pct,
    }


def collect_dynamic_metrics(base: dict[str, str], cand: dict[str, str]) -> dict[str, str]:
    result = dict(CORE_METRICS)
    suffix_direction = {
        "_avg_execution_latency": "lower",
        "_dispatch_blocked_ratio": "lower",
        "_primary_unattributed_ratio": "lower",
        "_primary_result_backpressure_ratio": "lower",
        "_primary_result_queue_full_ratio": "lower",
        "_primary_operand_wait_ratio": "lower",
        "_primary_long_latency_busy_ratio": "lower",
        "_vrf_bank_conflict_ratio": "lower",
        "_predicate_active_ratio": "higher",
    }
    common = set(base) & set(cand)
    for key in common:
        if key.startswith("op_") or any(key.startswith(c + "_") for c in (
            "valu", "mul", "div", "fp", "slide", "mask", "load", "store",
            "move_to_vec", "move_from_vec", "reshuffle"
        )):
            for suffix, direction in suffix_direction.items():
                if key.endswith(suffix):
                    result[key] = direction
                    break
    return result


def build_report(base_path: str, cand_path: str) -> dict[str, object]:
    base = parse_perf_log(base_path)
    cand = parse_perf_log(cand_path)
    base_diag = build_diagnosis(base)
    cand_diag = build_diagnosis(cand)
    fp_diff = workload_diff(fingerprint(base), fingerprint(cand))
    changes = []
    for key, direction in collect_dynamic_metrics(base, cand).items():
        b, c = number(base, key), number(cand, key)
        if b is not None and c is not None:
            changes.append(metric_change(key, direction, b, c))
    comparable = [x for x in changes if x["improvement_pct"] is not None]
    improvements = sorted(comparable, key=lambda x: float(x["improvement_pct"]), reverse=True)
    regressions = sorted(comparable, key=lambda x: float(x["improvement_pct"]))
    total = next((x for x in changes if x["metric"] == "total_cycles"), None)
    return {
        "baseline": str(Path(base_path).resolve()),
        "candidate": str(Path(cand_path).resolve()),
        "baseline_ready": base_diag["coverage_audit"]["close_loop_ready"],
        "candidate_ready": cand_diag["coverage_audit"]["close_loop_ready"],
        "baseline_blockers": base_diag["coverage_audit"]["readiness_blockers"],
        "candidate_blockers": cand_diag["coverage_audit"]["readiness_blockers"],
        "workload_equivalent": not fp_diff,
        "comparison_valid": not fp_diff and
            base_diag["coverage_audit"]["close_loop_ready"] and
            cand_diag["coverage_audit"]["close_loop_ready"],
        "workload_differences": fp_diff,
        "total_cycles_change": total,
        "improvements": improvements,
        "regressions": regressions,
        "all_changes": changes,
    }


def print_markdown(report: dict[str, object], top_n: int) -> None:
    print("## Ara PERF 优化前后对比")
    print(f"- baseline: `{report['baseline']}`")
    print(f"- candidate: `{report['candidate']}`")
    print(f"- 单日志门禁: baseline={report['baseline_ready']} / candidate={report['candidate_ready']}")
    print(f"- workload 等价: {'是' if report['workload_equivalent'] else '否'}")
    print(f"- 可用于优化结论: {'是' if report['comparison_valid'] else '否'}")
    total = report["total_cycles_change"]
    if total:
        pct = "n/a" if total["improvement_pct"] is None else f"{total['improvement_pct']:+.3f}%"
        print(f"- total cycles: {total['baseline']:.0f} -> {total['candidate']:.0f}，改善 {pct}")
    if report["workload_differences"]:
        print("\n### Workload 差异（存在时禁止直接宣称 speedup）")
        for item in report["workload_differences"][:top_n]:
            print(f"- `{item['metric']}`: {item['baseline']} -> {item['candidate']} (delta={item['delta']:+d})")
    if not report["comparison_valid"]:
        print("\n> 对比门禁未通过；以下逐指标排名已抑制，不能据此宣称优化或退化。")
        return
    print("\n### 改善 Top")
    for item in report["improvements"][:top_n]:
        if float(item["improvement_pct"]) <= 0:
            continue
        print(f"- `{item['metric']}`: {item['baseline']:.6g} -> {item['candidate']:.6g} ({item['improvement_pct']:+.3f}%)")
    print("\n### 退化 Top")
    for item in report["regressions"][:top_n]:
        if float(item["improvement_pct"]) >= 0:
            continue
        print(f"- `{item['metric']}`: {item['baseline']:.6g} -> {item['candidate']:.6g} ({item['improvement_pct']:+.3f}%)")


def main() -> int:
    ns = arguments()
    report = build_report(ns.baseline, ns.candidate)
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        print(text)
    else:
        print_markdown(report, ns.top_n)
    if ns.json_out:
        Path(ns.json_out).write_text(text + "\n", encoding="utf-8")
    failed = False
    if ns.require_ready and not (report["baseline_ready"] and report["candidate_ready"]):
        failed = True
    if ns.require_equivalent and not report["workload_equivalent"]:
        failed = True
    if ns.fail_regression_pct is not None and report["total_cycles_change"]:
        improvement = report["total_cycles_change"]["improvement_pct"]
        if improvement is None or float(improvement) < -ns.fail_regression_pct:
            failed = True
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
