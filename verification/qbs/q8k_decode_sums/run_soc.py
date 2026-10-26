#!/usr/bin/env python3
"""Run a sealed Q8_K ABBA pair on an existing VCS SoC image."""
import argparse
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check_soc import check
from run_half_scale_soc import ROOT, atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command



def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("build", "simv", "output"):
        p.add_argument("--"+name, type=Path, required=True)
    p.add_argument("--timeout", type=int, default=7200)
    a = p.parse_args()
    if not 1 <= a.timeout <= 10800: p.error("timeout must be 1..10800 seconds")
    build, simv = a.build.resolve(strict=True), a.simv.resolve(strict=True)
    out = a.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    state = dict(state="PREFLIGHT", pid=os.getpid(), child_pid=None)
    def save(): atomic_json(out/"status.json", state)
    save()
    try:
        report = json.loads((build/"build.json").read_text())
        source_pins = json.loads((build/"manifest.json").read_text())
        elf = build/"q8k_decode_sums_soc"
        if (report["state"] != "BUILT_NOT_EXECUTED" or digest(elf) != report["elf_sha256"] or
            digest(build/"manifest.json") != report["manifest_sha256"] or hashes(map(Path,source_pins)) != source_pins):
            raise ValueError("Build drift")
        pins = hashes([*image_files(simv),*script_files(),Path(__file__),
                       ROOT/"verification/qbs/run_half_scale_soc.py",ROOT/"verification/qbs/run_tile_context_engine.py",
                       Path(__file__).parent/"check_soc.py",elf,build/"build.json",build/"manifest.json",*map(Path,source_pins)])
        atomic_json(out/"manifest.json", pins)
        env = os.environ.copy(); env["ARA_VCS_TIMEOUT_SECONDS"] = str(a.timeout)
        command = ["bash",str(ROOT/"verification/uvm/run_real_dut_case.sh"),str(simv),str(elf),"q8k_decode_sums_soc",str(out/"soc")]
        def started(pid):
            state.update(state="RUNNING",child_pid=pid,command=command); save()
        rc = run_command(command,out/"worker.log",a.timeout+120,env,started)
        state["child_pid"] = None
        if rc: raise RuntimeError(f"VCS/checker returned {rc}")
        log = out/"soc/work/run.vcs.log"
        trials = check(log.read_text(), report['golden_trials'])
        if hashes(map(Path,pins)) != pins: raise ValueError("Execution provenance drift")
        comparisons = []
        for k in (1536,8960):
            original = sum(t['cycles'] for t in trials if t['k']==k and not t['candidate'])
            candidate = sum(t['cycles'] for t in trials if t['k']==k and t['candidate'])
            comparisons.append(dict(k=k,original_cycles=original,candidate_cycles=candidate,
                                    speedup=original/candidate))
        atomic_json(out/'result.json',dict(state='PASS',trials=trials,comparisons=comparisons,
            log_sha256=digest(log),manifest_sha256=digest(out/'manifest.json'),
            scope='Complete captured Decode activation preparation; not projection or model'))
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc)); raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__": main()
