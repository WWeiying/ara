#!/usr/bin/env python3
"""Analytical work/traffic estimates, never measured performance counters."""

import argparse
import hashlib
import json
from pathlib import Path


def amdahl(fraction, local_speedup):
    if not 0 <= fraction <= 1 or local_speedup <= 0:
        raise ValueError("fraction must be in [0, 1]; speedup must be positive")
    return 1 / (1 - fraction + fraction / local_speedup)


def audit_board_projection(model, path):
    raw = Path(path).read_bytes()
    trace = model["board_trace"]
    if hashlib.sha256(raw).hexdigest() != trace["sha256"]:
        raise ValueError("not the sealed board log")
    records = {}
    for line in raw.decode().splitlines():
        if line.startswith("GGML_RISCV_QBS_EXEC "):
            fields = dict(token.split("=", 1) for token in line.split()[1:])
            profile = fields["type"]
            if profile in records:
                raise ValueError("duplicate QBS profile summary")
            records[profile] = fields
    if set(records) != {"Q4_K", "Q6_K"}:
        raise ValueError("unexpected model profile set")
    observed = 0
    for profile, fields in records.items():
        count = int(fields["command_dot_elements"])
        if (count != int(fields["dot_elements"])
                or count != trace[profile.lower() + "_command_dot_elements"]
                or int(fields["emulated_commands"]) != 0):
            raise ValueError("operation/command work or execution mode mismatch")
        observed += count
    groups = model["groups"]
    layer_work = sum(groups[k]["elements"] for k in
                     ("attention_projection", "ffn_projection"))
    omitted_ffn_rows = trace["prompt_tokens"] - trace["prefill_last_layer_ffn_rows"]
    expected = (layer_work * (trace["prompt_tokens"] + trace["decode_evals"])
                - 3 * model["hidden"] * model["intermediate"] * omitted_ffn_rows
                + groups["output"]["elements"] * trace["output_rows"])
    if observed != expected:
        raise ValueError("graph and native command work disagree")
    return {"status": "AGGREGATE_PROJECTION_WORK_MATCHES",
            "expected_macs": expected, "successful_command_macs": observed,
            "source_sha256": trace["sha256"],
            "is_hardware_pmu_or_timing_measurement": False}


def summarize(model, lengths, clock_hz=50_000_000, bus_bits=64):
    if clock_hz <= 0 or bus_bits <= 0 or bus_bits % 8:
        raise ValueError("invalid clock or byte-addressable bus width")
    keys = ("attention_projection", "ffn_projection", "output")
    groups = model["groups"]
    macs = sum(groups[key]["elements"] for key in keys)
    weight_bytes = sum(groups[key]["bytes"] for key in keys)
    layers, hidden, dim = model["layers"], model["hidden"], model["head_dim"]
    expected_macs = layers * (
        2 * hidden * model["query_heads"] * dim
        + 2 * hidden * model["kv_heads"] * dim
        + 3 * hidden * model["intermediate"]
    ) + hidden * model["vocabulary"]
    if expected_macs != macs:
        raise ValueError("tensor inventory and dense model geometry disagree")
    bandwidth = clock_hz * (bus_bits // 8)
    rows = []
    for length in lengths:
        if length <= 0:
            raise ValueError("context length must be positive")
        attention_macs = 2 * layers * model["query_heads"] * dim * length
        kv_bytes = 2 * layers * model["kv_heads"] * dim * length * 2
        rows.append({
            "visible_tokens": length,
            "attention_macs": attention_macs,
            "attention_fraction_of_projection_plus_attention_macs":
                attention_macs / (macs + attention_macs),
            "ideal_f16_kv_read_bytes": kv_bytes,
            "ideal_f16_kv_read_mib": kv_bytes / 2**20,
            "kv_bytes_over_projection_weight_bytes": kv_bytes / weight_bytes,
        })
    return {
        "status": "ANALYTICAL_NOT_MEASURED",
        "projection_macs_per_decode_token": macs,
        "projection_stored_weight_bytes": weight_bytes,
        "projection_groups": {
            key: {
                **groups[key],
                "projection_mac_fraction": groups[key]["elements"] / macs,
                "projection_weight_fraction": groups[key]["bytes"] / weight_bytes,
            } for key in keys
        },
        "bus_payload_ceiling_bytes_per_second": bandwidth,
        "weight_transfer_seconds_if_each_stored_byte_crosses_bus_once":
            weight_bytes / bandwidth,
        "contexts": rows,
        "amdahl_no_added_cost": [
            {"baseline_time_fraction": p, "local_speedup": s,
             "end_to_end_speedup": amdahl(p, s)}
            for p in (0.1, 0.2, 0.3, 0.4) for s in (2, 4)
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path(__file__).with_name(
        "model_inventory_20261108.json"))
    parser.add_argument("--contexts", type=int, nargs="+",
                        default=[137, 1024, 4096, 8192, 16384])
    parser.add_argument("--clock-hz", type=int, default=50_000_000)
    parser.add_argument("--bus-bits", type=int, default=64)
    parser.add_argument("--board-log", type=Path)
    args = parser.parse_args()
    model = json.loads(args.inventory.read_text())
    report = summarize(model, args.contexts, args.clock_hz, args.bus_bits)
    if args.board_log:
        report["board_work_audit"] = audit_board_projection(model, args.board_log)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
