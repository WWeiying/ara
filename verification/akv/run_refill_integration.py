#!/usr/bin/env python3
"""Build an independent SoC image, then replay the sealed REFILL probe."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"verification/qbs"))
from run_half_scale_soc import atomic_json,digest,hashes,build_command
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--tools-root",type=Path,default=Path("/home/wangwy/openproject/ara"))
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/n for n in ("Bender.yml","hardware/src/ara.sv","hardware/src/ara_system.sv",
        "hardware/src/ara_dispatcher.sv","hardware/src/ara_sequencer.sv",
        "hardware/src/vlsu/akv/akv_refill_order_guard.sv","verification/akv/run_refill_overlap_probe.py",
        "verification/akv/test_refill_overlap_probe.py","verification/qbs/run_half_scale_soc.py",
        "verification/qbs/run_tile_context_engine.py")]+[Path(__file__)]
    pins=hashes(sources);atomic_json(out/"source-pins.json",pins)
    state=dict(state="BUILDING",pid=os.getpid(),child_pid=None,scope="Restricted REFILL versus older FMA; sealed arithmetic/memory probe, not production Attention")
    def save():atomic_json(out/"status.json",state)
    def started(pid):state["child_pid"]=pid;save()
    save()
    try:
        command=build_command(a.tools_root.resolve(strict=True),out/"build",l2_mb=16)
        atomic_json(out/"build-command.json",command)
        if run_command(command,out/"build.log",7200,os.environ.copy(),started):raise RuntimeError("VCS image build failed")
        if hashes(sources)!=pins:raise ValueError("Candidate source drift during build")
        state.update(state="PROBE",child_pid=None);save()
        command=[sys.executable,str(ROOT/"verification/akv/run_refill_overlap_probe.py"),
            "--simv",str(out/"build/sim/simv"),"--output",str(out/"probe"),"--timeout","2700"]
        atomic_json(out/"probe-command.json",command)
        if run_command(command,out/"probe.log",3000,os.environ.copy(),started):raise RuntimeError("REFILL probe failed")
        child=json.loads((out/"probe/status.json").read_text())
        if child["state"]!="PASS" or hashes(sources)!=pins:raise ValueError("Probe acceptance or source drift")
        state.update(state="PASS",probe_result_sha256=digest(out/"probe/result.json"),
            note="Probe functional acceptance only; independently join first payload AR and older FMA completion before claiming overlap")
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__=="__main__":main()
