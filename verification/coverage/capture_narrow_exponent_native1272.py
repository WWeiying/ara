#!/usr/bin/env python3
"""Exact single-test round/SRT exponent qualification, not product admission."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import prepare_narrow_exponent_native1272 as proof

ff1 = proof.ff1
lifecycle, common = ff1.lifecycle, ff1.common
require, sha, write, tool = proof.require, proof.sha, proof.write, ff1.tool
HERE = Path(__file__).resolve().parent
SEALED = proof.prep.OUT / "narrow-exponent-native1272-prepare-20261006-01"
PLAN_SEAL = "1ef02170ed379a4ac738d6d4351b5b2e572591f3150b5d2d40e2c683fa97d026"
HOOK = HERE / "capture_narrow_exponent_native1272.tcl"
ANNOTATION = "Narrow round SRT double exponent exact case native qualification only; not application approval"
STAGES = lifecycle.STAGES
DOC = HERE / "DIVSQRT_NARROW_EXPONENT_SCOPE.md"
DOC_SHA = "4dd9f19c426f1be53360caef13ccb08a78609a67ed4531dc4776d79ec4188eda"
DOC_SNAPSHOT = proof.prep.OUT / "narrow-exponent-native1272-document-evidence-20261006-01/original-scope.md"


def document_binding():
    require(DOC_SNAPSHOT.is_file() and not DOC_SNAPSHOT.is_symlink() and DOC_SNAPSHOT.resolve() == DOC_SNAPSHOT and
            sha(DOC_SNAPSHOT) == DOC_SHA, "Historical document snapshot differs")
    return dict(original_path=str(DOC), expected_sha256=DOC_SHA, entity_path=str(DOC_SNAPSHOT),
                classification="Exact historical documentation bytes only; no source/checker pin redirection")


def load_plan():
    require(sha(SEALED / "manifest.json") == PLAN_SEAL, "External plan manifest seal differs")
    manifest = json.loads((SEALED / "manifest.json").read_bytes())
    require(set(manifest) == {str(SEALED / n) for n in ("capture-plan.json", "selection.tcl")}, "Wrong sealed plan members")
    for path, expected in manifest.items():
        require(sha(path) == expected, "Sealed plan member differs")
    plan = json.loads((SEALED / "capture-plan.json").read_bytes())
    require(plan["status"] == "NARROW_EXPONENT1272_EXACT_CAPTURE_PLAN_REQUIRES_PARENT_REVIEW_NO_DVE" and
            plan["targets"] == 1272 and plan["protected"] == 4344 and plan["all_branch_positions"] == 5616 and
            plan["pack_included"] is False and plan["default_protected"] is True and plan["WIDTH64_all_protected"] is True,
            "Wrong reviewed proof population")
    for path, expected in plan["pins"].items():
        if path == str(DOC):
            require(expected == DOC_SHA, "Historical document expected hash differs")
            document_binding()
        else:
            require(sha(path) == expected, "Proof input pin differs: " + path)
    tool.revalidate(plan["tool_identity"])
    return plan


def capture_plan(sealed, membership):
    return dict(design_vdb=sealed["design_vdb"], selected_test_vdb=sealed["selected_test_vdb"],
                tool_identity=sealed["tool_identity"], input_membership=membership,
                scopes={s: {"branch": group["branch"]} for s, group in sealed["scopes"].items()})


def check(config):
    sealed = load_plan()
    require(config["historical_document_binding"] == document_binding() and
            config["pins"].get(str(DOC_SNAPSHOT)) == DOC_SHA and str(DOC) not in config["pins"],
            "Historical document entity binding differs")
    require(config["plan"] == capture_plan(sealed, config["plan"]["input_membership"]) and
            config["selected_test"] == sealed["selected_test"] and config["command"] == tool.launch_command(sealed["tool_identity"], HOOK),
            "Capture plan/command differs from sealed proof")
    require(set(config["plan"]["input_membership"]) == {sealed["design_vdb"], sealed["selected_test_vdb"]},
            "Wrong single-test input trees")
    lifecycle.check_inputs(config)


def read_config(output, seal):
    require(re.fullmatch(r'[0-9a-f]{64}', seal or '') and sha(output / "config.json") == seal, "External capture config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "narrow-exponent-native1272-v1" and config["output"] == str(output) and
            config["plan_manifest_sha256"] == PLAN_SEAL and config["targets"] == 1272 and config["protected"] == 4344 and
            config["capture_only"] is True and config["application_approval"] is False and config["pack_included"] is False,
            "Wrong capture config")
    check(config)
    return config


def prepare(output):
    require(output.parent == proof.prep.OUT and not output.exists(), "Fresh direct output required")
    sealed = load_plan()
    pins = dict(sealed["pins"])
    require(pins.pop(str(DOC)) == DOC_SHA, "Historical document pin differs")
    pins[str(DOC_SNAPSHOT)] = DOC_SHA
    for name in ("manifest.json", "capture-plan.json", "selection.tcl"):
        pins[str(SEALED / name)] = sha(SEALED / name)
    design = proof.prep.compiled.Design(Path(sealed["design_vdb"]))
    bitmap = json.loads((proof.prep.CORPUS / "combined-bits.json").read_bytes())
    for scope, group in sealed["scopes"].items():
        require(design.source(scope) == group["source"], "Compiled source identity differs")
        definition = design.definition(scope, "branch")
        record = bitmap["metrics"]["branch"][scope]
        require(record["width"] == group["module_width"] and record["checksum"] == definition.get("chksum"), "Compiled branch shape differs")
        points = proof.prep.compiled.points("branch", definition, record["width"])
        require(points == [r["point"] for r in group["branch"]], "Full compiled point reconstruction differs")
        specs = {n.get("id"): n for n in definition.iter("branch_spec")}
        owner = proof.OWNERS[scope.rsplit(".", 1)[1]]
        for row in group["branch"]:
            p = row["point"]
            hit = bool(int(record["bits"], 16) & (1 << (record["width"]-1-p["raw_index"])))
            target, item = proof.classify(p, specs[p["native_id"]], group["physical_position"][1], hit, owner)
            require((target, item, hit) == (row["target"], row["case_item"], row["hit"]), "Exact case/default eligibility differs")
    membership = {root: lifecycle.proof.tree_members(root) for root in (sealed["design_vdb"], sealed["selected_test_vdb"])}
    for root, names in membership.items():
        for name in names:
            path = Path(root) / name
            value = sha(path)
            require(str(path) not in pins or pins[str(path)] == value, "VDB pin conflict")
            pins[str(path)] = value
    for path in (Path(__file__), HOOK, HERE / "test_capture_narrow_exponent_native1272.py", Path(lifecycle.__file__),
                 Path(lifecycle.proof.__file__), Path(common.__file__), HERE / "capture_operand_debug.tcl"):
        pins[str(path)] = sha(path)
    plan = capture_plan(sealed, membership)
    selection = common.selection(plan)
    selection += "set exp_python " + lifecycle.literal(sys.executable) + "\n"
    selection += "set exp_driver " + lifecycle.literal(str(Path(__file__).resolve())) + "\n"
    selection += "set exp_test_identity " + lifecycle.literal(sealed["selected_test"]) + "\n"
    output.mkdir()
    (output / "selection.tcl").write_text(selection)
    pins[str(output / "selection.tcl")] = sha(output / "selection.tcl")
    config = dict(schema="narrow-exponent-native1272-v1", output=str(output), plan_manifest_sha256=PLAN_SEAL,
                  pins=pins, plan=plan, selected_test=sealed["selected_test"], targets=1272, protected=4344,
                  command=tool.launch_command(plan["tool_identity"], HOOK), capture_only=True,
                  historical_document_binding=document_binding(),
                  application_approval=False, pack_included=False, product_VDB_admission=False,
                  default_and_WIDTH64_protected=True)
    check(config)
    write(output / "config.json", config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE_REQUIRES_PARENT_CONFIG_REVIEW", config_sha256=seal,
                                       targets=1272, protected=4344, application_approval=False))
    print("EXP1272_PREPARED seal=" + seal, flush=True)


def bind_native(raw, config):
    records = lifecycle.parse_native(raw)
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        require(scope.rsplit(".", 1)[1] in proof.OWNERS, "Pack or foreign module forbidden")
        for row in metrics["branch"]:
            if row["target"]:
                p = row["point"]
                key = scope + "|Branch %s (%s)" % (p["native_id"], p["vector"])
                require(key not in expected and row["case_item"] is not None and row["case_item"]["name"] != "default" and
                        row["hit"] is False, "Invalid/duplicate/default/hit target")
                expected[key] = row
    require(len(expected) == config["targets"] == 1272 and set(records) == set(expected), "Extra/missing native population")
    for key, row in expected.items():
        p, actual = row["point"], records[key]
        require(actual["checksum"] == [row["module_checksum"], row["metric_checksum"]] and
                actual["spec_checksum"] == p["attributes"]["chksum"] and actual["expression"] == p["expression"] and
                actual["annotation"] == ANNOTATION and actual["signature"] == p["expression"] + " " + row["case_item"]["name"],
                "Complete native checksum/expression/case signature differs")
    return records


def audit_states(path, config, stage, previous=None):
    require(stage in STAGES, "Unknown audit stage")
    got = common.audit_states(path, config, stage, previous)
    require(len(got) == 5616, "Incomplete full selector audit")
    for (scope, metric, coordinate), (meta, native_path) in got.items():
        sid, vid = coordinate.split(",")
        require(metric == "branch" and re.fullmatch(r'(Branch|MISSING_ELSE|MISSING_DEFAULT)' + re.escape(sid) + r'\.' + re.escape(vid), meta) and
                native_path == "Item%s.%s" % (sid, meta), "Observed native selector identity differs")
    return got


def verify(output, config):
    check(config)
    names = ["first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
             "DVEfiles/dve_gui.log", "live-identity.json", "execution.json", "integrity-before.json", "integrity-after.json"]
    names += ["states_%s.tsv" % s for s in STAGES]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing/aliased native evidence")
    first, second = [bind_native((output / n).read_bytes(), config) for n in ("first.el", "second.el")]
    require(first == second, "Exact complete native roundtrip differs")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Global exclusion reset not empty")
    previous = None
    for stage in STAGES:
        previous = audit_states(output / ("states_%s.tsv" % stage), config, stage, previous)
    require((output / "selected_tests.txt").read_text().splitlines() == [config["selected_test"]], "Selected test differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("EXP1272_CAPTURE_DONE") == 1 and not re.search(
        r'EXP1272_FAILED|EXP1272_SESSION_ERROR|EK-CMD-|UCAPI-DLMA|DVCDT136|invalid command name|(?:^|\s)(Error|Fatal):|checksum.*mismatch',
        log, re.I), "GUI failed/incomplete")
    for stage in STAGES:
        require(log.splitlines().count("EXP1272_AUDIT %s 5616" % stage) == 1, "GUI audit marker differs")
    execution = json.loads((output / "execution.json").read_bytes())
    live = json.loads((output / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and live["executable_verified"] is True and
            live["executable"] == config["plan"]["tool_identity"]["executable"] and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"], "Live execution identity differs")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / name).read_bytes()) == {field: True, "pins": config["pins"],
                     "membership": config["plan"]["input_membership"]}, "Input integrity differs")
    return dict(status="NARROW_EXPONENT1272_NATIVE_ROUNDTRIP_VERIFIED_NOT_APPLICATION_APPROVAL", captured_tests=1,
                records=1272, targets=1272, protected=4344, exact_selectors=5616, final_reset=True,
                default_and_WIDTH64_protected=True, pack_included=False, application_approval=False,
                product_VDB_admission=False, official_denominator_verified=False, files={str(p): sha(p) for p in paths})


def capture(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / "status.json").read_bytes())["status"] == "PREPARED_NO_DVE_REQUIRES_PARENT_CONFIG_REVIEW" and
            not any((output / n).exists() for n in ("execution.json", "live-ready", "first.el", "DVEfiles")), "No repeat launch")
    status = dict(status="RUNNING", config_sha256=seal, application_approval=False)
    write(output / "status.json", status)
    write(output / "integrity-before.json", dict(checked=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
    process = None
    try:
        env = tool.controlled_environment(config["plan"]["tool_identity"], os.environ)
        env.pop("DVE", None)
        env.update(DVE_COVERAGE_OUTPUT=str(output), EXP1272_CAPTURE_SEAL=seal)
        with (output / "launcher.log").open("w") as stream:
            process = subprocess.Popen(config["command"], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1)
            write(output / "execution.json", execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, config["plan"]["tool_identity"], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, "No launch-bound live DVE executable")
            write(output / "live-identity.json", live)
            check(config)
            (output / "live-ready").write_text("LIVE_EXECUTABLE_VERIFIED\n")
            print("EXP1272_DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=2400)
            write(output / "execution.json", execution)
        require(execution["returncode"] == 0, "DVE exited nonzero")
        check(config)
        write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
        status.update(verify(output, config))
        status["files"].update({str(output / n): sha(output / n) for n in ("config.json", "selection.tcl")})
        write(output / "capture-result.json", status)
        status["capture_result_sha256"] = sha(output / "capture-result.json")
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status.update(status="FAILED", reason="%s: %s" % (type(error).__name__, error))
        raise
    finally:
        write(output / "status.json", status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "first", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    parser.add_argument("--result-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == proof.prep.OUT and not output.is_symlink(), "Unsafe output")
    if args.command == "prepare":
        prepare(output)
    elif args.command == "capture":
        capture(output, args.seal)
    elif args.command == "first":
        print("EXP1272_FIRST_EXACT " + str(len(bind_native((output / "first.el").read_bytes(), read_config(output, args.seal)))))
    else:
        require(sha(output / "capture-result.json") == args.result_seal, "External result seal differs")
        saved = json.loads((output / "capture-result.json").read_bytes())
        require(saved["config_sha256"] == args.seal, "Result/config binding differs")
        for path, expected in saved["files"].items():
            require(sha(path) == expected, "Captured artifact differs")
        fresh = verify(output, read_config(output, args.seal))
        require(all(saved.get(k) == v for k, v in fresh.items() if k != "files") and
                all(saved["files"].get(k) == v for k, v in fresh["files"].items()), "Result regeneration differs")
        print("EXP1272_NATIVE_REVERIFIED")
