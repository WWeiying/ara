#!/usr/bin/env python3
"""Exact180 structural exclusions on historical689; no replay or new RTL signoff.

Normal two-state operation only, all real input patterns unconstrained. Reachable
unhit points remain included. Native full-set application does not issue a legacy
receipt or qualify four-state initialization, other images or other exclusions.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import capture_lzc_batch as capture
import retry_gap81_dve as environment

ROOT,OUT,HERE = capture.ROOT,capture.OUT,capture.HERE
BASELINE = OUT/"gap81-dve-only-retry-20261006-01"
COMBINE = OUT/"gap82-combine-complete-baseline-20261006-01"
RAW_UNION = OUT/"gap82-raw-union-689-20261006-01"
BATCH = OUT/"lzc-native-batch-20261006-02"
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix(".tcl")
TEST = HERE/"test_apply_lzc_historical.py"
require = capture.require
seals = capture.admission
bitmaps = seals.bitmaps
STAGES = ("before","applied","final")


def save(path,value):
    with Path(path).open("x") as stream:
        json.dump(value,stream,indent=2)
        stream.write("\n")


def assert_zero(bitmap,candidates):
    for row in candidates:
        point = row["point"]
        value = bitmap["metrics"]["cond"][point["scope"]]
        require(str(value["checksum"]) == point["metric_checksum"],"Candidate checksum changed")
        index = point["raw_index"]
        require(type(index) is int and 0 <= index < value["width"],"Candidate index invalid")
        bits = format(int(value["bits"],16),"0%db"%value["width"])
        require(len(bits) == value["width"] and bits[index] == "0","New hit contradicts LZC proof")


def membership(inputs,before,new_vdb,design,status):
    require(status.get("status") == status.get("coverage_status") == "COMPLETE"
            and status.get("aggregate_passed") == 688,"Completed688 baseline required")
    expected = [design,*before["tests"],new_vdb]
    require(len(before["tests"]) == 688 and len(expected) == len(set(expected)) == 690
            and inputs == expected,"Not exact ordered historical689")
    require(len({str(Path(p).resolve(strict=True)) for p in inputs}) == 690,"Aliased VDB membership")
    return expected


def capture_helpers():
    text = capture.TCL.read_text()
    marker = "proc apply_reviewed_waivers {id} {"
    require(text.count(marker) == 1,"Frozen helper boundary changed")
    return text.split(marker,1)[0]


def absolute_pins(entries):
    result = {}
    for name,digest in entries.items():
        path = Path(name)
        if not path.is_absolute():
            require(".." not in path.parts,"Parent traversal in preparation pin")
            path = ROOT/path
        require(str(path) not in result,"Aliased preparation pins")
        result[str(path)] = digest
    return result


def prepare(output):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == OUT.resolve(strict=True),"Fresh output required")
    seal = seals.FileSeal()
    bound,groups,audit = capture.load_evidence(seal)
    certificate = capture.verify_artifacts(BATCH,bound,groups,audit["vdb"])
    sealed_capture = seal.read(BATCH/"status.json")
    require(certificate["artifact_sha256"] == sealed_capture["artifact_sha256"],"Native artifacts changed")
    seal.hashes(certificate["artifact_sha256"])
    seal.hashes(seal.read(BATCH/"pins.json"))
    plan = seal.read(seals.old.CURRENT/"plan.json")
    build_path = OUT/"repaired-aligned-build-20260930-01/build-source-pins.json"
    seal.pin(build_path,plan["files"][str(build_path)])
    build = seal.read(build_path)
    for rel in ("hardware/deps/common_cells/src/lzc.sv","hardware/src/lane/operand_queue.sv","hardware/include/ara_pkg.sv"):
        path = ROOT/rel
        seal.pin(path,build[str(path)])
    state = seal.read(BASELINE/"status.json")
    require(state["image"] == plan["simv"] and state["new_waivers_applied"] is False,"Foreign baseline image/waivers")
    before = seal.read(BASELINE/"combined-bits.json")
    require(before["tests"][:687] == bound["tests"] and before["design"] == bound["design"],"Historical687 prefix changed")
    require(seal.pin(BASELINE/"combined-inputs.txt").read_text().splitlines() == [plan["design_vdb"],*before["tests"]],"GAP81 list differs")
    baseline_pins = seal.read(BASELINE/"evidence-pins.json")
    seal.hashes(baseline_pins["files"])
    require(seal.read(BASELINE/"runtime-audit.json")["status"] == "PASS","GAP81 runtime not PASS")
    descriptor = seal.read(COMBINE/"single-case-description.json")
    require(descriptor["status"] == "PREPARED_NOT_AGGREGATE_ADMISSION" and descriptor["baseline"] == str(BASELINE)
            and descriptor["baseline_terminal"] == state and descriptor["proposed_cases"] == 689,"Wrong prepared baseline")
    seal.hashes(absolute_pins(seal.read(COMBINE/"preparation-pins.json")))
    sidecar = Path(descriptor["gap82_sidecar"])
    single = seal.read(sidecar/"status.json")
    require(single["status"] == "OFFLINE_SINGLE_CASE_VERIFIED" and single["both_targets_hit"] is True
            and single["simulation_rerun"] is False and single["rtl_error_observed"] is False,"GAP82 not independently verified")
    new_vdb = descriptor["case_vdb"]
    static = seal.read(Path(new_vdb).parent/"static-plan.json")
    require(static["simv"] == plan["simv"] and static["image"] == plan["image"],"Foreign GAP82 frozen image")
    inputs = seal.pin(COMBINE/"proposed-inputs.txt").read_text().splitlines()
    membership(inputs,before,new_vdb,plan["design_vdb"],state)
    assert_zero(before,bound["candidates"])
    provenance = seal.read(RAW_UNION/"provenance.json")
    require(provenance["status"] == "RAW_DIAGNOSTIC_UNION_COMPLETE"
            and provenance["historical_tests"] == 689
            and provenance["baseline"] == str(BASELINE) and provenance["preparation"] == str(COMBINE)
            and all(provenance[k] is False for k in ("dve_run","waivers_applied","new_rtl_signoff")),
            "Wrong raw union provenance")
    require(provenance["preparation_pins"] == seal.read(COMBINE/"preparation-pins.json"),
            "Raw union preparation pins differ")
    require(set(provenance["outputs"]) == {str(RAW_UNION/n) for n in
            ("combined-bits.json","combined-inputs.txt","raw-bitmap-delta.json")},"Raw union outputs differ")
    seal.hashes(provenance["outputs"])
    seal.pin(HERE/"combine_gap82_bitmap.py",provenance["script_sha256"])
    require((RAW_UNION/"combined-inputs.txt").read_text().splitlines() == inputs,"Raw union list differs")
    combined = seal.read(RAW_UNION/"combined-bits.json")
    require(combined["design"] == before["design"] and combined["tests"] == inputs[1:],"Raw union membership differs")
    seal.hashes(combined["input_hashes"])
    assert_zero(combined,bound["candidates"])
    for vdb in inputs:
        seal.tree(Path(vdb))
    code = {str(p):seals.sha_bytes(p.read_bytes()) for p in (SCRIPT,TCL,TEST,capture.SCRIPT,capture.TCL,
        Path(environment.__file__),Path(environment.old.tools.__file__),HERE/"export_dve_coverage.tcl",
        HERE/"lzc_native_records.py",HERE/"lzc_padding_candidates.py",HERE/"lzc_padding_proof.py")}
    seal.hashes(code)
    output.mkdir()
    try:
        points = [x["point"] for x in [*bound["candidates"],*bound["retained"]]]
        bindings = capture.shape.shape_bindings(points,combined,Path(inputs[0])/"snps/coverage/db")
        recomputed = capture.shape.classify(points,combined,bindings)
        require(recomputed["candidates"] == bound["candidates"] and
                [x["point"] for x in recomputed["retained"]] == [x["point"] for x in bound["retained"]],"Structural/retained binding changed")
        for name,text in (("inputs.txt","\n".join(inputs)+"\n"),("groups.tcl",capture.group_script(groups)),
                          ("capture-helpers.tcl",capture_helpers()),("points.el",(BATCH/"first.el").read_text())):
            with (output/name).open("x") as stream:
                stream.write(text)
            seal.pin(output/name)
        save(output/"combined-bits.json",combined)
        save(output/"gap82-raw-bitmap-delta.json",bitmaps.delta(before,combined))
        for name in ("combined-bits.json","gap82-raw-bitmap-delta.json"):
            seal.pin(output/name)
        seal.finish()
        manifest = dict(schema="historical689-lzc180-v1",status="PREPARED_NOT_RUN",tests=689,
            inputs=inputs,candidates=bound["candidates"],retained=bound["retained"],groups=groups,
            evidence_sha256=dict(seal.files),sourcepins=code,native_records=capture.parse_records((output/"points.el").read_text()),
            historical_PASS_only=True,new_RTL_signoff=False,current_checker_replay_required=False,
            proof_domain="two-state normal operation; all real input patterns permitted",
            four_state_initialization_qualified=False,unhit_reachable_points_excluded=False,
            GAP81_GAP82_unreachable_hits=0,legacy_receipt_issued=False)
        save(output/"manifest.json",manifest)
        return dict(status=manifest["status"],tests=689,exclusions=180,
            manifest_sha256=seals.sha_bytes((output/"manifest.json").read_bytes()))
    except Exception as error:
        save(output/"status.json",dict(status="PREPARE_FAILED",reason=f"{type(error).__name__}: {error}"))
        raise


def verify_artifacts(output,manifest):
    output = Path(output)
    require((output/"selected_tests.txt").read_text().splitlines() ==
        [str(Path(p).with_suffix("")/next((Path(p)/"snps/coverage/db/testdata").iterdir()).name) for p in manifest["inputs"][1:]],
        "DVE selected population differs")
    records = capture.parse_records((output/"exclusions.el").read_text())
    capture.bind_records(records,manifest["candidates"])
    require(sorted(records,key=capture.key) == sorted(manifest["native_records"],key=capture.key),"Native imported IDs/records changed")
    for name in ("initial-empty.el","final-empty.el"):
        capture.bind_records(capture.parse_records((output/name).read_text()),[])
    expected = []
    for stage in STAGES:
        for g in manifest["groups"]:
            expected.append(dict(zip(capture.AUDIT_COLUMNS,[stage,g["scope"],g["expression"]," ".join(g["names"]),
                " ".join(g["targets"])," ".join(g["retained"]),str(len(g["targets"]) if stage == "applied" else 0),"0"])))
    with (output/"neighbor-audit.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == capture.AUDIT_COLUMNS and list(reader) == expected,"Incomplete/changed native neighbor checks")
    log = (output/"DVEfiles/dve_gui.log").read_text()
    for marker in ("DVE_COVERAGE_EXPORT_DONE","DVE_WAIVER_EXPORT_DONE","LZC_FORMAL_WAIVER_DONE 180"):
        require(log.splitlines().count(marker) == 1,"Missing/ambiguous completion")
    for path in (output/"launcher.log",output/"DVEfiles/dve_gui.log"):
        require(not capture.re.search(r"(^|\s)(Warning|Error|Fatal)([\s:-]|$)|EXPORT_FAILED|checksum.*mismatch|will not be merged|Version Check Error",path.read_text(),capture.re.I|capture.re.M),"DVE diagnostic")
    raw,reset = (output/"summary.csv.partial").read_bytes(),(output/"summary_reset.csv.partial").read_bytes()
    require(raw and raw == reset,"Raw/reset report differs")
    require((output/"summary_waived.csv.partial").stat().st_size > 0,"Empty waived report")
    return dict(exact_exclusions=180,native_neighbor_expressions=120,native_retained_vectors=180,
                retained_inventory=142,full_retained_inventory_native_queried=False,final_reset=True,raw_reset_equal=True)


def run(output,manifest_sha):
    require(isinstance(manifest_sha,str) and capture.re.fullmatch(r"[0-9a-f]{64}",manifest_sha),
            "Explicit manifest SHA256 required")
    output = Path(output).resolve(strict=True)
    require(output.parent == OUT.resolve(strict=True) and not (output/"launcher.log").exists(),"Fresh prepared run required")
    seal = seals.FileSeal()
    seal.pin(output/"manifest.json",manifest_sha)
    manifest = seal.read(output/"manifest.json")
    require(manifest["schema"] == "historical689-lzc180-v1" and manifest["status"] == "PREPARED_NOT_RUN"
            and manifest["tests"] == 689 and manifest["current_checker_replay_required"] is False,"Wrong context")
    seal.hashes(manifest["evidence_sha256"])
    for path in manifest["inputs"]:
        seal.tree(Path(path))
    tools = environment.old.tools
    identity = tools.prepare(shutil.which("dve"),shutil.which("xvfb-run"))
    save(output/"tool-identity-before.json",identity)
    env = environment.launcher_environment(identity,os.environ)
    env.update(DVE_COVERAGE_OUTPUT=str(output),DVE_REVIEWED_WAIVERS=str(TCL))
    command = tools.launch_command(identity,HERE/"export_dve_coverage.tcl")
    save(output/"command.json",dict(command=command,cwd=str(output),timeout_s=1200,entry_DVE_unset=True,
        hook=str(TCL),hook_sha256=manifest["sourcepins"][str(TCL)],policy="exact180 only"))
    observed = None
    print(json.dumps(dict(phase="DVE_STARTING",tests=689,exclusions=180)),flush=True)
    try:
        with (output/"launcher.log").open("x") as log:
            process = subprocess.Popen(command,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            start = tools.process_info(process.pid)["starttime"]
            deadline = time.monotonic()+1200
            try:
                while process.poll() is None:
                    if observed is None:
                        for entry in Path("/proc").iterdir():
                            if not entry.name.isdigit():continue
                            try:
                                if (entry/"exe").resolve(strict=True) != Path(identity["executable"]):continue
                                observed = tools.verify_live_executable(int(entry.name),identity,process.pid,start)
                                save(output/"runtime-executable.json",observed)
                                break
                            except (OSError,ValueError):continue
                    require(time.monotonic() < deadline,"DVE deadline exceeded")
                    time.sleep(0.5)
                require(process.returncode == 0 and observed is not None,"DVE process failed/unproven")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
        result = verify_artifacts(output,manifest)
        tools.revalidate(identity)
        save(output/"tool-identity-after.json",identity)
        seal.finish()
        for name in ("summary.csv","summary_waived.csv","summary_reset.csv"):
            (output/(name+".partial")).rename(output/name)
        artifact_pins = {str(p):seals.sha_bytes(p.read_bytes()) for p in
            [output/name for name in ("summary.csv","summary_waived.csv","summary_reset.csv","exclusions.el",
                "initial-empty.el","final-empty.el","neighbor-audit.csv","selected_tests.txt","launcher.log","DVEfiles/dve_gui.log") ]}
        save(output/"evidence-pins.json",dict(input_sha256=seal.files,artifact_sha256=artifact_pins))
        status = dict(status="RAW_WAIVED_COMPLETE_HISTORICAL_ONLY",**result,tests=689,
            historical_PASS_only=True,new_RTL_signoff=False,current_checker_replay_required=False,
            proof_domain=manifest["proof_domain"],four_state_initialization_qualified=False,
            legacy_receipt_issued=False,RTL_changed=False,simulation_rerun=False)
        save(output/"status.json",status)
        return status
    except Exception as error:
        save(output/"status.json",dict(status="FAIL",reason=f"{type(error).__name__}: {error}",new_RTL_signoff=False))
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("prepare","run"))
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    result = prepare(args.output) if args.command == "prepare" else run(args.output,args.manifest_sha256)
    print(json.dumps(result,indent=2),flush=True)
