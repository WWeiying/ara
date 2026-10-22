#!/usr/bin/env python3
"""Exact source-reviewed debug Branch application, independent of functional waivers."""
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
import capture_operand_debug_branch_v5 as qualification

base = qualification.base
debug = base.debug
tool = base.capture.tool
HERE = Path(__file__).resolve().parent
OUT = debug.OUT
NATIVE = OUT / "operand-debug-branch-native1832-20261006-02"
NATIVE_SEAL = "bd29afc080af54891b4c8a35e86a396e7e16ab88783211bad12d5fd6221f84d1"
RAW = OUT / "raw701-dve-20261006-01"
CORPUS = OUT / "gap94-offline-admitted-701-20261006-01"
HOOK = HERE / "apply_operand_debug_1832.tcl"
require = base.require
sha = base.sha
write = base.write


def summaries(path):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(set(reader.fieldnames)) == len(reader.fieldnames) and
                {"Name", "Depth", "Score", "Branch", "Condition", "Line", "Toggle", "FSM"} <= set(reader.fieldnames),
                "Incomplete hierarchy schema")
        rows = list(reader)
    result, stack = {}, []
    for row in rows:
        depth = int(row["Depth"])
        require(0 <= depth <= len(stack) and row["Name"] and None not in row, "Invalid hierarchy row")
        # Generate labels may contain dots: stack positions, not name splitting, define depth.
        stack = stack[:depth] + [row["Name"]]
        scope = ".".join(stack)
        require(scope not in result, "Duplicate reconstructed hierarchy scope")
        result[scope] = row
    require(bool(result), "Empty hierarchy")
    return result


def merge_roots(table, roots, config):
    rows = summaries(table)
    with Path(roots).open(newline="") as stream:
        reader = csv.DictReader(stream)
        actual = list(reader)
    require(len(actual) == len(config["report_roots"]) and {r["Scope"] for r in actual} == set(config["report_roots"]),
            "Missing/extra rooted refresh")
    for row in actual:
        scope = row["Scope"]
        require(scope in rows and row["Handle"] and row["LocalPath"] == row["LocalName"] and
                row["LocalPath"] in {scope.rsplit(".", 1)[-1], rows[scope]["Name"]}, "Root identity mismatch")
        require(set(row) == {"Scope", "LocalPath", "LocalName", "Handle"} | (set(rows[scope]) - {"Name", "Depth"}),
                "Root column schema differs")
        for metric in set(rows[scope]) - {"Name", "Depth"}:
            rows[scope][metric] = row[metric]
    return rows


