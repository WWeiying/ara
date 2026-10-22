#!/usr/bin/env python3
"""Bounded single-PASS-VDB GUI summary inspection, never processor simulation."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import apply_lzc_historical as a

SCRIPT = Path(__file__).resolve()
HOOK = SCRIPT.with_suffix(".tcl")
BASE = a.OUT/"lzc-historical-689-20261006-01"
SAMPLE = a.OUT/"gap83-midmant-old-image-20261006-01/code.vdb"


def run(output):
    output = output.absolute()
    a.require(not output.exists() and output.parent == a.OUT,"Fresh diagnostic directory required")
    seal = a.seals.FileSeal()
    m = seal.read(BASE/"manifest.json","bb4bfae5bac62dcb4d08e4407b3c349204a288245ddb1a3a5bc893d7532de6f8")
    state = seal.read(a.OUT/"gap83-offline-admitted-690-20261006-02/status.json")
    a.require(state.get("status") == "PASS_RAW_UNION_HISTORICAL_ONLY" and state.get("new_passed") == 1
              and state.get("aggregate_passed") == 690 and state.get("rtl_changed") is False,"Sample sidecar not accepted")
    listing = seal.pin(a.OUT/"gap83-offline-admitted-690-20261006-02/combined-inputs.txt").read_text().splitlines()
    a.require(listing == [*m["inputs"],str(SAMPLE)],"Not exact historical689 plus sample")
    for p in (SCRIPT,HOOK,a.TCL,a.HERE/"export_dve_coverage.tcl"):seal.pin(p)
    seal.pin(a.TCL,m["sourcepins"][str(a.TCL)])
    seal.tree(SAMPLE)
    output.mkdir()
    for name in ("groups.tcl","capture-helpers.tcl","points.el"):
        seal.pin(BASE/name,m["evidence_sha256"][str(BASE/name)])
        shutil.copyfile(BASE/name,output/name)
        seal.pin(output/name)
    (output/"inputs.txt").write_text(m["inputs"][0]+"\n"+str(SAMPLE)+"\n")
    seal.pin(output/"inputs.txt")
    tools = a.environment.old.tools
    identity = tools.prepare(shutil.which("dve"),shutil.which("xvfb-run"))
    a.save(output/"tool-identity-before.json",identity)
    env = a.environment.launcher_environment(identity,os.environ)
    env.update(DVE_COVERAGE_OUTPUT=str(output),DVE_REVIEWED_WAIVERS=str(HOOK),LZC_FROZEN_HOOK=str(a.TCL))
    command = tools.launch_command(identity,a.HERE/"export_dve_coverage.tcl")
    a.save(output/"command.json",dict(command=command,cwd=str(output),timeout_s=300,
        sourcepins=seal.files,sample_tests=1,historical_aggregate=False,diagnostic_only=True))
    observed = None
    with (output/"launcher.log").open("x") as stream:
        process = subprocess.Popen(command,cwd=output,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
        start = tools.process_info(process.pid)["starttime"]
        deadline = time.monotonic()+300
        try:
            while process.poll() is None:
                if observed is None:
                    for entry in Path("/proc").iterdir():
                        if not entry.name.isdigit():continue
                        try:
                            if (entry/"exe").resolve(strict=True) != Path(identity["executable"]):continue
                            observed = tools.verify_live_executable(int(entry.name),identity,process.pid,start)
                            a.save(output/"runtime-executable.json",observed)
                            break
                        except (ValueError,OSError):continue
                a.require(time.monotonic() < deadline,"Bounded diagnostic timeout")
                time.sleep(0.5)
            a.require(process.returncode == 0 and observed is not None,"Diagnostic process failed/unproven")
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
    log = (output/"DVEfiles/dve_gui.log").read_text()
    a.require(log.splitlines().count("LZC_SINGLE_SUMMARY_INSPECTION_DONE") == 1,"Diagnostic export incomplete")
    a.capture.bind_records(a.capture.parse_records((output/"exclusions.el").read_text()),m["candidates"])
    for name in ("initial-empty.el","final-empty.el","exit-empty.el"):
        a.capture.bind_records(a.capture.parse_records((output/name).read_text()),[])
    tools.revalidate(identity)
    seal.finish()
    a.save(output/"status.json",dict(status="SINGLE_VDB_DIAGNOSTIC_EXPORTED",official_denominator_verified=False,
        sample_tests=1,aggregate_admitted=False,new_RTL_signoff=False,selector_exclusions_applied=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True,type=Path)
    run(p.parse_args().output)
