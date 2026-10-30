#!/usr/bin/env python3
"""Recheck frozen RTL preparation evidence and archive its bounded claim."""
import argparse
import json
from pathlib import Path

from run_half_scale_soc import digest, hashes
from run_m4_prepare_soc import check_result


def audit(worker):
    worker = worker.resolve(strict=True)
    status = json.loads((worker / "status.json").read_text())
    result = json.loads((worker / "result.json").read_text())
    uvm = json.loads((worker / "soc/uvm_result.json").read_text())
    pins = json.loads((worker / "manifest.json").read_text())
    if status["state"] != "PASS" or result["state"] != "PASS":
        raise ValueError("Worker did not finish successfully")
    if uvm["status"] != "PASS" or uvm["issues"]:
        raise ValueError("Protocol check failed")
    if hashes(map(Path, pins)) != pins:
        raise ValueError("Pinned source/image/input changed")
    log = worker / "soc/work/run.vcs.log"
    log_hash = digest(log)
    if result["log_sha256"] != log_hash or uvm["log_sha256"] != log_hash:
        raise ValueError("Checker does not describe this log")
    trials = check_result(log.read_text())
    if trials != result["trials"]:
        raise ValueError("Recorded trials differ from log")
    generic = sum(t["cycles"] for t in trials if t["path"] == "generic")
    vector = sum(t["cycles"] for t in trials if t["path"] == "vector")
    if (generic != result["generic_sum_cycles"] or
            vector != result["vector_sum_cycles"]):
        raise ValueError("Recorded cycle sums differ")
    return dict(schema_version=1, state="PASS", worker=str(worker),
                scope="Real Qwen Q8_0 M4/K896 preparation only, not whole projection/model",
                oracle="Independent Linux GGML generic packed bytes and FP state",
                trials=trials, generic_sum_cycles=generic, vector_sum_cycles=vector,
                preparation_speedup=generic / vector,
                preparation_cycle_reduction_percent=100 * (generic - vector) / generic,
                elf_sha256=uvm["elf_sha256"], simv_sha256=uvm["simv_sha256"],
                evidence_sha256=hashes(worker / name for name in (
                    "manifest.json", "status.json", "result.json",
                    "soc/uvm_result.json", "soc/work/run.vcs.log")),
                limitations=["Two ABBA observations per path, one real capture",
                             "Production GGML selection is not changed by this test",
                             "No Q8_K fused-preparation or whole-model timing claim"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    result = audit(args.worker)
    with args.output.open("x") as target:
        json.dump(result, target, indent=2, sort_keys=True)
        target.write("\n")
    print(json.dumps({key: result[key] for key in (
        "state", "generic_sum_cycles", "vector_sum_cycles", "preparation_speedup")}))


if __name__ == "__main__":
    main()
