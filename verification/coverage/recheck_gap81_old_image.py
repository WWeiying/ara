#!/usr/bin/env python3
"""Corrected offline gap81 acceptance and optional raw DVE report, no VCS rerun.

Original FAIL/status/VDB are read-only. Only a fresh independent sidecar is
writable. The historical687 prefix is not current-checker aggregate admission.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT/"verification"))
sys.path.insert(0, str(ROOT/"verification/tests"))
import admit_gap81_m4_phase12 as host_admission
import analyze_gap81_m4_phase12 as target
import old_image_waiver_admission as seals
import coverage_bitmap_delta as bitmaps
import dve_tool_identity as tools
from ara_verify.contract import check_contract_log
from ara_verify.trace import validate_trace
from ara_verify.vector_commit import _parse_vector_trace, _architectural_bytes

OUT = ROOT/"verification/out"
ORIGINAL = OUT/"gap81-old-image-20261006-01"
PREFLIGHT = OUT/"gap81-m4-phase12-preflight-20261006-02"
RUNNER = HERE/"run_gap81_old_image.py"
SNAPSHOT_SHA = "84ed1bad78c6e3a8221bfdfdc7fcd85b5a09058f3ea28317d21fe5e12832ef07"
UNIT = "ara-coverage-gap81-old-image-20261006-01.service"
NAME = "qbs_gap81_m4_phase12"
SCRIPT = Path(__file__).resolve()
TEST = HERE/"test_recheck_gap81_old_image.py"
require = target.require


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def terminal_record():
    command = ["/usr/bin/systemctl", "--user", "show", UNIT, "--no-pager",
               "-p", "Id", "-p", "LoadState", "-p", "ActiveState", "-p", "SubState",
               "-p", "MainPID", "-p", "ExecMainCode", "-p", "ExecMainStatus",
               "-p", "ExecStart", "-p", "WorkingDirectory"]
    result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
    return dict(line.split("=",1) for line in result.stdout.splitlines() if "=" in line)


def eligibility(service, status, source_sha):
    require(source_sha == SNAPSHOT_SHA, "Unreviewed original runner bytes")
    require(service.get("Id") == UNIT and service.get("LoadState") == "loaded"
            and service.get("ActiveState") in ("failed", "inactive")
            and service.get("SubState") in ("failed", "dead") and service.get("MainPID") == "0"
            and service.get("ExecMainCode") == "1"
            and service.get("WorkingDirectory") == str(ROOT), "Original service not proven terminal")
    match = re.search(r"argv\[\]=(.*?) ;", service.get("ExecStart", ""))
    require(match is not None, "Missing original launch identity")
    argv = shlex.split(match[1])
    require(len(argv) == 7 and argv[:2] == ["/usr/bin/python3", "-u"]
            and (ROOT/argv[2]).resolve(strict=True) == RUNNER
            and argv[3] == "--preflight" and (ROOT/argv[4]).resolve(strict=True) == PREFLIGHT
            and argv[5] == "--output" and (ROOT/argv[6]).resolve(strict=True) == ORIGINAL,
            "Foreign service command")
    if status.get("status") == "FAIL":
        require(status.get("reason") == "ValueError: DUT command selfcheck incomplete"
                and status.get("coverage_status") == "INCOMPLETE" and status.get("rtl_changed") is False
                and service.get("ExecMainStatus") == "1", "Not the isolated 18-vs17 audit rejection")
        return "sealed_original_check_true_subprocess_returned_zero_before_runtime_audit"
    require(status.get("status") == status.get("coverage_status") == "COMPLETE"
            and status.get("rtl_changed") is False and service.get("ExecMainStatus") == "0",
            "VCS failure/timeout cannot be recovered")
    return "sealed_original_runner_successfully_exited"


def baseline_members(before, design, first, second):
    expected = [design, *before["tests"]]
    require(len(expected) == 688 and len(set(expected)) == 688, "Not unique historical687 members")
    require(first == second == expected, "Baseline DVE membership/order differs from pinned bitmap")
    return expected


def validate_command(record, static, elf, original):
    expected = [static["simv"], "-l", "run.vcs.log", "+NO_FSDB", "+ntb_random_seed=1",
        "+PRELOAD="+str(elf), "+TESTCASE="+NAME,
        "+COMMIT_TRACE="+str(original/"commit_trace.csv"),
        "+VECTOR_TRACE="+str(original/"vector_trace.csv"), "+QBS_PERF",
        "-cm", "line+cond+fsm+tgl+branch", "-cm_dir", str(original/"code.vdb"), "-cm_name", NAME]
    require(record == dict(command=expected,cwd=str(original),timeout_s=600), "Foreign VCS image/command")


def runtime(commit, vector, log, site, command_checks=17):
    require(type(command_checks) is int and command_checks == 17, "Only corrected DUT17 contract")
    text = log.read_text(errors="replace")
    require(text.splitlines().count(f"GAP81 command=0 checks={command_checks} errors=0") == 1,
            "DUT command selfcheck incomplete")
    require(text.splitlines().count("GAP81 inspected vrf_words=1024 initial_words=1024 source_bytes=3440 csr_words=12") == 1,
            "DUT full-state checks incomplete")
    require(text.splitlines().count("PASSED: qbs_gap81_m4_phase12 checks=24 errors=0") == 1,
            "DUT final selfcheck incomplete")
    require(text.count("Core Test *** SUCCESS ***") == 1 and
            not re.search(r"Fatal:|Error:|FAILED:|Core Test \*\*\* FAIL|watchdog|UVM_(?:ERROR|FATAL)\s*:\s*[1-9]",text,re.I),
            "Simulator did not complete cleanly")
    require(len(re.findall(r"^\$finish at simulation time\s+\d+\s*$",text,re.M)) == 1,
            "Simulator finish missing/duplicated")
    require(not check_contract_log(log), "Runtime contract violation")
    trace = validate_trace(commit)
    pending, custom, retired = {}, [], []
    with commit.open() as stream:
        for row in csv.DictReader(stream):
            word = int(row["insn"],16)
            if row["event"] == "cvx_req":
                key = int(row["trans_id"])
                require(key not in pending, "Duplicate outstanding transaction")
                pending[key] = word
            elif row["event"] == "cvx_resp":
                key = int(row["trans_id"])
                require(key in pending and not int(row["trap"]), "Orphan/failed response")
                requested = pending.pop(key)
                if requested == 0x06b5045b:
                    # ara_commit_monitor.sv emits no instruction on cvx_resp.
                    require(word == 0, "Unexpected response instruction field")
                    custom.append(requested)
            elif row["event"] == "retire" and word == 0x06b5045b:
                require(not int(row["trap"]), "Faulting QBS retirement")
                retired.append(int(row["pc"],16))
    require(not pending and custom == [0x06b5045b] and retired == [site],
            "Custom request/response/retirement conservation failed")
    lanes,vlen,activities = _parse_vector_trace(vector)
    require((lanes,vlen) == (4,1024), "Wrong vector configuration")
    selected = [a for a in activities.values() if a.instruction == 0x06b5045b]
    require(len(selected) == 1 and selected[0].allocations > 0
            and selected[0].allocations == selected[0].completions, "Custom activity incomplete")
    values = _architectural_bytes(selected[0].writes,lanes,vlen)
    expected = {}
    for context in range(4):
        data = struct.pack("<f",float(256*(context+1)))+bytes(124)
        expected.update({(8+context,i):value for i,value in enumerate(data)})
    require({key:value for key,(value,_) in values.items()} == expected,
            "Independent QBS architectural VRF bytes differ")
    return dict(status="PASS",trace=trace,custom_requests=1,command_checks=17,final_checks=24,
        compared_custom_vrf_bytes=512,full_vrf_words=1024,csr_words=12,source_bytes=3440,
        oracle="pinned independent native host reference, exact custom writeback and DUT full-state selfcheck")


def collect_gain(before, sample):
    after = bitmaps.combine(before,sample)
    old = before["metrics"]["cond"][target.SCOPE]
    new = after["metrics"]["cond"][target.SCOPE]
    require(str(old["checksum"]) == str(new["checksum"]) == "2250470448"
            and old["width"] == new["width"] == 5914, "Target shape/checksum differs")
    require(target.bit(old,400) == "0" and target.bit(new,400) == "1", "Target raw400 did not change 0->1")
    return after, bitmaps.delta(before,after)


def run_dve(output, inputs):
    wrapper,xvfb = shutil.which("dve"),shutil.which("xvfb-run")
    require(wrapper is not None and xvfb is not None, "DVE/Xvfb unavailable")
    identity = tools.prepare(wrapper,xvfb)
    save(output/"dve-tool-identity-before.json",identity)
    env = tools.controlled_environment(identity,os.environ)
    env["PATH"] = str(Path(identity["roles"]["launcher"]).parent)+":/usr/bin:/bin"
    env.update(DVE_COVERAGE_TIMEOUT="1200",DVE_WAIVERS="off")
    command = ["/bin/bash",str(HERE/"run_dve_coverage.sh"),str(output/"combined-dve"),
               "--inputs-file",str(inputs)]
    save(output/"dve.command.json",dict(command=command,cwd=str(ROOT),timeout_s=1260,
        controlled_environment={k:env[k] for k in ("VCS_HOME","DVE","VCS_TARGET_ARCH","PATH","DVE_COVERAGE_TIMEOUT","DVE_WAIVERS")}))
    observed = None
    with (output/"dve.log").open("x") as log:
        process = subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        launch_start = tools.process_info(process.pid)["starttime"]
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
                            observed = tools.verify_live_executable(int(entry.name),identity,process.pid,launch_start)
                            save(output/"dve-runtime-executable.json",observed)
                            break
                        except (OSError,ValueError):
                            continue
                require(time.monotonic() < deadline, "DVE timeout")
                time.sleep(0.5)
            require(process.returncode == 0 and observed is not None, "DVE failed or live executable unproven")
        finally:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
    tools.revalidate(identity)
    save(output/"dve-tool-identity-after.json",identity)


def validate_dve(seal, directory, expected):
    require(seal.pin(directory/"inputs.txt").read_text().splitlines() == expected, "DVE used different inputs")
    selected = []
    for vdb in expected[1:]:
        root = Path(vdb)/"snps/coverage/db/testdata"
        names = [p.name for p in root.iterdir() if p.is_dir()]
        require(len(names) == 1, "Ambiguous coverage test identity")
        selected.append(str(Path(vdb).with_suffix("")/names[0]))
    require(seal.pin(directory/"selected_tests.txt").read_text().splitlines() == selected,
            "DVE selected population/order differs")
    require(seal.pin(directory/"diagnostics.txt").read_text() == "", "DVE diagnostics nonempty")
    gui = seal.pin(directory/"DVEfiles/dve_gui.log").read_text(errors="replace")
    require("DVE_COVERAGE_EXPORT_DONE" in gui.splitlines(), "DVE export incomplete")
    require(seal.pin(directory/"summary.csv").stat().st_size > 0
            and not (directory/"summary.csv.partial").exists(), "Partial/empty DVE summary")
    waiver = seal.read(directory/"waiver_status.json")
    require(waiver.get("mode") == "off" and waiver.get("status") == "DISABLED"
            and waiver.get("waived_report") is None, "Unexpected waivers")


def accept(output, with_dve=False):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == OUT.resolve(strict=True), "Fresh independent output required")
    service = terminal_record()
    seal = seals.FileSeal()
    snapshot = seal.pin(ORIGINAL/"driver-source-original.py",SNAPSHOT_SHA)
    pins = seal.read(ORIGINAL/"source-pins.json")
    require(pins.get(str(RUNNER)) == SNAPSHOT_SHA, "Original runner sourcepin differs")
    seal.hashes(pins)
    status = seal.read(ORIGINAL/"status.json")
    exit_proof = eligibility(service,status,target.sha(snapshot))
    host_result = host_admission.preflight(PREFLIGHT)
    seal.tree(PREFLIGHT)
    static = target.analyze()
    require(seal.read(ORIGINAL/"static-plan.json") == static, "Original static preflight plan differs")
    seal.hashes(static["source_hashes"])
    seal.hashes(static["image"])
    proof = seal.read(PREFLIGHT/"elf-proof.json")
    elf = seal.pin(proof["elf"],proof["elf_sha256"])
    validate_command(seal.read(ORIGINAL/"rtl.command.json"),static,elf,ORIGINAL)
    require(seal.read(ORIGINAL/"started.json") == dict(status="RUNNING",image=static["simv"],rtl_changed=False),
            "Foreign startup record")
    seal.tree(ORIGINAL)
    before = seal.read(target.BASELINE/"combined-bits.json")
    seal.hashes(before["input_hashes"])
    first = seal.pin(target.BASELINE/"combined-inputs.txt").read_text().splitlines()
    second = seal.pin(target.BASELINE/"combined-dve/inputs.txt").read_text().splitlines()
    expected = baseline_members(before,static["design_vdb"],first,second)
    new_vdb = str(ORIGINAL/"code.vdb")
    require(new_vdb not in expected, "New VDB is not new")
    names = list((ORIGINAL/"code.vdb/snps/coverage/db/testdata").iterdir())
    require(len(names) == 1 and names[0].name == NAME and names[0].is_dir(), "Wrong VDB test identity")
    result = runtime(ORIGINAL/"commit_trace.csv",ORIGINAL/"vector_trace.csv",ORIGINAL/"run.vcs.log",proof["site"]["pc"])
    require(runtime(ORIGINAL/"commit_trace.csv",ORIGINAL/"vector_trace.csv",ORIGINAL/"console.log",proof["site"]["pc"]) == result,
            "Console/runtime evidence differs")
    code = {str(p):target.sha(p) for p in [SCRIPT,TEST,Path(host_admission.__file__),Path(target.__file__),
        Path(seals.__file__),Path(bitmaps.__file__),Path(tools.__file__),HERE/"run_dve_coverage.sh",
        HERE/"export_dve_coverage.tcl",HERE/"prepare_dve_waivers.py",
        *sorted((ROOT/"verification/ara_verify").glob("*.py"))]}
    seal.hashes(code)
    output.mkdir()
    try:
        save(output/"original-terminal.json",dict(service=service,exit_proof=exit_proof,original_status=status))
        save(output/"runtime-audit.json",dict(result,host_preflight=host_result,old_status_preserved=True,
            new_test_only=True,historical_prefix_current_checker_revalidated=False,aggregate_admitted=False))
        inputs = output/"new-inputs.txt"
        inputs.write_text(static["design_vdb"]+"\n"+new_vdb+"\n")
        seal.pin(inputs)
        sample = bitmaps.collect(inputs)
        seal.hashes(sample["input_hashes"])
        after,delta = collect_gain(before,sample)
        require(after["tests"] == [*before["tests"],new_vdb], "After bitmap population differs")
        save(output/"combined-bits.json",after)
        save(output/"raw-bitmap-delta.json",delta)
        combined = output/"combined-inputs.txt"
        combined.write_text("\n".join([*expected,new_vdb])+"\n")
        seal.pin(combined)
        seal.pin(output/"combined-bits.json")
        seal.pin(output/"raw-bitmap-delta.json")
        if with_dve:
            run_dve(output,combined)
            validate_dve(seal,output/"combined-dve",[*expected,new_vdb])
        host_admission.preflight(PREFLIGHT)
        seal.finish()
        save(output/"evidence-pins.json",dict(files=seal.files,current_checker_sourcepins=code,
            original_source_snapshot_sha256=SNAPSHOT_SHA,original_status_preserved=True))
        final = dict(status="COMPLETE" if with_dve else "OFFLINE_PASS_DVE_PENDING",
            coverage_status="COMPLETE" if with_dve else "PENDING",new_passed=1,aggregate_passed=688,
            target_raw_index=400,target_before="0",target_after="1",target_hit=True,
            original_status_preserved=True,original_vdb=str(ORIGINAL/"code.vdb"),
            historical_prefix_current_checker_revalidated=False,aggregate_admitted=False,
            image=static["simv"],rtl_changed=False,vcs_rerun=False,new_waivers_applied=False)
        save(output/"status.json",final)
        return final
    except Exception as error:
        save(output/"status.json",dict(status="FAIL",coverage_status="INCOMPLETE",reason=f"{type(error).__name__}: {error}",
            original_status_preserved=True,aggregate_admitted=False,vcs_rerun=False))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--dve",action="store_true")
    args = parser.parse_args()
    print(json.dumps(accept(args.output,args.dve),indent=2),flush=True)


if __name__ == "__main__":
    main()
