#!/usr/bin/env python3
"""List watched RTL control signals from an integrity-checked toggle merge."""

import argparse
import json
import re
from pathlib import Path

from audit_merged import audit
from run_verilator_coverage import iter_raw_points, sha256


BIT = re.compile(r"\[\d+\]$")


def summarize(raw: Path, hierarchy: str, includes: list[str],
              patterns: list[str]) -> dict:
    watchers = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
    signals = {}
    for props, count in iter_raw_points(raw, hierarchy):
        source = props.get("f", "")
        label = props.get("o", "")
        if (props.get("t") != "toggle" or not label or
                (includes and not any(part in source for part in includes)) or
                (watchers and not any(pattern.search(label) for pattern in watchers))):
            continue
        name = BIT.sub("", label)
        key = (source, props.get("h", ""), name)
        bucket = signals.setdefault(key, {"bits_total": 0, "bits_toggled": 0,
                                          "transition_count": 0})
        bucket["bits_total"] += 1
        bucket["bits_toggled"] += count > 0
        bucket["transition_count"] += count
    rows = [
        {"source": source, "instance": instance, "signal": signal, **counts}
        for (source, instance, signal), counts in signals.items()
    ]
    rows.sort(key=lambda row: (row["bits_toggled"] - row["bits_total"],
                               row["source"], row["instance"], row["signal"]))
    return {"signals_total": len(rows),
            "signal_bits_total": sum(row["bits_total"] for row in rows),
            "signal_bits_toggled": sum(row["bits_toggled"] for row in rows),
            "signals": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=1)
    parser.add_argument("--pattern", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    integrity = audit(args.audit, args.minimum_cases)
    if integrity["status"] != "PASS":
        parser.error(f"merge audit failed: {integrity['issues']}")
    record = json.loads(args.audit.read_text(encoding="utf-8"))
    result = summarize(args.audit.parent / "merged.dat",
                       record["hierarchy_coverage"]["hierarchy_prefix"],
                       record["include_paths"], args.pattern)
    if result["signal_bits_total"] == 0:
        parser.error("no watched toggle points matched the requested scope")
    result.update({"status": "REVIEW_REQUIRED", "merge_audit": str(args.audit.resolve()),
                   "merge_audit_sha256": sha256(args.audit), "patterns": args.pattern,
                   "scope_note": "A nonzero toggle count proves at least one transition, not both directions"})
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['signal_bits_toggled']}/{result['signal_bits_total']} watched bits toggled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
