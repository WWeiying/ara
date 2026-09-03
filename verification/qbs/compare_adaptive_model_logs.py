#!/usr/bin/env python3
"""Compare ABI-derived QBS weight-plus-activation traffic from matched logs.

The report reconstructs logical weight and activation payload bytes from the
observed GGML QBS call shapes and the canonical ABI. It excludes descriptor
reads, result traffic, and software staging accesses, and does not claim
measured AXI traffic or cycle speedup. Trace command counts are checked against
the reconstruction so a stale geometry model cannot silently produce evidence.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from analyze_adaptive_tiles import Geometry, chunks, estimate, percent_reduction


GGML_TYPE_TO_PROFILE = {
    "q2_K": "Q2_K",
    "q3_K": "Q3_K",
    "q4_0": "Q4_0",
    "q4_K": "Q4_K",
    "q5_0": "Q5_0",
    "q5_K": "Q5_K",
    "q6_K": "Q6_K",
    "q8_0": "Q8_0_WEIGHT",
    "iq4_nl": "IQ4_NL",
}

CALL_PATTERN = re.compile(
    r"GGML_RISCV_QBS_CALL type=(\S+) mode=(\S+) k=(\d+) "
    r"input_rows=(\d+) output_rows=(\d+) split_k=(\d+)"
)
FIELD_PATTERN = re.compile(r"([A-Za-z0-9_]+)=([^\s]+)")


@dataclass(frozen=True)
class Call:
    weight_type: str
    mode: str
    k: int
    m: int
    n: int
    split_k: bool


def parse_calls(path: Path) -> list[Call]:
    calls: list[Call] = []
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            match = CALL_PATTERN.search(line)
            if match is None:
                continue
            weight_type, mode, k, m, n, split_k = match.groups()
            if weight_type not in GGML_TYPE_TO_PROFILE:
                raise ValueError(f"unsupported traced GGML type: {weight_type}")
            calls.append(
                Call(
                    weight_type=weight_type,
                    mode=mode,
                    k=int(k),
                    m=int(m),
                    n=int(n),
                    split_k=split_k != "0",
                )
            )
    if not calls:
        raise ValueError(f"no GGML_RISCV_QBS_CALL records in {path}")
    return calls


def parse_exec_counters(path: Path) -> dict[str, object]:
    commands_by_m = Counter()
    totals = Counter()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.startswith("GGML_RISCV_QBS_EXEC "):
                continue
            fields = dict(FIELD_PATTERN.findall(line))
            for m in range(1, 9):
                commands_by_m[m] += int(fields.get(f"commands_m{m}", 0))
            for field in (
                "native_qbexec",
                "emulated_commands",
                "command_dot_elements",
            ):
                totals[field] += int(fields.get(field, 0))
    if not commands_by_m:
        raise ValueError(f"no GGML_RISCV_QBS_EXEC command counters in {path}")
    return {
        "commands_by_m": dict(sorted(commands_by_m.items())),
        **totals,
    }


def parse_model_nodes(path: Path) -> dict[str, int]:
    counts = Counter()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if not line.startswith("GGML_RISCV_MODEL_NODE "):
                continue
            fields = dict(FIELD_PATTERN.findall(line))
            counts["total"] += 1
            if fields.get("op") == "MUL_MAT":
                counts["mul_mat"] += 1
    if not counts["total"]:
        raise ValueError(f"no GGML_RISCV_MODEL_NODE records in {path}")
    return dict(counts)


def choose_geometry(abi: dict, call: Call, adaptive: bool) -> Geometry:
    narrow = Geometry("m4n32", 4, 32)
    if not adaptive or call.m < int(abi["limits"]["wide_m_min"]):
        return narrow
    if call.split_k:
        return narrow

    block_elements = int(
        abi["weight_profiles"][GGML_TYPE_TO_PROFILE[call.weight_type]][
            "block_elements"
        ]
    )
    if call.k % block_elements or (
        call.k // block_elements > int(abi["limits"]["max_k_blocks"])
    ):
        return narrow

    wide = Geometry(
        "m8n16",
        int(abi["limits"]["max_m"]),
        int(abi["limits"]["wide_m_max_n"]),
    )
    profile = GGML_TYPE_TO_PROFILE[call.weight_type]
    current = estimate(abi, "trace", profile, call.m, call.n, call.k, narrow)
    candidate = estimate(abi, "trace", profile, call.m, call.n, call.k, wide)
    reduction = percent_reduction(current.input_bytes, candidate.input_bytes)
    threshold = float(abi["limits"]["wide_m_min_input_reduction_percent"])
    return wide if reduction >= threshold else narrow


def analyze_log(path: Path, abi: dict, adaptive: bool) -> dict[str, object]:
    totals = Counter()
    by_mode: dict[str, Counter] = defaultdict(Counter)
    by_profile: dict[str, Counter] = defaultdict(Counter)
    commands_by_m = Counter()

    calls = parse_calls(path)
    for index, call in enumerate(calls):
        geometry = choose_geometry(abi, call, adaptive)
        profile = GGML_TYPE_TO_PROFILE[call.weight_type]
        item = estimate(
            abi,
            f"trace-{index}",
            profile,
            call.m,
            call.n,
            call.k,
            geometry,
        )
        fields = {
            "calls": 1,
            "commands": item.command_count,
            "weight_bytes": item.weight_bytes,
            "activation_bytes": item.activation_bytes,
            "input_bytes": item.input_bytes,
            "dot_elements": item.useful_pairs,
        }
        totals.update(fields)
        by_mode[call.mode].update(fields)
        by_profile[profile].update(fields)
        n_tiles = len(chunks(call.n, geometry.max_n))
        for tile_m in chunks(call.m, geometry.max_m):
            commands_by_m[tile_m] += n_tiles

    trace = parse_exec_counters(path)
    traced_by_m = {
        int(m): int(count)
        for m, count in trace["commands_by_m"].items()
        if int(count) != 0
    }
    modeled_by_m = dict(sorted(commands_by_m.items()))
    if modeled_by_m != traced_by_m:
        raise ValueError(
            f"{path}: modeled M counts {modeled_by_m} do not match trace "
            f"{traced_by_m}"
        )
    traced_commands = int(trace["native_qbexec"]) + int(
        trace["emulated_commands"]
    )
    if totals["commands"] != traced_commands:
        raise ValueError(
            f"{path}: modeled commands {totals['commands']} != traced "
            f"{traced_commands}"
        )
    if totals["dot_elements"] != int(trace["command_dot_elements"]):
        raise ValueError(
            f"{path}: modeled dot work {totals['dot_elements']} != traced "
            f"{trace['command_dot_elements']}"
        )

    return {
        **totals,
        "model_nodes": parse_model_nodes(path),
        "commands_by_m": modeled_by_m,
        "native_commands": int(trace["native_qbexec"]),
        "emulated_commands": int(trace["emulated_commands"]),
        "by_mode": {name: dict(values) for name, values in sorted(by_mode.items())},
        "by_profile": {
            name: dict(values) for name, values in sorted(by_profile.items())
        },
    }


def reduction_record(
    baseline: Mapping[str, int], adaptive: Mapping[str, int]
) -> dict:
    result = {}
    for field in ("weight_bytes", "activation_bytes", "input_bytes"):
        old = int(baseline[field])
        new = int(adaptive[field])
        result[f"{field}_reduction_pct"] = percent_reduction(old, new)
    return result


def compare_logs(
    baseline_log: Path, adaptive_log: Path, abi: dict
) -> dict[str, object]:
    baseline = analyze_log(baseline_log, abi, adaptive=False)
    adaptive = analyze_log(adaptive_log, abi, adaptive=True)
    if baseline["model_nodes"] != adaptive["model_nodes"]:
        raise ValueError("matched logs do not contain the same model graph nodes")
    if baseline["dot_elements"] != adaptive["dot_elements"]:
        raise ValueError("matched logs do not contain the same QBS dot work")
    if baseline["emulated_commands"] or adaptive["emulated_commands"]:
        raise ValueError("model traffic comparison requires native QBS commands")

    mode_changes = {}
    for mode in sorted(set(baseline["by_mode"]) | set(adaptive["by_mode"])):
        if mode not in baseline["by_mode"] or mode not in adaptive["by_mode"]:
            raise ValueError(f"mode {mode} is not present in both logs")
        mode_changes[mode] = reduction_record(
            baseline["by_mode"][mode], adaptive["by_mode"][mode]
        )

    return {
        "schema_version": 1,
        "semantics": (
            "ABI-derived logical weight-plus-activation payload bytes; "
            "excludes descriptors, results, and software staging; not "
            "measured AXI traffic and not a cycle-speedup result"
        ),
        "baseline_log": str(baseline_log),
        "adaptive_log": str(adaptive_log),
        "baseline": baseline,
        "adaptive": adaptive,
        "reduction": reduction_record(baseline, adaptive),
        "reduction_by_mode": mode_changes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-log", type=Path, required=True)
    parser.add_argument("--adaptive-log", type=Path, required=True)
    parser.add_argument("--abi", type=Path, default=Path("config/qbs_abi.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    abi = json.loads(args.abi.read_text(encoding="utf-8"))
    report = compare_logs(args.baseline_log, args.adaptive_log, abi)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(encoded, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
