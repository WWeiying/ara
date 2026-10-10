#!/usr/bin/env python3
"""Single historical PASS native qualification, not aggregate waiver admission."""
import argparse
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_operand_1144 as capture
import inventory_operand_debug as inventory
import dve_tool_identity as tool
from audit_readonly import sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "verification/out"
TCL = HERE / "capture_operand_debug.tcl"
TEST = HERE / "test_capture_operand_debug.py"
BASE = OUT / "gap83-offline-admitted-690-20261006-02"
INVENTORY = OUT / "operand-debug-inventory-690-20261006-01.json"
REVIEW = OUT / "operand-debug-noninterference-review-690-20261006-01.json"
PLAN = OUT / "closure90-current-20261005-01/plan.json"
SAMPLE = OUT / "gap83-midmant-old-image-20261006-01/code.vdb"
ANNOTATION = "Reviewed operand debug instrumentation; native qualification only; not aggregate approval"
STAGES = capture.STAGES
require = capture.require
write = capture.write


def complete(point, metric, file_id):
    """Include only whole compiled objects inside one reviewed region."""
    children = point["statements"] if metric == "line" else point["expressions"]
    require(bool(children), "Empty compiled object")
    require(point["file_id"] == file_id and all(c["file_id"] == file_id for c in children),
            "Mixed source ownership")
    locations = [int(point["line"])]
    locations += [int(c["line_num"] if metric == "line" else c["id"]) for c in children]
    if metric == "branch":
        for child in children:
            for attr in ("true_clause_line", "false_clause_line"):
                value = int(child[attr])
                require(value >= 0, "Unknown branch clause endpoint")
                if value:
                    locations.append(value)
    return any(all(start <= n <= end for n in locations) for start, end in inventory.REGIONS)


def coordinate(point, metric):
    return point["native_id"] + ("," + point["vector"] if metric == "branch" else "")


def selection(plan):
    literal = capture.literal
    lines = ["set dbg_design " + literal(plan["design_vdb"]),
             "set dbg_test " + literal(plan["selected_test_vdb"]),
             "set dbg_python " + literal(sys.executable),
             "set dbg_driver " + literal(str(Path(__file__).resolve())),
             "set dbg_scopes {" + " ".join(literal(s) for s in plan["scopes"]) + "}"]
    for name in ("keys", "targets"):
        rows = []
        for scope, metrics in plan["scopes"].items():
            for metric, points in metrics.items():
                keys = [p["coordinate"] for p in points if name == "keys" or p["target"]]
                require(len(keys) == len(set(keys)), "Duplicate selection")
                rows.append(literal(scope + "|" + metric) + " {" + " ".join(keys) + "}")
        lines.append("array set dbg_%s {\n%s\n}" % (name, "\n".join(rows)))
    return "\n".join(lines) + "\n"


