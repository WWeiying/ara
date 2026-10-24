#!/usr/bin/env python3
"""Wait by pidfd, audit immutable QBACC evidence, then run two neighbor gates.

No source repair, simulator rebuild, repeated probe or status polling. Run the
worker directly under its owning service, in a fresh output directory.
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import sys

from run_half_scale_soc import ROOT, atomic_json, digest, hashes, now
from run_tile_context_engine import run_command


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();source=args.run.resolve(strict=True)
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    state=dict(state="PREPARING",pid=os.getpid(),child_pid=None,started=now())
    def save():state["updated"]=now();atomic_json(out/"status.json",state)
    def started(pid):state["child_pid"]=pid;save()
    env=dict(os.environ,PYTHONPATH=str(ROOT/"verification"),PYTHONDONTWRITEBYTECODE="1")
    def run(command,name,timeout):
        atomic_json(out/(name+".command.json"),list(map(str,command)))
        try:
            if run_command(list(map(str,command)),out/(name+".log"),timeout,env,started):
                raise RuntimeError(name+" failed; do not continue")
        finally:state["child_pid"]=None;save()
    def interrupted(signum,_frame):raise InterruptedError(f"signal {signum}")
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,interrupted)
    save()
    try:
        sources=[Path(__file__).resolve(),*(ROOT/"verification/qbs"/name for name in
            ("audit_qbacc_probe.py","run_qbacc_soc.py","run_half_scale_soc.py",
             "run_tile_context_engine.py"))]
        pins=hashes(sources);atomic_json(out/"helper-pins.json",pins)
        parent=json.loads((source/"status.json").read_text())
        if parent["state"] not in ("PASS","FAIL"):
            pid=parent["pid"]
            try:
                fd=os.pidfd_open(pid)
            except ProcessLookupError:
                parent=json.loads((source/"status.json").read_text())
                if parent["state"] not in ("PASS","FAIL"):
                    raise RuntimeError("Parent missing without terminal evidence")
            else:
                try:
                    command=Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                    if str(ROOT/"verification/qbs/run_qbacc_soc.py").encode() not in command:
                        raise RuntimeError("Parent PID identity mismatch")
                    state.update(state="WAITING",parent_pid=pid,wait="pidfd process-exit event")
                    save();waiter=select.poll();waiter.register(fd,select.POLLIN)
                    if not waiter.poll(10800*1000):
                        raise TimeoutError("Parent did not terminate within bounded wait")
                finally:os.close(fd)
        parent=json.loads((source/"status.json").read_text())
        if parent["state"] not in ("PASS","FAIL") or parent.get("child_pid") is not None:
            raise RuntimeError("Parent evidence is not terminal")
        if hashes(sources)!=pins:raise ValueError("Helper drift while waiting")
        state["state"]="AUDITING";save()
        run([sys.executable,ROOT/"verification/qbs/audit_qbacc_probe.py","--run",source,
             "--output",out/"probe-audit"],"probe-audit",300)
        audit=json.loads((out/"probe-audit/result.json").read_text())
        if audit["state"]!="PASS":raise ValueError("Probe not accepted")
        state["state"]="NEIGHBORS";save()
        run([sys.executable,ROOT/"verification/qbs/run_half_scale_soc.py","--tools-root",
             "/home/wangwy/openproject/ara","--simv",source/"build/sim/simv","--l2-mb","16",
             "--elf-dir",source/"elf","--cases","qbs_akv_handoff_smoke","rv64uv-ara-vfmacc",
             "--timeout","1800","--output",out/"neighbors"],"neighbors",4200)
        neighbors=json.loads((out/"neighbors/status.json").read_text())
        if neighbors["state"]!="passed" or hashes(sources)!=pins:
            raise ValueError("Neighbor acceptance or helper drift")
        state["state"]="PASS"
        atomic_json(out/"result.json",dict(state="PASS",commands=13,computed=12,
            validation_faults=1,neighbors=2,default_enabled=False,
            scope="Actual optional QBACC SoC probe plus ordinary RVV/QBS-AKV neighbors; no performance claim",
            original_run=str(source),probe_audit_sha256=digest(out/"probe-audit/result.json"),
            neighbor_status_sha256=digest(out/"neighbors/status.json"),
            evidence_sha256=hashes([out/"helper-pins.json",out/"probe-audit/result.json",out/"neighbors/status.json"])))
    except BaseException as exc:state.update(state="FAIL",error=repr(exc));raise
    finally:state["child_pid"]=None;save()


if __name__=="__main__":main()
