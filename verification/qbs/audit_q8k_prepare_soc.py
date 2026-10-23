#!/usr/bin/env python3
"""Independently archive a completed Q8_K preparation ABBA result."""
import argparse
import json
from pathlib import Path
from run_half_scale_soc import ROOT,digest,hashes
from run_q8k_prepare_soc import check_result


def audit(worker):
    worker=worker.resolve(strict=True)
    state=json.loads((worker/"status.json").read_text())
    result=json.loads((worker/"result.json").read_text())
    uvm=json.loads((worker/"soc/uvm_result.json").read_text())
    pins=json.loads((worker/"manifest.json").read_text())
    if state["state"]!="PASS" or result["state"]!="PASS" or uvm["status"]!="PASS" or uvm["issues"]:
        raise ValueError("Incomplete or failed worker/protocol result")
    if hashes(map(Path,pins))!=pins:raise ValueError("Source/input/image drift")
    command=state["command"]
    if len(command)!=6 or command[4]!="qbs_q8k_prepare_soc":raise ValueError("Wrong worker command")
    simv,elf=Path(command[2]),Path(command[3])
    if (pins.get(str(simv))!=uvm["simv_sha256"] or pins.get(str(elf))!=uvm["elf_sha256"] or
        digest(worker/"soc/work/input.elf")!=uvm["elf_sha256"]):raise ValueError("Executed image/ELF mismatch")
    if not uvm["sim_image_sha256"] or any(pins.get(path)!=value for path,value in uvm["sim_image_sha256"].items()):
        raise ValueError("Image library identity mismatch")
    log=worker/"soc/work/run.vcs.log";trace=worker/"soc/work/vector_trace.csv"
    if digest(log)!=result["log_sha256"] or digest(log)!=uvm["log_sha256"] or digest(trace)!=uvm["vector_trace_sha256"]:
        raise ValueError("Log/trace identity mismatch")
    trials=check_result(log.read_text())
    if trials!=result["trials"]:raise ValueError("Recorded trials differ from raw output")
    generic=sum(t["cycles"] for t in trials if t["path"]=="generic")
    vector=sum(t["cycles"] for t in trials if t["path"]=="vector")
    if generic!=result["generic_sum_cycles"] or vector!=result["vector_sum_cycles"]:
        raise ValueError("Cycle sum mismatch")
    contract=uvm["contract_counts"];backend=uvm["backend_counts"]
    if (contract["requests"]!=contract["responses"] or contract["outstanding"] or contract["exceptions"] or contract["protocol_errors"]
        or backend["allocations"]!=backend["completions"] or backend["aborted"]):raise ValueError("Protocol did not drain cleanly")
    variant="integer_vla_preflight" if str(ROOT/"verification/qbs/ggml_q8k_m4_prepare_vla_candidate.h") in pins else "scalar_preflight"
    return dict(state="PASS",worker=str(worker),variant=variant,
        scope="Real M4/K1536 preparation only; not full projection or model speedup",trials=trials,
        generic_sum_cycles=generic,vector_sum_cycles=vector,preparation_speedup=generic/vector,
        preparation_cycle_reduction_percent=100*(generic-vector)/generic,
        contract_counts=contract,backend_counts=backend,elf_sha256=uvm["elf_sha256"],simv_sha256=uvm["simv_sha256"],
        evidence_sha256=hashes(worker/name for name in ("manifest.json","status.json","result.json","soc/uvm_result.json",
            "soc/work/run.vcs.log","soc/work/vector_trace.csv")),
        limitations=["One real capture, two ABBA observations per path", "No production GGML enablement from this gate alone"])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--worker",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();result=audit(a.worker)
    with a.output.open("x") as f:json.dump(result,f,indent=2,sort_keys=True);f.write("\n")
    print(json.dumps({k:result[k] for k in ("state","variant","generic_sum_cycles","vector_sum_cycles","preparation_speedup")}))


if __name__=="__main__":main()