def prepare(output):
    require(output.parent.resolve() == OUT.resolve() and not output.exists(), "Fresh direct out required")
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased input: " + str(path))
        if str(path) in pins:
            require(expected is None or pins[str(path)] == expected, "Pin collision")
            return path
        value = sha(path)
        require(expected is None or value == expected, "Input hash differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Pin collision")
        pins[str(path)] = value
        return path
    def read(path, expected=None):
        return json.loads(pin(path, expected).read_bytes())
    old = read(PLAN)
    baseline = read(BASE / "status.json")
    require(baseline["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and
            baseline["aggregate_passed"] == 690 and baseline["new_RTL_signoff"] is False,
            "Not completed historical690 baseline")
    inputs = pin(BASE / "combined-inputs.txt").read_text().splitlines()
    design_path = Path(old["design_vdb"])
    require(len(inputs) == len(set(inputs)) == 691 and inputs[0] == str(design_path) and
            str(SAMPLE) in inputs[1:], "Not exact unique historical690 membership/sample")
    bitmap = read(BASE / "combined-bits.json",
                  "a3c4a5cbea199b33b648f5733e23fd5af1dcf783ef3afabe9e39ef1fb25ab95a")
    for path, expected in read(BASE / "evidence-pins.json").items():
        pin(path, expected)
    scalar = read(BASE / "scalar-comparison.json")
    vector = read(BASE / "vector-comparison.json")
    require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["stopped_at_unobservable"] is None and
            scalar["matched_instructions"] == scalar["ara_retired_instructions"] == 4058 and
            vector["status"] == "PASS" and vector["selected_index"] is None and
            vector["stopped_at_spike_index"] is None and vector["compared_instructions"] == 8 and
            vector["compared_bytes"] == 2048 and not vector["incomplete_requests"] and
            not vector["unretired_requests"] and vector["first_mismatch"] is None,
            "Single sample not completely admitted")
    pin(BASE / "raw-bitmap-delta.json")
    inv = read(INVENTORY, "82dcc5a1576514a5b2837006d0bf61932fca770ebf20c1960541822de3919ee2")
    review = read(REVIEW, "dba1bc6fc1372f7005e264e7b9b528b7abd7ccc32484abbe7a4e94b570066158")
    require(review["source_sha256"] == inventory.SOURCE_SHA and
            review["reviewed_regions"] == [list(r) for r in inventory.REGIONS] and
            review["writes_to_functional_state_or_ports_observed"] is False and
            review["assertions_or_fatal_or_finish_or_delay_observed_in_regions"] is False,
            "Noninterference review differs")
    for path, expected in inv["input_sha256"].items():
        pin(path, expected)
    build = read(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    pin(inventory.SOURCE, inventory.SOURCE_SHA)
    require(build[str(inventory.SOURCE)] == inventory.SOURCE_SHA, "Compiled source pin differs")
    for path, expected in old["image"].items():
        pin(path, expected)
    db = design_path / "snps/coverage/db"
    for rel, expected in bitmap["design"].items():
        pin(db / rel, expected)
    for rel in ["auxiliary/verilog.sourceinfo.xml"] + [
            "shape/%s.verilog.%s.xml" % (m, kind) for m in ("line", "branch", "tgl")
            for kind in ("shape", "info")]:
        pin(db / rel)
    membership = {str(SAMPLE): capture.proof.tree_members(SAMPLE)}
    for path in sorted(SAMPLE.rglob("*")):
        if path.is_file():
            pin(path)
    design = inventory.Design(design_path)
    scopes, reproduced = {}, []
    for lane in range(4):
        scope = "ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%s].i_lane.i_operand_requester" % lane
        source = design.source(scope)
        require(source["resolved_path"] == str(inventory.SOURCE), "Wrong compiled source")
        scopes[scope] = {}
        for metric in ("line", "branch"):
            record = bitmap["metrics"][metric][scope]
            definition = design.definition(scope, metric)
            require(record["checksum"] == definition.get("chksum"), "Compiled checksum differs")
            points = inventory.points(metric, definition, record["width"])
            rows = []
            for p in points:
                eligible = inventory.contained(p, metric)
                if eligible:
                    require(complete(p, metric, source["file_id"]), "Incomplete reviewed block")
                row = dict(point=p, coordinate=coordinate(p, metric), target=eligible,
                           module_checksum=source["definition_checksum"], metric_checksum=record["checksum"])
                rows.append(row)
                if eligible:
                    hit = bool(int(record["bits"], 16) & (1 << (record["width"] - 1 - p["raw_index"])))
                    reproduced.append(dict(scope=scope, metric=metric, point=p, hit=hit,
                        module_checksum=source["definition_checksum"], metric_checksum=record["checksum"],
                        decision="REVIEW_REQUIRED_NOT_WAIVED"))
            require(len({r["coordinate"] for r in rows}) == len(rows), "Ambiguous compiled coordinate")
            require(any(r["target"] for r in rows) and any(not r["target"] for r in rows), "Whole module forbidden")
            scopes[scope][metric] = rows
    require(reproduced == inv["points"], "Independent full inventory reproduction differs")
    identity = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    for path in (Path(__file__).resolve(), TCL, TEST, Path(capture.__file__),
                 Path(capture.proof.__file__), Path(tool.__file__), Path(inventory.__file__),
                 HERE / "closure_point_inventory.py", HERE / "reviewed_20261004/audit_readonly.py"):
        pin(path)
    plan = dict(design_vdb=str(design_path), selected_test_vdb=str(SAMPLE), scopes=scopes,
                input_membership=membership, tool_identity=identity)
    targets = {metric: sum(r["target"] for s in scopes.values() for r in s[metric]) for metric in ("line", "branch")}
    protected = {metric: sum(not r["target"] for s in scopes.values() for r in s[metric]) for metric in ("line", "branch")}
    require(targets == {"line": 3076, "branch": 1832}, "Unexpected qualification population")
    output.mkdir()
    (output / "selection.tcl").write_text(selection(plan))
    pin(output / "selection.tcl")
    config = dict(schema="operand-debug-native-qualification-v1", output=str(output), pins=pins, plan=plan,
                  command=tool.launch_command(identity, TCL), targets=targets, protected=protected,
                  conditions="HOLD_NO_NATIVE_ID_QUALIFICATION", capture_only=True, application_approval=False,
                  historical_only=True, compiled_input_pins=True)
    write(output / "config.json", config)
    capture.check_inputs(config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal,
                                      targets=targets, protected=protected, application_approval=False))
    print("PREPARED_NO_DVE config_sha256=" + seal, flush=True)
    return seal


