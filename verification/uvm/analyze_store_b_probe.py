#!/usr/bin/env python3
"""Compare the first store's bounded cycle trace in two source-matched runs."""

import argparse
import csv
import hashlib
import json
from pathlib import Path


REQUIRED = {
    "cycle", "commit_ack", "cvx_req_valid", "cvx_req_ready", "cvx_req_insn",
    "cvx_resp_valid", "ara_req_valid", "ara_req_ready", "seq_wait",
    "seq_addr_ack", "seq_store_done", "disp_state", "vstu_pending_b",
    "wlast_fire", "b_valid", "b_ready", "store_complete",
}


def load(path: Path) -> list[dict]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not REQUIRED.issubset(reader.fieldnames or ()):
            raise ValueError(f"unexpected probe columns: {path}")
        rows = []
        for record in reader:
            # Extended probes may add hex-valued diagnostic fields. This
            # analysis uses only its documented base columns.
            row = {key: int(record[key], 16 if key in {"commit_ack", "cvx_req_insn"} else 10)
                   for key in REQUIRED}
            if rows and row["cycle"] != rows[-1]["cycle"] + 1:
                raise ValueError(f"probe has a missing or repeated cycle: {path}")
            rows.append(row)
    if not rows:
        raise ValueError(f"empty probe: {path}")
    return rows


def first_store(rows: list[dict], store_insn: int) -> dict:
    def first(predicate, start=0):
        for index in range(start, len(rows)):
            if predicate(rows[index]):
                return index
        raise ValueError("required store timeline event is outside the probe window")

    offer = first(lambda row: row["cvx_req_valid"] and row["cvx_req_insn"] == store_insn)
    accept = first(lambda row: row["cvx_req_valid"] and row["cvx_req_ready"] and
                   row["cvx_req_insn"] == store_insn, offer)
    response = first(lambda row: row["cvx_resp_valid"], accept)
    next_request = first(lambda row: row["cvx_req_valid"] and row["cvx_req_ready"],
                         response + 1)
    next_store = first(lambda row: row["cvx_req_valid"] and
                       row["cvx_req_insn"] == store_insn, accept + 1)
    span = rows[offer:next_store]

    def event_cycle(predicate):
        match = next((row["cycle"] for row in span if predicate(row)), None)
        return match

    return {
        "first_store_offer": rows[offer]["cycle"],
        "first_store_accept": rows[accept]["cycle"],
        "first_response_valid_after_accept": rows[response]["cycle"],
        "next_accepted_request": rows[next_request]["cycle"],
        "next_store_offer": rows[next_store]["cycle"],
        "first_wlast_fire": event_cycle(lambda row: row["wlast_fire"]),
        "first_b_fire": event_cycle(lambda row: row["b_valid"] and row["b_ready"]),
        "first_vstu_complete": event_cycle(lambda row: row["store_complete"]),
        "seq_wait_before_store_response": sum(row["seq_wait"] != 0 for row in
                                              rows[offer:response + 1]),
        "seq_wait_with_pending_b_before_response": sum(
            row["seq_wait"] != 0 and row["vstu_pending_b"] != 0
            for row in rows[offer:response + 1]),
        "ara_req_blocked_cycles_until_next_store": sum(
            row["ara_req_valid"] != 0 and row["ara_req_ready"] == 0 for row in span),
        "cvx_req_blocked_cycles_until_next_store": sum(
            row["cvx_req_valid"] != 0 and row["cvx_req_ready"] == 0 for row in span),
        "dispatcher_states": {str(state): sum(row["disp_state"] == state for row in span)
                              for state in sorted({row["disp_state"] for row in span})},
    }


def interval_counts(rows: list[dict], start: int, end: int) -> dict:
    span = [row for row in rows if start <= row["cycle"] < end]
    if len(span) != end - start:
        raise ValueError("comparison interval is not fully covered by the probe")
    return {
        "commit_slots": sum(bin(row["commit_ack"]).count("1") for row in span),
        "cvx_request_fires": sum(row["cvx_req_valid"] != 0 and
                                 row["cvx_req_ready"] != 0 for row in span),
        "sequencer_wait_cycles": sum(row["seq_wait"] != 0 for row in span),
        "ara_request_blocked_cycles": sum(row["ara_req_valid"] != 0 and
                                          row["ara_req_ready"] == 0 for row in span),
        "pending_b_cycles": sum(row["vstu_pending_b"] != 0 for row in span),
        "wlast_fires": sum(row["wlast_fire"] != 0 for row in span),
        "b_fires": sum(row["b_valid"] != 0 and row["b_ready"] != 0 for row in span),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--precise", type=Path, required=True)
    parser.add_argument("--store-insn", default="020661a7")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = {"store_insn": args.store_insn.lower(),
              "scope": "bounded cycle probe; first store only, not whole-task attribution"}
    traces = {}
    for name, path in (("baseline", args.baseline), ("precise", args.precise)):
        rows = load(path)
        traces[name] = rows
        result[name] = {"path": str(path.resolve()),
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "window_start": rows[0]["cycle"],
                        "window_end": rows[-1]["cycle"],
                        **first_store(rows, int(args.store_insn, 16))}
    start = result["precise"]["first_store_accept"]
    end = result["precise"]["first_response_valid_after_accept"]
    result["same_wall_cycle_interval"] = {
        "start_inclusive": start, "end_exclusive": end,
        "baseline": interval_counts(traces["baseline"], start, end),
        "precise": interval_counts(traces["precise"], start, end),
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({name: result[name] for name in ("baseline", "precise")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
