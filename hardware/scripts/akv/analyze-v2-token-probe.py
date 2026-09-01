#!/usr/bin/env python3
"""Check that AKV-v2 token 5 survives context fill and K-column gather."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


CONTEXT_RE = re.compile(
    r"\[AKV_V2_CONTEXT_PROBE\].* q=([0-9a-fA-F]+) k=([0-9a-fA-F]+) "
    r"v=([0-9a-fA-F]+) rows=(\d+) dim=(\d+) kv=(\d+) "
    r"tile_start=(\d+) tile_count=(\d+)"
)
WRITE_RE = re.compile(
    r"\[AKV_V2_TOKEN_WRITE\].* stream=(\d+) token=(\d+) offset=(\d+) "
    r"strb=([0-9a-fA-F]+) data=([0-9a-fA-F]+)"
)
GATHER_RE = re.compile(
    r"\[AKV_V2_TOKEN_GATHER\].* stream=(\d+) dim=(\d+) count=(\d+) "
    r"token5=([0-9a-fA-F]+)"
)
V2_FULL_RE = re.compile(r"\[AKV_PERF\].*\bv2_full=1\b")

AKV_STREAM_K = 1


@dataclass
class Context:
    index: int
    q_base: int
    k_base: int
    v_base: int
    rows: int
    head_dim: int
    kv_length: int
    tile_start: int
    reported_tile_count: int
    streams: dict[int, bytearray] = field(default_factory=dict)
    written: dict[int, set[int]] = field(default_factory=dict)
    gathers: dict[tuple[int, int], list[int]] = field(default_factory=dict)
    ignored_prefill_gathers: int = 0
    fill_complete: bool = False
    gather_started: bool = False

    @property
    def tile_count(self) -> int:
        return min(self.kv_length - self.tile_start, 64)

    def add_write(self, stream: int, offset: int, strobe: int, data: int) -> None:
        payload = data.to_bytes(16, "little")
        image = self.streams.setdefault(stream, bytearray(self.head_dim * 2))
        valid = self.written.setdefault(stream, set())
        for lane, value in enumerate(payload):
            if (strobe >> lane) & 1:
                position = offset + lane
                if position >= len(image):
                    raise ValueError(
                        f"context {self.index}: write byte {position} exceeds "
                        f"D{self.head_dim} row"
                    )
                image[position] = value
                valid.add(position)

    def expected_k(self, dimension: int) -> int | None:
        valid = self.written.get(AKV_STREAM_K, set())
        byte = 2 * dimension
        if byte not in valid or byte + 1 not in valid:
            return None
        image = self.streams[AKV_STREAM_K]
        return int.from_bytes(image[byte : byte + 2], "little")


def parse_log(path: Path) -> list[Context]:
    contexts: list[Context] = []
    current: Context | None = None
    for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        match = CONTEXT_RE.search(line)
        if match:
            values = [int(value, 16 if index < 3 else 10)
                      for index, value in enumerate(match.groups())]
            current = Context(len(contexts), *values)
            contexts.append(current)
            continue

        match = WRITE_RE.search(line)
        if match:
            if current is None:
                raise ValueError(f"line {line_number}: token write before context")
            stream, token, offset = (int(match.group(i)) for i in range(1, 4))
            if token != 5:
                raise ValueError(f"line {line_number}: unexpected token {token}")
            current.add_write(
                stream, offset, int(match.group(4), 16), int(match.group(5), 16)
            )
            continue

        if V2_FULL_RE.search(line):
            if current is None:
                raise ValueError(f"line {line_number}: V2 FULL before context")
            current.fill_complete = True
            continue

        match = GATHER_RE.search(line)
        if match:
            if current is None:
                raise ValueError(f"line {line_number}: gather before context")
            stream, dimension, count = (int(match.group(i)) for i in range(1, 4))
            if count != current.tile_count:
                raise ValueError(
                    f"line {line_number}: gather count {count} != context tile "
                    f"count {current.tile_count}"
                )
            # column_valid remains asserted until the next column command.  In
            # old observation logs, a new FULL descriptor can therefore be
            # followed by samples from the preceding context while the new
            # token-5 row is still being filled.  They are not command results.
            if (not current.fill_complete or
                    current.expected_k(dimension) is None):
                current.ignored_prefill_gathers += 1
                continue
            if not current.gather_started:
                if stream != AKV_STREAM_K or dimension != 0:
                    current.ignored_prefill_gathers += 1
                    continue
                current.gather_started = True
            current.gathers.setdefault((stream, dimension), []).append(
                int(match.group(4), 16)
            )
    return contexts


def analyze(contexts: list[Context]) -> dict[str, object]:
    mismatches: list[dict[str, int | str]] = []
    checked_dimensions = 0
    duplicate_samples = 0
    contexts_with_token5 = 0
    stale_reported_tile_counts = 0

    for context in contexts:
        if context.reported_tile_count != context.tile_count:
            stale_reported_tile_counts += 1
        if context.tile_count <= 5:
            continue
        contexts_with_token5 += 1
        for (stream, dimension), samples in sorted(context.gathers.items()):
            if stream != AKV_STREAM_K:
                continue
            duplicate_samples += len(samples) - 1
            unique = set(samples)
            if len(unique) != 1:
                mismatches.append(
                    {
                        "context": context.index,
                        "stream": stream,
                        "dimension": dimension,
                        "kind": "unstable_gather",
                        "observed_samples": len(unique),
                    }
                )
                continue
            expected = context.expected_k(dimension)
            observed = samples[0]
            checked_dimensions += 1
            if expected is None or observed != expected:
                mismatches.append(
                    {
                        "context": context.index,
                        "stream": stream,
                        "dimension": dimension,
                        "kind": "missing_write" if expected is None else "data_mismatch",
                        "expected": -1 if expected is None else expected,
                        "observed": observed,
                    }
                )

        expected_dimensions = set(range(context.head_dim))
        observed_dimensions = {
            dimension
            for stream, dimension in context.gathers
            if stream == AKV_STREAM_K
        }
        for dimension in sorted(expected_dimensions - observed_dimensions):
            mismatches.append(
                {
                    "context": context.index,
                    "stream": AKV_STREAM_K,
                    "dimension": dimension,
                    "kind": "missing_gather",
                }
            )

    return {
        "contexts": len(contexts),
        "contexts_with_token5": contexts_with_token5,
        "checked_k_dimensions": checked_dimensions,
        "duplicate_gather_samples": duplicate_samples,
        "ignored_prefill_gathers": sum(
            context.ignored_prefill_gathers for context in contexts
        ),
        "stale_reported_tile_counts": stale_reported_tile_counts,
        "mismatch_count": len(mismatches),
        "first_mismatch": mismatches[0] if mismatches else None,
        "mismatches": mismatches,
        "status": "PASS" if contexts_with_token5 and not mismatches else "FAIL",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    result = analyze(parse_log(args.log))
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
