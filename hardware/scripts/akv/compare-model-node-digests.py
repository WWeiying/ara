#!/usr/bin/env python3
"""Locate the first differing GGML node output in two matched model runs."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path


DIGEST_PATTERN = re.compile(
    r"^GGML_RISCV_MODEL_DIGEST "
    r"graph=(?P<graph>\d+) node=(?P<node>\d+) "
    r"op=(?P<op>\S+) type=(?P<type>\S+) "
    r"ne0=(?P<ne0>\d+) ne1=(?P<ne1>\d+) ne2=(?P<ne2>\d+) ne3=(?P<ne3>\d+) "
    r"bytes=(?P<bytes>\d+) hash=(?P<hash>[0-9a-fA-F]{16}) name=(?P<name>.*)$"
)


@dataclass(frozen=True)
class NodeDigest:
    graph: int
    node: int
    op: str
    type: str
    ne0: int
    ne1: int
    ne2: int
    ne3: int
    bytes: int
    hash: str
    name: str

    @property
    def identity(self) -> tuple[int, int]:
        return self.graph, self.node

    @property
    def contract(self) -> tuple[object, ...]:
        return (
            self.graph,
            self.node,
            self.op,
            self.type,
            self.ne0,
            self.ne1,
            self.ne2,
            self.ne3,
            self.bytes,
            self.name,
        )


def parse_digests(path: Path) -> list[NodeDigest]:
    records: list[NodeDigest] = []
    seen: set[tuple[int, int]] = set()
    with path.open(encoding="utf-8", errors="replace") as stream:
        for line_number, line in enumerate(stream, start=1):
            match = DIGEST_PATTERN.match(line.rstrip("\r\n"))
            if match is None:
                continue
            values = match.groupdict()
            record = NodeDigest(
                graph=int(values["graph"]),
                node=int(values["node"]),
                op=values["op"],
                type=values["type"],
                ne0=int(values["ne0"]),
                ne1=int(values["ne1"]),
                ne2=int(values["ne2"]),
                ne3=int(values["ne3"]),
                bytes=int(values["bytes"]),
                hash=values["hash"].lower(),
                name=values["name"],
            )
            if record.identity in seen:
                raise ValueError(
                    f"{path}:{line_number}: duplicate graph/node identity {record.identity}"
                )
            seen.add(record.identity)
            records.append(record)
    if not records:
        raise ValueError(f"no GGML_RISCV_MODEL_DIGEST records in {path}")
    return records


def compare_digests(baseline_path: Path, candidate_path: Path) -> dict[str, object]:
    baseline = parse_digests(baseline_path)
    candidate = parse_digests(candidate_path)
    if len(baseline) != len(candidate):
        raise ValueError(
            f"digest record count differs: baseline={len(baseline)} candidate={len(candidate)}"
        )

    first_mismatch: dict[str, object] | None = None
    matching_prefix = 0
    mismatch_count = 0
    for index, (left, right) in enumerate(zip(baseline, candidate)):
        if left.contract != right.contract:
            raise ValueError(
                f"digest topology differs at record {index}: "
                f"baseline={left.contract} candidate={right.contract}"
            )
        if left.hash == right.hash:
            if first_mismatch is None:
                matching_prefix += 1
            continue
        mismatch_count += 1
        if first_mismatch is None:
            first_mismatch = {
                "record_index": index,
                "graph": left.graph,
                "node": left.node,
                "op": left.op,
                "type": left.type,
                "shape": [left.ne0, left.ne1, left.ne2, left.ne3],
                "bytes": left.bytes,
                "name": left.name,
                "baseline_hash": left.hash,
                "candidate_hash": right.hash,
            }

    return {
        "schema_version": 1,
        "semantics": "exact FNV-1a digest over logical tensor rows after node completion",
        "baseline_log": str(baseline_path),
        "candidate_log": str(candidate_path),
        "record_count": len(baseline),
        "matching_prefix_records": matching_prefix,
        "mismatch_count": mismatch_count,
        "all_equal": mismatch_count == 0,
        "first_mismatch": first_mismatch,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--require-equal",
        action="store_true",
        help="return failure when any selected node output differs",
    )
    args = parser.parse_args()

    report = compare_digests(args.baseline, args.candidate)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 1 if args.require_equal and not report["all_equal"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
