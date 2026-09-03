#!/usr/bin/env python3
"""Compare exact QBS input traffic for alternative command geometries.

The model deliberately does not predict implementation speedup. It computes
quantities fixed by the ABI layout and command loop nest, plus two optimistic
lower bounds. Measured RTL counters must decide whether reduced traffic is on
the execution critical path.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROW_MICROTILE = 4
DOT_PAIRS_PER_CYCLE = 32
READ_BYTES_PER_CYCLE = 16
ACCUMULATOR_ENTRIES = 128
NARROW_MAX_N = 32


@dataclass(frozen=True)
class Geometry:
    name: str
    max_m: int
    max_n: int


@dataclass(frozen=True)
class Estimate:
    case: str
    profile: str
    m: int
    n: int
    k: int
    geometry: str
    command_count: int
    max_command_results: int
    k_blocks: int
    weight_bytes: int
    activation_bytes: int
    input_bytes: int
    useful_pairs: int
    pair_capacity: int
    pair_utilization: float
    ideal_dot_cycles: int
    ideal_read_cycles: int
    roofline_cycles: int
    activation_block_buffer_bytes: int


def chunks(total: int, maximum: int) -> list[int]:
    if total <= 0 or maximum <= 0:
        raise ValueError("shape dimensions and tile limits must be positive")
    return [min(maximum, total - start) for start in range(0, total, maximum)]


def round_up(value: int, alignment: int) -> int:
    return ((value + alignment - 1) // alignment) * alignment


def command_n_limit(geometry: Geometry, tile_m: int) -> int:
    """Mirror the runtime's mixed-width tail policy for wide-M storage."""
    if geometry.max_m > 4 and tile_m <= 4:
        return NARROW_MAX_N
    return geometry.max_n


def compatible_activation_profile(abi: dict, weight_profile: str) -> str:
    weight = abi["weight_profiles"][weight_profile]
    profiles = weight["activation_profiles"]
    if len(profiles) != 1:
        raise ValueError(
            f"{weight_profile} has {len(profiles)} activation profiles; "
            "the model requires an explicit unique pair"
        )
    return profiles[0]


def estimate(
    abi: dict,
    case: str,
    weight_profile: str,
    m: int,
    n: int,
    k: int,
    geometry: Geometry,
) -> Estimate:
    weight = abi["weight_profiles"][weight_profile]
    activation_name = compatible_activation_profile(abi, weight_profile)
    activation = abi["activation_profiles"][activation_name]
    block_elements = int(weight["block_elements"])
    if int(activation["block_elements"]) != block_elements:
        raise ValueError(f"incompatible profile pair for {weight_profile}")
    if k % block_elements:
        raise ValueError(
            f"{case}: K={k} is not divisible by block size {block_elements}"
        )

    m_tiles = chunks(m, geometry.max_m)
    n_tiles_by_m = [chunks(n, command_n_limit(geometry, mt)) for mt in m_tiles]
    if max(
        mt * nt
        for mt, n_tiles in zip(m_tiles, n_tiles_by_m)
        for nt in n_tiles
    ) > ACCUMULATOR_ENTRIES:
        raise ValueError(
            f"{geometry.name}: command result tile exceeds "
            f"{ACCUMULATOR_ENTRIES} accumulators"
        )

    k_blocks = k // block_elements
    padded_n_rows_by_m = [
        sum(round_up(nt, ROW_MICROTILE) for nt in n_tiles)
        for n_tiles in n_tiles_by_m
    ]

    # Every M command group walks all N tiles and therefore rereads weights.
    weight_bytes = (
        sum(padded_n_rows_by_m)
        * k_blocks
        * int(weight["block_bytes"])
    )
    # M8 uses a fixed eight-row payload built from two M4-interleaved groups.
    # The final M5--M7 group is padded; this is the byte cost paid to avoid a
    # variable divider/modulo network in the RTL input steering path.
    # Every N command tile rereads the activation payload in its M group.
    activation_bytes = (
        sum(
            (geometry.max_m if geometry.max_m > 4 and mt > 4 else mt)
            * len(n_tiles)
            for mt, n_tiles in zip(m_tiles, n_tiles_by_m)
        )
        * k_blocks * int(activation["block_bytes"])
    )
    useful_pairs = m * n * k
    pair_capacity = sum(
        round_up(mt, ROW_MICROTILE) * padded_n_rows
        for mt, padded_n_rows in zip(m_tiles, padded_n_rows_by_m)
    ) * k
    ideal_dot_cycles = math.ceil(pair_capacity / DOT_PAIRS_PER_CYCLE)
    input_bytes = weight_bytes + activation_bytes
    ideal_read_cycles = math.ceil(input_bytes / READ_BYTES_PER_CYCLE)

    return Estimate(
        case=case,
        profile=weight_profile,
        m=m,
        n=n,
        k=k,
        geometry=geometry.name,
        command_count=sum(len(n_tiles) for n_tiles in n_tiles_by_m),
        max_command_results=max(
            mt * nt
            for mt, n_tiles in zip(m_tiles, n_tiles_by_m)
            for nt in n_tiles
        ),
        k_blocks=k_blocks,
        weight_bytes=weight_bytes,
        activation_bytes=activation_bytes,
        input_bytes=input_bytes,
        useful_pairs=useful_pairs,
        pair_capacity=pair_capacity,
        pair_utilization=useful_pairs / pair_capacity,
        ideal_dot_cycles=ideal_dot_cycles,
        ideal_read_cycles=ideal_read_cycles,
        roofline_cycles=max(ideal_dot_cycles, ideal_read_cycles),
        activation_block_buffer_bytes=(
            (geometry.max_m
             if geometry.max_m > 4 and min(m, geometry.max_m) > 4
             else min(m, geometry.max_m))
            * int(activation["block_bytes"])
        ),
    )


