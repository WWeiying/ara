#!/usr/bin/env python3
"""Run a sealed Q8_K ABBA pair on an existing VCS SoC image."""
import argparse
import json
import os
from pathlib import Path
import re
from run_half_scale_soc import ROOT, atomic_json, digest, hashes, image_files, script_files
from run_tile_context_engine import run_command


def check_result(text):
    rows = re.findall(r"^Q8K_SOC trial=(\d+) path=(generic|vector) cycles=(\d+) flags=(\d+) used=(\d+)\s*$", text, re.M)
    if len(rows) != 4:
        raise ValueError("Missing/duplicate trials")
    trials = []
    for i, (index, path, cycles, flags, used) in enumerate(rows):
        vector = i in (1, 2)
        if (int(index) != i or path != ("vector" if vector else "generic") or
                int(used) != int(vector) or int(cycles) <= 0 or not 0 <= int(flags) <= 31):
            raise ValueError("Invalid ABBA record")
        trials.append(dict(trial=i, path=path, cycles=int(cycles), fcsr=int(flags)))
    if len({t["fcsr"] for t in trials}) != 1:
        raise ValueError("FP state mismatch")
    lines = [line.strip() for line in text.splitlines() if "Q8K_SOC_RESULT" in line]
    if lines != ["Q8K_SOC_RESULT errors=0 bytes=7008 inputs=6144 k=1536 calls=4 golden=linux_ggml"]:
        raise ValueError("Missing/failed golden byte or CSR checks")
    return trials


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
        elf = build/"qbs_q8k_prepare_soc"
        if (report["state"] != "BUILT_NOT_EXECUTED" or digest(elf) != report["elf_sha256"] or
            digest(build/"manifest.json") != report["manifest_sha256"] or hashes(map(Path,source_pins)) != source_pins):
            raise ValueError("Build drift")
        pins = hashes([*image_files(simv),*script_files(),Path(__file__),
                       ROOT/"verification/qbs/run_half_scale_soc.py",ROOT/"verification/qbs/run_tile_context_engine.py",
                       elf,build/"build.json",build/"manifest.json",*map(Path,source_pins)])
        atomic_json(out/"manifest.json", pins)
        env = os.environ.copy(); env["ARA_VCS_TIMEOUT_SECONDS"] = str(a.timeout)
        command = ["bash",str(ROOT/"verification/uvm/run_real_dut_case.sh"),str(simv),str(elf),"qbs_q8k_prepare_soc",str(out/"soc")]
        def started(pid):
            state.update(state="RUNNING",child_pid=pid,command=command); save()
        rc = run_command(command,out/"worker.log",a.timeout+120,env,started)
        state["child_pid"] = None
        if rc: raise RuntimeError(f"VCS/checker returned {rc}")
        log = out/"soc/work/run.vcs.log"
        trials = check_result(log.read_text())
        if hashes(map(Path,pins)) != pins: raise ValueError("Execution provenance drift")
        generic = sum(t["cycles"] for t in trials if t["path"] == "generic")
        vector = sum(t["cycles"] for t in trials if t["path"] == "vector")
        atomic_json(out/"result.json",dict(state="PASS",trials=trials,generic_sum_cycles=generic,
            vector_sum_cycles=vector,preparation_speedup=generic/vector,log_sha256=digest(log),
            scope="Real M4/K1536 preparation ABBA including preflight, not full projection/model"))
        state["state"] = "PASS"
    except BaseException as exc:
        state.update(state="FAIL",error=repr(exc)); raise
    finally:
        state["child_pid"] = None
        save()


if __name__ == "__main__": main()
