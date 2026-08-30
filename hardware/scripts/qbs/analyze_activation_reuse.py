#!/usr/bin/env python3
"""Audit real-model activation reuse and estimate QBS read-reuse bounds."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


REUSE_GROUPS = {
    "attention_qkv": (
        "blk_0_attn_q_weight",
        "blk_0_attn_k_weight",
        "blk_0_attn_v_weight",
    ),
    "ffn_gate_up": (
        "blk_0_ffn_gate_weight",
        "blk_0_ffn_up_weight",
    ),
}


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_single_row_csv(path: Path) -> Dict[str, str]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 1:
        raise ValueError(f"{path} must contain exactly one data row")
    return rows[0]


def read_phase_csv(path: Path) -> Dict[str, Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    result = {row["phase"]: row for row in rows}
    if "total" not in result or "quantize" not in result:
        raise ValueError(f"{path} lacks total or quantize phase")
    return result


def parse_named_paths(values: Iterable[str]) -> List[Tuple[str, Path]]:
    result = []
    for value in values:
        if "=" not in value:
            raise ValueError(f"expected NAME=PATH, got {value!r}")
        name, path = value.split("=", 1)
        if not name or not path:
            raise ValueError(f"expected NAME=PATH, got {value!r}")
        result.append((name, Path(path)))
    return result


def activation_record(operator_dir: Path) -> Dict[str, object]:
    data_path = operator_dir / "activation_f32.bin"
    metadata_path = operator_dir / "activation_f32.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "operator": operator_dir.name,
        "bytes": data_path.stat().st_size,
        "sha256": file_hash(data_path),
        "type": metadata.get("type", "unknown"),
        "shape": metadata.get("shape", "unknown"),
    }


def format_shape(shape: object) -> str:
    if isinstance(shape, list):
        return "x".join(str(item) for item in shape)
    return str(shape)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--capture-root",
        type=Path,
        required=True,
        help="model capture root containing PHASE/operators",
    )
    parser.add_argument("--phase", choices=("decode", "prefill"), default="decode")
    parser.add_argument(
        "--qbs-perf",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="single-row summarize_qbs_perf.py output; repeat as needed",
    )
    parser.add_argument(
        "--metrics",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="phase metrics.csv associated with a named QBS perf input",
    )
    args = parser.parse_args()

    operators_root = args.capture_root / args.phase / "operators"
    print("# Real-model activation identity")
    print()
    print("| Group | Operators | Shape | Bytes | Identical | SHA-256 |")
    print("| --- | --- | ---: | ---: | --- | --- |")
    for group_name, operators in REUSE_GROUPS.items():
        records = [activation_record(operators_root / operator) for operator in operators]
        hashes = {record["sha256"] for record in records}
        sizes = {record["bytes"] for record in records}
        shapes = {format_shape(record["shape"]) for record in records}
        identical = len(hashes) == 1 and len(sizes) == 1
        shape = next(iter(shapes)) if len(shapes) == 1 else "/".join(sorted(shapes))
        size = str(next(iter(sizes))) if len(sizes) == 1 else "/".join(
            str(item) for item in sorted(sizes)
        )
        digest = next(iter(hashes))[:16] if len(hashes) == 1 else "different"
        print(
            f"| {group_name} | {', '.join(operators)} | {shape} | {size} | "
            f"{'yes' if identical else 'no'} | `{digest}` |"
        )

    perf_inputs = parse_named_paths(args.qbs_perf)
    metrics_inputs = dict(parse_named_paths(args.metrics))
    if not perf_inputs:
        return 0

    print()
    print("# Per-operator QBS activation-read reuse bound")
    print()
    print(
        "The cycle estimate removes the proportional share of activation-phase "
        "cycles for all but the first command. It is an upper bound, not a "
        "measured context-buffer result."
    )
    print()
    print(
        "| Case | Commands | Current activation bytes | Unique bytes | Repeat bytes | "
        "Activation phase | Removable estimate | Busy-cycle bound | Total-cycle bound |"
    )
    print("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for name, path in perf_inputs:
        row = read_single_row_csv(path)
        commands = int(row["commands"])
        busy_cycles = int(row["busy_cycles"])
        activation_cycles = int(row["phase_activation_cycles"])
        activation_bytes = int(row["activation_bytes"])
        if commands <= 0 or activation_bytes % commands != 0:
            raise ValueError(f"{path} has a non-uniform activation byte count")
        unique_bytes = activation_bytes // commands
        repeat_bytes = activation_bytes - unique_bytes
        removable_cycles = activation_cycles * (commands - 1) // commands
        busy_bound = busy_cycles - removable_cycles
        busy_speedup = busy_cycles / busy_bound if busy_bound else 0.0

        total_bound_text = "n/a"
        if name in metrics_inputs:
            phases = read_phase_csv(metrics_inputs[name])
            total_cycles = int(phases["total"]["cycles"])
            total_bound = total_cycles - removable_cycles
            total_speedup = total_cycles / total_bound if total_bound else 0.0
            total_bound_text = f"{total_bound} ({total_speedup:.3f}x)"

        print(
            f"| {name} | {commands} | {activation_bytes} | {unique_bytes} | "
            f"{repeat_bytes} | {activation_cycles} | {removable_cycles} | "
            f"{busy_bound} ({busy_speedup:.3f}x) | {total_bound_text} |"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