def config_read(output, seal):
    require(re.fullmatch(r"[a-f0-9]{64}", seal or "") and sha(output / "config.json") == seal, "External seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "operand-debug-native-qualification-v1" and config["output"] == str(output), "Wrong config")
    capture.check_inputs(config)
    return config


def bind_native(raw, config):
    require(raw.endswith(b"\n") and b"\r" not in raw and b"\x00" not in raw, "Invalid native bytes")
    text = raw.decode("ascii")
    lines = text.splitlines()
    # Strict grammar: no INSTANCE-wide, Toggle/Condition, comments or unknown directives.
    require(all(not l or re.fullmatch(r'CHECKSUM: "[0-9]+ [0-9]+"|INSTANCE: ?[A-Za-z_][A-Za-z0-9_.\[\]]*|ANNOTATION: "' +
        re.escape(ANNOTATION) + r'"|Block [0-9]+ "[0-9]+" ".*"|Branch [0-9]+ "[0-9]+" ".*" \([0-9]+\) ".*"', l)
        for l in lines), "Unsupported native directive/annotation")
    entries, scope, checksums = [], None, None
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        header = re.fullmatch(r'CHECKSUM: "([0-9]+) ([0-9]+)"', line)
        if header:
            require(index + 2 < len(lines), "Dangling native header")
            inst = re.fullmatch(r'INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)', lines[index + 1])
            require(inst is not None and lines[index + 2] == 'ANNOTATION: "' + ANNOTATION + '"', "Empty native instance")
            scope, checksums = inst[1], [header[1], header[2]]
            index += 2
            continue
        require(scope is not None and line == 'ANNOTATION: "' + ANNOTATION + '"' and index + 1 < len(lines),
                "Native annotation/header order differs")
        directive = lines[index + 1]
        block = re.fullmatch(r'Block (0|[1-9][0-9]*) "([0-9]+)" "(.*)"', directive)
        branch = re.fullmatch(r'Branch (0|[1-9][0-9]*) "([0-9]+)" "(.*)" \((0|[1-9][0-9]*)\) "(.*)"', directive)
        require(block is not None or branch is not None, "Unsupported native point")
        point = "Block " + block[1] if block else "Branch %s (%s)" % (branch[1], branch[4])
        entries.append(dict(scope=scope, point=point, checksum=checksums, native_directive=directive,
                            native_signature=block[3] if block else branch[5]))
        index += 2
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        for metric, rows in metrics.items():
            for r in rows:
                if r["target"]:
                    p = r["point"]
                    key = scope, ("Block " + p["native_id"] if metric == "line" else
                                  "Branch %s (%s)" % (p["native_id"], p["vector"]))
                    require(key not in expected, "Duplicate expected native point")
                    expected[key] = (metric, r)
    require({(r["scope"], r["point"]) for r in entries} == set(expected) and len(entries) == len(expected),
            "Extra/missing/instance-wide native records")
    for e in entries:
        metric, r = expected[e["scope"], e["point"]]
        p = r["point"]
        require(e["checksum"] == [r["module_checksum"], r["metric_checksum"]], "Native checksum differs")
        if metric == "line":
            require(e["native_signature"] == p["expression"], "Native complete block signature differs")
        else:
            directive = re.fullmatch(r'Branch [0-9]+ "([0-9]+)" "(.*)" \([0-9]+\) "(.*)"', e["native_directive"])
            require(directive is not None and directive[1] == p["attributes"]["chksum"] and
                    directive[2] == p["expressions"][0]["exprstr"] and directive[3],
                    "Native branch checksum/expression differs")
    return entries


def audit_states(path, config, stage, previous=None):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames == ["scope", "metric", "coordinate", "meta", "path", "excluded"], "Audit header differs")
        rows = list(reader)
    expected = {(s, m, p["coordinate"]): p for s, metrics in config["plan"]["scopes"].items()
                for m, points in metrics.items() for p in points}
    got = {}
    for r in rows:
        key = r["scope"], r["metric"], r["coordinate"]
        require(key in expected and key not in got and r["meta"] and r["path"], "Unexpected/duplicate/empty audit row")
        wanted = stage in ("selected", "reloaded") and expected[key]["target"]
        require(r["excluded"] == str(int(wanted)), "Target/protected singleton differs")
        got[key] = r["meta"], r["path"]
    require(set(got) == set(expected) and (previous is None or got == previous), "Audit inventory/identity differs")
    return got


