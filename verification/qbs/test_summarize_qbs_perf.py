#!/usr/bin/env python3
"""Regression checks for direct and context-reuse QBS byte accounting."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "hardware/scripts/qbs/summarize_qbs_perf.py"
SPEC = importlib.util.spec_from_file_location("summarize_qbs_perf", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def record(sequence: int, saved: int) -> dict[str, int]:
    return {
        "seq": sequence,
        "id": 0,
        "m": 1,
        "n": 32,
        "vlen": 1024,
        "lanes": 4,
        "success": 1,
        "fault": 0,
        "validation_fault": 0,
        "validation_error": 0,
        "read_fault": 0,
        "useful_pairs": 49152,
        "pair_capacity": 49152,
        "commit_groups": 4,
        "weight_bytes": 27648,
        "activation_bytes": 1752,
        "activation_axi_bytes_saved": saved,
        "payload_bytes": 16 + 27648 + 1752 - saved,
    }


def main() -> None:
    direct = record(1, 0)
    reuse = record(2, 1752)
    errors = MODULE.validate([direct, reuse])
    if errors:
        raise SystemExit("valid direct/context records rejected: " + "; ".join(errors))

    impossible = record(1, 1753)
    impossible["payload_bytes"] = 16 + impossible["weight_bytes"]
    errors = MODULE.validate([impossible])
    if not any("saved activation bytes exceed" in error for error in errors):
        raise SystemExit("impossible activation saving was not rejected")

    wide = record(1, 0)
    wide.update({"m": 8, "n": 16, "commit_groups": 16})
    errors = MODULE.validate([wide])
    if errors:
        raise SystemExit("valid M8/N16 commit geometry rejected: " + "; ".join(errors))

    wide_tail = record(1, 0)
    wide_tail.update({"m": 7, "n": 7, "commit_groups": 7})
    errors = MODULE.validate([wide_tail])
    if errors:
        raise SystemExit("valid M7/N7 commit geometry rejected: " + "; ".join(errors))

    wrong_wide = dict(wide)
    wrong_wide["commit_groups"] = 32
    errors = MODULE.validate([wrong_wide])
    if not any("commit_groups=32, expected 16" in error for error in errors):
        raise SystemExit("invalid M8/N16 commit geometry was not rejected")
    print("PASS: QBS direct/context payload accounting")


if __name__ == "__main__":
    main()