def check(config):
    for path, expected in config["pins"].items():
        require(sha(path) == expected, "Pin differs: " + path)
    for root, members in config["membership"].items():
        require(base.capture.proof.tree_members(root) == members, "VDB membership differs")
    tool.revalidate(config["tool_identity"])


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    require(mode in ("pilot", "full") and output.parent == OUT and not output.exists(), "Fresh direct output required")
    native = base.config_read(NATIVE, NATIVE_SEAL)
    expected = base.verify_artifacts(NATIVE, native)
    saved = json.loads((NATIVE / "capture-result.json").read_bytes())
    require(saved["config_sha256"] == NATIVE_SEAL and
            all(saved.get(k) == v for k, v in expected.items() if k != "files") and
            all(saved["files"].get(k) == v for k, v in expected["files"].items()) and
            set(saved["files"]) == set(expected["files"]) | {str(NATIVE / "config.json"), str(NATIVE / "selection.tcl")},
            "Native qualification changed")
    require(native["targets"] == {"branch": 1832} and native["protected"] == {"branch": 1176}, "Wrong qualified population")
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased evidence: " + str(path))
        value = sha(path)
        require(expected is None or value == expected, "Evidence hash differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Conflicting evidence pin")
        pins[str(path)] = value
        return path
    for path, expected in native["pins"].items():
        pin(path, expected)
    for path, expected in saved["files"].items():
        pin(path, expected)
    pin(NATIVE / "capture-result.json")
    population = json.loads(pin(RAW / "population-verification.json").read_bytes())
    require(population["status"] == "VERIFIED_HISTORICAL_RAW_REPORT" and population["admitted_tests"] == 701 and
            population["current_RTL_signoff"] is False, "Not verified701 raw report")
    for path, expected in population["pins"].items():
        pin(path, expected)
    status = json.loads(pin(CORPUS / "status.json").read_bytes())
    require(status["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and status["aggregate_passed"] == 701,
            "701 corpus not admitted")
    bitmap = json.loads(pin(CORPUS / "combined-bits.json").read_bytes())
    listing = pin(CORPUS / "combined-inputs.txt").read_text().splitlines()
    require(len(listing) == len(set(listing)) == 702 and listing[1:] == bitmap["tests"] and
            listing == (RAW / "inputs.txt").read_text().splitlines() and listing[0] == native["plan"]["design_vdb"],
            "701 corpus/design membership differs")
    require(len({str(Path(p).resolve()) for p in listing}) == 702, "Aliased VDB inputs")
    for path, expected in bitmap["input_hashes"].items():
        pin(path, expected)
    design = debug.inventory.Design(Path(listing[0]))
    for relative, expected in bitmap["design"].items():
        pin(Path(listing[0]) / "snps/coverage/db" / relative, expected)
    counts = {}
    for scope, metrics in native["plan"]["scopes"].items():
        source = design.source(scope)
        require(source["resolved_path"] == str(debug.inventory.SOURCE), "Source owner changed")
        require(sha(debug.inventory.SOURCE) == debug.inventory.SOURCE_SHA, "Old source pin changed")
        record = bitmap["metrics"]["branch"].get(scope)
        require(record is not None, "Missing metric is not unreachability evidence")
        definition = design.definition(scope, "branch")
        require(record["width"] == 752 and record["checksum"] == definition.get("chksum"), "Metric binding differs")
        points = debug.inventory.points("branch", definition, record["width"])
        require(len(points) == len(metrics["branch"]) == 752, "Compiled inventory width differs")
        hits = 0
        for point, row in zip(points, metrics["branch"]):
            eligible = debug.inventory.contained(point, "branch")
            if eligible:
                require(debug.complete(point, "branch", source["file_id"]), "Incomplete debug region object")
            rebuilt = dict(point=point, coordinate=debug.coordinate(point, "branch"), target=eligible,
                           module_checksum=source["definition_checksum"], metric_checksum=record["checksum"])
            require(rebuilt == row, "Exact source/compiled target identity differs")
            if eligible:
                hits += bool(int(record["bits"], 16) & (1 << (record["width"] - 1 - point["raw_index"])))
        counts[scope] = dict(targets=sum(r["target"] for r in metrics["branch"]), target_hits=hits)
    reference = summaries(RAW / "summary.csv")
    target_scopes = set(native["plan"]["scopes"])
    roots = [s for s in reference if any(t == s or t.startswith(s + ".") for t in target_scopes)]
    require(target_scopes <= set(roots) and "ara_tb.dut.i_ara_soc.i_system" in roots, "Missing report scope")
    selected, membership = [], {}
    for root in listing:
        membership[root] = base.capture.proof.tree_members(root)
        for relative in membership[root]:
            pin(Path(root) / relative)
        if root == listing[0]:
            continue
        dirs = list((Path(root) / "snps/coverage/db/testdata").iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir(), "Ambiguous test VDB")
        selected.append(str(Path(root).with_suffix("") / dirs[0].name))
    require(len(set(selected)) == 701 and selected == (RAW / "selected_tests.txt").read_text().splitlines(),
            "Actual raw701 selected tests differ")
    sample = native["plan"]["selected_test_vdb"]
    require(sample in listing[1:], "Qualified single test not in701")
    if mode == "pilot":
        index = listing[1:].index(sample)
        active_inputs, active_tests = [sample], [selected[index]]
    else:
        require(pilot is not None and sha(pilot / "config.json") == pilot_seal and
                sha(pilot / "application-result.json") == pilot_result_seal, "External real pilot seals required")
        old = read_config(pilot, pilot_seal)
        outcome = verify(pilot, old)
        recorded = json.loads((pilot / "application-result.json").read_bytes())
        require(old["mode"] == "pilot" and all(recorded.get(k) == v for k, v in outcome.items()), "Real pilot not verified")
        for path, expected in recorded["files"].items():
            pin(path, expected)
        pin(pilot / "application-result.json", pilot_result_seal)
        active_inputs, active_tests = listing[1:], selected
    for path in (Path(__file__), HOOK, HERE / "test_apply_operand_debug_1832.py", HERE / "capture_operand_debug.tcl"):
        pin(path)
    identity = native["plan"]["tool_identity"]
    tool.revalidate(identity)
    output.mkdir()
    selection = debug.selection(native["plan"])
    for name, values in (("databases", active_inputs), ("tests", active_tests), ("roots", roots)):
        selection += "set obd_%s {%s}\n" % (name, " ".join(base.capture.literal(v) for v in values))
    selection += "set obd_native " + base.capture.literal(str(NATIVE / "first.el")) + "\n"
    (output / "selection.tcl").write_text(selection)
    (output / "inputs.txt").write_text("\n".join([listing[0]] + active_inputs) + "\n")
    pin(output / "selection.tcl")
    pin(output / "inputs.txt")
    config = dict(mode=mode, output=str(output), native_seal=NATIVE_SEAL, native_config=native,
                  pins=pins, membership=membership, tool_identity=identity, selected_tests=active_tests,
                  report_roots=roots, raw_reference=str(RAW / "summary.csv"), corpus_tests=701,
                  classification="Reviewed nonfunctional instrumentation, not unreachable assertions/functions",
                  target_hit_counts_701=counts, command=tool.launch_command(identity, HOOK))
    check(config)
    write(output / "config.json", config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode))
    print("PREPARED config_sha256=" + seal, flush=True)


