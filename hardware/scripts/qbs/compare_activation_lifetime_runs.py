#!/usr/bin/env python3
"""Validate paired baseline/cross-operator QBS activation-lifetime runs."""

from __future__ import annotations

import argparse
import hashlib
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    return values


def eliminated_lifetimes(
    lifetimes: Sequence[Mapping[str, object]],
    groups: Sequence[Mapping[str, object]],
) -> list[Dict[str, object]]:
    """Return the exact baseline quantizations removed by eligible chains."""
    eliminated: list[Dict[str, object]] = []
    for group in groups:
        if not int(group["eligible_single_context"]):
            continue
        required_roles = lifetime.REUSE_FAMILIES[str(group["family"])]
        records = [
            record
            for record in lifetimes
            if int(record["graph_epoch"]) == int(group["graph_epoch"])
            and str(record["source_id"]) == str(group["source_id"])
            and int(record["activation_profile"]) == int(group["activation_profile"])
            and int(record["m"]) == int(group["m"])
            and int(record["k"]) == int(group["k"])
            and str(record["role"]) in required_roles
        ]
        selected = []
        for role in required_roles:
            matches = [record for record in records if record["role"] == role]
            if len(matches) != 1:
                raise ValueError(
                    f"eligible {group['family']} group has {len(matches)} records for {role}"
                )
            selected.append(matches[0])
        selected.sort(key=lambda record: int(record["seq"]))
        for record in selected[1:]:
            eliminated.append(
                {
                    "family": group["family"],
                    "graph_epoch": int(record["graph_epoch"]),
                    "op": record["op"],
                    "weight": record["weight"],
                    "weight_type": str(record["weight_type"]).upper(),
                    "activation_profile": int(record["activation_profile"]),
                    "m": int(record["m"]),
                    "n": int(record["n"]),
                    "k": int(record["k"]),
                    "quantized_bytes": int(record["bytes"]),
                    "input_elements": int(record["m"]) * int(record["k"]),
                    "input_bytes": 4 * int(record["m"]) * int(record["k"]),
                }
            )
    return eliminated


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
    return summary, commands, trace, cross, lifetimes, groups


def compare_log(log: Path, baseline_label: str, optimized_label: str) -> Dict[str, object]:
    (
        baseline_summary,
        baseline_commands,
        baseline_trace,
        baseline_cross,
        baseline_lifetimes,
        baseline_groups,
    ) = load_run(log, baseline_label)
    (
        optimized_summary,
        optimized_commands,
        optimized_trace,
        optimized_cross,
        optimized_lifetimes,
        _optimized_groups,
    ) = load_run(log, optimized_label)
    if any(int(value) for value in baseline_cross.values()):
        raise ValueError("baseline unexpectedly contains cross-operator context activity")
    result = compare_data(
        baseline_summary,
        optimized_summary,
        baseline_commands,
        optimized_commands,
        optimized_cross,
        baseline_trace,
        optimized_trace,
    )
    eliminated = eliminated_lifetimes(baseline_lifetimes, baseline_groups)
    baseline_input_elements = sum(
        int(record["m"]) * int(record["k"]) for record in baseline_lifetimes
    )
    optimized_input_elements = sum(
        int(record["m"]) * int(record["k"]) for record in optimized_lifetimes
    )
    eliminated_input_elements = sum(int(record["input_elements"]) for record in eliminated)
    if baseline_input_elements - optimized_input_elements != eliminated_input_elements:
        raise ValueError("input-element reduction does not match eliminated lifetime records")
    if len(eliminated) != int(result["cross_operator"]["quantizations_eliminated"]):
        raise ValueError("eliminated lifetime detail does not match quantization reduction")
    if sum(int(record["quantized_bytes"]) for record in eliminated) != int(
        result["cross_operator"]["activation_bytes_eliminated"]
    ):
        raise ValueError("eliminated lifetime detail does not match activation-byte reduction")

    result["baseline"].update(
        {
            "quantization_input_elements": baseline_input_elements,
            "quantization_input_bytes": 4 * baseline_input_elements,
        }
    )
    result["cross_operator"].update(
        {
            "quantization_input_elements": optimized_input_elements,
            "quantization_input_bytes": 4 * optimized_input_elements,
            "quantization_input_elements_eliminated": eliminated_input_elements,
            "quantization_input_bytes_eliminated": 4 * eliminated_input_elements,
        }
    )
    result["eliminated_quantizations"] = eliminated
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--baseline-label", default="QBS_CONTEXT_BASELINE")
    parser.add_argument("--optimized-label", default="QBS_CROSS_OP")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = compare_log(args.log, args.baseline_label, args.optimized_label)
    manifest = args.log.parent / "manifest.txt"
    result["provenance"] = {
        "tool": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256(Path(__file__).resolve()),
        },
        "log": {
            "path": str(args.log.resolve()),
            "sha256": sha256(args.log),
        },
        "manifest": {
            "path": str(manifest.resolve()),
            "sha256": sha256(manifest) if manifest.is_file() else None,
            "values": read_manifest(manifest),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
