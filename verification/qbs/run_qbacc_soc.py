#!/usr/bin/env python3
"""Build optional QBACC SoC and run strict source/CSR/padding plus RVV gates.

This worker must be owned directly by its transient systemd service. It never
repairs sources or retries a failed case. The engine gate is not a substitute
for this real dispatcher/Lane/StA/VRF integration check.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sys

from run_half_scale_soc import (ROOT, atomic_json, build_command, check_result,
    digest, hashes, image_files, now, script_files)
from run_tile_context_engine import run_command


def check_probe(log, trace):
    markers = [line for line in log.splitlines() if line.startswith("QBACC_")]
    if markers != ["QBACC_SOC_PASS cases=13 computed=12 validation_faults=1 "
                   "csr_preserved=1 tail_policy_checked=1 padding_preserved=1"]:
        raise ValueError("Missing/duplicate/failed software QBACC result")
    expected = [(1,1),(1,1),(3,17),(3,17),(4,32),(4,32),(5,7),(5,7),
                (8,15),(8,15),(8,16),(8,16),(4,0)]
    perf = [dict(re.findall(r"(\w+)=(\d+)", line))
            for line in log.splitlines() if line.startswith("[QBS_PERF]")]
    if len(perf) != len(expected):
        raise ValueError("Wrong actual hardware command count")
    for i, (record, (m,n)) in enumerate(zip(perf, expected), 1):
        # N is unread for descriptor-version failure; only its fault is strict.
        want = dict(seq=i, m=m, success=int(i!=13), fault=int(i==13),
                    validation_fault=int(i==13))
        if i != 13:
            want["n"] = n
        if any(record.get(k) != str(v) for k,v in want.items()):
            raise ValueError("Hardware command geometry/result mismatch: " + str(record))
    starts = [dict(re.findall(r"(\w+)=(\d+)", line))
              for line in log.splitlines() if line.startswith("[QBACC_START]")]
    ends = [dict(re.findall(r"(\w+)=(\d+)", line))
            for line in log.splitlines() if line.startswith("[QBACC_END]")]
    if len(starts) != 13 or len(ends) != 13:
        raise ValueError("Missing source-ownership start/end trace")
    for i,(start,end,(m,_)) in enumerate(zip(starts,ends,expected),1):
        want = dict(seq=i,m=m,vd=8,vl=m*32,sew=2)
        if any(start.get(k)!=str(v) for k,v in want.items()):
            raise ValueError("Source geometry depends on unrelated vset")
        if end != dict(seq=str(i),success=str(int(i!=13)),fault=str(int(i==13))):
            raise ValueError("Ownership termination trace mismatch")
    words = {str(i):0 for i in range(1,14)}
    for line in log.splitlines():
        if line.startswith("[QBACC_SEED]"):
            fields = dict(re.findall(r"(\w+)=(\d+)", line))
            if fields.get("seq") not in words or fields.get("fire")!="1111" or \
                    fields.get("owner")!="1" or fields.get("store_valid")!="0000":
                raise ValueError("Lane data leaked to store or non-atomic source consumption")
            words[fields["seq"]] += 1
    if any(words[str(i)] != 4*m for i,(m,_) in enumerate(expected,1)):
        raise ValueError("Not all active/tail source words drained: " + str(words))
    allocations = []
    with trace.open() as stream:
        for record in csv.DictReader(stream):
            word = int(record["insn"],16)
            if record["event"]=="alloc" and word&0x707f==0x5b and word&(1<<28):
                allocations.append(record)
    if len(allocations)!=13:
        raise ValueError("Actual sequencer QBACC allocation count")
    for row,(m,_) in zip(allocations,expected):
        if (row["vd"],row["eew"],row["vl"],row["vstart"]) != ("8","2",str(m*32),"0"):
            raise ValueError("Sequencer allocation geometry mismatch")
    return dict(state="PASS", commands=13, computed=12, validation_faults=1,
        source_words_per_lane=sum(words.values()), csr_preserved=True,
        padding_preserved=True, existing_narrow_zero_and_wide_preserve_policy=True,
        scope="Actual optional ISA/dispatcher/Lane/StA/QBS/VRF, not performance")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe-build",type=Path,required=True)
    p.add_argument("--neighbors",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--tools-root",type=Path,default=Path("/home/wangwy/openproject/ara"))
    p.add_argument("--simv",type=Path,help="Reuse a complete source-matching optional QBACC image")
    args=p.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=dict(state="PREPARING",pid=os.getpid(),child_pid=None,started=now(),cases={})
    def save():state["updated"]=now();atomic_json(out/"status.json",state)
    def started(pid):state["child_pid"]=pid;save()
    env=dict(os.environ,PYTHONPATH=str(ROOT/"verification"),PYTHONDONTWRITEBYTECODE="1",
             ARA_VCS_CODE_COVERAGE="0",ARA_VCS_TIMEOUT_SECONDS="1800")
    for key in ("MAKEFLAGS","MFLAGS","MAKEOVERRIDES"):env.pop(key,None)
    def run(command,log,timeout):
        atomic_json(log.with_suffix(".command.json"),list(map(str,command)))
        try:
            code=run_command(list(map(str,command)),log,timeout,env,started)
            if code:raise RuntimeError(f"{log.name} exited {code}")
        finally:state["child_pid"]=None;save()
    def interrupted(signum,_frame):raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    save()
    try:
        report_path=args.probe_build.resolve(strict=True)/"build.json"
        report=json.loads(report_path.read_text());probe=Path(report["elf"])
        if report["disassembly_checks"]!="PASS" or digest(probe)!=report["elf_sha256"]:
            raise ValueError("Probe build receipt/ELF invalid")
        if hashes(map(Path,report["input_hashes"]))!=report["input_hashes"]:
            raise ValueError("Probe build sources changed")
        rtl=[*ROOT.glob("hardware/src/**/*.sv"),*ROOT.glob("hardware/include/**/*.sv"),
             *ROOT.glob("hardware/include/**/*.svh")]
        pins=hashes([*rtl,*script_files(),ROOT/"hardware/Makefile",ROOT/"Bender.yml",
            ROOT/"verification/qbs/run_tile_context_engine.py",
            Path(__file__).resolve(),report_path,*map(Path,report["input_hashes"])])
        elfs={"qbacc_soc_probe":probe}
        for name in ("qbs_akv_handoff_smoke","rv64uv-ara-vfmacc"):
            elfs[name]=args.neighbors.resolve(strict=True)/name
        frozen=out/"elf";frozen.mkdir()
        for name,source in elfs.items():
            sha=digest(source);target=frozen/name;shutil.copyfile(source,target);target.chmod(0o444)
            if digest(target)!=sha or digest(source)!=sha:raise ValueError("ELF copy drift")
            pins[str(target)]=sha;state["cases"][name]=dict(state="PENDING",elf_sha256=sha)
        atomic_json(out/"source-pins.json",pins)
        if args.simv:
            simv=args.simv.resolve(strict=True)
        else:
            state["state"]="BUILDING";save()
            command=build_command(args.tools_root.resolve(strict=True),out/"build",16)
            command.append("REAL_UVM_QBS_VRF_CONTINUATION=1")
            run(command,out/"build.log",7200)
            simv=out/"build/sim/simv"
        image=hashes(image_files(simv));atomic_json(out/"image-pins.json",image)
        config=dict(line.split("=",1) for line in (simv.parent/"simulator.conf").read_text().splitlines() if "=" in line)
        if config.get("qbs_vrf_continuation")!="1" or config.get("sim_l2_mb")!="16":
            raise ValueError("Optional feature or memory configuration mismatch")
        def gate(label):
            if hashes(map(Path,pins))!=pins or hashes(image_files(simv))!=image:
                raise ValueError("Sources/helper/ELF/image drift")
            run([sys.executable,"-m","ara_verify.vcs_source_manifest","--output",
                simv.parent/"vcs_source_manifest.json","--check"],out/f"manifest-{label}.log",300)
        gate("ready")
        for name in elfs:
            entry=state["cases"][name];entry["state"]="RUNNING"
            state.update(state="RUNNING",active_case=name);save()
            if name=="qbacc_soc_probe":
                case=out/name;work=case/"work";work.mkdir(parents=True)
                trace=work/"vector_trace.csv";log=work/"run.vcs.log"
                run([simv,"-no_save","-l",log,"+PRELOAD="+str(frozen/name),
                     "+TESTCASE="+name,"+NO_FSDB","+NO_INSTR_TRACE","+QBS_PERF","+QBACC_TRACE",
                     "+VECTOR_TRACE="+str(trace),"+COMMIT_TRACE="+str(work/"commit_trace.csv"),
                     "+ARA_CONTRACT_TRACE_LIMIT=100000","+ARA_UVM_TRACE_LIMIT=100000"],
                    work/"console.log",1800)
                run([sys.executable,"-m","ara_verify.uvm_dut","--require-events","--require-backend",
                     "--require-axi","--require-axi-write","--vector-trace",trace,"--log",log,
                     "--simv",simv,"--elf",frozen/name,"--output",case/"uvm_result.json"],
                    work/"checker.log",300)
                result=check_probe(log.read_text(),trace)
                result["evidence_sha256"]=hashes([log,trace,work/"commit_trace.csv",case/"uvm_result.json"])
                atomic_json(case/"result.json",result)
            else:
                run(["bash",ROOT/"verification/uvm/run_real_dut_case.sh",simv,frozen/name,name,out/name],
                    out/f"{name}.log",1920)
            check_result(out/name/"uvm_result.json",entry["elf_sha256"],image)
            gate(name)
            entry.update(state="PASS",result_sha256=digest(out/name/"uvm_result.json"));save()
        state.update(state="PASS",active_case=None)
        atomic_json(out/"result.json",dict(state="PASS",cases=state["cases"],
            scope="Optional QBACC full SoC + two unchanged neighbors; no speedup claim",
            source_pins_sha256=digest(out/"source-pins.json"),image_pins_sha256=digest(out/"image-pins.json")))
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__=="__main__":main()
