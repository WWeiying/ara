#!/usr/bin/env python3
"""Analyze Ara RVV [PERF] logs and produce a bottleneck-oriented diagnosis.

Usage:
  python3 hardware/scripts/analyze_perf_bottleneck.py <perf_log>

Optional:
  --json          Output raw diagnosis JSON only.
  --md            Output markdown table style text.
  --json-out PATH Write JSON report to file.
  --require-ready Exit with status 2 unless the log is safe for closed-loop use.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


PERF_PREFIX = re.compile(r"^\[PERF\]\s+(?P<key>[^:]+):\s*(?P<val>.*)$")
OP_TOP_RE = re.compile(r"^op_(?P<entity>.+?)_(?P<metric>top_.*)$")
CLASS_TOP_RE = re.compile(r"^(?P<entity>[a-z0-9_]+)_(?P<metric>top_.*)$")

GLOBAL_REQUIRED_FIELDS = [
    "global_total_dispatch_request_cycles",
    "global_total_exec_active_cycles",
    "global_stage_mode",
    "global_bottleneck_focus",
    "global_dispatch_blocked_ratio",
    "global_issue_progress_ratio",
    "global_no_issue_progress_ratio",
    "global_top_primary_dispatch_bottleneck_reason",
    "global_top_primary_exec_bottleneck_reason",
    "global_top_primary_dispatch_bottleneck_advice",
    "global_top_primary_exec_bottleneck_advice",
    "global_top_dispatch_bottleneck_dominance_ratio",
    "global_top_exec_bottleneck_dominance_ratio",
    "global_top2_dispatch_bottleneck_share",
    "global_top2_exec_bottleneck_share",
    "global_dispatch_exec_class_overlap",
    "global_dispatch_exec_opcode_overlap",
    "global_bottleneck_pressure_alignment",
    "global_bottleneck_opcode_alignment",
    "global_top_class_request_share",
    "global_top_class_active_share",
    "global_top_class_share_skew",
    "global_top_opcode_request_share",
    "global_top_opcode_active_share",
    "global_top_opcode_share_skew",
    "global_primary_dispatch_partition_consistent",
    "global_primary_exec_partition_consistent",
    "global_exec_progress_partition_consistent",
]

OP_REQUIRED_TOP_FIELDS = [
    "top_primary_dispatch_bottleneck_reason",
    "top_primary_dispatch_bottleneck_cycles",
    "top_primary_dispatch_bottleneck_ratio_dispatch_request",
    "top_primary_dispatch_bottleneck_ratio_dispatch_blocked",
    "top_secondary_dispatch_bottleneck_reason",
    "top_secondary_dispatch_bottleneck_cycles",
    "top_secondary_dispatch_bottleneck_ratio_dispatch_request",
    "top_secondary_dispatch_bottleneck_ratio_dispatch_blocked",
    "top_dispatch_bottleneck_reason_gap",
    "top_dispatch_bottleneck_gap_ratio_dispatch_request",
    "top_dispatch_bottleneck_dominance_ratio",
    "top_secondary_dispatch_bottleneck_dominance_ratio",
    "top_primary_dispatch_bottleneck_advice",
    "top_primary_exec_bottleneck_reason",
    "top_primary_exec_bottleneck_cycles",
    "top_primary_exec_bottleneck_ratio_exec_active",
    "top_secondary_exec_bottleneck_reason",
    "top_secondary_exec_bottleneck_cycles",
    "top_secondary_exec_bottleneck_ratio_exec_active",
    "top_exec_bottleneck_reason_gap",
    "top_exec_bottleneck_gap_ratio_exec_active",
    "top_exec_bottleneck_dominance_ratio",
    "top_secondary_exec_bottleneck_dominance_ratio",
    "top_primary_exec_bottleneck_advice",
]

CLASS_REQUIRED_TOP_FIELDS = [
    "top_primary_dispatch_bottleneck_reason",
    "top_primary_dispatch_bottleneck_cycles",
    "top_primary_dispatch_bottleneck_ratio_dispatch_request",
    "top_primary_dispatch_bottleneck_ratio_dispatch_blocked",
    "top_secondary_dispatch_bottleneck_reason",
    "top_secondary_dispatch_bottleneck_cycles",
    "top_secondary_dispatch_bottleneck_ratio_dispatch_request",
    "top_secondary_dispatch_bottleneck_ratio_dispatch_blocked",
    "top_dispatch_bottleneck_reason_gap",
    "top_dispatch_bottleneck_gap_ratio_dispatch_request",
    "top_dispatch_bottleneck_dominance_ratio",
    "top_secondary_dispatch_bottleneck_dominance_ratio",
    "top_primary_dispatch_bottleneck_advice",
    "top_primary_exec_bottleneck_reason",
    "top_primary_exec_bottleneck_cycles",
    # class uses a generic ratio name to reduce duplication in tb code
    ["top_primary_exec_bottleneck_ratio", "top_primary_exec_bottleneck_ratio_exec_active"],
    "top_secondary_exec_bottleneck_reason",
    "top_secondary_exec_bottleneck_cycles",
    ["top_secondary_exec_bottleneck_ratio", "top_secondary_exec_bottleneck_ratio_exec_active"],
    "top_exec_bottleneck_reason_gap",
    "top_exec_bottleneck_gap_ratio_exec_active",
    "top_exec_bottleneck_dominance_ratio",
    "top_secondary_exec_bottleneck_dominance_ratio",
    "top_primary_exec_bottleneck_advice",
]

OP_CONSISTENCY_FIELDS = [
    "primary_dispatch_partition_consistent",
    "dispatch_reasons_within_request",
    "primary_exec_partition_consistent",
    "dispatch_wait_hist_consistent",
    "execution_hist_consistent",
    "sew_hist_consistent",
    "lmul_hist_consistent",
    "shape_uop_consistent",
    "shape_completion_consistent",
    "window_lifecycle_complete",
]

CLASS_CONSISTENCY_FIELDS = [
    "window_lifecycle_complete",
    "dispatch_hist_consistent",
    "execution_hist_consistent",
    "active_partition_consistent",
    "primary_attribution_partition_consistent",
    "predicate_hist_consistent",
    "predicate_active_le_total_consistent",
    "vrf_request_partition_consistent",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", help="ARA perf log path")
    parser.add_argument("--json", action="store_true", help="Print JSON only")
    parser.add_argument("--md", action="store_true", help="Output markdown-friendly text")
    parser.add_argument("--json-out", default="", help="Optional json report output path")
    parser.add_argument("--top-n", type=int, default=8, help="Top-N entity candidates in markdown/json output")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="Exit 2 when coverage, samples, or counter consistency are insufficient for closed-loop attribution",
    )
    return parser.parse_args()


def parse_perf_log(path: str) -> dict[str, str]:
    metrics: dict[str, str] = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                if not raw.startswith("[PERF]"):
                    continue
                if "[PERF] ====" in raw:
                    continue
                m = PERF_PREFIX.match(raw.strip())
                if m:
                    key = m.group("key").strip()
                    val = m.group("val").strip()
                    metrics[key] = val
    except FileNotFoundError:
        print(f"ERROR: log not found: {path}", file=sys.stderr)
        raise
    return metrics


def _to_float(v: str) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        try:
            return float(int(v, 0))
        except Exception:
            return None


def _to_int(v: str) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(v, 0)
        except Exception:
            return None


def _clamp01(v: float | None) -> float:
    if v is None:
        return 0.0
    if v != v:
        return 0.0
    return max(0.0, min(1.0, v))


def _ratio(m: dict[str, str], key: str) -> float | None:
    return _to_float(m.get(key))


def _pick_metric(metrics: dict[str, str], candidates: str | list[str], default: str | None = None) -> str | None:
    if isinstance(candidates, str):
        candidates = [candidates]
    for key in candidates:
        if key in metrics:
            return metrics[key]
    return default


def _to_float_or_int_like(v: str | None) -> float:
    return _to_float(v) or 0.0


def _missing_metrics(metrics: dict[str, str], keys: list[str]) -> list[str]:
    return [k for k in keys if k not in metrics]


def _severity_color(v: float, thresholds: tuple[float, float] = (0.3, 0.6)) -> str:
    if v >= thresholds[1]:
        return "high"
    if v >= thresholds[0]:
        return "medium"
    return "low"


def _health_is_good(health: str) -> bool:
    return health == "good"


def _to_float_zero(v: str | None) -> float:
    return _to_float(v) or 0.0


def _safe_metric(metrics: dict[str, str], name: str, default: str = "none") -> str:
    return metrics.get(name, default)


def _extract_entities(metrics: dict[str, str], scope: str) -> dict[str, dict[str, str]]:
    entities: dict[str, dict[str, str]] = {}
    if scope == "op":
        matcher = OP_TOP_RE
        prefix = "op_"
    elif scope == "class":
        matcher = CLASS_TOP_RE
        prefix = ""
    else:
        raise ValueError(f"unknown scope: {scope}")

    for key, val in metrics.items():
        if scope == "class" and key.startswith("op_"):
            continue
        if not key.startswith(prefix):
            continue
        m = matcher.match(key)
        if not m:
            continue
        entity = m.group("entity")
        metric = m.group("metric")
        if scope == "class":
            if entity == "global":
                continue
            if not key.startswith(f"{entity}_"):
                continue
        # only parse top-level bottleneck metrics for ranking
        if not metric.startswith("top_"):
            continue
        if "bottleneck" not in metric and not metric.startswith("top_exec_wait_"):
            continue
        entities.setdefault(entity, {})[metric] = val
    return entities


def _is_entity_active(metrics: dict[str, str], scope: str, name: str) -> bool:
    if scope == "op":
        base_fields = [
            f"op_{name}_dispatch_request_cycles",
            f"op_{name}_active_cycles",
            f"op_{name}_dispatch_wait_cycles",
        ]
    elif scope == "class":
        base_fields = [
            f"{name}_dispatch_request_cycles",
            f"{name}_active_cycles",
            f"{name}_dispatch_wait_cycles",
            f"{name}_issued_insns",
        ]
    else:
        return False
    for fld in base_fields:
        val = _to_int(metrics.get(fld))
        if val is not None and val > 0:
            return True
    return False


def _entity_required_fields(scope: str) -> list:
    if scope == "op":
        return OP_REQUIRED_TOP_FIELDS
    if scope == "class":
        return CLASS_REQUIRED_TOP_FIELDS
    return []


def _field_present(metrics: dict[str, str], key_set: str | list[str]) -> tuple[bool, str | None]:
    if isinstance(key_set, str):
        return (key_set in metrics, key_set)
    for key in key_set:
        if key in metrics:
            return True, key
    return False, None


def _check_entity_top_completeness(metrics: dict[str, str], scope: str) -> dict[str, object]:
    required = _entity_required_fields(scope)
    raw = _extract_entities(metrics, scope)
    missing_entities: list[dict[str, object]] = []
    total_entities = 0
    covered_entities = 0
    coverage_sum = 0.0
    consistency_failures: list[dict[str, object]] = []

    for name, entity_metrics in raw.items():
        if not _is_entity_active(metrics, scope, name):
            continue
        total_entities += 1
        missing: list[str] = []
        present_count = 0
        for spec in required:
            if isinstance(spec, list):
                present, actual = _field_present(entity_metrics, spec)
                if not present:
                    missing.append("/".join(spec))
                else:
                    present_count += 1
            else:
                present, _ = _field_present(entity_metrics, spec)
                if not present:
                    missing.append(spec)
                else:
                    present_count += 1
        coverage = present_count / len(required) if required else 1.0
        coverage_sum += coverage
        if coverage < 1.0:
            missing_entities.append(
                {
                    "name": name,
                    "coverage": round(coverage * 100.0, 2),
                    "present_fields": present_count,
                    "required_fields": len(required),
                    "missing_fields": missing,
                }
            )
        else:
            covered_entities += 1

        consistency_fields = OP_CONSISTENCY_FIELDS if scope == "op" else CLASS_CONSISTENCY_FIELDS
        failed_checks: list[str] = []
        missing_checks: list[str] = []
        for check in consistency_fields:
            full_key = f"op_{name}_{check}" if scope == "op" else f"{name}_{check}"
            value = _to_int(metrics.get(full_key))
            if value is None:
                missing_checks.append(check)
            elif value != 1:
                failed_checks.append(check)
        if failed_checks or missing_checks:
            consistency_failures.append(
                {
                    "name": name,
                    "failed_checks": failed_checks,
                    "missing_checks": missing_checks,
                }
            )

    if total_entities == 0:
        return {
            "entity_count": 0,
            "covered_count": 0,
            # No sample is not complete coverage.  Keeping this at zero avoids
            # declaring an empty/truncated report ready for optimization.
            "avg_coverage": 0.0,
            "incomplete_count": 0,
            "top_incomplete": [],
            "sample_present": False,
            "consistency_failure_count": 0,
            "consistency_failures": [],
        }

    return {
        "entity_count": total_entities,
        "covered_count": covered_entities,
        "avg_coverage": round((coverage_sum / total_entities) * 100.0, 2),
        "incomplete_count": len(missing_entities),
        "top_incomplete": sorted(
            missing_entities, key=lambda x: (x["coverage"], -x["required_fields"])  # type: ignore[index]
        )[:20],
        "sample_present": True,
        "consistency_failure_count": len(consistency_failures),
        "consistency_failures": consistency_failures[:20],
    }


def _build_entity_candidates(
    metrics: dict[str, str], scope: str, top_n: int
) -> list[dict[str, object]]:
    raw = _extract_entities(metrics, scope)
    entries: list[dict[str, object]] = []

    for name, em in raw.items():
        dispatch_ratio = _to_float_or_int_like(
            _pick_metric(em, "top_primary_dispatch_bottleneck_ratio_dispatch_request")
        )
        exec_ratio = _to_float_or_int_like(
            _pick_metric(
                em,
                [
                    "top_primary_exec_bottleneck_ratio_exec_active",
                    "top_primary_exec_bottleneck_ratio",
                ],
            )
        )
        dispatch_gap_ratio = _to_float_or_int_like(
            _pick_metric(em, "top_dispatch_bottleneck_gap_ratio_dispatch_request")
        )
        exec_gap_ratio = _to_float_or_int_like(
            _pick_metric(
                em,
                [
                    "top_exec_bottleneck_gap_ratio_exec_active",
                    "top_exec_bottleneck_gap_ratio",
                ],
            )
        )
        dispatch_dominance = _to_float_zero(em.get("top_dispatch_bottleneck_dominance_ratio"))
        exec_dominance = _to_float_zero(em.get("top_exec_bottleneck_dominance_ratio"))
        dispatch_gap_cycles = _to_int(em.get("top_dispatch_bottleneck_reason_gap")) or 0
        exec_gap_cycles = _to_int(em.get("top_exec_bottleneck_reason_gap")) or 0

        if (
            dispatch_ratio == 0.0
            and exec_ratio == 0.0
            and dispatch_dominance == 0.0
            and exec_dominance == 0.0
        ):
            continue

        dispatch_score = (
            _clamp01(dispatch_ratio) * 45.0
            + _clamp01(dispatch_dominance) * 25.0
            + _clamp01(dispatch_gap_ratio) * 15.0
            + (0.5 if dispatch_ratio > 0.0 else 0.0)
        )
        exec_score = (
            _clamp01(exec_ratio) * 45.0
            + _clamp01(exec_dominance) * 25.0
            + _clamp01(exec_gap_ratio) * 15.0
            + (0.5 if exec_ratio > 0.0 else 0.0)
        )

        if dispatch_score >= exec_score:
            stage = "dispatch"
            reason = _safe_metric(em, "top_primary_dispatch_bottleneck_reason")
            secondary = _safe_metric(em, "top_secondary_dispatch_bottleneck_reason")
            secondary_ratio = dispatch_gap_ratio
            dominant = dispatch_dominance
            secondary_dominance = _to_float_zero(em.get("top_secondary_dispatch_bottleneck_dominance_ratio"))
        else:
            stage = "execution"
            reason = _safe_metric(em, "top_primary_exec_bottleneck_reason")
            secondary = _safe_metric(em, "top_secondary_exec_bottleneck_reason")
            secondary_ratio = exec_gap_ratio
            dominant = exec_dominance
            secondary_dominance = _to_float_zero(em.get("top_secondary_exec_bottleneck_dominance_ratio"))

        entries.append(
            {
                "scope": scope,
                "name": name,
                "stage": stage,
                "reason": reason,
                "secondary": secondary,
                "score": round(float(max(dispatch_score, exec_score)), 6),
                "dispatch_ratio": dispatch_ratio,
                "exec_ratio": exec_ratio,
                "dispatch_dominance": dispatch_dominance,
                "exec_dominance": exec_dominance,
                "dominant": dominant,
                "dispatch_gap_ratio": dispatch_gap_ratio,
                "exec_gap_ratio": exec_gap_ratio,
                "secondary_ratio": secondary_ratio,
                "dispatch_gap_cycles": dispatch_gap_cycles,
                "exec_gap_cycles": exec_gap_cycles,
                "secondary_dominance": secondary_dominance,
                "advice": _safe_metric(em, f"{'top_primary_dispatch_bottleneck_advice' if stage == 'dispatch' else 'top_primary_exec_bottleneck_advice'}"),
            }
        )

    entries.sort(key=lambda item: item["score"], reverse=True)
    return entries[: max(top_n, 0)]


def _build_memory_attribution(metrics: dict[str, str]) -> list[dict[str, object]]:
    """Rank VLSU-local causes separately from the generic execution buckets.

    Load/store activity is intentionally labelled ``special_path`` by the
    common backend partition.  That label is useful for partition closure but
    is not an optimization diagnosis.  This view drills into the address
    generator, translation, AXI and result interfaces and keeps state
    residency visible when no handshake-level cause fully explains a stall.
    """
    state_names = {
        0: "idle",
        1: "address_generation",
        2: "indexed_offset_generation",
        3: "indexed_offset_drain",
        4: "last_translation_wait",
    }
    axi_state_names = {
        0: "idle",
        1: "misaligned_store_split",
        2: "core_store_pending_wait",
        3: "axi_request_generation",
    }
    reason_fields = {
        "addrgen_operand_wait": "addrgen_operand_wait_cycles",
        "indexed_spill_wait": "indexed_spill_wait_cycles",
        "last_translation_wait": "last_translation_wait_cycles",
        "addrgen_queue_consumer_wait": "addrgen_queue_consumer_wait_cycles",
        "addrgen_queue_full": "addrgen_queue_full_cycles",
        "core_store_pending_wait": "core_store_pending_wait_cycles",
        "mmu_translation_wait": "mmu_wait_cycles",
        "axi_address_backpressure": "axi_address_backpressure_cycles",
        "axi_read_data_wait": "axi_data_wait_cycles",
        "axi_data_backpressure": "axi_data_backpressure_cycles",
        "axi_response_wait": "axi_response_wait_cycles",
        "mask_wait": "mask_wait_cycles",
        "vlsu_result_queue_full": "vlsu_result_queue_full_cycles",
        "vlsu_result_backpressure": "vlsu_result_backpressure_cycles",
    }
    advice = {
        "addrgen_operand_wait": "inspect indexed-address operand production, VRF read grants and lane synchronization",
        "indexed_spill_wait": "inspect indexed-address spill-register consumer readiness and AXI request generation",
        "last_translation_wait": "inspect final MMU translation response/exception handshake",
        "addrgen_queue_consumer_wait": "inspect LDU/STU acceptance of address-generator queue entries",
        "addrgen_queue_full": "increase or drain the address request queue; inspect downstream LDU/STU service rate",
        "core_store_pending_wait": "inspect scalar/core pending-store serialization",
        "mmu_translation_wait": "inspect DTLB/PTW latency and translation concurrency",
        "axi_address_backpressure": "inspect AXI AR/AW ready and interconnect arbitration",
        "axi_read_data_wait": "inspect memory response latency and outstanding-request concurrency",
        "axi_data_backpressure": "inspect AXI R/W data consumer readiness",
        "axi_response_wait": "inspect AXI B/R response completion and ID tracking",
        "mask_wait": "inspect mask delivery to VLSU",
        "vlsu_result_queue_full": "inspect VLSU result queue depth and lane writeback service",
        "vlsu_result_backpressure": "inspect lane result grants and VRF writeback contention",
        "addrgen_unexplained_no_progress": "inspect the dominant addrgen/AXI state and add a handshake counter at that state's exit condition",
    }
    result: list[dict[str, object]] = []
    for cls in ("load", "store"):
        active = _to_int(metrics.get(f"{cls}_addrgen_active_cycles")) or 0
        arch = _to_int(metrics.get(f"{cls}_arch_memory_insns")) or 0
        if active == 0 and arch == 0:
            continue
        causes = [(name, _to_int(metrics.get(f"{cls}_{field}")) or 0)
                  for name, field in reason_fields.items()]
        no_progress = _to_int(metrics.get(f"{cls}_addrgen_no_progress_cycles")) or 0
        explained = max((cycles for _, cycles in causes), default=0)
        if no_progress > explained:
            causes.append(("addrgen_unexplained_no_progress", no_progress - explained))
        causes.sort(key=lambda item: item[1], reverse=True)
        states = sorted(
            ((state_names[s], _to_int(metrics.get(f"{cls}_addrgen_state_{s}_cycles")) or 0)
             for s in state_names), key=lambda item: item[1], reverse=True)
        axi_states = sorted(
            ((axi_state_names[s], _to_int(metrics.get(f"{cls}_axi_addrgen_state_{s}_cycles")) or 0)
             for s in axi_state_names), key=lambda item: item[1], reverse=True)
        primary, primary_cycles = causes[0] if causes else ("none", 0)
        result.append({
            "class": cls,
            "active_cycles": active,
            "no_progress_cycles": no_progress,
            "no_progress_ratio": (no_progress / active) if active else 0.0,
            "primary_reason": primary,
            "primary_cycles": primary_cycles,
            "primary_ratio_active": (primary_cycles / active) if active else 0.0,
            "advice": advice.get(primary, "inspect VLSU pipeline signals"),
            "top_causes": [{"reason": n, "cycles": c, "ratio_active": (c / active) if active else 0.0}
                           for n, c in causes[:5] if c],
            "dominant_addrgen_state": states[0][0] if states and states[0][1] else "unavailable",
            "dominant_addrgen_state_cycles": states[0][1] if states else 0,
            "dominant_axi_addrgen_state": axi_states[0][0] if axi_states and axi_states[0][1] else "unavailable",
            "dominant_axi_addrgen_state_cycles": axi_states[0][1] if axi_states else 0,
        })
    return result


def _build_mask_attribution(metrics: dict[str, str]) -> dict[str, object] | None:
    active = _to_int(metrics.get("mask_active_cycles")) or 0
    if active == 0:
        return None
    fields = {
        "operand_incomplete": "mask_operand_incomplete_cycles",
        "vcompress_issue_end_residency": "mask_issue_end_cycles",
        "commit_pending": "mask_commit_pending_cycles",
        "result_queue_nonempty": "mask_result_queue_nonempty_cycles",
        "final_grant_wait": "mask_final_grant_wait_cycles",
        "index_fifo_nonempty": "mask_index_fifo_nonempty_cycles",
        "request_fifo_nonempty": "mask_request_fifo_nonempty_cycles",
    }
    advice = {
        "operand_incomplete": "inspect masku operand requester validity per lane and source-register hazards",
        "vcompress_issue_end_residency": "element scan ended; inspect result construction, commit_cnt and completion clearing",
        "commit_pending": "inspect masku commit counter, result queue drain and vinsn_done generation",
        "result_queue_nonempty": "inspect lane writeback grants and mask result queue drain",
        "final_grant_wait": "inspect result_final_gnt and VRF writeback acknowledgement",
        "index_fifo_nonempty": "inspect vrgather/compress index FIFO consumer progress",
        "request_fifo_nonempty": "inspect gather broadcast grants and request FIFO pop conditions",
    }
    ranked = sorted(((name, _to_int(metrics.get(key)) or 0) for name, key in fields.items()),
                    key=lambda item: item[1], reverse=True)
    reason, cycles = ranked[0]
    return {
        "active_cycles": active,
        "primary_reason": reason,
        "primary_cycles": cycles,
        "primary_ratio_active": cycles / active if active else 0.0,
        "advice": advice[reason],
        "top_causes": [{"reason": n, "cycles": c, "ratio_active": c / active}
                       for n, c in ranked if c][:5],
        "compress_examined_elements": _to_int(metrics.get("mask_compress_examined_elements")) or 0,
        "compress_selected_elements": _to_int(metrics.get("mask_compress_selected_elements")) or 0,
        "gather_grant_ratio": _to_float_or_int_like(metrics.get("mask_gather_broadcast_grant_ratio")),
    }


def build_diagnosis(metrics: dict[str, str], top_n: int = 8) -> dict[str, object]:
    missing = _missing_metrics(metrics, GLOBAL_REQUIRED_FIELDS)
    op_audit = _check_entity_top_completeness(metrics, "op")
    class_audit = _check_entity_top_completeness(metrics, "class")
    global_coverage = 100.0 * (len(GLOBAL_REQUIRED_FIELDS) - len(missing)) / len(GLOBAL_REQUIRED_FIELDS)


    dispatch_blocked_ratio = _ratio(metrics, "global_dispatch_blocked_ratio") or 0.0
    no_issue_progress_ratio = _ratio(metrics, "global_no_issue_progress_ratio") or 0.0
    issue_progress_ratio = _ratio(metrics, "global_issue_progress_ratio") or 0.0
    top2_dispatch_bottleneck = _ratio(metrics, "global_top2_dispatch_bottleneck_share") or 0.0
    top2_exec_bottleneck = _ratio(metrics, "global_top2_exec_bottleneck_share") or 0.0
    top_dispatch_dominance = _ratio(metrics, "global_top_dispatch_bottleneck_dominance_ratio") or 0.0
    top_exec_dominance = _ratio(metrics, "global_top_exec_bottleneck_dominance_ratio") or 0.0
    top_class_share_skew = _ratio(metrics, "global_top_class_share_skew") or 0.0
    top_opcode_share_skew = _ratio(metrics, "global_top_opcode_share_skew") or 0.0
    dispatch_exec_class_overlap = _ratio(metrics, "global_dispatch_exec_class_overlap") or 0.0
    dispatch_exec_opcode_overlap = _ratio(metrics, "global_dispatch_exec_opcode_overlap") or 0.0
    pressure_alignment = metrics.get("global_bottleneck_pressure_alignment", "unknown")
    opcode_alignment = metrics.get("global_bottleneck_opcode_alignment", "unknown")

    dispatch_partition_ok = _to_int(metrics.get("global_primary_dispatch_partition_consistent", "0")) == 1
    exec_partition_ok = _to_int(metrics.get("global_primary_exec_partition_consistent", "0")) == 1
    progress_partition_ok = _to_int(metrics.get("global_exec_progress_partition_consistent", "0")) == 1
    partition_ok = dispatch_partition_ok and exec_partition_ok and progress_partition_ok

    total_dispatch_request = _to_int(metrics.get("global_total_dispatch_request_cycles")) or 0
    total_exec_active = _to_int(metrics.get("global_total_exec_active_cycles")) or 0
    workload_sample_present = total_dispatch_request > 0 or total_exec_active > 0
    timeout_snapshot = _to_int(metrics.get("watchdog_timeout")) == 1

    stage_mode = metrics.get("global_stage_mode", "unknown")
    focus = metrics.get("global_bottleneck_focus", "unknown")

    dispatch_score = (
        _clamp01(dispatch_blocked_ratio) * 40.0
        + _clamp01(top_dispatch_dominance) * 25.0
        + _clamp01(top2_dispatch_bottleneck) * 20.0
        + (0.0 if pressure_alignment == "aligned" else 2.0)
        + (_clamp01(top_class_share_skew) * 10.0)
        + (_clamp01(top_opcode_share_skew) * 5.0)
    ) * 100.0 / 100.0

    exec_score = (
        _clamp01(no_issue_progress_ratio) * 40.0
        + _clamp01(top_exec_dominance) * 25.0
        + _clamp01(top2_exec_bottleneck) * 20.0
        + (0.0 if dispatch_exec_class_overlap >= 0.35 else 2.0)
        + _clamp01((1.0 - issue_progress_ratio) * 5.0)
    ) * 100.0 / 100.0

    candidates: list[dict[str, object]] = []
    if dispatch_blocked_ratio > 0:
        candidates.append(
            {
                "stage": "dispatch",
                "reason": metrics.get("global_top_primary_dispatch_bottleneck_reason", "none"),
                "advice": metrics.get("global_top_primary_dispatch_bottleneck_advice", "no advice"),
                "score": dispatch_score,
                "dominance": top_dispatch_dominance,
                "secondary": metrics.get("global_top_secondary_dispatch_bottleneck_reason", "none"),
                "top_class": metrics.get("global_top_dispatch_blocked_class", "none"),
                "top_opcode": metrics.get("global_top_dispatch_blocked_opcode", "none"),
                "top2_share": top2_dispatch_bottleneck,
            }
        )
    if top_exec_dominance > 0 or no_issue_progress_ratio > 0:
        candidates.append(
            {
                "stage": "execution",
                "reason": metrics.get("global_top_primary_exec_bottleneck_reason", "none"),
                "advice": metrics.get("global_top_primary_exec_bottleneck_advice", "no advice"),
                "score": exec_score,
                "dominance": top_exec_dominance,
                "secondary": metrics.get("global_top_secondary_exec_bottleneck_reason", "none"),
                "top_class": metrics.get("global_top_exec_wait_class", "none"),
                "top_opcode": metrics.get("global_top_exec_wait_opcode", "none"),
                "top2_share": top2_exec_bottleneck,
            }
        )

    candidates.sort(key=lambda x: x["score"], reverse=True)

    health = "good"
    risks = []
    if not partition_ok:
        health = "warning"
        risks.append("Primary-raw partition inconsistent; verify counter base for dispatch/exec attribution.")
    if no_issue_progress_ratio > 0.5 and issue_progress_ratio > 0.5:
        risks.append("dispatch is healthy but execution progress is low while no_issue is not high; inspect memory/AXI or result consumer side.")
    if "global_dispatch_exec_class_overlap" in metrics and dispatch_exec_class_overlap < 0.25:
        risks.append("Dispatch bottleneck class/op overlap is weak; pressure may not turn into real exec progress.")
    if "global_dispatch_exec_opcode_overlap" in metrics and dispatch_exec_opcode_overlap < 0.20:
        risks.append("Top dispatch-blocked opcode differs from top exec-wait opcode; investigate scheduling-front skew.")
    if "global_top_class_share_skew" in metrics and top_class_share_skew > 0.30:
        risks.append("Top class share skew is high between request and active; verify waveform-level shape/issue mix.")
    if "global_top_opcode_share_skew" in metrics and top_opcode_share_skew > 0.35:
        risks.append("Top opcode share skew is high between request and active; decode/front-end path may be masking hotspots.")

    readiness_blockers: list[str] = []
    if timeout_snapshot:
        readiness_blockers.append("watchdog_timeout")
    if missing:
        readiness_blockers.append(f"missing_global_fields:{len(missing)}")
    if not workload_sample_present:
        readiness_blockers.append("no_global_workload_sample")
    if not op_audit["sample_present"]:
        readiness_blockers.append("no_active_opcode_sample")
    elif op_audit["incomplete_count"]:
        readiness_blockers.append(f"incomplete_opcode_entities:{op_audit['incomplete_count']}")
    if op_audit["consistency_failure_count"]:
        readiness_blockers.append(
            f"opcode_consistency_failures:{op_audit['consistency_failure_count']}"
        )
    if not class_audit["sample_present"]:
        readiness_blockers.append("no_active_class_sample")
    elif class_audit["incomplete_count"]:
        readiness_blockers.append(f"incomplete_class_entities:{class_audit['incomplete_count']}")
    if class_audit["consistency_failure_count"]:
        readiness_blockers.append(
            f"class_consistency_failures:{class_audit['consistency_failure_count']}"
        )
    if op_audit["consistency_failure_count"]:
        risks.append(
            "Opcode-level counter consistency failed; do not use opcode ranking for RTL decisions until the listed checks pass."
        )
    if class_audit["consistency_failure_count"]:
        risks.append(
            "Class-level counter consistency failed; class ranking is exploratory only."
        )
    if not partition_ok:
        readiness_blockers.append("counter_partition_inconsistent")

    # A complete report can still be ambiguous: when the leading cause barely
    # separates from the runner-up, use it for exploration, not an RTL decision.
    attribution_ambiguous = False
    if candidates:
        lead = candidates[0]
        attribution_ambiguous = float(lead["dominance"]) < 0.50
        if attribution_ambiguous:
            readiness_blockers.append("primary_cause_not_dominant")
    else:
        readiness_blockers.append("no_ranked_bottleneck_candidate")

    close_loop_ready = not readiness_blockers
    if close_loop_ready:
        confidence = "high"
    elif missing or not workload_sample_present or not partition_ok:
        confidence = "insufficient"
    else:
        confidence = "exploratory"

    actionable = []
    if candidates:
        action_primary = candidates[0]
        actionable.append(
            {
                "priority": 1,
                "stage": action_primary["stage"],
                "reason": action_primary["reason"],
                "score": round(float(action_primary["score"]), 6),
                "advice": action_primary["advice"],
            }
        )
    if candidates and len(candidates) > 1:
        action_secondary = candidates[1]
        actionable.append(
            {
                "priority": 2,
                "stage": action_secondary["stage"],
                "reason": action_secondary["reason"],
                "score": round(float(action_secondary["score"]), 6),
                "advice": action_secondary["advice"],
            }
        )

    summary = {
        "stage_mode": stage_mode,
        "focus": focus,
        "pressure_alignment": pressure_alignment,
        "opcode_alignment": opcode_alignment,
        "global_coverage": round(global_coverage, 2),
        "coverage_audit": {
            "global": {
                "required": len(GLOBAL_REQUIRED_FIELDS),
                "present": len(GLOBAL_REQUIRED_FIELDS) - len(missing),
                "coverage": round(global_coverage, 2),
                "missing_fields": missing,
            },
            "op": op_audit,
            "class": class_audit,
            "workload_sample_present": workload_sample_present,
            "attribution_ambiguous": attribution_ambiguous,
            "confidence": confidence,
            "readiness_blockers": readiness_blockers,
            "close_loop_ready": close_loop_ready,
        },
        "timeout_snapshot": {
            "triggered": timeout_snapshot,
            "limit_cycles": _to_int(metrics.get("watchdog_limit_cycles")),
            "observed_cycles": _to_int(metrics.get("watchdog_observed_cycles")),
            "dispatcher_state": metrics.get("watchdog_dispatcher_state"),
            "inflight_count": _to_int(metrics.get("watchdog_inflight_count")),
            "inflight_opcodes": sorted(
                value for key, value in metrics.items()
                if key.startswith("watchdog_inflight_id_") and key.endswith("_opcode")
            ),
        },
        "health": health,
        "ratio_summary": {
            "dispatch_blocked_ratio": dispatch_blocked_ratio,
            "no_issue_progress_ratio": no_issue_progress_ratio,
            "issue_progress_ratio": issue_progress_ratio,
            "top2_dispatch_bottleneck_share": top2_dispatch_bottleneck,
            "top2_exec_bottleneck_share": top2_exec_bottleneck,
        },
        "top_metrics": {
            "top_dispatch_reason": metrics.get("global_top_primary_dispatch_bottleneck_reason"),
            "top_exec_reason": metrics.get("global_top_primary_exec_bottleneck_reason"),
            "top_class_request": metrics.get("global_top_dispatch_request_class"),
            "top_class_active": metrics.get("global_top_active_class"),
            "top_opcode_request": metrics.get("global_top_dispatch_request_opcode"),
            "top_opcode_active": metrics.get("global_top_active_opcode"),
            "dispatch_exec_class_overlap": dispatch_exec_class_overlap,
            "dispatch_exec_opcode_overlap": dispatch_exec_opcode_overlap,
        },
        "partition_checks": {
            "dispatch_partition_ok": dispatch_partition_ok,
            "exec_partition_ok": exec_partition_ok,
            "progress_partition_ok": progress_partition_ok,
        },
        "candidate_rankings": candidates,
        "opcode_level_candidates": _build_entity_candidates(metrics, "op", top_n),
        "class_level_candidates": _build_entity_candidates(metrics, "class", top_n),
        "memory_attribution": _build_memory_attribution(metrics),
        "mask_attribution": _build_mask_attribution(metrics),
        "actionable": actionable,
        "risks": risks,
        "missing_metrics": missing,
    }
    return summary


def print_text(path: str, metrics: dict[str, str], summary: dict[str, object], md: bool = False) -> None:
    if md:
        print(f"## Ara PERF 瓶颈归因报告")
        print(f"- 日志: `{path}`")
        print(f"- 阶段模式: `{summary['stage_mode']}`")
        print(f"- 关注方向: `{summary['focus']}`")
        print(f"- 分区一致性: dispatch={summary['partition_checks']['dispatch_partition_ok']} / exec={summary['partition_checks']['exec_partition_ok']} / progress={summary['partition_checks']['progress_partition_ok']}")
        print(f"- 全局指标齐套: {summary['coverage_audit']['global']['coverage']:.2f}% ({summary['coverage_audit']['global']['present']}/{summary['coverage_audit']['global']['required']})")
        print(f"- close-loop 可归因能力: {'可直接归因' if summary['coverage_audit']['close_loop_ready'] else '需补齐指标'}")
        print(f"- 归因置信度: `{summary['coverage_audit']['confidence']}`")
        if summary["timeout_snapshot"]["triggered"]:
            timeout = summary["timeout_snapshot"]
            print(
                f"- Watchdog 超时快照: observed={timeout['observed_cycles']} / "
                f"limit={timeout['limit_cycles']} cycles，inflight={timeout['inflight_count']} "
                f"opcodes={','.join(timeout['inflight_opcodes']) or 'none'}"
            )
        if summary["coverage_audit"]["readiness_blockers"]:
            print(f"- 阻断项: {', '.join(summary['coverage_audit']['readiness_blockers'])}")
        print()
        if summary["missing_metrics"]:
            print(f"> ⚠️ 全局缺失 {len(summary['missing_metrics'])} 个关键字段：{', '.join(summary['missing_metrics'])}")
            print()
        for scope in ("op", "class"):
            audit = summary["coverage_audit"][scope]
            print(f"### {scope.upper()} 级指标齐套性")
            if audit["entity_count"] == 0:
                print("- 无活跃实体")
                continue
            print(f"- 已出现实体: {audit['entity_count']}，完全齐套: {audit['covered_count']}")
            print(f"- 平均齐套率: {audit['avg_coverage']}%；未齐套实体: {audit['incomplete_count']}")
            print(f"- 一致性失败实体: {audit['consistency_failure_count']}")
            if audit["top_incomplete"]:
                print(f"- 缺失最多的实体（前 {len(audit['top_incomplete'])}）:")
                for item in audit["top_incomplete"]:
                    print(
                        f"  - {item['name']}: coverage={item['coverage']}% "
                        f"missing={len(item['missing_fields'])}/{item['required_fields']} "
                        f"({', '.join(item['missing_fields'])})"
                    )
            for item in audit["consistency_failures"]:
                details = []
                if item["failed_checks"]:
                    details.append("failed=" + ",".join(item["failed_checks"]))
                if item["missing_checks"]:
                    details.append("missing=" + ",".join(item["missing_checks"]))
                print(f"  - {item['name']} consistency: {'; '.join(details)}")

        print("### 一阶归因")
        if summary["actionable"]:
            for item in summary["actionable"]:
                print(
                    f"- P{item['priority']}: {item['stage']} | reason=`{item['reason']}` | score={item['score']} | advice={item['advice']}"
                )
        if summary["opcode_level_candidates"]:
            print("### Opcode 级候选 Top")
            for c in summary["opcode_level_candidates"]:
                print(
                    f"- {c['name']}: {c['stage']} -> `{c['reason']}` "
                    f"| score={c['score']} | d_ratio={c['dispatch_ratio']:.6f} | e_ratio={c['exec_ratio']:.6f} | advice={c['advice']}"
                )
        if summary["class_level_candidates"]:
            print("### Class 级候选 Top")
            for c in summary["class_level_candidates"]:
                print(
                    f"- {c['name']}: {c['stage']} -> `{c['reason']}` "
                    f"| score={c['score']} | d_ratio={c['dispatch_ratio']:.6f} | e_ratio={c['exec_ratio']:.6f} | advice={c['advice']}"
                )
        if summary["memory_attribution"]:
            print("### VLSU 专属归因")
            for m in summary["memory_attribution"]:
                print(
                    f"- {m['class']}: `{m['primary_reason']}` {m['primary_cycles']} cycles "
                    f"({m['primary_ratio_active']:.2%} of addrgen active)，"
                    f"no-progress={m['no_progress_ratio']:.2%}；"
                    f"addrgen-state=`{m['dominant_addrgen_state']}` "
                    f"({m['dominant_addrgen_state_cycles']})，"
                    f"axi-state=`{m['dominant_axi_addrgen_state']}` "
                    f"({m['dominant_axi_addrgen_state_cycles']})"
                )
                print(f"  - 建议: {m['advice']}")
                if m["top_causes"]:
                    print("  - 候选: " + ", ".join(
                        f"{c['reason']}={c['cycles']}({c['ratio_active']:.2%})"
                        for c in m["top_causes"]
                    ))
        if summary["mask_attribution"]:
            m = summary["mask_attribution"]
            print("### MASKU 专属归因")
            print(
                f"- `{m['primary_reason']}` {m['primary_cycles']} cycles "
                f"({m['primary_ratio_active']:.2%} of mask active)；"
                f"compress examined/selected={m['compress_examined_elements']}/"
                f"{m['compress_selected_elements']}，gather-grant={m['gather_grant_ratio']:.2%}"
            )
            print(f"  - 建议: {m['advice']}")
            print("  - 候选: " + ", ".join(
                f"{c['reason']}={c['cycles']}({c['ratio_active']:.2%})"
                for c in m["top_causes"]
            ))
        print()
        print("### 风险与校验")
        if summary["risks"]:
            for r in summary["risks"]:
                print(f"- {r}")
        else:
            print("- 风险可控，当前指标无明显断点")
        return

    print("=" * 78)
    print("Ara PERF Bottleneck Diagnosis")
    print(f"log: {path}")
    if summary["missing_metrics"]:
        print(f"WARN: missing {len(summary['missing_metrics'])} key fields")
        for k in summary["missing_metrics"]:
            print(f"  - {k}")
    cov = summary["coverage_audit"]
    print("=" * 78)
    print(f"Global metric coverage: {cov['global']['coverage']:.2f}% ({cov['global']['present']}/{cov['global']['required']})")
    print(f"Close-loop ready: {'YES' if cov['close_loop_ready'] else 'NO'}")
    print(f"Attribution confidence: {cov['confidence']}")
    if summary["timeout_snapshot"]["triggered"]:
        timeout = summary["timeout_snapshot"]
        print(
            f"Watchdog snapshot: observed={timeout['observed_cycles']} limit={timeout['limit_cycles']} "
            f"inflight={timeout['inflight_count']} opcodes={','.join(timeout['inflight_opcodes']) or 'none'}"
        )
    if cov["readiness_blockers"]:
        print(f"Readiness blockers: {', '.join(cov['readiness_blockers'])}")
    print("=" * 78)
    print(f"Stage mode: {summary['stage_mode']}")
    print(f"Focus: {summary['focus']}")
    print(f"Health: {summary['health']}")
    print(f"Pressure alignment: {summary['pressure_alignment']}, opcode alignment: {summary['opcode_alignment']}")
    print("Ratio summary:")
    rs = summary["ratio_summary"]
    print(f"  dispatch_blocked_ratio     = {rs['dispatch_blocked_ratio']:.6f}")
    print(f"  no_issue_progress_ratio    = {rs['no_issue_progress_ratio']:.6f}")
    print(f"  issue_progress_ratio      = {rs['issue_progress_ratio']:.6f}")
    print(f"  top2_dispatch_bottleneck  = {rs['top2_dispatch_bottleneck_share']:.6f}")
    print(f"  top2_exec_bottleneck      = {rs['top2_exec_bottleneck_share']:.6f}")
    print("Top metrics:")
    tm = summary["top_metrics"]
    print(f"  dispatch reason : {tm['top_dispatch_reason']}")
    print(f"  exec reason    : {tm['top_exec_reason']}")
    print(f"  top request cls: {tm['top_class_request']}")
    print(f"  top active cls : {tm['top_class_active']}")
    print(f"  top request op : {tm['top_opcode_request']}")
    print(f"  top active  op : {tm['top_opcode_active']}")
    print(f"  dispatch-exec overlap class : {tm['dispatch_exec_class_overlap']:.6f}")
    print(f"  dispatch-exec overlap opcode: {tm['dispatch_exec_opcode_overlap']:.6f}")
    print("Partition checks:")
    pc = summary["partition_checks"]
    print(f"  dispatch={pc['dispatch_partition_ok']} exec={pc['exec_partition_ok']} progress={pc['progress_partition_ok']}")

    print("Actionable priorities:")
    for item in summary["actionable"]:
        print(f"  P{item['priority']}: {item['stage']} -> {item['reason']} (score={item['score']})")
        print(f"    advice: {item['advice']}")
    print("Risks:")
    if summary["risks"]:
        for r in summary["risks"]:
            print(f"  - {r}")
    else:
        print("  - none")

    if summary["opcode_level_candidates"]:
        print("Opcode 级 Top candidates:")
        for c in summary["opcode_level_candidates"]:
            print(
                f"  {c['name']:<20}: stage={c['stage']:<9} reason={c['reason']:<28} "
                f"score={c['score']:.6f} d_ratio={c['dispatch_ratio']:.6f} e_ratio={c['exec_ratio']:.6f}"
            )
            print(
                f"    secondary={c['secondary']} secondary_ratio={c['secondary_ratio']:.6f} "
                f"advice={c['advice']}"
            )
    if summary["class_level_candidates"]:
        print("Class 级 Top candidates:")
        for c in summary["class_level_candidates"]:
            print(
                f"  {c['name']:<20}: stage={c['stage']:<9} reason={c['reason']:<28} "
                f"score={c['score']:.6f} d_ratio={c['dispatch_ratio']:.6f} e_ratio={c['exec_ratio']:.6f}"
            )
            print(
                f"    secondary={c['secondary']} secondary_ratio={c['secondary_ratio']:.6f} "
                f"advice={c['advice']}"
            )
    if summary["memory_attribution"]:
        print("VLSU-specific attribution:")
        for m in summary["memory_attribution"]:
            print(
                f"  {m['class']}: reason={m['primary_reason']} cycles={m['primary_cycles']} "
                f"ratio_active={m['primary_ratio_active']:.6f} no_progress={m['no_progress_ratio']:.6f} "
                f"addrgen_state={m['dominant_addrgen_state']} "
                f"axi_state={m['dominant_axi_addrgen_state']}"
            )
            print(f"    advice: {m['advice']}")
    if summary["mask_attribution"]:
        m = summary["mask_attribution"]
        print("MASKU-specific attribution:")
        print(
            f"  reason={m['primary_reason']} cycles={m['primary_cycles']} "
            f"ratio_active={m['primary_ratio_active']:.6f} "
            f"examined={m['compress_examined_elements']} selected={m['compress_selected_elements']} "
            f"gather_grant_ratio={m['gather_grant_ratio']:.6f}"
        )
        print(f"    advice: {m['advice']}")

    # 贴近“教学”场景：给出关键原始字段索引，便于回到源码或日志核对
    print("Key raw field preview:")
    preview_fields = [
        "global_top2_dispatch_bottleneck_share",
        "global_top2_exec_bottleneck_share",
        "global_dispatch_exec_class_overlap",
        "global_dispatch_exec_opcode_overlap",
        "global_bottleneck_pressure_alignment",
        "global_bottleneck_opcode_alignment",
        "global_top_primary_dispatch_bottleneck_reason",
        "global_top_primary_exec_bottleneck_reason",
        "global_top_primary_dispatch_bottleneck_advice",
        "global_top_primary_exec_bottleneck_advice",
    ]
    for fld in preview_fields:
        print(f"  {fld}: {metrics.get(fld, 'missing')}")


def main() -> int:
    args = parse_args()
    log_path = args.log
    if not os.path.exists(log_path):
        print(f"ERROR: cannot open log file {log_path}", file=sys.stderr)
        return 1
    metrics = parse_perf_log(log_path)
    if not metrics:
        print(f"ERROR: no [PERF] entries found in {log_path}", file=sys.stderr)
        return 1

    summary = build_diagnosis(metrics, top_n=args.top_n)
    if args.json:
        output = {"log": str(Path(log_path).resolve()), "metrics": metrics, "diagnosis": summary}
        text = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
        if args.json_out:
            with open(args.json_out, "w", encoding="utf-8") as f:
                f.write(text + "\n")
        else:
            print(text)
        return 2 if args.require_ready and not summary["coverage_audit"]["close_loop_ready"] else 0

    print_text(log_path, metrics, summary, md=args.md)
    if args.json_out:
        output = {"log": str(Path(log_path).resolve()), "metrics": metrics, "diagnosis": summary}
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    return 2 if args.require_ready and not summary["coverage_audit"]["close_loop_ready"] else 0


if __name__ == "__main__":
    sys.exit(main())
