#!/usr/bin/env python3
"""Independent single-test native format capture; no corpus merge or receipt."""
import argparse
import csv
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
import seal_operand_1144_preflight as proof
import dve_tool_identity as tool

HERE = Path(__file__).resolve().parent
OUT = proof.OUT
PRECHECK = OUT / "operand-1144-binding-689-preflight-20261006-02"
SEAL = "8bde8a159443af197b876b9c035c59e1a5b69bd8103c093e796c64e1d2abb596"
TCL = HERE / "capture_operand_1144.tcl"
TEST = HERE / "test_capture_operand_1144.py"
ANNOTATION = "Operand parameter native discovery; exact vectors only; not application approval"
STAGES = ("before", "selected", "reset", "reloaded", "final")
require = proof.require


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def hash_file(path):
    return proof.digest(Path(path).read_bytes())


def literal(value):
    require(not any(c in value for c in "{}\\\n\r\t"), "Unsafe Tcl literal")
    return "{" + value + "}"


def selection(plan):
    scopes = sorted(plan["scopes"])
    lines = ["set op1144_design " + literal(plan["design_vdb"]),
             "set op1144_test " + literal(plan["selected_test_vdb"]),
             "set op1144_scopes {" + " ".join(literal(s) for s in scopes) + "}"]
    for scope in scopes:
        row = plan["scopes"][scope]
        all_rows = row["targets"] + row["protected"]
        keys = [p["selector"] for p in sorted(all_rows, key=lambda p: p["raw_index"])]
        targets = [p["selector"] for p in row["targets"]]
        require(len(keys) == len(set(keys)) == 101 and set(targets) <= set(keys), "Wrong selectors")
    lines += ["array set op1144_%s {\n%s\n}" % (name, "\n".join(
        literal(s) + " {" + " ".join(p["selector"] for p in
        (sorted(plan["scopes"][s]["targets"] + plan["scopes"][s]["protected"], key=lambda p: p["raw_index"])
         if name == "keys" else plan["scopes"][s]["targets"])) + "}" for s in scopes))
        for name in ("keys", "targets")]
    return "\n".join(lines) + "\n"


def environment(record, output):
    env = tool.controlled_environment(record, os.environ)
    env.pop("DVE", None)
    env["DVE_COVERAGE_OUTPUT"] = str(output)
    return env


def check_inputs(config):
    for path, sha in config["pins"].items():
        require(hash_file(path) == sha, "Input pin differs: " + path)
    for root, members in config["plan"]["input_membership"].items():
        require(proof.tree_members(root) == members, "Input tree differs")
    tool.revalidate(config["plan"]["tool_identity"])


def prepare(output):
    output = Path(output).absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.exists(), "Fresh direct out required")
    manifest = proof.load_bound(PRECHECK / "manifest.sha256.json", {}, SEAL)
    require(set(manifest) == {"evidence.json", "capture-plan.json"}, "Wrong preflight members")
    for name, sha in manifest.items():
        proof.read_bound(PRECHECK / name, {}, sha)
    evidence, plan = proof.audit()
    require(evidence == json.loads((PRECHECK / "evidence.json").read_text()) and
            plan == json.loads((PRECHECK / "capture-plan.json").read_text()), "Preflight reproduction differs")
    pins = dict(evidence["pins"])
    for name in ("manifest.sha256.json", "evidence.json", "capture-plan.json"):
        pins[str(PRECHECK / name)] = hash_file(PRECHECK / name)
    for path in (Path(__file__), TCL, TEST):
        pins[str(path)] = hash_file(path)
    helper = HERE / "reviewed_20261004/audit_readonly.py"
    spec = importlib.util.spec_from_file_location("operand_native_shape", helper)
    design_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(design_module)
    design = design_module.Design(Path(plan["design_vdb"]))
    expectations = {}
    for scope, rows in plan["scopes"].items():
        defs = design.definition(scope, "branch")
        expressions = {s.get("id"): [n for n in s if n.tag in ("branch_expr", "branch_cexpr")][0].get("exprstr")
                       for s in defs.iter("branch_spec")}
        for p in rows["targets"]:
            expectations[scope + "|" + p["point"]] = dict(p, expression=expressions[p["selector"].split(",")[0]])
    pilot = OUT / "gap58-operand-native-pilot-20261004-02"
    seal = "e9d59a34fb400a9d703c2fec4a55fc1a16ac5b95d8508a3c8a2592189914e97e"
    pilot_manifest = proof.load_bound(pilot / "manifest.sha256.json", pins, seal)
    for path, sha in pilot_manifest.items():
        proof.read_bound(path, pins, sha)
    observed = parse_native((pilot / "dve/branches.saved.el").read_bytes())
    require(len(observed) == 18 and set(observed) <= set(expectations), "Wrong pilot18")
    output.mkdir()
    (output / "selection.tcl").write_text(selection(plan))
    pins[str(output / "selection.tcl")] = hash_file(output / "selection.tcl")
    command = tool.launch_command(plan["tool_identity"], TCL)
    config = dict(plan=plan, expectations=expectations, pilot=observed, pins=pins, command=command,
                  output=str(output), preflight_seal=SEAL, capture_only=True)
    write(output / "config.json", config)
    config_seal = hash_file(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=config_seal))
    check_inputs(config)
    print("PREPARED_NO_DVE config_sha256=" + config_seal, flush=True)
    return config_seal