def read_config(output, seal):
    require(re.fullmatch(r"[0-9a-f]{64}", seal or "") and sha(output / "config.json") == seal, "External config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["output"] == str(output) and config["native_seal"] == NATIVE_SEAL and config["corpus_tests"] == 701,
            "Wrong application config")
    check(config)
    return config


def verify(output, config):
    require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Selected tests differ")
    require(len(config["selected_tests"]) == (1 if config["mode"] == "pilot" else 701), "Wrong population")
    expected = qualification.bind_native((NATIVE / "first.el").read_bytes(), config["native_config"])
    for name in ("applied.el", "after-refresh.el"):
        require(qualification.bind_native((output / name).read_bytes(), config["native_config"]) == expected,
                "Exact1832 complete native signatures changed")
    identities = None
    for stage, mode in (("raw", "before"), ("applied", "selected"), ("after", "selected"), ("reset", "reset"), ("final", "final")):
        identities = base.audit_states(output / ("states_" + stage + ".tsv"), config["native_config"], mode, identities)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Reset not globally empty")
    reports = {s: merge_roots(output / ("table_" + s + ".csv"), output / ("roots_" + s + ".csv"), config)
               for s in ("raw", "applied", "reset")}
    require(reports["raw"] == reports["reset"], "Rooted raw/reset report differs")
    if config["mode"] == "full":
        require(reports["raw"] == summaries(config["raw_reference"]), "Independent raw701 report differs")
    require(set(reports["applied"]) == set(reports["raw"]), "Hierarchy membership changed")
    changes = []
    for scope, row in reports["raw"].items():
        for metric, value in row.items():
            other = reports["applied"][scope][metric]
            if value != other:
                require(scope in config["report_roots"] and metric in ("Branch", "Score"), "Unexpected report change")
                changes.append(dict(scope=scope, metric=metric, raw=value, applied=other))
    require(changes and any(r["scope"] == "ara_tb.dut.i_ara_soc.i_system" and r["metric"] == "Branch" for r in changes),
            "No actual refreshed i_system Branch observation")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("OBD_DONE_RESET") == 1 and not re.search(
        r'OBD_FAILED|OBD_CLEANUP_ERROR|EK-CMD-|UCAPI-DLMA|DVCDT136|invalid command name|(?:^|\s)(Error|Fatal):', log), "GUI application failed")
    for stage in ("raw", "applied", "after", "reset", "final"):
        require(log.splitlines().count("OBD_AUDIT %s 3008" % stage) == 1, "Incomplete protected audit")
    execution = json.loads((output / "execution.json").read_bytes())
    live = json.loads((output / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and
            live["executable_verified"] is True and live["launch_pid"] == execution["launch_pid"] and
            live["launch_starttime"] == execution["launch_starttime"] and live["executable"] == config["tool_identity"]["executable"],
            "Live execution identity differs")
    files = [p for p in output.iterdir() if p.is_file() and p.name not in ("status.json", "application-result.json")]
    files.append(output / "DVEfiles/dve_gui.log")
    return dict(status="EXACT1832_SINGLE_TEST_ROOTED_APPLICATION_PILOT_VERIFIED" if config["mode"] == "pilot" else
                "FULL701_EXACT1832_DEBUG_BRANCH_ROOTED_APPLICATION_REPORT_VERIFIED", tests=len(config["selected_tests"]),
                targets=1832, protected=1176, final_reset=True, other_policy_imported=False, current_RTL_signoff=False,
                target_hit_counts_701=config["target_hit_counts_701"], summary_deltas=changes,
                files={str(p): sha(p) for p in files})


def run(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / "status.json").read_bytes())["status"] == "PREPARED_NO_DVE" and
            not (output / "execution.json").exists(), "No repeated launch")
    require(config["command"] == tool.launch_command(config["tool_identity"], HOOK), "Unexpected launch command")
    status = dict(status="RUNNING", config_sha256=seal, mode=config["mode"])
    write(output / "status.json", status)
    process = None
    try:
        env = tool.controlled_environment(config["tool_identity"], os.environ)
        env.pop("DVE", None)
        env.update(DVE_COVERAGE_OUTPUT=str(output), OBD_SELECTION=str(output / "selection.tcl"))
        with (output / "launcher.log").open("w") as log:
            process = subprocess.Popen(config["command"], cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1)
            write(output / "execution.json", execution)
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                live = base.capture.find_live(process, config["tool_identity"], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, "No launch-bound live DVE executable")
            write(output / "live-identity.json", live)
            check(config)
            (output / "live-ready").write_text("LIVE_ELF_VERIFIED\n")
            print("LIVE_DVE pid=" + str(live["pid"]), flush=True)
            execution["returncode"] = process.wait(timeout=2400)
            write(output / "execution.json", execution)
        check(config)
        result = verify(output, config)
        result["config_sha256"] = seal
        write(output / "application-result.json", result)
        status.update(status=result["status"], application_result_sha256=sha(output / "application-result.json"))
        print(json.dumps(status), flush=True)
    except Exception as error:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        status.update(status="FAILED", reason=str(error))
        raise
    finally:
        write(output / "status.json", status)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--seal")
    parser.add_argument("--result-seal")
    parser.add_argument("--pilot", type=Path)
    parser.add_argument("--pilot-seal")
    parser.add_argument("--pilot-result-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and not output.is_symlink(), "Unsafe output path")
    if args.command == "prepare":
        prepare(output, args.mode, args.pilot.absolute() if args.pilot else None, args.pilot_seal, args.pilot_result_seal)
    elif args.command == "run":
        run(output, args.seal)
    else:
        require(sha(output / "application-result.json") == args.result_seal, "External result seal differs")
        saved = json.loads((output / "application-result.json").read_bytes())
        for path, expected in saved["files"].items():
            require(sha(path) == expected, "Application artifact differs")
        regenerated = verify(output, read_config(output, args.seal))
        require(all(saved.get(k) == v for k, v in regenerated.items()), "Independent application verification differs")
        print("EXACT1832_APPLICATION_REVERIFIED")


if __name__ == "__main__":
    main()
