#!/usr/bin/env python3
"""Audit completed probe without replay, then run unchanged SoC neighbors."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys

from qbacc_probe_maintenance import check_probe_with_maintenance
from run_half_scale_soc import ROOT,atomic_json,check_result,digest,hashes,image_files,now
from run_qbacc_soc import check_compile_log
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--probe-run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();prior=args.probe_run.resolve(strict=True)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=dict(state="AUDITING",pid=os.getpid(),child_pid=None,started=now())
    def save():state["updated"]=now();atomic_json(out/"status.json",state)
    def started(pid):state["child_pid"]=pid;save()
    def interrupted(signum,_frame):raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    env=dict(os.environ,PYTHONPATH=str(ROOT/"verification"),PYTHONDONTWRITEBYTECODE="1")
    def run(command,name,timeout):
        atomic_json(out/(name+".command.json"),list(map(str,command)))
        try:
            if run_command(list(map(str,command)),out/(name+".log"),timeout,env,started):
                raise RuntimeError(name+" failed")
        finally:state["child_pid"]=None;save()
    save()
    try:
        old=json.loads((prior/"status.json").read_text())
        if old["state"]!="FAIL" or old.get("child_pid") is not None or \
                old.get("error")!="ValueError('Actual sequencer QBACC allocation count')":
            raise ValueError("Only the diagnosed completed trace-classification rejection may be reaudited")
        pins=json.loads((prior/"source-pins.json").read_text())
        if hashes(map(Path,pins))!=pins:raise ValueError("Original probe source/ELF drift")
        simv=Path(old["simv"]);image=json.loads((prior/"image-pins.json").read_text())
        if hashes(image_files(simv))!=image:raise ValueError("Image drift")
        check_compile_log(Path(old["compile_log"]).read_text())
        probe=prior/"qbacc_soc_probe";work=probe/"work"
        check_result(probe/"uvm_result.json",old["cases"]["qbacc_soc_probe"]["elf_sha256"],image)
        result=check_probe_with_maintenance((work/"run.vcs.log").read_text(),work/"vector_trace.csv")
        pins.update(hashes([Path(__file__).resolve(),ROOT/"verification/qbs/qbacc_probe_maintenance.py",
            prior/"status.json",prior/"source-pins.json",prior/"image-pins.json",work/"run.vcs.log",
            work/"vector_trace.csv",probe/"uvm_result.json"]))
        atomic_json(out/"source-pins.json",pins);atomic_json(out/"image-pins.json",image)
        atomic_json(out/"probe-result.json",result)
        state.update(state="NEIGHBORS",simv=str(simv),compile_log=old["compile_log"],
            original_probe_run=str(prior));save()
        run([sys.executable,ROOT/"verification/qbs/run_half_scale_soc.py","--tools-root",
             "/home/wangwy/openproject/ara","--simv",simv,"--l2-mb","16","--elf-dir",prior/"elf",
             "--cases","qbs_akv_handoff_smoke","rv64uv-ara-vfmacc","--timeout","1800",
             "--output",out/"neighbors"],"neighbors",4200)
        neighbors=json.loads((out/"neighbors/status.json").read_text())
        if neighbors["state"]!="passed" or hashes(map(Path,pins))!=pins or hashes(image_files(simv))!=image:
            raise ValueError("Neighbor result or source/image drift")
        state["state"]="PASS"
        atomic_json(out/"result.json",dict(state="PASS",probe=result,neighbors=2,
            original_probe_run=str(prior),original_worker_error=old["error"],
            evidence_sha256=hashes([out/"source-pins.json",out/"image-pins.json",out/"probe-result.json",
                out/"neighbors/status.json"]),scope="Actual optional QBACC SoC plus two unchanged neighbors; no performance claim"))
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__=="__main__":main()