def parse_native(raw):
    require(raw.endswith(b"\n") and not re.search(rb"[^\x0a\x20-\x7e]", raw), "Native encoding")
    lines = raw.decode("ascii").splitlines()
    records, scope, checksums, i = {}, None, None, 0
    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue
        match = re.fullmatch(r'CHECKSUM: "([0-9]+) ([0-9]+)"', line)
        if match:
            require(i+1 < len(lines), "Dangling header")
            inst = re.fullmatch(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)', lines[i+1])
            require(inst is not None, "Native instance expected")
            scope, checksums = inst[1], [match[1], match[2]]
            require(i+2 < len(lines) and lines[i+2].startswith("ANNOTATION:"), "Empty header")
            i += 2
            continue
        note = re.fullmatch(r'ANNOTATION: "([^"\\]*)"', line)
        require(scope is not None and note is not None and i+1 < len(lines), "Unexpected native content")
        branch = re.fullmatch(r'Branch (0|[1-9][0-9]*) "([0-9]+)" "([^"\\]+)" \((0|[1-9][0-9]*)\) "([^"\\]+)"', lines[i+1])
        require(branch is not None, "Unsupported native directive")
        point = "Branch %s (%s)" % (branch[1], branch[4])
        key = scope + "|" + point
        require(key not in records, "Duplicate native record")
        records[key] = dict(scope=scope, point=point, checksum=checksums, annotation=note[1],
                            spec_checksum=branch[2], expression=branch[3], signature=branch[5], directive=lines[i+1])
        i += 2
    require(bool(records), "No native records")
    return records


def bind_native(records, expected, pilot):
    require(set(records) == set(expected), "Native record population differs")
    for key, p in expected.items():
        row = records[key]
        require(row["checksum"] == [p["module_checksum"], p["metric_checksum"]] and
                row["spec_checksum"] == p["spec_checksum"] and row["expression"] == p["expression"] and
                row["annotation"] == ANNOTATION, "Native binding differs")
        if key in pilot:
            require(row["directive"] == pilot[key]["directive"] and row["checksum"] == pilot[key]["checksum"],
                    "Observed pilot native signature differs")


def states(path, plan, stage, previous=None):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames == ["scope", "coordinate", "meta", "path", "excluded"], "Wrong audit header")
        rows = list(reader)
    expected = {(s, p["selector"]): p for s, g in plan["scopes"].items() for p in g["targets"] + g["protected"]}
    targets = {(s, p["selector"]) for s, g in plan["scopes"].items() for p in g["targets"]}
    got = {}
    for row in rows:
        key = row["scope"], row["coordinate"]
        require(key in expected and key not in got, "Extra/duplicate audit coordinate")
        sid, vid = row["coordinate"].split(",")
        require(re.fullmatch(r'(Branch|MISSING_ELSE)' + re.escape(sid) + r'\.' + re.escape(vid), row["meta"])
                and row["path"] == "Item%s.%s" % (sid, row["meta"]), "Audit native identity differs")
        require(row["excluded"] == ("1" if stage in ("selected", "reloaded") and key in targets else "0"),
                "Singleton audit state differs")
        got[key] = (row["meta"], row["path"])
    require(set(got) == set(expected), "Missing audit coordinate")
    require(previous is None or previous == got, "Metadata changed across audit stages")
    return got