def percent_reduction(old: int, new: int) -> float:
    return 100.0 * (old - new) / old


def comparisons(
    estimates: Iterable[Estimate], selection_threshold_pct: float
) -> list[dict[str, object]]:
    groups: dict[tuple[str, int], dict[str, Estimate]] = {}
    for item in estimates:
        groups.setdefault((item.case, item.m), {})[item.geometry] = item

    rows: list[dict[str, object]] = []
    for (case, m), pair in sorted(groups.items()):
        current = pair["m4n32"]
        adaptive = pair["m8n16"]
        rows.append(
            {
                "case": case,
                "profile": current.profile,
                "m": m,
                "n": current.n,
                "k": current.k,
                "current_commands": current.command_count,
                "adaptive_commands": adaptive.command_count,
                "current_weight_bytes": current.weight_bytes,
                "adaptive_weight_bytes": adaptive.weight_bytes,
                "weight_reduction_pct": percent_reduction(
                    current.weight_bytes, adaptive.weight_bytes
                ),
                "current_activation_bytes": current.activation_bytes,
                "adaptive_activation_bytes": adaptive.activation_bytes,
                "activation_change_pct": -percent_reduction(
                    current.activation_bytes, adaptive.activation_bytes
                ),
                "current_input_bytes": current.input_bytes,
                "adaptive_input_bytes": adaptive.input_bytes,
                "input_reduction_pct": percent_reduction(
                    current.input_bytes, adaptive.input_bytes
                ),
                "current_roofline_cycles": current.roofline_cycles,
                "adaptive_roofline_cycles": adaptive.roofline_cycles,
                "roofline_reduction_pct": percent_reduction(
                    current.roofline_cycles, adaptive.roofline_cycles
                ),
                "pair_capacity_equal": current.pair_capacity
                == adaptive.pair_capacity,
                "adaptive_buffer_bytes": adaptive.activation_block_buffer_bytes,
                "select_adaptive": (
                    m > 4
                    and percent_reduction(
                        current.input_bytes, adaptive.input_bytes
                    )
                    >= selection_threshold_pct
                ),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, rows: list[dict[str, object]]) -> None:
    selected = [row for row in rows if row["m"] in (8, 15)]
    lines = [
        "# QBS Adaptive-Tile Traffic Model",
        "",
        "This report contains exact ABI-derived traffic and optimistic lower "
        "bounds. It is not an RTL speedup prediction.",
        "",
        "| Case | Profile | M | Weight reduction | Activation change | "
        "Total-input reduction | Roofline reduction | Select |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in selected:
        lines.append(
            "| {case} | {profile} | {m} | {weight_reduction_pct:.2f}% | "
            "+{activation_change_pct:.2f}% | {input_reduction_pct:.2f}% | "
            "{roofline_reduction_pct:.2f}% | {select_adaptive} |".format(**row)
        )
    lines.extend(
        [
            "",
            "The roofline uses max(padded pairs / 32, input bytes / 16). "
            "A zero roofline reduction means the idealized command remains "
            "compute-bound; only measured RTL can establish exposed-cycle "
            "benefit.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--abi", type=Path, default=Path("config/qbs_abi.json"))
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("verification/qbs/adaptive_tile_cases.json"),
    )
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--markdown", type=Path)
    args = parser.parse_args()

    abi = json.loads(args.abi.read_text(encoding="utf-8"))
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    geometries = [Geometry("m4n32", 4, 32), Geometry("m8n16", 8, 16)]
    estimates: list[Estimate] = []
    for case in cases["cases"]:
        for m in cases["m_values"]:
            for geometry in geometries:
                estimates.append(
                    estimate(
                        abi,
                        case["name"],
                        case["weight_profile"],
                        int(m),
                        int(case["n"]),
                        int(case["k"]),
                        geometry,
                    )
                )

    selection_threshold_pct = float(
        abi["limits"]["wide_m_min_input_reduction_percent"]
    )
    rows = comparisons(estimates, selection_threshold_pct)
    if args.csv:
        write_csv(args.csv, rows)
    if args.markdown:
        write_markdown(args.markdown, rows)
    if not args.csv and not args.markdown:
        writer = csv.DictWriter(__import__("sys").stdout, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
