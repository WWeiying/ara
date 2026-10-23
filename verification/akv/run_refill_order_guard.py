#!/usr/bin/env python3
"""Reproducible isolated VCS test; does not alter a SoC image or Bender list."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[2]
    sources=[root/"hardware/src/vlsu/akv/akv_refill_order_guard.sv",
             root/"verification/akv/akv_refill_order_guard_tb.sv",Path(__file__).resolve()]
    pins={str(s):sha(s) for s in sources}
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def save(name,value):(out/name).write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
    save("manifest.json",pins)
    state=dict(state="BUILDING",scope="Isolated admission/drain guard, not integrated REFILL overlap")
    save("status.json",state)
    commands=[]
    try:
        vcs=shutil.which("vcs")
        if not vcs:raise RuntimeError("Host VCS not found")
        for name,command in (("compile",[vcs,"-full64","-sverilog","-timescale=1ns/1ps",
             "-top","akv_refill_order_guard_tb",str(sources[0]),str(sources[1]),"-o",str(out/"simv")]),
             ("run",[str(out/"simv")])):
            commands.append(command);save("commands.json",commands)
            state["state"]="BUILDING" if name=="compile" else "RUNNING";save("status.json",state)
            with (out/(name+".log")).open("x") as log:
                subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
        text=(out/"run.log").read_text()
        if re.findall(r"^AKV_REFILL_GUARD_PASS checks=(\d+)\s*$",text,re.M)!=["4104"]:
            raise ValueError("Missing/excess check records")
        if re.search(r"\b(?:Fatal|Error|Assertion failed)\b",text,re.I):raise ValueError("Simulator failure")
        if {str(s):sha(s) for s in sources}!=pins:raise ValueError("Source drift")
        state.update(state="PASS",checks=4104,log_sha256=sha(out/"run.log"),simv_sha256=sha(out/"simv"))
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc));raise
    finally:save("status.json",state)


if __name__ == "__main__":main()
