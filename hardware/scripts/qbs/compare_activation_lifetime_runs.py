#!/usr/bin/env python3
"""Validate paired baseline/cross-operator QBS activation-lifetime runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Mapping, Sequence

try:
    from . import summarize_activation_lifetime as lifetime
except ImportError:
    import summarize_activation_lifetime as lifetime


COMMAND_WORK_FIELDS = (
    "seq",
    "graph_epoch",
    "weight_type",
    "weight_profile",
    "activation_profile",
    "m",
    "n",
    "k_blocks",
    "segmented",
    "emulated",
)


def compare_data(
    baseline_summary: Mapping[str, object],
    optimized_summary: Mapping[str, object],
    baseline_commands: Sequence[Mapping[str, object]],
    optimized_commands: Sequence[Mapping[str, object]],
    optimized_cross: Mapping[str, object],
    baseline_trace: Mapping[str, object],
    optimized_trace: Mapping[str, object],
) -> Dict[str, object]:
    if len(baseline_commands) != len(optimized_commands):
        raise ValueError("paired runs have different QBS command counts")
    for index, (baseline, optimized) in enumerate(zip(baseline_commands, optimized_commands)):
        differing = [field for field in COMMAND_WORK_FIELDS if baseline[field] != optimized[field]]
        if differing:
            raise ValueError(
                f"paired command index {index} changes semantic work fields: {', '.join(differing)}"
            )

    baseline_quantizations = int(baseline_summary["quantizations"])
    optimized_quantizations = int(optimized_summary["quantizations"])
    eliminated_quantizations = baseline_quantizations - optimized_quantizations
    baseline_bytes = int(baseline_summary["quantized_bytes"])
    optimized_bytes = int(optimized_summary["quantized_bytes"])
    eliminated_bytes = baseline_bytes - optimized_bytes
    expected_quantizations = int(baseline_summary["removable_quantizations"])
    expected_bytes = int(baseline_summary["removable_quantized_bytes"])
    expected_chains = int(baseline_summary["eligible_groups"])

    if eliminated_quantizations <= 0 or eliminated_quantizations != expected_quantizations:
        raise ValueError("quantization reduction does not match baseline reuse opportunities")
    if eliminated_bytes <= 0 or eliminated_bytes != expected_bytes:
        raise ValueError("activation-byte reduction does not match baseline reuse opportunities")
    if int(optimized_cross["quantization_skips"]) != eliminated_quantizations:
        raise ValueError("cross-operator skip count does not match eliminated quantizations")
    if int(optimized_cross["activation_bytes_saved"]) != eliminated_bytes:
        raise ValueError("cross-operator byte count does not match eliminated activation bytes")
    if not (
        int(optimized_cross["chains"])
        == int(optimized_cross["fills"])
        == int(optimized_cross["releases"])
        == expected_chains
    ):
        raise ValueError("cross-operator context chains are not balanced with baseline groups")
    if int(optimized_cross["reuses"]) != eliminated_quantizations:
        raise ValueError("cross-operator reuse count does not match eliminated quantizations")
    if int(baseline_summary["unlinked_commands"]) or int(optimized_summary["unlinked_commands"]):
        raise ValueError("paired run contains unlinked QBS commands")

    return {
        "semantic_command_stream_equal": True,
        "command_work_fields": list(COMMAND_WORK_FIELDS),
        "commands": len(baseline_commands),
        "baseline": {
            "quantizations": baseline_quantizations,
            "activation_bytes": baseline_bytes,
            "eligible_context_chains": expected_chains,
        },
        "cross_operator": {
            "quantizations": optimized_quantizations,
            "activation_bytes": optimized_bytes,
            "context_chains": int(optimized_cross["chains"]),
            "quantizations_eliminated": eliminated_quantizations,
            "activation_bytes_eliminated": eliminated_bytes,
        },
        "families": baseline_summary["families"],
        "qemu_timing_diagnostic": {
            "scope": "QEMU host timing; not an RTL cycle measurement or an acceptance invariant",
            "baseline_total_quantize_time_us": int(baseline_trace["quantize_time_us"]),
            "cross_operator_total_quantize_time_us": int(optimized_trace["quantize_time_us"]),
            "baseline_reusable_quantize_time_us": int(baseline_summary["removable_quantize_time_us"]),
        },
    }


def load_run(log: Path, label: str):
    lifetimes, commands, trace = lifetime.parse_log(log, label)
    cross_records = lifetime.parse_cross_ops(log, label)
    cross = lifetime.validate_cross_ops(lifetimes, commands, trace, cross_records)
    groups = lifetime.build_groups(lifetimes, commands)
    summary = lifetime.summarize(lifetimes, commands, groups)
    summary["cross_operator_context"] = cross
    return summary, commands, trace, cross


def compare_log(log: Path, baseline_label: str, optimized_label: str) -> Dict[str, object]:
    baseline_summary, baseline_commands, baseline_trace, baseline_cross = load_run(log, baseline_label)
    optimized_summary, optimized_commands, optimized_trace, optimized_cross = load_run(log, optimized_label)
    if any(int(value) for value in baseline_cross.values()):
        raise ValueError("baseline unexpectedly contains cross-operator context activity")
    return compare_data(
        baseline_summary,
        optimized_summary,
        baseline_commands,
        optimized_commands,
        optimized_cross,
        baseline_trace,
        optimized_trace,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--baseline-label", default="QBS_CONTEXT_BASELINE")
    parser.add_argument("--optimized-label", default="QBS_CROSS_OP")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compare_log(args.log, args.baseline_label, args.optimized_label)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
