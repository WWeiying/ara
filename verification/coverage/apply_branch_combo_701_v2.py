#!/usr/bin/env python3
"""Four-policy successor with selectable ancestors from actual raw701 Depth rows."""
import csv
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import os
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import apply_branch_combo_701 as original
from report_scope_ancestors import report_ancestors

SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix(".tcl")
TEST = SCRIPT.with_name("test_apply_branch_combo_701_v2.py")
COORDINATES = original.OUT / "four-policy-coordinate-audit-701-20261006-01.json"
COORDINATE_SEAL = "35bb77432beac3857e7b95ee69a951e1208d62ddefd55bb1a8d988b9a3888033"
prepare_original = original.prepare
verify_original = original.verify_artifacts
read_original = original.read_config


def active_scopes(groups):
    targets = set()
    for group in original.GROUPS:
        for scope, records in groups[group]["plan"]["scopes"].items():
            wanted = bool(records["targets"]) if group == "operand" else any(
                row["target"] for rows in records.values() for row in rows)
            if wanted:
                targets.add(scope)
    original.require(len(targets) == 66, "Active target scope count differs; protected-only WIDTH64 must remain protected")
    return targets


def report_binding(groups):
    import apply_qbs_rooted_701 as q
    reference = q.reference_rows(q.RAW701 / "summary.csv")
    roots = report_ancestors(list(reference.values()), active_scopes(groups))
    original.require(all(root in reference and (root == "ara_tb" or root.startswith("ara_tb.")) for root in roots),
                     "Absent or external aggregate root")
    return roots, {root: reference[root]["Name"] for root in roots}


def rooted_rows(path, roots, names, reference):
    header = ["Stage", "RequestedScope", "Token", "Handle", "GUIPath", "Name", "Branch", "Score"]
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        original.require(reader.fieldnames == header, "Aggregate rooted schema differs")
        rows = list(reader)
    found = {}
    for row in rows:
        original.require(None not in row and all(row.values()), "Partial rooted row")
        key = row["Stage"], row["RequestedScope"]
        original.require(key[0] in ("raw", "applied", "reset") and key[1] in names and key not in found,
                         "Extra/duplicate rooted observation")
        original.require(row["Token"] == key[1] and row["Handle"] != "0" and row["GUIPath"] == row["Name"]
                         and row["Name"] in (names[key[1]], key[1].split(".")[-1]), "Precise LOCAL root binding differs")
        for metric in ("Branch", "Score"):
            value = row[metric]
            original.require(value == "NA" or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", value) is not None,
                             "Invalid rooted value")
            if value != "NA":
                original.require(Decimal(value[:-1]) <= 100, "Rooted value out of range")
        found[key] = row
    original.require(set(found) == {(stage, scope) for stage in ("raw", "applied", "reset") for scope in roots},
                     "Missing actual report root")
    for scope in roots:
        for metric in ("Branch", "Score"):
            raw = found["raw", scope][metric]
            applied = found["applied", scope][metric]
            original.require(raw == found["reset", scope][metric] == reference[scope][metric], "Raw/reset/reference root value differs")
            if raw == "NA":
                original.require(applied == "NA", "NA ancestor became a numeric metric")
            else:
                original.require(applied != "NA" and Decimal(applied[:-1]) >= Decimal(raw[:-1]), "Rooted metric regressed")
    system = "ara_tb.dut.i_ara_soc.i_system"
    original.require(Decimal(found["applied", system]["Branch"][:-1]) > Decimal(found["raw", system]["Branch"][:-1]),
                     "No actual combined i_system Branch increase")
    return rows


def prepare(output, qbs_result_seal, rebind_seal):
    original.require(original.sha(COORDINATES) == COORDINATE_SEAL, "Coordinate preflight seal differs")
    diagnostic = json.loads(COORDINATES.read_bytes())
    original.require(diagnostic["status"] == "FOUR_POLICY_COORDINATES_DISJOINT_NOT_APPLICATION_APPROVAL"
                     and diagnostic["tests"] == 701 and diagnostic["unique_targets"] == 4328
                     and diagnostic["target_counts"] == dict(operand1144=1144, debug1832=1832, ff1_904=904, qbs448=448)
                     and diagnostic["target_hits"] == dict(operand1144=0, debug1832=408, ff1_904=0, qbs448=0)
                     and diagnostic["application_approval"] is False, "Coordinate preflight differs")
    for path, value in diagnostic["pins"].items():
        original.require(original.sha(path) == value, "Coordinate diagnostic pin differs")
    prepare_original(output, qbs_result_seal, rebind_seal)
    config = json.loads((output / "config.json").read_bytes())
    roots, names = report_binding(config["groups"])
    config["root_refresh_scopes"] = roots
    config["root_display_names"] = names
    config["actual_depth_ancestor_binding"] = True
    config["coordinate_diagnostic_sha256"] = COORDINATE_SEAL
    config["run_timeout_seconds"] = 7200
    config["timeout_basis"] = "12610 singleton checks per phase, four phases; nearly three times the 4238-per-phase QBS application, with one fixed bounded run"
    selection = "set qbsrefresh_scopes {" + " ".join("{" + r + "}" for r in roots) + "}\n"
    selection += "global combo_root_names\narray unset combo_root_names\narray set combo_root_names {" + " ".join(
        "{" + r + "} {" + names[r] + "}" for r in roots) + "}\n"
    (output / "root-selection.tcl").write_text(selection)
    text = (original.HERE / "apply_branch_combo_701.tcl").read_text()
    marker = "set failed [catch {qbsapp_session} message]"
    original.require(text.count(marker) == 1, "Frozen combination boundary differs")
    (output / "combo-library.tcl").write_text(text.split(marker)[0])
    paths = [SCRIPT, TCL, TEST, original.HERE / "apply_branch_combo_701.py", original.HERE / "apply_branch_combo_701.tcl",
             original.HERE / "test_apply_branch_combo_701.py", original.HERE / "report_scope_ancestors.py",
             original.HERE / "test_report_scope_ancestors.py", COORDINATES, output / "combo-library.tcl"]
    for path in paths:
        original.pin(config["pins"], path)
    for path, value in diagnostic["pins"].items():
        original.pin(config["pins"], path, value)
    # The intermediate prepare has not been launched; replace only our newly
    # generated selection pin with the actual Depth-stack selection bytes.
    config["pins"][str(output / "root-selection.tcl")] = original.sha(output / "root-selection.tcl")
    import apply_qbs_rooted_701 as q
    q.base.capture.check_inputs(config)
    original.write(output / "config.json", config)
    value = original.sha(output / "config.json")
    original.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=value,
                                                aggregate_admission=False, actual_depth_ancestors=True))
    print("FOUR_POLICY701_V2_FINAL_SEAL " + value)


