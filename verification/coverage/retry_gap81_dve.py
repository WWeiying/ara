#!/usr/bin/env python3
"""DVE-only retry of independently rechecked gap81; old failures stay sealed."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import recheck_gap81_old_image as old

FAILED = old.OUT/"gap81-offline-rechecked-20261006-01"
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name("test_retry_gap81_dve.py")
require = old.require


def launcher_environment(identity, inherited):
    env = old.tools.controlled_environment(identity,inherited)
    # Check_Environment in the sealed wrapper warns if the caller sets DVE.
    # It derives and exports the same installation from VCS_HOME itself.
    env.pop("DVE",None)
    env["PATH"] = str(Path(identity["roles"]["launcher"]).parent)+":/usr/bin:/bin"
    env.update(DVE_COVERAGE_TIMEOUT="1200",DVE_WAIVERS="off")
    return env


def launch(output, inputs):
    wrapper,xvfb = shutil.which("dve"),shutil.which("xvfb-run")
    require(wrapper is not None and xvfb is not None,"DVE/Xvfb unavailable")
    identity = old.tools.prepare(wrapper,xvfb)
    old.save(output/"dve-tool-identity-before.json",identity)
    env = launcher_environment(identity,os.environ)
    command = ["/bin/bash",str(old.HERE/"run_dve_coverage.sh"),str(output/"combined-dve"),
               "--inputs-file",str(inputs)]
    old.save(output/"dve.command.json",dict(command=command,cwd=str(old.ROOT),timeout_s=1260,
        entry_environment_DVE_unset=True,warning_policy="unchanged fail on every diagnostic",
        controlled_environment={k:env[k] for k in ("VCS_HOME","VCS_TARGET_ARCH","PATH","DVE_COVERAGE_TIMEOUT","DVE_WAIVERS")}))
    observed = None
    with (output/"dve.log").open("x") as log:
        process = subprocess.Popen(command,cwd=old.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        start = old.tools.process_info(process.pid)["starttime"]
        deadline = time.monotonic()+1260
        try:
            while process.poll() is None:
                if observed is None:
                    for entry in Path("/proc").iterdir():
                        if not entry.name.isdigit():
                            continue
                        try:
                            if (entry/"exe").resolve(strict=True) != Path(identity["executable"]):
                                continue
                            observed = old.tools.verify_live_executable(int(entry.name),identity,process.pid,start)
                            old.save(output/"dve-runtime-executable.json",observed)
                            break
                        except (OSError,ValueError):
                            continue
                require(time.monotonic() < deadline,"DVE-only retry timed out")
                time.sleep(0.5)
            require(process.returncode == 0 and observed is not None,"DVE failure or unproven running executable")
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
    old.tools.revalidate(identity)
    old.save(output/"dve-tool-identity-after.json",identity)


def run(output):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == old.OUT.resolve(strict=True),
            "Fresh independent retry output required")
    seal = old.seals.FileSeal()
    failure = seal.read(FAILED/"status.json")
    require(failure["status"] == "FAIL" and failure["reason"] == "ValueError: DVE failed or live executable unproven",
            "Not the qualified failed DVE-only predecessor")
    runtime = seal.read(FAILED/"runtime-audit.json")
    require(runtime["status"] == "PASS" and runtime["command_checks"] == 17
            and runtime["final_checks"] == 24 and runtime["compared_custom_vrf_bytes"] == 512,
            "No corrected runtime PASS")
    # Never promote the predecessor's partial report; only its pinned inputs and raw union are reused.
    seal.pin(old.ORIGINAL/"driver-source-original.py",old.SNAPSHOT_SHA)
    pins = seal.read(old.ORIGINAL/"source-pins.json")
    require(pins[str(old.RUNNER)] == old.SNAPSHOT_SHA,"Original sourcepin differs")
    seal.hashes(pins)
    terminal = old.terminal_record()
    old.eligibility(terminal,seal.read(old.ORIGINAL/"status.json"),old.SNAPSHOT_SHA)
    static = seal.read(old.ORIGINAL/"static-plan.json")
    require(static == old.target.analyze(),"Original static/source/old-image binding differs")
    old.host_admission.preflight(old.PREFLIGHT)
    seal.tree(old.PREFLIGHT)
    proof = seal.read(old.PREFLIGHT/"elf-proof.json")
    elf = seal.pin(proof["elf"],proof["elf_sha256"])
    old.validate_command(seal.read(old.ORIGINAL/"rtl.command.json"),static,elf,old.ORIGINAL)
    seal.tree(old.ORIGINAL)
    actual = old.runtime(old.ORIGINAL/"commit_trace.csv",old.ORIGINAL/"vector_trace.csv",
                         old.ORIGINAL/"run.vcs.log",proof["site"]["pc"])
    require(all(actual[k] == runtime[k] for k in actual),"Corrected runtime no longer matches")
    before = seal.read(old.target.BASELINE/"combined-bits.json")
    seal.hashes(before["input_hashes"])
    baseline = old.baseline_members(before,static["design_vdb"],
        seal.pin(old.target.BASELINE/"combined-inputs.txt").read_text().splitlines(),
        seal.pin(old.target.BASELINE/"combined-dve/inputs.txt").read_text().splitlines())
    expected = [*baseline,str(old.ORIGINAL/"code.vdb")]
    require(len(expected) == len(set(expected)) == 689,"Not exact unique688 report inputs")
    require(seal.pin(FAILED/"combined-inputs.txt").read_text().splitlines() == expected,
            "Predecessor report inputs differ")
    after = seal.read(FAILED/"combined-bits.json")
    require(after["tests"] == expected[1:] and after["design"] == before["design"],"Raw union membership differs")
    require(all(after["input_hashes"].get(p) == h for p,h in before["input_hashes"].items()),"Historical bitmap pins changed")
    seal.hashes({p:h for p,h in after["input_hashes"].items() if p not in before["input_hashes"]})
    oldrow = before["metrics"]["cond"][old.target.SCOPE]
    newrow = after["metrics"]["cond"][old.target.SCOPE]
    require(oldrow["width"] == newrow["width"] == 5914 and
            str(oldrow["checksum"]) == str(newrow["checksum"]) == "2250470448"
            and old.target.bit(oldrow,400) == "0" and old.target.bit(newrow,400) == "1","No proven target gain")
    delta = seal.read(FAILED/"raw-bitmap-delta.json")
    require(delta == old.bitmaps.delta(before,after),"Raw delta differs")
    code = {str(p):old.target.sha(p) for p in (SCRIPT,TEST,old.SCRIPT,old.TEST,
        Path(old.tools.__file__),old.HERE/"run_dve_coverage.sh",old.HERE/"export_dve_coverage.tcl")}
    seal.hashes(code)
    output.mkdir()
    try:
        for name,value in (("runtime-audit.json",runtime),("combined-bits.json",after),("raw-bitmap-delta.json",delta)):
            old.save(output/name,value)
            seal.pin(output/name)
        inputs = output/"combined-inputs.txt"
        with inputs.open("x") as stream:
            stream.write("\n".join(expected)+"\n")
        seal.pin(inputs)
        old.save(output/"provenance.json",dict(predecessor=str(FAILED),predecessor_status=failure,
            prior_partial_report_used=False,vcs_rerun=False,current_retry_sourcepins=code))
        print(json.dumps(dict(phase="DVE_ONLY_STARTING",tests=688,output=str(output))),flush=True)
        launch(output,inputs)
        old.validate_dve(seal,output/"combined-dve",expected)
        seal.finish()
        old.save(output/"evidence-pins.json",dict(files=seal.files,current_retry_sourcepins=code))
        status = dict(status="COMPLETE",coverage_status="COMPLETE",new_passed=1,aggregate_passed=688,
            target_hit=True,target_raw_index=400,target_before="0",target_after="1",raw_delta=delta["metrics"],
            image=static["simv"],original_status_preserved=True,vcs_rerun=False,new_waivers_applied=False,
            historical_prefix_current_checker_revalidated=False,aggregate_admitted=False)
        old.save(output/"status.json",status)
        return status
    except Exception as error:
        old.save(output/"status.json",dict(status="FAIL",coverage_status="INCOMPLETE",reason=f"{type(error).__name__}: {error}",
            original_status_preserved=True,vcs_rerun=False,aggregate_admitted=False))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    print(json.dumps(run(parser.parse_args().output),indent=2),flush=True)
