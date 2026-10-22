#!/usr/bin/env python3
"""Exact1144-only application on full690; no legacy16 or other waiver additions."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import capture_operand_1144 as native
import seal_operand_1144_preflight as proof
import dve_tool_identity as tool

HERE = Path(__file__).resolve().parent
OUT = proof.OUT
QUALIFICATION = OUT / "operand-native-static-qualification-690-20261006-01"
QUALIFICATION_SEAL = "28b37e48ad7fad4b8663fb8cd39c0de758f122ef1d4bca0709286c86767004b0"
TCL = HERE / "apply_operand_1144_690.tcl"
require = proof.require


def check(config):
    for path, sha in config["pins"].items():
        require(native.hash_file(path) == sha, "Pin differs: " + path)
    for root, members in config["membership"].items():
        require(proof.tree_members(root) == members, "VDB membership differs")
    tool.revalidate(config["tool_identity"])


def prepare(output, seal):
    require(seal == QUALIFICATION_SEAL, "External qualification seal differs")
    require(output.parent == OUT and not output.exists(), "Fresh direct out required")
    pins = {}
    manifest = proof.load_bound(QUALIFICATION / "manifest.sha256.json", pins, seal)
    require(set(manifest) == {"qualification.json", "qualified-records.json"}, "Wrong qualification members")
    for name, sha in manifest.items():
        proof.read_bound(QUALIFICATION / name, pins, sha)
    qualification = proof.load_bound(QUALIFICATION / "qualification.json", pins)
    qualified = proof.load_bound(QUALIFICATION / "qualified-records.json", pins)["records"]
    require(qualification["status"] == "NATIVE_STATIC_1144_QUALIFIED_FOR_EXACT_OLD_DESIGN_NOT_APPLIED" and
            qualification["points"] == len(qualified) == 1144 and qualification["target_corpus_tests"] == 690 and
            qualification["selected_hits_690"] == 0, "Wrong qualification")
    for path, sha in qualification["pins"].items():
        proof.read_bound(path, pins, sha)
    capture = proof.load_bound(Path(qualification["native_file"]).parent / "config.json", pins,
                               qualification["config_sha256"])
    plan = capture["plan"]
    require(set((p["scope"], p["point"]) for p in qualified) ==
            {(s, p["point"]) for s, g in plan["scopes"].items() for p in g["targets"]}, "Scope target set differs")
    listing = proof.read_bound(qualification["corpus_input_list"], pins).decode().splitlines()
    require(listing == [plan["design_vdb"]] + qualification["corpus_tests"] and len(listing) == 691, "Not exact690 inputs")
    bitmap = proof.load_bound(Path(qualification["corpus_input_list"]).parent / "combined-bits.json", pins)
    require(bitmap["tests"] == listing[1:] and bitmap["design"] == qualification["corpus_design"], "690 bitmap binding differs")
    for path, sha in bitmap["input_hashes"].items():
        proof.read_bound(path, pins, sha)
    selected, membership = [], {}
    for root in listing:
        membership[root] = proof.tree_members(root)
        for name in membership[root]:
            proof.read_bound(Path(root) / name, pins)
        if root == listing[0]:
            continue
        testroot = Path(root) / "snps/coverage/db/testdata"
        dirs = sorted(p for p in testroot.iterdir() if p.is_dir())
        require(len(dirs) == 1, "Each test VDB must contain exactly one test")
        selected.append(str(Path(root).with_suffix("") / dirs[0].name))
    require(len(selected) == len(set(selected)) == 690 and len(set(listing)) == 691 and
            len({str(Path(p).resolve()) for p in listing}) == 691, "Duplicate/alias input")
    for path in (Path(__file__), TCL, HERE / "test_apply_operand_1144_690.py", HERE / "capture_operand_1144.py",
                 HERE / "capture_operand_1144.tcl", HERE / "seal_operand_1144_preflight.py", HERE / "dve_tool_identity.py"):
        proof.read_bound(path, pins)
    record = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    for row in record["files"]:
        proof.read_bound(row["path"], pins, row["sha256"])
    output.mkdir()
    script = native.selection(plan)
    for name, rows in (("databases", listing[1:]), ("tests", selected)):
        script += "set opapp_%s {%s}\n" % (name, " ".join(native.literal(p) for p in rows))
    script += "set opapp_native " + native.literal(qualification["native_file"]) + "\n"
    (output / "selection.tcl").write_text(script)
    (output / "inputs.txt").write_text("\n".join(listing) + "\n")
    for path in (output / "selection.tcl", output / "inputs.txt"):
        proof.read_bound(path, pins)
    config = dict(output=str(output), qualification_sha256=seal, plan=plan, qualified=qualified,
                  selected_tests=selected, inputs=listing, membership=membership, pins=pins, tool_identity=record,
                  command=tool.launch_command(record, TCL), expected_additions=1144,
                  baseline="NO_WAIVERS; previously reviewed16 are not automatically imported")
    check(config)
    native.write(output / "config.json", config)
    config_sha = native.hash_file(output / "config.json")
    native.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=config_sha))
    print("PREPARED_NO_DVE config_sha256=" + config_sha, flush=True)


def summaries(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
                {"Name", "Depth", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"} <= set(reader.fieldnames),
                "Incomplete summary columns")
        rows = list(reader)
    tree, result = [], {}
    for row in rows:
        depth = int(row["Depth"])
        require(0 <= depth <= len(tree) and row["Name"] and None not in row, "Invalid summary hierarchy")
        tree = tree[:depth] + [row["Name"]]
        scope = ".".join(tree)
        require(scope not in result, "Duplicate summary scope")
        result[scope] = row
    require(bool(result), "Empty summary")
    return result


def summary_deltas(raw, applied, reset, scopes):
    require(raw == reset and set(raw) == set(applied), "Reset summary or membership differs")
    changes = []
    for scope, row in raw.items():
        require(set(row) == set(applied[scope]), "Summary schema differs")
        affected = any(target == scope or target.startswith(scope + ".") for target in scopes)
        for metric, value in row.items():
            if value != applied[scope][metric]:
                require(affected and metric in ("Branch", "Score"), "Unexpected summary metric/scope change")
                changes.append(dict(scope=scope, metric=metric, raw=value, applied=applied[scope][metric]))
    require(bool(changes), "No actual applied report change")
    return changes


def verify_artifacts(output, config):
    rows = native.parse_native((output / "applied.el").read_bytes())
    qualified = {(p["scope"]+"|"+p["point"]): p for p in config["qualified"]}
    require(set(rows) == set(qualified) and len(rows) == 1144, "Applied EL not exact1144")
    for key, p in qualified.items():
        actual = rows[key]
        saved = p["native"]
        require(actual["checksum"] == saved["checksum"] and actual["directive"] == saved["native_directive"]
                and actual["signature"] == saved["native_signature"] and actual["annotation"] == native.ANNOTATION,
                "Applied native signature differs")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Not globally empty")
    identities = None
    for phase, stage in (("raw", "before"), ("applied", "selected"), ("reset", "reset"), ("final", "final")):
        identities = native.states(output / ("states_%s.tsv" % phase), config["plan"], stage, identities)
    require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Not exact690 selected tests")
    raw, applied, reset = (summaries(output / ("summary_%s.csv" % stage)) for stage in ("raw", "applied", "reset"))
    deltas = summary_deltas(raw, applied, reset, config["plan"]["scopes"])
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("OPAPP_DONE_EXACT1144_FULL690") == 1 and
            log.splitlines().count("OPAPP_HELPERS_READY") == 1 and
            log.splitlines().count("OPAPP_NATIVE_REVIEW_EMPTY") == 1 and
            not re.search(r'OPAPP_FAILED|EK-CMD-|invalid command name|(?:^|\s)(Error|Fatal):|checksum.*mismatch', log, re.I),
            "Incomplete/failed GUI application")
    for stage in ("raw", "applied", "reset", "final"):
        require(log.splitlines().count("OP1144_AUDIT %s 3636" % stage) == 1, "Missing exact state audit")
    live = json.loads((output / "live-identity.json").read_text())
    execution = json.loads((output / "execution.json").read_text())
    require(live["executable_verified"] is True and live["executable"] == config["tool_identity"]["executable"] and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"] and
            execution["returncode"] == 0 and execution["launch_count"] == 1, "Execution identity differs")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        integrity = json.loads((output / name).read_text())
        require(integrity == {field: True, "pins": config["pins"], "membership": config["membership"]},
                "Integrity evidence differs")
    names = ["applied.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
             "DVEfiles/dve_gui.log", "live-identity.json", "execution.json", "config.json", "inputs.txt", "selection.tcl",
             "integrity-before.json", "integrity-after.json"]
    names += ["summary_%s.csv" % s for s in ("raw", "applied", "reset")]
    names += ["states_%s.tsv" % s for s in ("raw", "applied", "reset", "final")]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing/aliased artifact")
    return dict(status="FULL690_EXACT1144_APPLICATION_REPORT_VERIFIED", tests=690, added_exclusions=1144,
                prior16_imported=False, protected_branch_points=2492, final_reset=True,
                summary_deltas=deltas, report_scope="old pinned image only; no current RTL signoff",
                files={str(p): native.hash_file(p) for p in paths})


def read_config(output, seal):
    require(re.fullmatch("[0-9a-f]{64}", seal or "") is not None and native.hash_file(output / "config.json") == seal,
            "External config seal differs")
    config = json.loads((output / "config.json").read_text())
    require(config["output"] == str(output) and config["qualification_sha256"] == QUALIFICATION_SEAL, "Wrong config binding")
    check(config)
    return config


def run(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / "status.json").read_text())["status"] == "PREPARED_NO_DVE" and
            not (output / "execution.json").exists() and not (output / "live-ready").exists(), "No repeated launch")
    require(config["command"] == tool.launch_command(config["tool_identity"], TCL), "Unexpected command")
    status = dict(status="RUNNING", config_sha256=seal, tests=690, expected_additions=1144)
    native.write(output / "status.json", status)
    native.write(output / "integrity-before.json", dict(checked=True, pins=config["pins"], membership=config["membership"]))
    process = None
    try:
        env = tool.controlled_environment(config["tool_identity"], os.environ)
        env.pop("DVE", None)
        env.update(DVE_COVERAGE_OUTPUT=str(output), OP1144_BASE_HOOK=str(HERE / "capture_operand_1144.tcl"))
        with (output / "launcher.log").open("w") as stream:
            process = subprocess.Popen(config["command"], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1, timeout_seconds=2400)
            native.write(output / "execution.json", execution)
            deadline = time.monotonic()+60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                live = native.find_live(process, config["tool_identity"], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, "No launch-bound live DVE ELF")
            native.write(output / "live-identity.json", live)
            check(config)
            (output / "live-ready").write_text("LIVE_ELF_VERIFIED\n")
            print("DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=2400)
            native.write(output / "execution.json", execution)
        require(execution["returncode"] == 0, "DVE exited nonzero")
        check(config)
        native.write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"], membership=config["membership"]))
        status.update(verify_artifacts(output, config))
        native.write(output / "application-result.json", status)
        status["application_result_sha256"] = native.hash_file(output / "application-result.json")
        print("APPLICATION_RESULT_SHA256 " + status["application_result_sha256"], flush=True)
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
        native.write(output / "status.json", status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal", required=True)
    parser.add_argument("--result-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and not output.is_symlink(), "Output outside direct out")
    if args.command == "prepare":
        prepare(output, args.seal)
    elif args.command == "run":
        run(output, args.seal)
    else:
        require(re.fullmatch("[0-9a-f]{64}", args.result_seal or "") is not None and
                native.hash_file(output / "application-result.json") == args.result_seal, "External result seal differs")
        result = json.loads((output / "application-result.json").read_text())
        for path, sha in result["files"].items():
            require(native.hash_file(path) == sha, "Application artifact differs")
        found = verify_artifacts(output, read_config(output, args.seal))
        require(all(result[k] == v for k,v in found.items()), "Regenerated result differs")
        print("FULL690_APPLICATION_REVERIFIED")


if __name__ == "__main__":
    main()
