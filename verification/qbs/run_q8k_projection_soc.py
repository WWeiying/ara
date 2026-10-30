#!/usr/bin/env python3
"""Measure exact paired preparation within a real full QBS projection."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
from run_half_scale_soc import ROOT, atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command


def check_result(text):
    rows=re.findall(r"^Q8K_PROJECTION trial=(\d+) path=(generic|vector) prep=(\d+) matmul=(\d+) total=(\d+) flags=(\d+) checksum=([0-9a-f]{16})\s*$",text,re.M)
    if len(rows)!=4:raise ValueError("Missing or duplicate trials")
    result=[]
    for i,(index,path,prep,matmul,total,flags,checksum) in enumerate(rows):
        if (int(index)!=i or path!=("vector" if i in (1,2) else "generic") or
            min(int(prep),int(matmul))<=0 or int(prep)+int(matmul)!=int(total) or not 0<=int(flags)<=31):
            raise ValueError("Invalid ABBA/phase record")
        result.append(dict(trial=i,path=path,prep_cycles=int(prep),matmul_cycles=int(matmul),total_cycles=int(total),fcsr=int(flags),checksum=checksum))
    if len({(r["fcsr"],r["checksum"]) for r in result})!=1:raise ValueError("Output or FP status differs")
    lines=[line.strip() for line in text.splitlines() if "Q8K_PROJECTION_RESULT" in line]
    if lines!=["Q8K_PROJECTION_RESULT errors=0 m=4 n=1536 k=1536 outputs=6144 calls=4 commands=192 golden=independent"]:
        raise ValueError("Failed/missing independent oracle check")
    return result


def check_trace(path):
    allocations=set(); writes={}
    with path.open(newline="") as stream:
        reader=csv.DictReader(stream)
        if not {"event","insn","arch_seq","vl","vd","eew","be"}.issubset(reader.fieldnames or []):
            raise ValueError("Incomplete trace schema")
        for row in reader:
            if row["event"] not in ("alloc","write"):continue
            insn=int(row["insn"],16)
            if insn & 127 != 0x5b:continue
            if insn!=0x06b5045b:raise ValueError("Unexpected custom instruction")
            sequence=int(row["arch_seq"])
            if row["event"]=="alloc":
                if sequence in allocations or (int(row["vl"]),int(row["vd"]),int(row["eew"]))!=(128,8,2):
                    raise ValueError("Duplicate or malformed QBS allocation")
                allocations.add(sequence)
            else:
                if sequence not in allocations:raise ValueError("Write without QBS allocation")
                mask=int(row["be"],16)
                if not 0<=mask<=255:raise ValueError("Invalid write byte enable")
                writes[sequence]=writes.get(sequence,0)+bin(mask).count("1")
    if len(allocations)!=192 or set(writes)!=allocations or any(n!=512 for n in writes.values()):
        raise ValueError("Incomplete QBS command or result write coverage")
    return dict(commands=192,result_bytes=sum(writes.values()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("build","simv","output"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--timeout",type=int,default=10800)
    a=p.parse_args()
    if not 1<=a.timeout<=10800:p.error("timeout must be 1..10800 seconds")
    build,simv=a.build.resolve(strict=True),a.simv.resolve(strict=True)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=dict(state="PREFLIGHT",pid=os.getpid(),child_pid=None)
    def save():atomic_json(out/"status.json",state)
    save()
    try:
        report=json.loads((build/"build.json").read_text());inherited=json.loads((build/"manifest.json").read_text())
        elf=build/"qbs_q8k_projection_soc"
        if (report["state"]!="BUILT_NOT_EXECUTED" or digest(elf)!=report["elf_sha256"] or
            digest(build/"manifest.json")!=report["manifest_sha256"] or hashes(map(Path,inherited))!=inherited):
            raise ValueError("Build identity drift")
        pins=hashes([*image_files(simv),*script_files(),Path(__file__),ROOT/"verification/qbs/run_half_scale_soc.py",
            ROOT/"verification/qbs/run_tile_context_engine.py",elf,build/"manifest.json",build/"build.json",*map(Path,inherited)])
        atomic_json(out/"manifest.json",pins)
        env=os.environ.copy();env["ARA_VCS_TIMEOUT_SECONDS"]=str(a.timeout)
        command=["bash",str(ROOT/"verification/uvm/run_real_dut_case.sh"),str(simv),str(elf),"qbs_q8k_projection_soc",str(out/"soc")]
        def started(pid):state.update(state="RUNNING",child_pid=pid,command=command);save()
        rc=run_command(command,out/"worker.log",a.timeout+120,env,started);state["child_pid"]=None
        if rc:raise RuntimeError(f"VCS/checker returned {rc}")
        log=out/"soc/work/run.vcs.log";trace=out/"soc/work/vector_trace.csv"
        trials=check_result(log.read_text());traffic=check_trace(trace)
        uvm=json.loads((out/"soc/uvm_result.json").read_text())
        if uvm["status"]!="PASS" or uvm.get("issues"):raise ValueError("UVM boundary checks failed")
        if hashes(map(Path,pins))!=pins:raise ValueError("Execution provenance drift")
        sums={mode:{phase:sum(t[phase+"_cycles"] for t in trials if t["path"]==mode) for phase in ("prep","matmul","total")} for mode in ("generic","vector")}
        atomic_json(out/"result.json",dict(state="PASS",trials=trials,sums=sums,traffic=traffic,
            full_projection_speedup=sums["generic"]["total"]/sums["vector"]["total"],
            preparation_speedup=sums["generic"]["prep"]/sums["vector"]["prep"],
            log_sha256=digest(log),trace_sha256=digest(trace),uvm_sha256=digest(out/"soc/uvm_result.json"),
            scope="Real full M4/N1536/K1536 Q projection, same QBS commands, only preparation differs; not model speedup"))
        state["state"]="PASS"
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__ == "__main__":main()