def verify_artifacts(output, config):
    import apply_qbs_rooted_701 as q
    roots, names = report_binding(config["groups"])
    original.require(config.get("actual_depth_ancestor_binding") is True and config["root_refresh_scopes"] == roots
                     and config["root_display_names"] == names, "Aggregate actual report-root binding differs")
    reference = q.reference_rows(q.RAW701 / "summary.csv")
    previous = q.previous.pilot.rooted_rows
    try:
        q.previous.pilot.rooted_rows = lambda path, requested: rooted_rows(path, requested, names, reference)
        result = verify_original(output, config)
    finally:
        q.previous.pilot.rooted_rows = previous
    active = active_scopes(config["groups"])
    for change in result["summary_changes"]:
        original.require(any(scope == change["scope"] or scope.startswith(change["scope"] + ".") for scope in active),
                         "Protected-only scope metric changed")
    result["actual_report_ancestors"] = roots
    result["coordinate_precheck_sha256"] = config["coordinate_diagnostic_sha256"]
    result["files"][str(output / "combo-library.tcl")] = original.sha(output / "combo-library.tcl")
    execution = json.loads((output / "execution.json").read_bytes())
    original.require(execution["timeout_seconds"] == config["run_timeout_seconds"] == 7200, "Bounded execution contract differs")
    return result


def read_config(output, seal):
    config = read_original(output, seal)
    roots, names = report_binding(config["groups"])
    original.require(config.get("actual_depth_ancestor_binding") is True and config["root_refresh_scopes"] == roots
                     and config["root_display_names"] == names and config["run_timeout_seconds"] == 7200,
                     "Unqualified aggregate root/timeout contract")
    return config


def run(output, seal):
    import capture_operand_1144 as lifecycle
    config = read_config(output, seal)
    original.require(json.loads((output / "status.json").read_bytes())["status"] == "PREPARED_NO_DVE", "No repeat launch")
    original.require(not any((output / n).exists() for n in ("live-ready", "execution.json", "DVEfiles")), "Preexisting run artifacts")
    record = config["plan"]["tool_identity"]
    original.require(config["command"] == lifecycle.tool.launch_command(record, TCL), "Combo launch command differs")
    status = dict(status="RUNNING", config_sha256=seal, application_approval=False, aggregate_admission=False)
    original.write(output / "status.json", status)
    original.write(output / "integrity-before.json", dict(checked=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
    process = None
    try:
        env = lifecycle.environment(record, output)
        for name in ("DVE_REVIEWED_WAIVERS", "DEBUG_CAPTURE_SEAL", "OP1144_BASE_HOOK", "OBD_SELECTION", "FF1_CAPTURE_SEAL"):
            env.pop(name, None)
        with (output / "launcher.log").open("w") as stream:
            process = subprocess.Popen(config["command"], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = lifecycle.tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=start, launch_count=1,
                             timeout_seconds=config["run_timeout_seconds"], command=config["command"])
            original.write(output / "execution.json", execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, record, start)
                if live:
                    break
                time.sleep(0.2)
            original.require(live is not None, "No launch-bound actual DVE executable")
            original.write(output / "live-identity.json", live)
            lifecycle.check_inputs(config)
            (output / "live-ready").write_text("LIVE_EXECUTABLE_VERIFIED\n")
            print("FOUR_POLICY_DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=config["run_timeout_seconds"])
            original.write(output / "execution.json", execution)
        original.require(execution["returncode"] == 0, "Combined DVE exited nonzero")
        lifecycle.check_inputs(config)
        original.write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
        status.update(verify_artifacts(output, config))
        status["files"].update({str(output / n): original.sha(output / n) for n in ("config.json", "selection.tcl")})
        original.write(output / "capture-result.json", status)
        status["capture_result_sha256"] = original.sha(output / "capture-result.json")
        print("FOUR_POLICY_RESULT_SHA256 " + status["capture_result_sha256"], flush=True)
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
        original.write(output / "status.json", status)


original.SCRIPT, original.TCL, original.TEST = SCRIPT, TCL, TEST
original.prepare, original.verify_artifacts, original.read_config = prepare, verify_artifacts, read_config
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("command", choices=("run",))
        parser.add_argument("--output", type=Path, required=True)
        parser.add_argument("--seal", required=True)
        args = parser.parse_args()
        directory = args.output.absolute()
        original.require(directory.parent.resolve() == original.OUT.resolve() and not directory.is_symlink(), "Unsafe run output")
        run(directory, args.seal)
    else:
        original.main()
