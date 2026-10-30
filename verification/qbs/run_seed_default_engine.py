#!/usr/bin/env python3
"""Rebuild the real QBS controller and require unchanged default-path cycles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from run_half_scale_soc import ROOT, atomic_json, hashes
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline",type=Path,required=True)
    p.add_argument("--real-vector",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    baseline=args.baseline.resolve(strict=True); real=args.real_vector.resolve(strict=True)
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    old=json.loads((baseline/"status.json").read_text())
    if old["state"]!="PASS": raise ValueError("Baseline did not pass")
    # The baseline's RTL must really be the pre-extension implementation,
    # not an unrelated old image that merely happens to have similar cycles.
    for name in ("qbs_fp_accumulator.sv","qbs_compute_engine.sv","qbs_engine.sv"):
        relative="hardware/src/vlsu/qbs/"+name
        data=subprocess.check_output(["git","show","11a180b5:"+relative],cwd=ROOT)
        if hashlib.sha256(data).hexdigest()!=old["sources_and_inputs"][str(ROOT/relative)]:
            raise ValueError("Pre-extension baseline identity mismatch")
    directory=ROOT/"verification/qbs"
    query=["make","-s","--no-print-directory","-C",str(directory),
           "--eval=print-default-sources:;@printf '%s\\n' $(RTL_SOURCES)","print-default-sources"]
    sources=[Path(x) for x in subprocess.check_output(query,text=True).splitlines()]
    pins=hashes([*sources,Path(__file__),directory/"qbs_engine_tb.sv",directory/"Makefile",
        directory/"run_half_scale_soc.py",directory/"run_tile_context_engine.py",
        baseline/"status.json",real,*ROOT.glob("hardware/deps/common_cells/include/**/*.svh"),
        *ROOT.glob("hardware/deps/axi/include/**/*.svh")])
    atomic_json(out/"manifest.json",pins)
    state=dict(state="BUILDING",pid=os.getpid(),child_pid=None)
    def save(): atomic_json(out/"status.json",state)
    def started(pid): state["child_pid"]=pid; save()
    save()
    try:
        command=["vcs","-full64","-sverilog","-timescale=1ns/1ps","+lint=TFIPC-L",
            "+incdir+"+str(ROOT/"hardware/deps/common_cells/include"),
            "+incdir+"+str(ROOT/"hardware/deps/axi/include"),*map(str,sources),
            str(directory/"qbs_engine_tb.sv"),"-top","qbs_engine_tb","-o",str(out/"simv")]
        atomic_json(out/"build-command.json",command)
        if run_command(command,out/"compile.log",600,os.environ.copy(),started):
            raise RuntimeError("Default QBS engine compile failed")
        state["state"]="RUNNING"; save()
        if run_command([sys.executable,str(directory/"run_tile_context_engine.py"),
            "--image",str(out/"simv"),"--real-vector",str(real),"--output",str(out/"acceptance")],
            out/"acceptance.log",1200,os.environ.copy(),started):
            raise RuntimeError("Default QBS engine regression failed")
        new=json.loads((out/"acceptance/status.json").read_text())
        if new["state"]!="PASS" or set(new["cases"])!=set(old["cases"]):
            raise ValueError("Default QBS cases missing")
        for name in old["cases"]:
            for field in ("direct","contexts","response_gap","vector_sha256"):
                if new["cases"][name][field]!=old["cases"][name][field]:
                    raise ValueError(f"Default QBS numerical/traffic/cycle change: {name}/{field}")
        if hashes(map(Path,pins))!=pins: raise ValueError("Execution input drift")
        state["state"]="PASS"
        atomic_json(out/"result.json",dict(state="PASS",default_cycles_identical=True,
            baseline=str(baseline),scope="Actual QBS engine only; ordinary RVV SoC regression not implied",
            cases=new["cases"],evidence_sha256=hashes([out/"manifest.json",out/"acceptance/status.json",out/"compile.log"])))
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc)); raise
    finally: state["child_pid"]=None; save()


if __name__=="__main__": main()
