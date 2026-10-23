#!/usr/bin/env python3
"""Join accepted REFILL payload reads to older arithmetic completion."""
import argparse
import json
from pathlib import Path
import re

from audit_refill_overlap_probe import audit
from run_refill_overlap_probe import check_log, check_traces, digest, hashes, require


def order_events(text):
    events = {}
    for line in text.splitlines():
        if "[AKV_REFILL_ORDER]" not in line:
            continue
        match = re.fullmatch(r"\[AKV_REFILL_ORDER\] event=(start|first_ar|terminal) "
                             r"cycle=(\d+) ordinal=(\d+) arch=(\d+) vid=(\d+)", line)
        require(match is not None, "Malformed REFILL order record")
        event, cycle, ordinal, arch, vid = match.groups()
        entry = events.setdefault(int(ordinal), {})
        require(event not in entry, "Duplicate REFILL order event")
        entry[event] = dict(cycle=int(cycle), arch=int(arch), vid=int(vid))
    require(set(events) == {1, 2}, "Expected two REFILL lifetimes")
    for entry in events.values():
        require(set(entry) == {"start", "first_ar", "terminal"}, "Missing REFILL event")
        require(len({(v["arch"], v["vid"]) for v in entry.values()}) == 1,
                "REFILL identity changed")
        require(entry["start"]["cycle"] < entry["first_ar"]["cycle"] <
                entry["terminal"]["cycle"], "REFILL event order")
    return events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--baseline-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    candidate, baseline = args.candidate.resolve(), args.baseline.resolve()
    new = audit(candidate)
    old_receipt = json.loads(args.baseline_receipt.read_text())
    require(old_receipt["state"] == "PASS" and
            hashes(old_receipt["evidence_sha256"]) == old_receipt["evidence_sha256"],
            "Archived baseline evidence changed")
    # Old compiled image remains the baseline; do not demand current RTL equal
    # its old source manifest after implementing the candidate.
    old = check_log((baseline / "work/run.vcs.log").read_text())
    with (baseline / "work/commit_trace.csv").open() as commit, \
            (baseline / "work/vector_trace.csv").open() as vector:
        old["trace"] = check_traces(commit, vector)
    require(dict(state="PASS", **old) == json.loads((baseline / "result.json").read_text()),
            "Baseline no longer matches checked raw evidence")
    old_artifacts = json.loads((baseline / "artifact-hashes.json").read_text())
    require(hashes(old_artifacts) == old_artifacts, "Baseline artifact drift")
    require(digest(candidate / "work/input.elf") == digest(baseline / "work/input.elf"),
            "Different software in hardware comparison")
    require({k:v for k,v in old["hardware_totals"].items() if k not in
             ("busy_cycles", "read_outstanding_occ_sum", "read_outstanding_full_cycles")} ==
            {k:v for k,v in new["hardware_totals"].items() if k not in
             ("busy_cycles", "read_outstanding_occ_sum", "read_outstanding_full_cycles")},
            "Work, outcomes or traffic differ")
    events = order_events((candidate / "work/run.vcs.log").read_text())
    modes = {}
    for ordinal, mode in enumerate(("immediate", "serial"), 1):
        row, lifetime = new["trace"]["modes"][mode], events[ordinal]
        require(lifetime["start"]["arch"] == row["refill_arch_order"] and
                lifetime["start"]["cycle"] >= row["refill_backend_first_alloc_cycle"] and
                lifetime["terminal"]["cycle"] <= row["refill_backend_last_done_cycle"],
                "Probe order/backend join mismatch")
        before, after = (r["software_cycles"][mode]["to_drain"] for r in (old, new))
        modes[mode] = dict(baseline_joint_cycles=before, candidate_joint_cycles=after,
            cycle_reduction_percent=100 * (before-after) / before,
            first_payload_ar_cycle=lifetime["first_ar"]["cycle"],
            older_arithmetic_last_done_cycle=row["arithmetic_last_done_cycle"],
            accepted_read_overlap_cycles=max(0, row["arithmetic_last_done_cycle"] -
                                              lifetime["first_ar"]["cycle"]),
            refill_done_cycle=row["refill_backend_last_done_cycle"])
        require(row["refill_backend_last_done_cycle"] >= row["arithmetic_last_done_cycle"],
                "REFILL completion preceded older arithmetic")
    require(modes["immediate"]["accepted_read_overlap_cycles"] > 0 and
            modes["immediate"]["candidate_joint_cycles"] < modes["immediate"]["baseline_joint_cycles"] and
            modes["serial"]["accepted_read_overlap_cycles"] == 0, "Overlap not demonstrated")
    result = dict(state="PASS", scope="Same sealed arithmetic/refill probe, not real Attention speedup",
                  modes=modes, candidate=str(candidate), baseline=str(baseline),
                  evidence_sha256=hashes([candidate / "result.json", candidate / "uvm_result.json",
                      candidate / "work/run.vcs.log", candidate / "work/commit_trace.csv",
                      candidate / "work/vector_trace.csv", args.baseline_receipt]),
                  elf_sha256=digest(candidate / "work/input.elf"))
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(result["modes"]))


if __name__ == "__main__":
    main()
