#!/usr/bin/env python3
"""Executable AKV-v2 token-axis Attention design-space model.

The model separates exact architectural counts from cycle projections.  The
cycle interval is anchored to the controlled tiled-RVV measurements and must
not be interpreted as an RTL performance result.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from typing import Iterable, TextIO


HEAD_DIM = 128
Q_ROWS = 6
KV_HEADS = 2
VLEN_BITS = 1024
VRF_REGISTERS = 32
F16_BYTES = 2
F32_BYTES = 4
CONTEXT_WORD_BYTES = 32
ROW_BYTES = HEAD_DIM * F16_BYTES
MAX_Q_ROWS = 8

# Measured on one simulator build with the same real Qwen2.5 capture.  Counter
# totals differ from the application's interval by a few bookkeeping cycles;
# the model consistently uses the counter totals and phase intervals below.
BASELINES = {
    16: {
        "rvv_cycles": 121_338,
        "akv_v1_cycles": 52_318,
        "tiled_total_cycles": 41_327,
        "tiled_pack_cycles": 7_679,
        "tiled_matmul_cycles": 29_537,
        "tiled_reductions": 24,
        "akv_v1_axi_read_bytes": 25_728,
    },
    128: {
        "rvv_cycles": 725_838,
        "akv_v1_cycles": 383_502,
        "tiled_total_cycles": 157_434,
        "tiled_pack_cycles": 60_429,
        "tiled_matmul_cycles": 92_798,
        "tiled_reductions": 48,
        "akv_v1_axi_read_bytes": 140_416,
    },
    256: {
        "rvv_cycles": 1_413_791,
        "akv_v1_cycles": 761_933,
        "tiled_total_cycles": 309_574,
        "tiled_pack_cycles": 120_809,
        "tiled_matmul_cycles": 184_480,
        "tiled_reductions": 96,
        "akv_v1_axi_read_bytes": 271_488,
    },
}

TARGET_CYCLES = {16: 41_327, 128: 130_000, 256: 250_000}

# AKV-v1 D128 local row loads measure 25 busy cycles for eight 32-byte replay
# words.  Seventeen cycles are therefore command/state overhead in this model.
LOCAL_LOAD_FIXED_CYCLES = 17

# Across KV=128/256, AKV-v1 fill busy time is accurately described by one
# cycle per 16-byte read beat plus about 19 command/state cycles per fill.
FILL_COMMAND_FIXED_CYCLES = 19

# Tiled-RVV measured roughly 40.5 active cycles per FP reduction.  This is used
# only to penalize designs with more reductions than the 64-token baseline.
FP_REDUCTION_CYCLES = 41


@dataclass(frozen=True)
class Layout:
    name: str
    description: str
    token_parallelism: int
    transposed_k: bool = False
    duplicate_k: bool = False
    phased_kv: bool = False


LAYOUTS = {
    "legacy_row": Layout(
        "legacy_row",
        "AKV-v1 word-banked slot-major rows; one K token contributes per gather cycle",
        token_parallelism=1,
    ),
    "transpose_k": Layout(
        "transpose_k",
        "K physically transposed at fill; V remains token-major",
        token_parallelism=16,
        transposed_k=True,
    ),
    "dual_k": Layout(
        "dual_k",
        "K keeps row and transposed views; V remains token-major",
        token_parallelism=16,
        transposed_k=True,
        duplicate_k=True,
    ),
    "token_banked8": Layout(
        "token_banked8",
        "row-major K/V with eight token-indexed banks and a gathered K-column view",
        token_parallelism=8,
    ),
    "token_banked8_phased": Layout(
        "token_banked8_phased",
        "eight-bank row view reused for separate K and V phases",
        token_parallelism=8,
        phased_kv=True,
    ),
}


@dataclass(frozen=True)
class ModelPoint:
    layout: str
    tile_tokens: int
    query_batch: int
    kv_length: int
    tiles_total: int
    reduction_count: int
    context_bytes: int
    vrf_peak_registers_lower_bound: int
    vrf_headroom_lower_bound: int
    k_column_loads: int
    v_row_loads: int
    local_load_commands: int
    local_replay_bytes: int
    k_view_read_cycles: int
    local_load_busy_cycles: int
    fill_commands: int
    model_external_bytes: int
    score_spill_bytes: int
    transpose_element_placements: int
    cycle_lower_bound: int
    cycle_conservative_bound: int
    target_cycles: int
    target_status: str
    implementation_risk: str


def ceil_div(numerator: int, denominator: int) -> int:
    return (numerator + denominator - 1) // denominator


def legal_tile(tile_tokens: int) -> bool:
    return tile_tokens in (8, 16, 32, 64)


def context_bytes(layout: Layout, tile_tokens: int) -> int:
    q_capacity = MAX_Q_ROWS * ROW_BYTES
    k_capacity = tile_tokens * ROW_BYTES
    v_capacity = tile_tokens * ROW_BYTES
    if layout.phased_kv:
        return q_capacity + max(k_capacity, v_capacity)
    return q_capacity + k_capacity * (2 if layout.duplicate_k else 1) + v_capacity


def vrf_peak_lower_bound(tile_tokens: int, query_batch: int) -> int:
    # One FP32 token-axis score uses m1 at T<=32 and m2 at T=64.  K uses one
    # e16,m1 register.  Two additional registers cover mask/score temporaries.
    score_lmul = ceil_div(tile_tokens, VLEN_BITS // 32)
    score_stage = query_batch * score_lmul + 1 + 2

    # Six persistent D128 F16 outputs consume 12 registers.  A V row consumes
    # two, and four registers cover factors and update temporaries.  This is a
    # liveness lower bound, not a compiler-allocation guarantee.
    output_stage = Q_ROWS * 2 + 2 + 4
    return max(score_stage, output_stage)


def k_view_cycles_per_column(layout: Layout, active_tokens: int) -> int:
    if layout.transposed_k:
        # Direct 32-byte replay words already account for the physical reads.
        return 0
    return ceil_div(active_tokens, layout.token_parallelism)


def model_point(layout: Layout, tile_tokens: int, query_batch: int,
                kv_length: int) -> ModelPoint:
    if not legal_tile(tile_tokens):
        raise ValueError(f"unsupported tile size: {tile_tokens}")
    if query_batch not in (2, 4, 6):
        raise ValueError(f"unsupported Query batch: {query_batch}")
    if kv_length not in BASELINES:
        raise ValueError(f"no frozen baseline for KV={kv_length}")

    tile_lengths = [
        min(tile_tokens, kv_length - tile_start)
        for tile_start in range(0, kv_length, tile_tokens)
    ]
    tiles_per_head = len(tile_lengths)
    tiles_total = KV_HEADS * tiles_per_head
    query_passes = ceil_div(Q_ROWS, query_batch)
    reductions = tiles_total * Q_ROWS * 2

    k_column_loads = tiles_total * HEAD_DIM * query_passes
    v_row_loads = KV_HEADS * kv_length
    v_words = ROW_BYTES // CONTEXT_WORD_BYTES
    v_load_cycles = LOCAL_LOAD_FIXED_CYCLES + v_words
    k_busy_per_head = 0
    k_replay_words_per_head = 0
    k_view_cycles_per_head = 0
    for active_tokens in tile_lengths:
        k_words = ceil_div(active_tokens * F16_BYTES, CONTEXT_WORD_BYTES)
        view_cycles = k_view_cycles_per_column(layout, active_tokens)
        columns = HEAD_DIM * query_passes
        k_busy_per_head += columns * (
            LOCAL_LOAD_FIXED_CYCLES + view_cycles + k_words
        )
        k_replay_words_per_head += columns * k_words
        k_view_cycles_per_head += columns * view_cycles
    local_busy = (KV_HEADS * k_busy_per_head +
                  v_row_loads * v_load_cycles)
    replay_bytes = (
        KV_HEADS * k_replay_words_per_head + v_row_loads * v_words
    ) * CONTEXT_WORD_BYTES
    total_k_view_cycles = KV_HEADS * k_view_cycles_per_head

    q_bytes = KV_HEADS * Q_ROWS * ROW_BYTES
    kv_bytes = KV_HEADS * kv_length * 2 * ROW_BYTES
    model_bytes = q_bytes + kv_bytes
    score_spill = 0
    if layout.phased_kv:
        # Scores must survive the K-to-V phase boundary.  This assumes one
        # write and one read of six FP32 score rows per tile.
        score_spill = KV_HEADS * kv_length * Q_ROWS * F32_BYTES * 2

    transpose_placements = 0
    if layout.transposed_k:
        transpose_placements = KV_HEADS * kv_length * HEAD_DIM

    fill_commands = tiles_total * (2 if layout.phased_kv else 1)
    fill_cycles = ceil_div(model_bytes, 16) + fill_commands * FILL_COMMAND_FIXED_CYCLES

    baseline = BASELINES[kv_length]
    nonpack_cycles = baseline["tiled_total_cycles"] - baseline["tiled_pack_cycles"]
    extra_reductions = max(0, reductions - baseline["tiled_reductions"])
    arithmetic_floor = nonpack_cycles + extra_reductions * FP_REDUCTION_CYCLES
    cycle_low = arithmetic_floor + fill_cycles
    cycle_high = cycle_low + local_busy

    target = TARGET_CYCLES[kv_length]
    if cycle_high <= target:
        target_status = "conservative-pass"
    elif cycle_low < target:
        target_status = "requires-overlap"
    else:
        target_status = "model-fail"

    risks = []
    if layout.transposed_k:
        risks.append("fill-transpose-unmodeled")
    if layout.duplicate_k:
        risks.append("duplicate-K-view")
    if layout.phased_kv:
        risks.append("score-spill-and-two-phase-fill")
    peak = vrf_peak_lower_bound(tile_tokens, query_batch)
    if peak > VRF_REGISTERS:
        risks.append("VRF-overflow")
    elif VRF_REGISTERS - peak < 8:
        risks.append("low-VRF-headroom")
    implementation_risk = ",".join(risks) if risks else "bounded"

    return ModelPoint(
        layout=layout.name,
        tile_tokens=tile_tokens,
        query_batch=query_batch,
        kv_length=kv_length,
        tiles_total=tiles_total,
        reduction_count=reductions,
        context_bytes=context_bytes(layout, tile_tokens),
        vrf_peak_registers_lower_bound=peak,
        vrf_headroom_lower_bound=VRF_REGISTERS - peak,
        k_column_loads=k_column_loads,
        v_row_loads=v_row_loads,
        local_load_commands=k_column_loads + v_row_loads,
        local_replay_bytes=replay_bytes,
        k_view_read_cycles=total_k_view_cycles,
        local_load_busy_cycles=local_busy,
        fill_commands=fill_commands,
        model_external_bytes=model_bytes,
        score_spill_bytes=score_spill,
        transpose_element_placements=transpose_placements,
        cycle_lower_bound=cycle_low,
        cycle_conservative_bound=cycle_high,
        target_cycles=target,
        target_status=target_status,
        implementation_risk=implementation_risk,
    )


def all_points() -> list[ModelPoint]:
    return [
        model_point(layout, tile, batch, kv)
        for layout in LAYOUTS.values()
        for tile in (8, 16, 32, 64)
        for batch in (2, 6)
        for kv in (16, 128, 256)
    ]


def markdown_table(rows: Iterable[ModelPoint], fields: list[str], out: TextIO) -> None:
    rows = list(rows)
    print("| " + " | ".join(fields) + " |", file=out)
    print("|" + "|".join("---" for _ in fields) + "|", file=out)
    for row in rows:
        values = asdict(row)
        print("| " + " | ".join(str(values[field]) for field in fields) + " |", file=out)


def emit_summary(out: TextIO) -> None:
    print("# AKV-v2 executable design-space summary\n", file=out)
    print("## Layout comparison: T=64, Q batch=6, KV=256\n", file=out)
    rows = [model_point(layout, 64, 6, 256) for layout in LAYOUTS.values()]
    markdown_table(rows, [
        "layout", "context_bytes", "reduction_count", "local_load_commands",
        "local_replay_bytes", "k_view_read_cycles",
        "transpose_element_placements", "score_spill_bytes",
        "vrf_headroom_lower_bound", "implementation_risk",
    ], out)

    print("\n## Tile and Query grouping: token_banked8, KV=256\n", file=out)
    rows = [
        model_point(LAYOUTS["token_banked8"], tile, batch, 256)
        for tile in (8, 16, 32, 64)
        for batch in (2, 4, 6)
    ]
    markdown_table(rows, [
        "tile_tokens", "query_batch", "reduction_count",
        "local_load_commands", "local_replay_bytes", "k_view_read_cycles",
        "vrf_peak_registers_lower_bound", "cycle_lower_bound",
        "cycle_conservative_bound", "target_status",
    ], out)

    print("\n## Selected structural candidate: token_banked8, T=64, Q batch=6\n", file=out)
    rows = [model_point(LAYOUTS["token_banked8"], 64, 6, kv)
            for kv in (16, 128, 256)]
    markdown_table(rows, [
        "kv_length", "tiles_total", "reduction_count", "context_bytes",
        "local_load_commands", "local_replay_bytes", "model_external_bytes",
        "cycle_lower_bound", "cycle_conservative_bound", "target_cycles",
        "target_status",
    ], out)

    print("\nCycle bounds are projections, not RTL measurements. The lower bound adds "
          "measured no-pack tiled execution and calibrated fill cost; the "
          "conservative bound additionally serializes every modeled local-load "
          "busy cycle. Fill-transpose placement and phased score-spill latency "
          "are intentionally not converted into hidden cycle estimates.", file=out)


def emit_csv(rows: Iterable[ModelPoint], out: TextIO) -> None:
    rows = list(rows)
    fieldnames = list(asdict(rows[0]).keys())
    writer = csv.DictWriter(out, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(asdict(row))


def validate_invariants() -> None:
    selected = [model_point(LAYOUTS["token_banked8"], 64, 6, kv)
                for kv in (16, 128, 256)]
    assert [point.reduction_count for point in selected] == [24, 48, 96]
    assert all(point.transpose_element_placements == 0 for point in selected)
    assert all(point.score_spill_bytes == 0 for point in selected)
    assert all(point.vrf_peak_registers_lower_bound <= VRF_REGISTERS
               for point in selected)
    assert selected[-1].model_external_bytes == 265_216
    assert selected[-1].context_bytes == 34_816


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("summary", "csv", "json"),
                        default="summary")
    args = parser.parse_args()

    validate_invariants()
    points = all_points()
    if args.format == "summary":
        emit_summary(sys.stdout)
    elif args.format == "csv":
        emit_csv(points, sys.stdout)
    else:
        json.dump([asdict(point) for point in points], sys.stdout, indent=2)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
