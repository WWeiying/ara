#!/usr/bin/env python3
"""Read-only byte evidence for archived vector faults; never promotes case status.

Uses pinned parsers, refuses oversized logs, and emits JSON only to stdout.
This is not a replacement for scalar, CSR, vstart, or full-stream checking.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True

PINS = {
    "vector_commit.py": "997ee3fef903892d81e0bf98933ec12a38543997736ab49d4020be727e0d965f",
    "spike_trace.py": "a51b88decd89cffe5fe48e613c759f5d4b73974c82246242ac48940875b467f5",
}
MAX_BYTES = 32 * 1024 * 1024


def bounded_input(path, limit=MAX_BYTES):
    size = path.stat().st_size
    if size > limit:
        raise ValueError(f"Refusing full parse of {size}-byte input: {path}")
    return {"bytes": size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def assess_bytes(actual, expected, unknown):
    mismatches, unresolved = [], []
    for (register, byte), (value, _) in sorted(actual.items()):
        if (value is None or register not in expected or
                (unknown.get(register, 0) >> (8 * byte)) & 0xff):
            unresolved.append([register, byte])
        elif value != (expected[register] >> (8 * byte)) & 0xff:
            mismatches.append([register, byte, value,
                               (expected[register] >> (8 * byte)) & 0xff])
    return {"observed_bytes": len(actual), "mismatches": mismatches,
            "unresolved_bytes": unresolved}


def audit(artifact):
    parser_root = Path(__file__).resolve().parent / "ara_verify"
    for name, expected in PINS.items():
        if hashlib.sha256((parser_root / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Parser pin changed: {name}")
    from ara_verify import vector_commit as vc

    names = ("input.elf", "spike_commit.log", "ara_commit_trace.csv",
             "ara_vector_trace.csv", "commit_comparison.json")
    identities = {name: bounded_input(artifact / name) for name in names}
    comparison = json.loads((artifact / "commit_comparison.json").read_text())
    lanes, vlen, activities = vc._parse_vector_trace(artifact / "ara_vector_trace.csv")
    starts, retires, traps = vc._parse_architecture_mapping(artifact / "ara_commit_trace.csv")
    commits = vc._spike_from_entry(artifact / "spike_commit.log", 0x80000000)
    faults = comparison.get("aligned_vector_faults", [])
    if not faults:
        mismatch = comparison.get("mismatch", {})
        spike = mismatch.get("spike", {})
        if mismatch.get("reason") != "pc_or_instruction" or not spike:
            raise ValueError("No archived fault candidate to inspect")
        faults = [{"index": mismatch["index"], "pc": spike["pc"],
                   "instruction": spike["instruction"]}]
    if len(faults) != 1 or len(traps) != 1:
        raise ValueError("This focused audit requires exactly one fault candidate and trap")
    fault = faults[0]
    index = fault["index"]
    if not isinstance(index, int) or not 0 <= index < len(commits):
        raise ValueError("Invalid fault index")
    arch = next(iter(traps))
    activity = activities[arch]
    commit = commits[index]
    if (commit.pc != int(fault["pc"], 16) or
            commit.instruction != int(fault["instruction"], 16) or
            activity.instruction != commit.instruction):
        raise ValueError("Fault PC/encoding evidence differs")
    arch_retires = vc._map_architecture_retires(starts, retires, traps,
                                               allow_incomplete_tail=True)
    mapping = vc._map_spike_commits(arch_retires, commits,
                                    allow_incomplete_tail=True, stop_spike_index=index)
    by_spike = {i: activities[a] for a, i in mapping.items() if a in activities}
    before, unknown = {}, {}
    for i, prior in enumerate(commits[:index]):
        previous = dict(before)
        before.update(prior.vector_writes)
        if i in by_spike:
            vc._advance_unknown_state(unknown, by_spike[i], prior, previous, vlen)
    after = dict(before)
    after.update(commit.vector_writes)
    actual = vc._architectural_bytes(activity.writes, lanes, vlen)
    return {
        "scope": "BYTE_EVIDENCE_ONLY_NOT_CASE_PASS",
        "artifact": str(artifact.resolve()), "input_identities": identities,
        "parser_pins": PINS, "arch_seq": arch, "fault": fault,
        "allocations": activity.allocations, "completions": activity.completions,
        "sources": sorted({write.source for write in activity.writes}),
        "accepted_byte_events": sum(bin(write.be & 0xff).count("1")
                                    for write in activity.writes),
        "pre_state": assess_bytes(actual, before, unknown),
        "post_state_conservative": assess_bytes(actual, after, unknown),
        "spike_vstart_before": commit.vector_vstart,
        "spike_csr_writes": {hex(k): hex(v) for k, v in commit.csr_writes.items()},
        "spike_memory_accesses": [[hex(a), None if v is None else hex(v)]
                                  for a, v in commit.memory_accesses],
        "remaining_requirements": [
            "Validate trap cause, mtval, mepc and architectural vstart on both sides",
            "Validate every required partial write and all inactive/preserved bytes",
            "Validate intermediate/duplicate writes and unknown-state provenance",
            "Re-align and strictly check the complete subsequent scalar/vector stream",
        ],
        "historical_status_modified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.artifact), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
