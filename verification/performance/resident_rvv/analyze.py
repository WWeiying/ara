#!/usr/bin/env python3
"""Attribute an accepted ABBA trace without labeling retirement spans as FU use."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
from collections import Counter

HELPERS = ("akv_experimental_qk_f16_pair_panel4", "akv_experimental_pv_f16_pair")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def helper_ranges(disassembly):
    symbols = [(int(m[1], 16), m[2]) for m in re.finditer(
        r"^([0-9a-f]+) <([^>]+)>:$", disassembly, re.M)]
    result = {}
    for (start, name), (end, _) in zip(symbols, symbols[1:]):
        if name in HELPERS:
            require(name not in result and end > start, "Invalid helper symbol range")
            result[name] = (start, end)
    require(set(result) == set(HELPERS), "Missing disassembled helper boundaries")
    return result


def trials_from_log(log):
    result = []
    for line in log.splitlines():
        if line.startswith("AKV_PAIR_TRIAL "):
            row = dict((k, int(v)) for k, v in
                       (part.split("=") for part in line.split()[1:]))
            require(row["errors"] == 0 and row["begin"] < row["returned"] < row["end"],
                    "Invalid or failed trial")
            result.append(row)
    require([r["trial"] for r in result] == [0, 1, 2, 3] and
            [r["arm"] for r in result] == [0, 1, 1, 0], "Expected accepted ABBA sequence")
    return result


def retirement_spans(rows, ranges, markers):
    active = None
    spans, matched = [], {}
    for row in rows:
        if row["event"] != "retire":
            continue
        cycle, pc, insn = int(row["cycle"]), int(row["pc"], 16), int(row["insn"], 16)
        if insn & 0xFFFFF07F == 0xC0002073:
            value = int(row["rd_wdata"], 16)
            if value in markers:
                require(value not in matched, "Duplicate cycle marker")
                matched[value] = cycle
        name = next((name for name, (lo, hi) in ranges.items() if lo <= pc < hi), None)
        if active is not None and active["helper"] != name:
            active["end"] = cycle
            spans.append(active)
            active = None
        if name and active is None:
            active = dict(helper=name, begin=cycle, retired=0, opcodes=Counter())
        if active:
            active["retired"] += 1
            active["opcodes"][f"{insn:08x}"] += 1
        if set(matched) == set(markers):
            break
    require(active is None and set(matched) == set(markers), "Incomplete spans/cycle markers")
    require(len({matched[v] - v for v in matched}) == 1, "Nonconstant cycle-domain offset")
    return spans, matched


def analyze(evidence, build):
    report = json.loads((evidence / "result.json").read_text())
    require(report["state"] == "PASS" and report["independent_protocol_checked"] and
            report["post_pins_match"], "Not accepted, independently checked evidence")
    meta = json.loads((build / "build.json").read_text())
    require(report["software_sha256"] == meta["elf_sha256"], "Software identity mismatch")
    paths = {"log": evidence / "work/run.vcs.log", "commit": evidence / "work/commit.csv",
             "vector": evidence / "work/vector_trace.csv", "disassembly": build / "disassembly.log"}
    digests = {}
    for name, path in paths.items():
        expected = (meta if name == "disassembly" else report)["artifacts"].get(str(path))
        digests[str(path)] = sha(path)
        require(expected == digests[str(path)], "Evidence hash mismatch: " + str(path))
    trials = trials_from_log(paths["log"].read_text())
    markers = {r[key] for r in trials for key in ("begin", "returned", "end")}
    ranges = helper_ranges(paths["disassembly"].read_text())
    with paths["commit"].open() as stream:
        spans, matched = retirement_spans(csv.DictReader(stream), ranges, markers)
    offset = next(matched[v] - v for v in matched)
    results = []
    for trial in trials:
        begin, end = matched[trial["begin"]], matched[trial["end"]]
        selected = [s for s in spans if begin <= s["begin"] < end]
        require(all(s["end"] <= end for s in selected), "Helper crosses trial boundary")
        if trial["arm"]:
            require([s["helper"] for s in selected] == list(HELPERS) * 3,
                    "Expected QK/PV for three complete/partial tiles")
        else:
            require(not selected, "Paired helper in generic trial")
        row = dict(trial=trial["trial"], arm=trial["arm"], trace_begin=begin, trace_end=end,
                   full_call_cycles=end-begin, helpers=selected)
        row["helper_retirement_span_cycles"] = dict(Counter({
            name: sum(s["end"] - s["begin"] for s in selected if s["helper"] == name)
            for name in HELPERS}))
        results.append(row)
    return dict(schema="resident-rvv-attribution-v1", state="ACCEPTED_TRACE_ANALYZED",
                no_new_rtl_execution=True, fpu_utilization_measured=False,
                trace_minus_rdcycle=offset, source_artifacts=digests, trials=results,
                warning="Retirement spans are not FU utilization or an additive stall breakdown")


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
