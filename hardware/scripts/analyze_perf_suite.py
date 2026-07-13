#!/usr/bin/env python3
"""Aggregate Ara PERF logs into an RVV coverage and attribution-readiness audit."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from analyze_perf_bottleneck import build_diagnosis, parse_perf_log, _to_int


EXEC_CLASSES = (
    "valu", "mul", "div", "fp", "slide", "mask", "load", "store",
    "move_to_vec", "move_from_vec", "reshuffle",
)
SEW_FIELDS = {8: "vset_sew8_insns", 16: "vset_sew16_insns", 32: "vset_sew32_insns", 64: "vset_sew64_insns"}
LEGAL_LMUL_ENCODINGS = (0, 1, 2, 3, 5, 6, 7)
MEMORY_SHAPES = {
    "unit_stride": ("load_arch_unit_stride_insns", "store_arch_unit_stride_insns"),
    "strided": ("load_arch_strided_insns", "store_arch_strided_insns"),
    "indexed_unordered": ("load_arch_indexed_unordered_insns", "store_arch_indexed_unordered_insns"),
    "indexed_ordered": ("load_arch_indexed_ordered_insns", "store_arch_indexed_ordered_insns"),
    "segment": ("load_arch_segment_insns", "store_arch_segment_insns"),
    "whole_register": ("load_arch_whole_register_insns", "store_arch_whole_register_insns"),
    "mask_memory": ("load_arch_mask_memory_insns", "store_arch_mask_memory_insns"),
    "fault_only_first": ("load_fault_only_first_insns",),
}
ACCEPTED_MEMORY_SHAPES = {
    "unit_stride": ("load_accepted_unit_stride_insns", "store_accepted_unit_stride_insns"),
    "strided": ("load_accepted_strided_insns", "store_accepted_strided_insns"),
    "indexed_unordered": ("load_accepted_indexed_unordered_insns", "store_accepted_indexed_unordered_insns"),
    "indexed_ordered": ("load_accepted_indexed_ordered_insns", "store_accepted_indexed_ordered_insns"),
    "segment": ("load_accepted_segment_insns", "store_accepted_segment_insns"),
    "whole_register": ("load_accepted_whole_register_insns", "store_accepted_whole_register_insns"),
    "mask_memory": ("load_accepted_mask_memory_insns", "store_accepted_mask_memory_insns"),
    "fault_only_first": ("load_accepted_fault_only_first_insns",),
}
OP_ACTIVITY_RE = re.compile(r"^op_(?P<op>.+?)_(?:arch_insns|backend_uops)$")


def args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("logs", nargs="+", help="PERF logs belonging to one regression suite")
    p.add_argument("--json", action="store_true", help="Print JSON")
    p.add_argument("--json-out", default="", help="Write JSON report")
    p.add_argument("--require-complete", action="store_true", help="Exit 2 unless all categories and every log pass")
    return p.parse_args()


def positive(metrics: dict[str, str], key: str) -> bool:
    return (_to_int(metrics.get(key)) or 0) > 0


def collect(logs: list[str]) -> dict[str, object]:
    observed_classes: set[str] = set()
    validated_classes: set[str] = set()
    timeout_attributed_classes: set[str] = set()
    observed_ops: set[str] = set()
    observed_sew: set[int] = set()
    observed_lmul: set[int] = set()
    observed_memory: set[str] = set()
    backend_memory_shapes: set[str] = set()
    accepted_memory_shapes: set[str] = set()
    masked_seen = False
    unmasked_seen = False
    per_log: list[dict[str, object]] = []

    for name in logs:
        metrics = parse_perf_log(name)
        diagnosis = build_diagnosis(metrics)
        classes = [
            c for c in EXEC_CLASSES
            if positive(metrics, f"{c}_active_cycles")
            or positive(metrics, f"{c}_arch_insns")
            or positive(metrics, f"{c}_dispatch_request_cycles")
        ]
        observed_classes.update(classes)
        if diagnosis["coverage_audit"]["close_loop_ready"]:
            validated_classes.update(classes)
        elif diagnosis["timeout_snapshot"]["triggered"]:
            timeout_attributed_classes.update(classes)

        log_ops: set[str] = set()
        for key, value in metrics.items():
            match = OP_ACTIVITY_RE.match(key)
            if match and (_to_int(value) or 0) > 0:
                log_ops.add(match.group("op"))
        observed_ops.update(log_ops)

        for sew, field in SEW_FIELDS.items():
            if positive(metrics, field) or any(positive(metrics, f"{c}_sew{sew}_insns") for c in EXEC_CLASSES):
                observed_sew.add(sew)
        for enc in LEGAL_LMUL_ENCODINGS:
            if positive(metrics, f"vset_lmul_encoding_{enc}_insns") or any(
                positive(metrics, f"op_{op}_lmul_encoding_{enc}_uops") for op in log_ops
            ):
                observed_lmul.add(enc)

        total_uops = sum((_to_int(metrics.get(f"op_{op}_backend_uops")) or 0) for op in log_ops)
        masked_uops = sum((_to_int(metrics.get(f"op_{op}_masked_uops")) or 0) for op in log_ops)
        masked_seen |= masked_uops > 0
        unmasked_seen |= total_uops > masked_uops

        for shape, fields in MEMORY_SHAPES.items():
            if any(positive(metrics, field) for field in fields):
                observed_memory.add(shape)
        for shape, fields in ACCEPTED_MEMORY_SHAPES.items():
            if any(positive(metrics, field) for field in fields):
                accepted_memory_shapes.add(shape)
        if positive(metrics, "load_unit_stride_backend_uops") or positive(metrics, "store_unit_stride_backend_uops"):
            backend_memory_shapes.add("unit_stride")
        if positive(metrics, "load_strided_backend_uops") or positive(metrics, "store_strided_backend_uops"):
            backend_memory_shapes.add("strided")
        if positive(metrics, "load_indexed_backend_uops") or positive(metrics, "store_indexed_backend_uops"):
            backend_memory_shapes.add("indexed_order_unspecified")
        if positive(metrics, "load_segment_backend_uops") or positive(metrics, "store_segment_backend_uops"):
            backend_memory_shapes.add("segment")
        if positive(metrics, "load_fault_only_first_backend_uops"):
            backend_memory_shapes.add("fault_only_first")

        per_log.append(
            {
                "log": str(Path(name).resolve()),
                "close_loop_ready": diagnosis["coverage_audit"]["close_loop_ready"],
                "confidence": diagnosis["coverage_audit"]["confidence"],
                "readiness_blockers": diagnosis["coverage_audit"]["readiness_blockers"],
                "observed_classes": sorted(classes),
                "observed_opcodes": sorted(log_ops),
            }
        )

    missing_classes = sorted(set(EXEC_CLASSES) - observed_classes)
    missing_validated_classes = sorted(set(EXEC_CLASSES) - validated_classes)
    missing_sew = sorted(set(SEW_FIELDS) - observed_sew)
    missing_lmul = sorted(set(LEGAL_LMUL_ENCODINGS) - observed_lmul)
    missing_memory = sorted(set(MEMORY_SHAPES) - observed_memory)
    failed_logs = [item["log"] for item in per_log if not item["close_loop_ready"]]
    shape_complete = not missing_sew and not missing_lmul and masked_seen and unmasked_seen and not missing_memory
    complete = not missing_classes and shape_complete and not failed_logs

    return {
        "suite_complete": complete,
        "log_count": len(per_log),
        "failed_log_count": len(failed_logs),
        "failed_logs": failed_logs,
        "class_coverage": {
            "observed": sorted(observed_classes),
            "missing": missing_classes,
            "coverage": round(100.0 * len(observed_classes) / len(EXEC_CLASSES), 2),
            "validated": sorted(validated_classes),
            "validation_missing": missing_validated_classes,
            "validated_coverage": round(100.0 * len(validated_classes) / len(EXEC_CLASSES), 2),
            "timeout_attributed": sorted(timeout_attributed_classes),
        },
        "opcode_coverage": {"observed": sorted(observed_ops), "count": len(observed_ops)},
        "shape_coverage": {
            "sew_observed": sorted(observed_sew),
            "sew_missing": missing_sew,
            "lmul_encoding_observed": sorted(observed_lmul),
            "lmul_encoding_missing": missing_lmul,
            "masked_seen": masked_seen,
            "unmasked_seen": unmasked_seen,
            "memory_shapes_observed": sorted(observed_memory),
            "accepted_memory_shapes_observed": sorted(accepted_memory_shapes),
            "backend_memory_shapes_observed": sorted(backend_memory_shapes),
            "memory_shapes_missing": missing_memory,
            "complete": shape_complete,
        },
        "logs": per_log,
    }


def print_md(report: dict[str, object]) -> None:
    classes = report["class_coverage"]
    shapes = report["shape_coverage"]
    print("## Ara RVV 性能回归套件覆盖审计")
    print(f"- 日志数: {report['log_count']}")
    print(f"- 套件闭环完备: {'是' if report['suite_complete'] else '否'}")
    print(f"- 类别覆盖: {classes['coverage']:.2f}%")
    print(f"- 已覆盖类别: {', '.join(classes['observed']) or '无'}")
    print(f"- 缺失类别: {', '.join(classes['missing']) or '无'}")
    print(f"- 正常闭环验证类别: {classes['validated_coverage']:.2f}%")
    print(f"- 已正常验证: {', '.join(classes['validated']) or '无'}")
    print(f"- 尚未正常验证: {', '.join(classes['validation_missing']) or '无'}")
    print(f"- 已有超时归因证据: {', '.join(classes['timeout_attributed']) or '无'}")
    print(f"- 已覆盖 opcode 数: {report['opcode_coverage']['count']}")
    print(f"- SEW 已覆盖/缺失: {shapes['sew_observed']} / {shapes['sew_missing']}")
    print(f"- LMUL 编码已覆盖/缺失: {shapes['lmul_encoding_observed']} / {shapes['lmul_encoding_missing']}")
    print(f"- masked/unmasked: {shapes['masked_seen']}/{shapes['unmasked_seen']}")
    print(f"- 内存形态缺失: {', '.join(shapes['memory_shapes_missing']) or '无'}")
    print(f"- sequencer 已接受的访存形态: {', '.join(shapes['accepted_memory_shapes_observed']) or '无'}")
    print(f"- backend 已接收的访存形态: {', '.join(shapes['backend_memory_shapes_observed']) or '无'}")
    print(f"- 未通过单日志闭环门禁: {report['failed_log_count']}")
    for item in report["logs"]:
        print(
            f"  - {item['log']}: ready={item['close_loop_ready']} confidence={item['confidence']} "
            f"classes={','.join(item['observed_classes']) or 'none'}"
        )
        if item["readiness_blockers"]:
            print(f"    blockers={','.join(item['readiness_blockers'])}")


def main() -> int:
    ns = args()
    try:
        report = collect(ns.logs)
    except FileNotFoundError:
        return 1
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if ns.json:
        print(text)
    else:
        print_md(report)
    if ns.json_out:
        Path(ns.json_out).write_text(text + "\n", encoding="utf-8")
    return 2 if ns.require_complete and not report["suite_complete"] else 0


if __name__ == "__main__":
    sys.exit(main())
