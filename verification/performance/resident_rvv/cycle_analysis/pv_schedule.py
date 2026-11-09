#!/usr/bin/env python3
"""Audit allocation/completion intervals in the accepted paired-PV helpers."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path

from analyze import reference, require

ROW_LOAD = 0x0205345B
PAIR_FMAS = (0xB2805057, 0xB280D157)


def lifetimes(rows):
    live, complete = {}, []
    previous = -1
    for row in rows:
        cycle = int(row["cycle"])
        require(cycle >= previous, "Nonmonotonic vector trace")
        previous = cycle
        require(row["event"] != "reset", "Unexpected reset epoch")
        if row["event"] not in ("alloc", "done"):
            continue
        vid, seq = int(row["vid"]), int(row["arch_seq"])
        insn = int(row["insn"], 16)
        if row["event"] == "alloc":
            require(vid not in live, "Live VID reallocated")
            live[vid] = dict(seq=seq, vid=vid, insn=insn, alloc=cycle,
                             vl=int(row["vl"]), vstart=int(row["vstart"]))
        else:
            require(vid in live and live[vid]["seq"] == seq and
                    live[vid]["insn"] == insn, "Completion identity mismatch")
            item = live.pop(vid)
            item["done"] = cycle
            complete.append(item)
    require(not live, "Incomplete instruction lifetimes")
    return sorted(complete, key=lambda item: (item["alloc"], item["seq"]))


def histogram(values):
    return dict(sorted(Counter(values).items()))


def pv_tiles(instructions, spans, expected_rows):
    require(len(spans) == len(expected_rows), "Unexpected PV helper count")
    result = []
    for span, nrows in zip(spans, expected_rows):
        groups = []
        for item in instructions:
            if not span["begin"] <= item["alloc"] < span["end"]:
                continue
            if item["insn"] == ROW_LOAD:
                groups.append([item])
            elif item["insn"] in PAIR_FMAS:
                require(groups, "PV FMA before its row replay")
                groups[-1].append(item)
        require(len(groups) == nrows, "Unexpected row command count")
        for group in groups:
            require(tuple(item["insn"] for item in group) == (ROW_LOAD,) + PAIR_FMAS,
                    "Unexpected paired-PV instruction sequence")
            require(all(item["vstart"] == 0 for item in group), "Restarted PV instruction")
        periods = [b[0]["alloc"] - a[0]["alloc"] for a, b in zip(groups, groups[1:])]
        gaps = [b[0]["alloc"] - max(item["done"] for item in a[1:])
                for a, b in zip(groups, groups[1:])]
        result.append(dict(begin=span["begin"], end=span["end"], rows=len(groups),
            row_allocation_period_histogram=histogram(periods),
            next_row_minus_previous_last_fma_done_histogram=histogram(gaps),
            first_fma_alloc_before_replay_done_count=sum(
                group[1]["alloc"] < group[0]["done"] for group in groups),
            replay_lifetime_histogram=histogram(group[0]["done"]-group[0]["alloc"]
                                               for group in groups),
            groups=groups))
    return result


def analyze(evidence, build):
    accepted = reference.analyze(evidence, build)
    with (evidence / "work/vector_trace.csv").open() as stream:
        instructions = lifetimes(csv.DictReader(stream))
    trials = []
    for trial in accepted["trials"]:
        if not trial["arm"]:
            continue
        spans = [s for s in trial["helpers"] if s["helper"] == reference.HELPERS[1]]
        trials.append(dict(trial=trial["trial"], tiles=pv_tiles(instructions, spans, (64, 64, 9))))
    return dict(schema="resident-pv-schedule-v1", state="ACCEPTED_LIFETIMES_ANALYZED",
        scope="Frozen Qwen3 D128/H2/T137 ABBA, both auto calls",
        fpu_activity_measured=False, no_new_rtl_execution=True,
        warning="Allocation overlap is not arithmetic overlap or proof of a removable stall",
        trials=trials, source_artifacts=accepted["source_artifacts"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.evidence.resolve(), args.build.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], output=str(args.output))))
