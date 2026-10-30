#!/usr/bin/env python3
"""After real QBACC SoC acceptance, time equal-work direct/striped matrix ABBA."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import select
import signal
import sys

from run_half_scale_soc import ROOT, atomic_json, check_result, digest, hashes, image_files, now
from run_tile_context_engine import run_command
from run_qbacc_soc import check_compile_log


def check_log(text):
    rows=[]
    for line in text.splitlines():
        if line.startswith("VRF_PANEL_TRIAL"):
            match=re.fullmatch(r"VRF_PANEL_TRIAL trial=(\d+) path=(direct|striped) cycles=(\d+) "
                               r"flags=(\d+) checksum=([0-9a-f]{16})",line)
            if not match:raise ValueError("Malformed timing record")
            rows.append(dict(trial=int(match[1]),path=match[2],cycles=int(match[3]),
                             flags=int(match[4]),checksum=match[5]))
    markers=[line for line in text.splitlines() if line.startswith("VRF_PANEL_RESULT")]
    if (markers!=["VRF_PANEL_RESULT errors=0 m=4 n=64 k=8960 outputs=256 calls=4 commands=40 preparation_timed=0 descriptor_setup_timed=1"] or
        [r["trial"] for r in rows]!=list(range(4)) or
        [r["path"] for r in rows]!=["direct","striped","striped","direct"] or
        any(r["cycles"]<=0 or r["flags"]!=1 for r in rows) or
        len({r["checksum"] for r in rows})!=1):
        raise ValueError("Incomplete timing, work or numerical acceptance")
    perf=[]
    for line in text.splitlines():
        if line.startswith("[QBS_PERF]"):
            if not re.fullmatch(r"\[QBS_PERF\](?: [a-z_]\w*=\d+)+",line):
                raise ValueError("Unknown or malformed hardware counters")
            perf.append({k:int(v) for k,v in re.findall(r"(\w+)=(\d+)",line)})
    if len(perf)!=40 or [r["seq"] for r in perf]!=list(range(1,41)):
        raise ValueError("Missing actual command accounting")
    position=0
    for trial in rows:
        striped=trial["path"]=="striped";count=18 if striped else 2
        group=perf[position:position+count];position+=count
        for r in group:
            if any(r.get(k)!=v for k,v in dict(m=4,n=32,vlen=1024,lanes=4,
                    success=1,fault=0,validation_fault=0,validation_error=0,read_fault=0).items()):
                raise ValueError("QBS command geometry or fault mismatch")
        totals={k:sum(r[k] for r in group) for k in ("payload_bytes","weight_bytes",
            "context_fill_count","context_reuse_count","activation_axi_bytes_saved",
            "read_ranges","ar","r_beats","busy_cycles","commit_groups")}
        want=dict(payload_bytes=511568 if striped else 552192,weight_bytes=470400,
            context_fill_count=9 if striped else 0,context_reuse_count=9 if striped else 0,
            activation_axi_bytes_saved=40880 if striped else 0)
        if any(totals[k]!=v for k,v in want.items()):
            raise ValueError("Matrix bytes/context accounting mismatch: "+str(totals))
        trial["hardware_totals"]=totals
    seeds=[]
    for line in text.splitlines():
        if line.startswith("[QBACC_SEED]"):
            match=re.fullmatch(r"\[QBACC_SEED\] seq=(\d+) fire=1111 owner=1 store_valid=0000",line)
            if not match:raise ValueError("Invalid four-lane seed ownership trace")
            seeds.append(int(match[1]))
    expected_seq=[*range(5,21),*range(23,39)]
    if seeds!=[seq for seq in expected_seq for _ in range(16)]:
        raise ValueError("Wrong QBACC source word count/order")
    sums={mode:sum(r["cycles"] for r in rows if r["path"]==mode) for mode in ("direct","striped")}
    return dict(state="PASS",trials=rows,sums=sums,matrix_speedup=sums["direct"]/sums["striped"],
        cycle_reduction_percent=100*(1-sums["striped"]/sums["direct"]),
        scope="Fixed reference-quantized real-model input, matrix phase only; not production-preparation or model speedup")


def check_trace(path):
    allowed={0x06b5045b,0x06b5085b,0x16b5045b,0x16b5085b}
    allocations=[];result_bytes=0
    with path.open() as stream:
        for row in csv.DictReader(stream):
            word=int(row["insn"],16)
            if word not in allowed:continue
            if row["event"]=="alloc":allocations.append(row)
            elif row["event"]=="write":
                mask=int(row["be"],16)
                if mask!=255:raise ValueError("Incomplete active M4/N32 result bytes")
                result_bytes+=bin(mask).count("1")
    expected=[0x06b5045b,0x06b5085b]
    expected+=([0x06b5045b,0x06b5085b]+[0x16b5045b,0x16b5085b]*8)*2
    expected+=[0x06b5045b,0x06b5085b]
    if [int(r["insn"],16) for r in allocations]!=expected or result_bytes!=20480:
        raise ValueError("Actual command sequence or intermediate-result traffic differs")
    for row in allocations:
        word=int(row["insn"],16)
        if (row["vd"],row["eew"],row["vl"],row["vstart"])!=(str((word>>7)&31),"2","128","0"):
            raise ValueError("Wrong architectural register group")
    return dict(commands=40,seeded_commands=32,result_bytes=result_bytes,seed_bytes=16384)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gate",type=Path,required=True)
    p.add_argument("--build",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();gate=args.gate.resolve(strict=True);build=args.build.resolve(strict=True)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=dict(state="PREPARING",pid=os.getpid(),child_pid=None,started=now())
    def save():state["updated"]=now();atomic_json(out/"status.json",state)
    def started(pid):state["child_pid"]=pid;save()
    def interrupted(signum,_frame):raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    env=dict(os.environ,PYTHONPATH=str(ROOT/"verification"),PYTHONDONTWRITEBYTECODE="1")
    def run(command,log,timeout):
        atomic_json(log.with_suffix(".command.json"),list(map(str,command)))
        try:
            if run_command(list(map(str,command)),log,timeout,env,started):
                raise RuntimeError("Worker failed: "+log.name)
        finally:state["child_pid"]=None;save()
    save()
    try:
        report=json.loads((build/"build.json").read_text())
        pins=json.loads((build/"manifest.json").read_text())
        if report["state"]!="BUILT_NOT_EXECUTED" or digest(build/"manifest.json")!=report["manifest_sha256"]:
            raise ValueError("Invalid build receipt")
        elf=Path(report["elf"])
        if digest(elf)!=report["elf_sha256"] or hashes(map(Path,pins))!=pins:
            raise ValueError("Benchmark build/ELF inputs changed")
        pins.update(hashes([elf,build/"build.json",build/"manifest.json",Path(__file__).resolve(),
            ROOT/"verification/qbs/run_half_scale_soc.py",ROOT/"verification/qbs/run_tile_context_engine.py",
            ROOT/"verification/qbs/run_qbacc_soc.py",ROOT/"verification/uvm/run_real_dut_case.sh",
            *ROOT.glob("verification/ara_verify/*.py")]))
        atomic_json(out/"source-pins.json",pins)
        parent=json.loads((gate/"status.json").read_text())
        if parent["state"] not in ("PASS","FAIL"):
            fd=os.pidfd_open(parent["pid"])
            try:
                command=Path(f'/proc/{parent["pid"]}/cmdline').read_bytes().split(b"\0")
                if not any(str(ROOT/"verification/qbs"/name).encode() in command
                           for name in ("run_qbacc_soc.py","accept_qbacc_soc.py")):
                    raise ValueError("Prerequisite PID changed")
                state.update(state="WAITING",parent_pid=parent["pid"],wait="pidfd process-exit event");save()
                waiter=select.poll();waiter.register(fd,select.POLLIN)
                if not waiter.poll(10800*1000):raise TimeoutError("SoC prerequisite wait expired")
            finally:os.close(fd)
        parent=json.loads((gate/"status.json").read_text())
        if parent["state"]!="PASS" or parent.get("child_pid") is not None:
            raise ValueError("SoC prerequisite failed; do not run performance")
        check_compile_log(Path(parent["compile_log"]).read_text())
        simv=Path(parent["simv"]);image=hashes(image_files(simv))
        if image!=json.loads((gate/"image-pins.json").read_text()):raise ValueError("SoC image drift")
        if hashes(map(Path,pins))!=pins:raise ValueError("Sources changed while queued")
        run([sys.executable,"-m","ara_verify.vcs_source_manifest","--output",
            simv.parent/"vcs_source_manifest.json","--check"],out/"manifest-ready.log",300)
        state["state"]="RUNNING";save();work=out/"work";work.mkdir()
        log=work/"run.vcs.log";trace=work/"vector_trace.csv"
        run([simv,"-no_save","-l",log,"+PRELOAD="+str(elf),"+TESTCASE=qbs_vrf_panel_abba",
             "+NO_FSDB","+NO_INSTR_TRACE","+QBS_PERF","+QBACC_TRACE","+VECTOR_TRACE="+str(trace),
             "+COMMIT_TRACE="+str(work/"commit_trace.csv"),"+ARA_CONTRACT_TRACE_LIMIT=100000",
             "+ARA_UVM_TRACE_LIMIT=100000"],work/"console.log",10800)
        state["state"]="CHECKING";save()
        run([sys.executable,"-m","ara_verify.uvm_dut","--require-events","--require-backend",
             "--require-axi","--require-axi-write","--vector-trace",trace,"--log",log,
             "--simv",simv,"--elf",elf,"--output",work/"uvm_result.json"],work/"checker.log",300)
        check_result(work/"uvm_result.json",report["elf_sha256"],image)
        result=check_log(log.read_text());result["vector_traffic"]=check_trace(trace)
        if hashes(map(Path,pins))!=pins or hashes(image_files(simv))!=image:
            raise ValueError("Execution source/image drift")
        result["evidence_sha256"]=hashes([out/"source-pins.json",log,trace,work/"commit_trace.csv",
            work/"uvm_result.json",gate/"result.json"])
        atomic_json(out/"result.json",result);state["state"]="PASS"
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__=="__main__":main()
