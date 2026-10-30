#!/usr/bin/env python3
"""Recheck a completed baseline probe; do not infer an implemented speedup."""
import argparse
import json
from pathlib import Path

from run_refill_overlap_probe import check_log, check_traces, digest, hashes, require


def audit(directory):
    directory = directory.resolve(strict=True)
    state = json.loads((directory / "status.json").read_text())
    require(state.get("state") == "PASS" and state.get("child_pid") is None and
            state.get("simulator_exit_code") == 0, "probe is not completed PASS")
    artifacts = json.loads((directory / "artifact-hashes.json").read_text())
    require(bool(artifacts) and hashes(artifacts) == artifacts, "probe artifacts changed")
    before = json.loads((directory / "pins-before.json").read_text())
    after = json.loads((directory / "pins-after.json").read_text())
    require(bool(before) and before == after == hashes(before), "probe source/image drift")
    work = directory / "work"
    result = check_log((work / "run.vcs.log").read_text())
    with (work / "commit_trace.csv").open(newline="") as commit, \
            (work / "vector_trace.csv").open(newline="") as vector:
        result["trace"] = check_traces(commit, vector)
    require(dict(state="PASS", **result) == json.loads((directory / "result.json").read_text()),
            "probe result differs from independent trace recheck")
    uvm = json.loads((directory / "uvm_result.json").read_text())
    require(uvm.get("status") == "PASS" and uvm.get("issues") == [], "protocol check failed")
    for key, path in (("elf_sha256", work / "input.elf"),
                      ("log_sha256", work / "run.vcs.log"),
                      ("vector_trace_sha256", work / "vector_trace.csv")):
        require(uvm[key] == digest(path), "protocol input mismatch: " + key)
    require(hashes(uvm["sim_image_sha256"]) == uvm["sim_image_sha256"], "protocol image changed")
    require(uvm["backend_counts"]["allocations"] == uvm["backend_counts"]["completions"]
            and uvm["axi_read_counts"]["pending"] == uvm["axi_write_counts"]["pending"] == 0,
            "unfinished backend/AXI transactions")
    return dict(state="PASS", schema_version=1, worker=str(directory), **result,
                artifact_manifest_sha256=digest(directory / "artifact-hashes.json"),
                evidence_sha256=hashes([directory / "status.json", directory / "result.json",
                    directory / "uvm_result.json", directory / "pins-before.json",
                    directory / "pins-after.json", directory / "artifact-hashes.json"]),
                interpretation=[
                    "First presentation is not command acceptance or first AXI read",
                    "Remaining older arithmetic measures an opportunity, not achieved overlap",
                    "The nominal serial mode blocks backend issue, not frontend presentation",
                    "A later overlap implementation must account for pending older requests too",
                    "Both modes use the unchanged image; no implementation speedup is established"],
                scope="Synthetic admission probe, not real Attention or model performance")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.worker)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps(dict(state=result["state"], modes=result["trace"]["modes"])))


if __name__ == "__main__":
    main()