def verify_artifacts(output, config):
    names = ["first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el",
             "live-identity.json", "execution.json", "selected_tests.txt", "DVEfiles/dve_gui.log",
             "integrity-before.json", "integrity-after.json"] + ["states_%s.tsv" % s for s in STAGES]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing native evidence")
    entries = [bind_native((output / n).read_bytes(), config) for n in ("first.el", "second.el")]
    require(entries[0] == entries[1], "Native roundtrip changed")
    for n in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / n).read_bytes() == b"", "Global reset not empty")
    previous = None
    for stage in STAGES:
        previous = audit_states(output / ("states_%s.tsv" % stage), config, stage, previous)
    dirs = list((SAMPLE / "snps/coverage/db/testdata").iterdir())
    require(len(dirs) == 1 and (output / "selected_tests.txt").read_text().splitlines() ==
            [str(SAMPLE.with_suffix("") / dirs[0].name)], "Selected test differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("DBG_CAPTURE_DONE") == 1 and not re.search(
        r'DBG_CAPTURE_FAILED|(?:^|\s)(Error|Fatal):|checksum.*mismatch', log, re.I), "GUI failed/incomplete")
    live = json.loads((output / "live-identity.json").read_bytes())
    execution = json.loads((output / "execution.json").read_bytes())
    require(live["executable_verified"] is True and live["executable"] == config["plan"]["tool_identity"]["executable"] and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"] and
            execution["launch_count"] == 1 and execution["returncode"] == 0, "Execution identity differs")
    for n, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / n).read_bytes()) == {field: True, "pins": config["pins"],
                "membership": config["plan"]["input_membership"]}, "Input integrity differs")
    return dict(status="DEBUG_NATIVE_ROUNDTRIP_QUALIFIED_NOT_AGGREGATE_APPROVAL", captured_tests=1,
                records=len(entries[0]), targets=config["targets"], protected=config["protected"],
                condition_qualified=False, application_approval=False, new_RTL_signoff=False,
                official_denominator_verified=False, final_reset=True,
                files={str(p): sha(p) for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "first", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), "Unsafe output")
    if args.command == "prepare":
        prepare(output)
        return
    # Reuse launch/runtime identity and before/after integrity machinery, not its policy.
    capture.TCL = TCL
    capture.config_read = config_read
    capture.verify_artifacts = verify_artifacts
    if args.command == "capture":
        original_environment = capture.environment
        def environment(identity, directory):
            env = original_environment(identity, directory)
            env["DEBUG_CAPTURE_SEAL"] = args.seal
            return env
        capture.environment = environment
        capture.capture(output, args.seal)
    elif args.command == "first":
        config = config_read(output, args.seal)
        rows = bind_native((output / "first.el").read_bytes(), config)
        print("DBG_FIRST_EXACT " + str(len(rows)), flush=True)
    else:
        print(json.dumps(verify_artifacts(output, config_read(output, args.seal)), indent=2))


if __name__ == "__main__":
    main()
