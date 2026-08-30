#!/usr/bin/env python3
"""Validate a DIRECT/DIRECT versus FILL/REUSE top-level QBS experiment."""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


QBS_PREFIX = "[QBS_PERF] "
BENCH_PREFIX = "QBS_REAL_BENCH "
DESCRIPTOR_BYTES = 16


def parse_fields(line: str, prefix: str) -> dict[str, str]:
    if not line.startswith(prefix):
        raise ValueError(f"line does not start with {prefix!r}")
    fields: dict[str, str] = {}
    for token in line[len(prefix) :].split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return fields


def parse_log(path: pathlib.Path) -> tuple[list[dict[str, int]], dict[str, str]]:
    qbs_commands: list[dict[str, int]] = []
    benchmark: dict[str, str] | None = None
    core_success = False

    for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
        if line.startswith(QBS_PREFIX):
            fields = parse_fields(line, QBS_PREFIX)
            try:
                qbs_commands.append({key: int(value, 0) for key, value in fields.items()})
            except ValueError as error:
                raise ValueError(f"{path}: invalid QBS_PERF integer: {error}") from error
        elif line.startswith(BENCH_PREFIX):
            benchmark = parse_fields(line, BENCH_PREFIX)
        elif "Core Test *** SUCCESS ***" in line:
            core_success = True

    if len(qbs_commands) != 2:
        raise ValueError(f"{path}: expected 2 QBS commands, found {len(qbs_commands)}")
    if benchmark is None:
        raise ValueError(f"{path}: QBS_REAL_BENCH record is missing")
    if not core_success:
        raise ValueError(f"{path}: top-level Core Test success marker is missing")
    return qbs_commands, benchmark


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def require_command_success(label: str, command: dict[str, int]) -> None:
    require(command.get("success") == 1, f"{label}: command did not succeed")
    for field in ("fault", "validation_fault", "validation_error", "read_fault"):
        require(command.get(field) == 0, f"{label}: {field} is not zero")


def require_benchmark_success(label: str, benchmark: dict[str, str]) -> None:
    require(benchmark.get("result") == "PASS", f"{label}: benchmark did not pass")
    require(int(benchmark.get("mismatches", "-1"), 0) == 0,
            f"{label}: benchmark has mismatches")


def percent_reduction(before: int, after: int) -> float:
    return 100.0 * (before - after) / before if before else 0.0


def validate(direct_path: pathlib.Path, context_path: pathlib.Path) -> str:
    direct, direct_bench = parse_log(direct_path)
    context, context_bench = parse_log(context_path)
    direct_first, direct_second = direct
    fill, reuse = context

    for index, command in enumerate(direct, start=1):
        require_command_success(f"DIRECT command {index}", command)
        require(command.get("activation_access") == 0,
                f"DIRECT command {index}: wrong activation access mode")
        require(command.get("context_fill_count") == 0,
                f"DIRECT command {index}: unexpected context fill")
        require(command.get("context_reuse_count") == 0,
                f"DIRECT command {index}: unexpected context reuse")

    require_command_success("FILL command", fill)
    require(fill.get("activation_access") == 1, "FILL: wrong activation access mode")
    require(fill.get("context_fill_count") == 1, "FILL: context was not filled")
    require(fill.get("context_reuse_count") == 0, "FILL: unexpected reuse")

    require_command_success("REUSE command", reuse)
    require(reuse.get("activation_access") == 2, "REUSE: wrong activation access mode")
    require(reuse.get("context_fill_count") == 0, "REUSE: unexpected fill")
    require(reuse.get("context_reuse_count") == 1, "REUSE: context was not reused")
    require(reuse.get("context_validation_fault_count") == 0,
            "REUSE: context validation faulted")

    require_benchmark_success("DIRECT", direct_bench)
    require_benchmark_success("FILL/REUSE", context_bench)
    require(direct_bench.get("checksum") == context_bench.get("checksum"),
            "DIRECT and FILL/REUSE checksums differ")

    activation_bytes = direct_second["activation_bytes"]
    require(activation_bytes > 0, "DIRECT: activation byte count is zero")
    require(direct_first["activation_bytes"] == activation_bytes,
            "DIRECT commands do not use the same activation shape")
    require(reuse["context_read_bytes"] == activation_bytes,
            "REUSE: context read bytes do not cover the activation")
    require(reuse["activation_axi_bytes_saved"] == activation_bytes,
            "REUSE: saved AXI byte counter does not match activation size")
    require(reuse["payload_bytes"] == reuse["weight_bytes"] + DESCRIPTOR_BYTES,
            "REUSE: AXI payload contains bytes beyond descriptor and weights")
    require(direct_second["payload_bytes"] - reuse["payload_bytes"] == activation_bytes,
            "REUSE: measured AXI payload reduction does not equal activation size")
    require(direct_second["read_ranges"] - reuse["read_ranges"] ==
            reuse["context_reuse_block_count"],
            "REUSE: removed read ranges do not match reused Q8_K blocks")
    require(int(direct_bench["logical_read_bytes"], 0) -
            int(context_bench["logical_read_bytes"], 0) == activation_bytes,
            "benchmark logical traffic reduction does not match activation size")

    # The first command is intentionally identical except for context capture.
    for field in ("busy_cycles", "read_ranges", "payload_bytes", "weight_bytes",
                  "activation_bytes"):
        require(direct_first[field] == fill[field],
                f"FILL perturbed first-command {field}")

    direct_busy = direct_second["busy_cycles"]
    reuse_busy = reuse["busy_cycles"]
    direct_matmul = int(direct_bench["matmul_cycles"], 0)
    context_matmul = int(context_bench["matmul_cycles"], 0)
    direct_total = int(direct_bench["timed_cycles"], 0)
    context_total = int(context_bench["timed_cycles"], 0)

    return "\n".join(
        (
            "QBS activation-context evidence: PASS",
            f"checksum={direct_bench['checksum']} mismatches=0",
            f"two_command_activation_axi_bytes: {2 * activation_bytes} -> "
            f"{activation_bytes} (saved {activation_bytes})",
            f"second_command_total_axi_payload_bytes: "
            f"{direct_second['payload_bytes']} -> {reuse['payload_bytes']}",
            f"second_command_total_read_ranges: {direct_second['read_ranges']} -> "
            f"{reuse['read_ranges']} (removed "
            f"{reuse['context_reuse_block_count']} activation ranges)",
            f"second_command_cycles: {direct_busy} -> {reuse_busy} "
            f"({percent_reduction(direct_busy, reuse_busy):.2f}% reduction)",
            f"matmul_cycles: {direct_matmul} -> {context_matmul} "
            f"({percent_reduction(direct_matmul, context_matmul):.2f}% reduction)",
            f"timed_cycles: {direct_total} -> {context_total} "
            f"({percent_reduction(direct_total, context_total):.2f}% reduction)",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direct", required=True, type=pathlib.Path,
                        help="DIRECT/DIRECT top-level console log")
    parser.add_argument("--context", required=True, type=pathlib.Path,
                        help="FILL/REUSE top-level console log")
    args = parser.parse_args()

    try:
        print(validate(args.direct, args.context))
    except (OSError, ValueError, KeyError) as error:
        print(f"QBS activation-context evidence: FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
