#!/usr/bin/env python3
"""Attribute only an accepted full-call register/layout control."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import re

import acceptance_audit as audit

e = audit.experiment
require, sha = e.require, e.sha
reference = e.load(e.HERE.parent / "analyze.py", "rotation_retirement_helpers")
QK, PV = reference.HELPERS
WRAPPER = "__wrap_" + PV


def ranges(text):
    symbols = [(int(m[1], 16), m[2]) for m in re.finditer(
        r"^([0-9a-f]+) <([^>]+)>:$", text, re.M)]
    result = {}
    for (start, name), (end, _) in zip(symbols, symbols[1:]):
        if name in (QK, PV, WRAPPER):
            require(name not in result and start < end, "Invalid helper boundary")
            result[name] = (start, end)
    require(set(result) == {QK, PV, WRAPPER}, "Missing actual helper code")
    return result


def merge_pv_spans(spans):
    result = []
    for original in spans:
        span = dict(original)
        span["opcodes"] = Counter(original["opcodes"])
        if span["helper"] == WRAPPER:
            span["helper"] = PV
        if result and result[-1]["helper"] == span["helper"] and result[-1]["end"] == span["begin"]:
            result[-1]["end"] = span["end"]
            result[-1]["retired"] += span["retired"]
            result[-1]["opcodes"].update(span["opcodes"])
        else:
            result.append(span)
    return result


def lifetimes(path):
    live, complete, previous = {}, [], -1
    audit.strict_header(path)
    with path.open() as stream:
        for row in csv.DictReader(stream):
            require(None not in row and all(v is not None for v in row.values()), "Malformed vector row")
            cycle = int(row["cycle"])
            require(cycle >= previous and row["event"] != "reset", "Time/reset epoch mismatch")
            previous = cycle
            if row["event"] not in ("alloc", "done"):
                continue
            vid, seq, insn = int(row["vid"]), int(row["arch_seq"]), int(row["insn"], 16)
            if row["event"] == "alloc":
                require(vid not in live, "Live VID reallocated")
                live[vid] = dict(seq=seq, vid=vid, insn=insn, alloc=cycle,
                                 vl=int(row["vl"]), vstart=int(row["vstart"]))
            else:
                require(vid in live and live[vid]["seq"] == seq and live[vid]["insn"] == insn,
                        "Completion identity mismatch")
                item = live.pop(vid)
                item["done"] = cycle
                complete.append(item)
    require(not live, "Incomplete instruction lifetimes")
    return sorted(complete, key=lambda item: (item["alloc"], item["seq"]))


def histogram(values):
    return dict(sorted(Counter(values).items()))


def pv_tile(instructions, span, nrows, arm):
    groups = []
    rows = {0x0205345B, 0x0205355B}
    fmas = {0xB2805057, 0xB280D157, 0xB2A05057, 0xB2A0D157}
    for item in instructions:
        if not span["begin"] <= item["alloc"] < span["end"]:
            continue
        if item["insn"] in rows:
            groups.append([item])
        elif item["insn"] in fmas:
            require(groups, "FMA before its row replay")
            groups[-1].append(item)
    require(len(groups) == nrows, "Wrong PV row count")
    for i, group in enumerate(groups):
        register = 10 if arm and i % 2 else 8
        expected = (0x0205305B | register << 7,
                    0xB2005057 | register << 20, 0xB200D157 | register << 20)
        require(tuple(item["insn"] for item in group) == expected, "Wrong row/FMA pairing")
        require(all(item["vl"] == 128 and item["vstart"] == 0 and item["done"] >= item["alloc"]
                    for item in group), "Unexpected PV shape/lifetime")
    intervals = [b[0]["alloc"] - a[0]["alloc"] for a, b in zip(groups, groups[1:])]
    gaps = [b[0]["alloc"] - max(x["done"] for x in a[1:]) for a, b in zip(groups, groups[1:])]
    distance = 2 if arm else 1
    same_group_gaps = [b[0]["alloc"] - max(x["done"] for x in a[1:])
                       for a, b in zip(groups, groups[distance:])]
    return dict(rows=nrows, begin=span["begin"], end=span["end"],
        row_allocation_period_histogram=histogram(intervals),
        next_row_minus_previous_last_fma_done_histogram=histogram(gaps),
        same_register_reuse_minus_previous_reader_done_histogram=histogram(same_group_gaps),
        next_row_before_previous_fma_done_count=sum(g < 0 for g in gaps),
        first_fma_before_replay_done_count=sum(g[1]["alloc"] < g[0]["done"] for g in groups),
        replay_lifetime_histogram=histogram(g[0]["done"] - g[0]["alloc"] for g in groups), groups=groups)


def analyze(directory):
    acceptance = audit.audit(directory)
    result = json.loads((directory / "result.json").read_text())
    build = Path(result["build"])
    disassembly = build / "disassembly.log"
    commit = directory / "work/commit.csv"
    require(result["artifacts"].get(str(commit)) == sha(commit), "Unaccepted retirement trace")
    trials = reference.trials_from_log((directory / "work/run.vcs.log").read_text())
    markers = {row[k] for row in trials for k in ("begin", "returned", "end")}
    with commit.open() as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)),
                "Duplicate retirement CSV columns")
        spans, matched = reference.retirement_spans(reader, ranges(disassembly.read_text()), markers)
    spans = merge_pv_spans(spans)
    instructions = lifetimes(directory / "work/vector_trace.csv")
    output = []
    for trial in trials:
        begin, end = matched[trial["begin"]], matched[trial["end"]]
        selected = [s for s in spans if begin <= s["begin"] < end]
        require(all(s["end"] <= end for s in selected) and
                [s["helper"] for s in selected] == [QK, PV]*3, "Wrong complete-call helper order")
        tiles = [pv_tile(instructions, span, count, trial["arm"])
                 for span, count in zip(selected[1::2], (64, 64, 9))]
        cycles = {kind: sum(s["end"] - s["begin"] for s in selected if s["helper"] == name)
                  for kind, name in (("qk", QK), ("pv", PV))}
        cycles["remaining"] = end - begin - sum(cycles.values())
        require(cycles["remaining"] >= 0, "Overlapping helper intervals")
        output.append(dict(trial=trial["trial"], arm=trial["arm"], full_call_cycles=end-begin,
                           helper_retirement_spans=cycles, pv_tiles=tiles))
    means = {label: {key: sum(t["helper_retirement_spans"][key] for t in output if t["arm"] == arm)/2
                     for key in ("qk", "pv", "remaining")}
             for arm, label in ((0, "auto"), (1, "rotation_and_loop"))}
    for arm, label in ((0, "auto"), (1, "rotation_and_loop")):
        means[label]["full_call"] = sum(t["full_call_cycles"] for t in output if t["arm"] == arm)/2
    return dict(state="CONTROL_LIFETIMES_ANALYZED", acceptance=acceptance, trials=output,
        mean_cycles=means, full_call_speedup=means["auto"]["full_call"]/means["rotation_and_loop"]["full_call"],
        attribution="Combined register rotation and loop layout, not isolated WAR savings",
        fpu_utilization_measured=False, hardware_changed=False,
        warning="CPU helper retirement spans are not independent stall or FU execution intervals",
        artifacts={str(p): sha(p) for p in (commit, disassembly, Path(__file__),
                    Path(audit.__file__), e.HERE.parent / "analyze.py")})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.resolve().is_relative_to(args.run.resolve()), "Use a separate output receipt")
    result = analyze(args.run.resolve())
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], means=result["mean_cycles"],
                         full_call_speedup=result["full_call_speedup"])))