def verify_artifacts(output, config):
    names = ["first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el",
             "selected_tests.txt", "DVEfiles/dve_gui.log", "live-identity.json", "execution.json"]
    names += ["states_%s.tsv" % s for s in STAGES]
    names += ["integrity-before.json", "integrity-after.json"]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths) and not (output / "DVEfiles").is_symlink(),
            "Missing/aliased artifacts")
    records = [parse_native((output / n).read_bytes()) for n in ("first.el", "second.el")]
    require(len(records[0]) == len(records[1]) == 1144, "Not exact1144")
    for rows in records:
        bind_native(rows, config["expectations"], config["pilot"])
    require(records[0] == records[1], "Full native roundtrip differs")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Reset not globally empty")
    identities = None
    for stage in STAGES:
        identities = states(output / ("states_%s.tsv" % stage), config["plan"], stage, identities)
    test = Path(config["plan"]["selected_test_vdb"])
    dirs = list((test / "snps/coverage/db/testdata").iterdir())
    require(len(dirs) == 1 and dirs[0].is_dir(), "Not one selected test")
    require((output / "selected_tests.txt").read_text().splitlines() == [str(test.with_suffix("") / dirs[0].name)],
            "Selected test differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("OP1144_CAPTURE_DONE_1144") == 1 and
            not re.search(r'OP1144_CAPTURE_FAILED|(?:^|\s)(Error|Fatal):|checksum.*mismatch', log, re.I),
            "GUI log failed/incomplete")
    for stage in STAGES:
        require(log.splitlines().count("OP1144_AUDIT %s 3636" % stage) == 1, "GUI audit marker differs")
    live = json.loads((output / "live-identity.json").read_text())
    execution = json.loads((output / "execution.json").read_text())
    require(live["executable_verified"] is True and live["executable"] == config["plan"]["tool_identity"]["executable"]
            and live["launch_pid"] == execution["launch_pid"] and
            live["launch_starttime"] == execution["launch_starttime"] and
            execution["returncode"] == 0 and execution["launch_count"] == 1, "Execution/live identity differs")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        integrity = json.loads((output / name).read_text())
        require(integrity == {field: True, "pins": config["pins"], "membership": config["plan"]["input_membership"]},
                "Integrity evidence differs")
    return dict(status="NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL", captured_tests=1,
                captured_records=1144, protected_branch_points=2492, singleton_queries=18180,
                final_reset=True, application_approval=False, native_review_approval=False,
                files={str(p): hash_file(p) for p in paths})


def config_read(output, seal):
    require(re.fullmatch("[0-9a-f]{64}", seal or "") is not None, "External config seal required")
    require(hash_file(output / "config.json") == seal, "Config seal differs")
    config = json.loads((output / "config.json").read_text())
    require(config["output"] == str(output) and config["preflight_seal"] == SEAL, "Wrong run binding")
    check_inputs(config)
    return config


def find_live(process, record, starttime):
    for path in Path("/proc").glob("[0-9]*/exe"):
        try:
            if path.resolve(strict=True) != Path(record["executable"]):
                continue
            return tool.verify_live_executable(int(path.parent.name), record, process.pid, starttime)
        except (ValueError, OSError, ProcessLookupError):
            continue
    return None


def capture(output, seal):
    config = config_read(output, seal)
    require(json.loads((output / "status.json").read_text())["status"] == "PREPARED_NO_DVE", "No repeat launch")
    require(not any((output / name).exists() for name in ("live-ready", "execution.json", "first.el", "DVEfiles")),
            "Preexisting launch/capture artifacts")
    require(config["command"] == tool.launch_command(config["plan"]["tool_identity"], TCL), "Command differs")
    status = dict(status="RUNNING", config_sha256=seal, capture_only=True, application_approval=False)
    write(output / "status.json", status)
    write(output / "integrity-before.json", dict(checked=True, pins=config["pins"],
                                               membership=config["plan"]["input_membership"]))
    process = None
    try:
        with (output / "launcher.log").open("w") as stream:
            process = subprocess.Popen(config["command"], cwd=output,
                env=environment(config["plan"]["tool_identity"], output), stdout=stream,
                stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1,
                             timeout_seconds=1800, command=config["command"])
            write(output / "execution.json", execution)
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                live = find_live(process, config["plan"]["tool_identity"], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, "No launch-bound live DVE executable")
            write(output / "live-identity.json", live)
            check_inputs(config)
            (output / "live-ready").write_text("LIVE_EXECUTABLE_VERIFIED\n")
            print("DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=1800)
            write(output / "execution.json", execution)
        require(execution["returncode"] == 0, "DVE exited nonzero")
        check_inputs(config)
        write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"],
                                                  membership=config["plan"]["input_membership"]))
        status.update(verify_artifacts(output, config))
        status["files"].update({str(output / n): hash_file(output / n) for n in
                               ("config.json", "integrity-before.json", "integrity-after.json", "selection.tcl")})
        write(output / "capture-result.json", status)
        status["capture_result_sha256"] = hash_file(output / "capture-result.json")
        print("CAPTURE_RESULT_SHA256 " + status["capture_result_sha256"], flush=True)
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "verify"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seal")
    parser.add_argument("--artifact-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), "Output outside direct out")
    if args.command == "prepare":
        prepare(output)
    elif args.command == "capture":
        capture(output, args.seal)
    else:
        require(re.fullmatch("[0-9a-f]{64}", args.artifact_seal or "") is not None,
                "External capture result seal required")
        require(hash_file(output / "capture-result.json") == args.artifact_seal, "Capture result seal differs")
        captured = json.loads((output / "capture-result.json").read_text())
        require(captured["config_sha256"] == args.seal, "Capture/config seal differs")
        for path, sha in captured["files"].items():
            require(Path(path).parent == output or Path(path).parent == output / "DVEfiles", "Foreign artifact pin")
            require(hash_file(path) == sha, "Captured artifact changed")
        result = verify_artifacts(output, config_read(output, args.seal))
        require(all(captured[k] == value for k, value in result.items() if k != "files") and
                all(captured["files"].get(k) == value for k, value in result["files"].items()), "Result differs")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
