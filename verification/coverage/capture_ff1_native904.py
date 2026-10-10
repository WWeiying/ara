#!/usr/bin/env python3
"""One historical test, exact FF1 case capture/roundtrip; never corpus admission."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import audit_ff1_native904_flags as flags
import capture_operand_1144 as lifecycle
import capture_operand_debug as common

prep = flags.prep
require, sha, write, tool = prep.require, prep.sha, prep.write, prep.tool
HERE = Path(__file__).resolve().parent
HOOK = HERE / "capture_ff1_native904.tcl"
FLAGFILE = prep.OUT / "ff1-native904-flags-audit-20261006-01/flags-audit.json"
FLAGSEAL = "86b4aa45908db349ba061f192141039eb97e24f3aacb5685b3f178a7d454922d"
ANNOTATION = "FF1 narrow width exact case native qualification only; not application approval"
STAGES = lifecycle.STAGES


def bind_parameters(variants, width, formats):
    require(len(variants) == 1 and variants[0].get("WIDTH") == width and variants[0].get("FpFmtConfig") == formats,
            "Compiled wrapper WIDTH/FpFmtConfig differs")
    return variants[0]


def check(config):
    lifecycle.check_inputs(config)


def read_config(output, seal):
    require(re.fullmatch(r'[0-9a-f]{64}', seal or '') and sha(output / "config.json") == seal, "External config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "ff1-native904-v1" and config["output"] == str(output) and
            config["flags_sha256"] == FLAGSEAL and config["static_sha256"] == flags.STATIC_SHA and
            config["targets"] == 904 and config["protected"] == 824 and config["application_approval"] is False,
            "Wrong qualification config")
    check(config)
    return config


def prepare(output):
    require(output.parent == prep.OUT and not output.exists(), "Fresh direct output required")
    require(sha(FLAGFILE) == FLAGSEAL, "External flags audit seal differs")
    audit = json.loads(FLAGFILE.read_bytes())
    require(audit == flags.audit() and audit["effective_compile_flags_defparam_audit_complete"] is True,
            "Flags audit reproduction differs")
    static = json.loads(flags.STATIC.read_bytes())
    pins = dict(audit["pins"])
    pins[str(FLAGFILE)] = FLAGSEAL
    design = prep.compiled.Design(Path(static["design_vdb"]))
    review_path = lifecycle.proof.REVIEW / "review.py"
    pins[str(review_path)] = sha(review_path)
    spec = importlib.util.spec_from_file_location("ff1_compiled_parameter_review", review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    top_variants = review.signature(design.definition(top, "tgl"))
    require(len(top_variants) == 1 and all(top_variants[0].get(k) == v for k, v in
            dict(NrLanes=4, VLEN=1024, FPUSupport=56).items()), "Compiled Ara parameters differ")
    wrapper_parameters = {}
    mapping = json.loads(prep.MAPPING.read_bytes())
    indices = {r["case"]: r["raw_index"] for r in mapping["observations"]}
    bitmap = json.loads((prep.CORPUS / "combined-bits.json").read_bytes())
    scopes = {}
    for scope, original in static["scopes"].items():
        wrapper = scope.split(".i_fpnew_divsqrt_th_64_c910.")[0] + ".i_fpnew_divsqrt_th_64_c910"
        inner = original["physical_position"][1]
        wrapper_parameters[wrapper] = bind_parameters(review.signature(design.definition(wrapper, "tgl")),
                                                     (64, 32, 16, 16)[inner], (56, 40, 8, 8)[inner])
        require(design.source(scope) == original["source"], "Compiled source ownership differs")
        definition = design.definition(scope, "branch")
        record = bitmap["metrics"]["branch"][scope]
        require(record["width"] == 54 and record["checksum"] == definition.get("chksum") == original["metric_checksum"],
                "Compiled metric differs")
        points = prep.compiled.points("branch", definition, 54)
        case_items = {n.get("index"): dict(n.attrib) for n in definition.iter("branch_citem")}
        require(points == [r["point"] for r in original["rows"]], "Complete compiled points differ")
        rows = []
        for row in original["rows"]:
            p, calibration = row["point"], row["calibration"]
            raw = p["raw_index"]
            hit = bool(int(record["bits"], 16) & (1 << (53 - raw)))
            require(raw == calibration["raw_index"] and hit == calibration["hit"] and
                    row["target"] == prep.decision(calibration["input_bit"], raw, hit, original["physical_position"][1], indices),
                    "Source/calibration eligibility differs")
            case_item = case_items.get(str(int(p["vector"]) + 1)) if row["target"] else None
            if row["target"]:
                bit = calibration["input_bit"]
                require(case_item is not None and case_item["file_id"] == p["file_id"] and
                        case_item["name"] == "52'b" + "0" * (51 - bit) + "1" + "z" * bit + " ",
                        "Calibrated input/native vector/compiled case arm differs")
            rows.append(dict(point=p, coordinate=p["native_id"] + "," + p["vector"], target=row["target"],
                             module_checksum=original["module_checksum"], metric_checksum=original["metric_checksum"],
                             calibrated_input_bit=calibration["input_bit"], raw_index=raw, case_item=case_item))
        require(len({r["coordinate"] for r in rows}) == 54, "Ambiguous compiled vector coordinate")
        scopes[scope] = {"branch": rows}
    require(len(scopes) == 32 and sum(r["target"] for s in scopes.values() for r in s["branch"]) == 904,
            "Wrong target population")
    sample = static["selected_test_vdb"]
    membership = {p: lifecycle.proof.tree_members(p) for p in (static["design_vdb"], sample)}
    for root, members in membership.items():
        for name in members:
            path = Path(root) / name
            value = sha(path)
            require(str(path) not in pins or pins[str(path)] == value, "VDB pin conflict")
            pins[str(path)] = value
    for path in (Path(__file__), HOOK, HERE / "test_capture_ff1_native904.py", Path(lifecycle.__file__),
                 Path(lifecycle.proof.__file__), Path(common.__file__), HERE / "capture_operand_debug.tcl"):
        pins[str(path)] = sha(path)
    plan = dict(design_vdb=static["design_vdb"], selected_test_vdb=sample, scopes=scopes,
                input_membership=membership, tool_identity=static["tool_identity"])
    selection = common.selection(plan) + "set ff1_python " + lifecycle.literal(sys.executable) + "\n"
    selection += "set ff1_driver " + lifecycle.literal(str(Path(__file__).resolve())) + "\n"
    selection += "set ff1_test_identity " + lifecycle.literal(static["selected_test"]) + "\n"
    output.mkdir()
    (output / "selection.tcl").write_text(selection)
    pins[str(output / "selection.tcl")] = sha(output / "selection.tcl")
    config = dict(schema="ff1-native904-v1", output=str(output), flags_sha256=FLAGSEAL, static_sha256=flags.STATIC_SHA,
                  pins=pins, plan=plan, command=tool.launch_command(plan["tool_identity"], HOOK),
                  selected_test=static["selected_test"], targets=904, protected=824, capture_only=True,
                  compiled_top_parameters=top_variants[0], compiled_wrapper_parameters=wrapper_parameters,
                  application_approval=False, product_VDB_admission=False, X_or_default_excluded=False)
    check(config)
    write(output / "config.json", config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, application_approval=False))
    print("FF1_PREPARED seal=" + seal, flush=True)


def bind_native(raw, config):
    records = lifecycle.parse_native(raw)
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        for row in metrics["branch"]:
            if row["target"]:
                point = row["point"]
                key = scope + "|Branch %s (%s)" % (point["native_id"], point["vector"])
                require(key not in expected, "Duplicate expected point")
                expected[key] = row
    require(len(expected) == config["targets"] == 904 and set(records) == set(expected), "Extra/missing native targets")
    for key, row in expected.items():
        actual, p = records[key], row["point"]
        require(actual["checksum"] == [row["module_checksum"], row["metric_checksum"]] and
                actual["spec_checksum"] == p["attributes"]["chksum"] and actual["expression"] == p["expression"] and
                actual["annotation"] == ANNOTATION and actual["signature"] == p["expression"] + " " + row["case_item"]["name"],
                "Native complete record binding differs")
        require(row["calibrated_input_bit"] >= 0, "Default/zero target forbidden")
    return records


def audit_states(path, config, stage, previous=None):
    require(stage in STAGES, "Unknown audit stage")
    got = common.audit_states(path, config, stage, previous)
    require(len(got) == 1728, "Incomplete full selector audit")
    for (scope, metric, coordinate), (meta, native_path) in got.items():
        sid, vid = coordinate.split(",")
        require(metric == "branch" and re.fullmatch(r'(Branch|MISSING_DEFAULT)' + re.escape(sid) + r'\.' + re.escape(vid), meta)
                and native_path == "Item%s.%s" % (sid, meta), "Observed native selector/path differs")
    return got


def verify(output, config):
    check(config)
    names = ["first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
             "DVEfiles/dve_gui.log", "live-identity.json", "execution.json", "integrity-before.json", "integrity-after.json"]
    names += ["states_%s.tsv" % s for s in STAGES]
    paths = [output / name for name in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing native evidence")
    first, second = [bind_native((output / name).read_bytes(), config) for name in ("first.el", "second.el")]
    require(first == second, "Complete native roundtrip differs")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Global reset not empty")
    identities = None
    for stage in STAGES:
        identities = audit_states(output / ("states_%s.tsv" % stage), config, stage, identities)
    require((output / "selected_tests.txt").read_text().splitlines() == [config["selected_test"]], "Selected test differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("FF1_CAPTURE_DONE_904") == 1 and not re.search(
        r'FF1_FAILED|FF1_SESSION_ERROR|EK-CMD-|UCAPI-DLMA|DVCDT136|invalid command name|(?:^|\s)(Error|Fatal):|checksum.*mismatch',
        log, re.I), "GUI failed/incomplete")
    for stage in STAGES:
        require(log.splitlines().count("FF1_AUDIT %s 1728" % stage) == 1, "Audit marker missing")
    execution = json.loads((output / "execution.json").read_bytes())
    live = json.loads((output / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and live["executable_verified"] is True and
            live["executable"] == config["plan"]["tool_identity"]["executable"] and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"],
            "Execution/live identity differs")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / name).read_bytes()) == {field: True, "pins": config["pins"],
                    "membership": config["plan"]["input_membership"]}, "Input integrity differs")
    return dict(status="FF1_NATIVE904_ROUNDTRIP_VERIFIED_NOT_APPLICATION_APPROVAL", captured_tests=1, records=904,
                targets=904, protected=824, exact_selectors=1728, final_reset=True, default_and_zero_protected=True,
                product_VDB_admission=False, application_approval=False, official_denominator_verified=False,
                files={str(p): sha(p) for p in paths})


def capture(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / "status.json").read_bytes())["status"] == "PREPARED_NO_DVE" and
            not any((output / name).exists() for name in ("execution.json", "live-ready", "first.el", "DVEfiles")),
            "No repeated launch")
    require(config["command"] == tool.launch_command(config["plan"]["tool_identity"], HOOK), "Launch command differs")
    status = dict(status="RUNNING", config_sha256=seal, application_approval=False)
    write(output / "status.json", status)
    write(output / "integrity-before.json", dict(checked=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
    process = None
    try:
        env = tool.controlled_environment(config["plan"]["tool_identity"], os.environ)
        env.pop("DVE", None)
        env.update(DVE_COVERAGE_OUTPUT=str(output), FF1_CAPTURE_SEAL=seal)
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
            print("FF1_DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=1800)
            write(output / "execution.json", execution)
        require(execution["returncode"] == 0, "DVE exited nonzero")
        check(config)
        write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
        status.update(verify(output, config))
        status["files"].update({str(output / name): sha(output / name) for name in ("config.json", "selection.tcl")})
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
    require(output.parent == prep.OUT and not output.is_symlink(), "Unsafe output path")
    if args.command == "prepare":
        prepare(output)
    elif args.command == "capture":
        capture(output, args.seal)
    elif args.command == "first":
        config = read_config(output, args.seal)
        print("FF1_FIRST_EXACT " + str(len(bind_native((output / "first.el").read_bytes(), config))))
    else:
        require(sha(output / "capture-result.json") == args.result_seal, "External result seal differs")
        saved = json.loads((output / "capture-result.json").read_bytes())
        require(saved["config_sha256"] == args.seal, "Result/config binding differs")
        for path, expected in saved["files"].items():
            require(sha(path) == expected, "Captured artifact changed")
        fresh = verify(output, read_config(output, args.seal))
        require(all(saved.get(k) == v for k, v in fresh.items() if k != "files") and
                all(saved["files"].get(k) == v for k, v in fresh["files"].items()), "Result regeneration differs")
        print("FF1_NATIVE904_REVERIFIED")
