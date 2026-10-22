#!/usr/bin/env python3
"""Two-point pilot followed by branch-only native qualification. No admission."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_operand_debug as debug

capture = debug.capture
HERE = Path(__file__).resolve().parent
TCL = HERE / "capture_operand_debug_branch.tcl"
TEST = HERE / "test_capture_operand_debug_branch.py"
PARENT = debug.OUT / "operand-debug-native-capture-20261006-02"
PARENT_SEAL = "c89c058f19b9339af8902c2f059624c25faf22b0ca9d0676a4210c9b81b2d752"
PROBE = debug.OUT / "operand-debug-native-api-probe-20261006-03"
PROBE_SEAL = "9711b2de4fb2a4659851825b566951dbe62667a14848b487ce0a9d187ca1b10f"
PILOT_COORDINATES = {"3,0", "3,4"}
require = debug.require
sha = debug.sha
write = debug.write


def branch_plan(original, mode):
    plan = copy.deepcopy(original)
    scopes = sorted(original["scopes"])
    plan["scopes"] = {s: {"branch": copy.deepcopy(original["scopes"][s]["branch"])}
                      for s in (scopes[:1] if mode == "pilot" else scopes)}
    if mode == "pilot":
        rows = plan["scopes"][scopes[0]]["branch"]
        eligible = {r["coordinate"] for r in rows if r["target"]}
        require(PILOT_COORDINATES <= eligible, "Pilot must use reviewed targets")
        for r in rows:
            r["target"] = r["coordinate"] in PILOT_COORDINATES
    for metrics in plan["scopes"].values():
        rows = metrics["branch"]
        missing_default = [r for r in rows if r["coordinate"] == "8,21"]
        require(len(missing_default) == 1 and not missing_default[0]["target"], "Functional default must remain protected")
    return plan


def pin_result(directory, config_seal, result_seal):
    directory = Path(directory).absolute()
    require(directory.parent.resolve() == debug.OUT.resolve() and not directory.is_symlink(), "Unsafe pilot path")
    require(re.fullmatch(r"[0-9a-f]{64}", result_seal or "") and
            sha(directory / "capture-result.json") == result_seal, "External pilot result seal required")
    result = json.loads((directory / "capture-result.json").read_bytes())
    require(result.get("config_sha256") == config_seal and result.get("status") ==
            "DEBUG_BRANCH_PILOT_EXACT2_ROUNDTRIP_NOT_AGGREGATE_APPROVAL", "Pilot not qualified")
    for path, expected in result["files"].items():
        path = Path(path)
        require(path.parent in (directory, directory / "DVEfiles") and sha(path) == expected, "Pilot artifact drift")
    config = config_read(directory, config_seal)
    require(config["mode"] == "pilot" and config["targets"] == {"branch": 2}, "Not two-point pilot")
    verified = verify_artifacts(directory, config)
    require(all(result[k] == v for k, v in verified.items() if k != "files") and
            all(result["files"].get(k) == v for k, v in verified["files"].items()),
            "Independent pilot verification differs")
    return result, config


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    require(mode in ("pilot", "full"), "Unknown mode")
    require(output.parent.resolve() == debug.OUT.resolve() and not output.exists(), "Fresh direct output required")
    parent = debug.config_read(PARENT, PARENT_SEAL)
    config = copy.deepcopy(parent)
    pins = config["pins"]
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased evidence")
        value = sha(path)
        require(expected is None or value == expected, "Evidence hash differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Pin differs")
        pins[str(path)] = value
    for path in (PARENT / "config.json", PARENT / "status.json", PROBE / "config.json",
                 PROBE / "capture-result.json", PROBE / "native-tree.tsv", PROBE / "DVEfiles/dve_gui.log"):
        pin(path, PROBE_SEAL if path == PROBE / "config.json" else None)
    observed = (PROBE / "native-tree.tsv").read_text().splitlines()
    require(any("\tMISSING_DEFAULT8.21\tItem8.MISSING_DEFAULT8.21\t0\t" in l for l in observed),
            "No observed native missing-default leaf")
    # Independently reproduce every branch coordinate and eligibility from compiled input.
    bitmap = json.loads((debug.BASE / "combined-bits.json").read_bytes())
    design = debug.inventory.Design(Path(parent["plan"]["design_vdb"]))
    for scope, metrics in parent["plan"]["scopes"].items():
        source = design.source(scope)
        require(source["resolved_path"] == str(debug.inventory.SOURCE), "Compiled owner differs")
        record = bitmap["metrics"]["branch"][scope]
        definition = design.definition(scope, "branch")
        require(record["checksum"] == definition.get("chksum"), "Branch checksum differs")
        points = debug.inventory.points("branch", definition, record["width"])
        rows = []
        for point in points:
            target = debug.inventory.contained(point, "branch")
            if target:
                require(debug.complete(point, "branch", source["file_id"]), "Mixed/incomplete reviewed group")
            rows.append(dict(point=point, coordinate=debug.coordinate(point, "branch"), target=target,
                             module_checksum=source["definition_checksum"], metric_checksum=record["checksum"]))
        require(rows == metrics["branch"], "Independent complete branch reconstruction differs")
    config["plan"] = branch_plan(parent["plan"], mode)
    if mode == "full":
        require(pilot is not None, "Full requires qualified exact2 pilot")
        result, pilot_config = pin_result(pilot, pilot_seal, pilot_result_seal)
        for path, expected in pilot_config["pins"].items():
            pin(path, expected)
        for path, expected in result["files"].items():
            pin(path, expected)
        pin(Path(pilot) / "capture-result.json", pilot_result_seal)
        config["pilot"] = dict(output=str(Path(pilot).absolute()), config_sha256=pilot_seal,
                               capture_result_sha256=pilot_result_seal)
    for path in (Path(__file__).resolve(), TCL, TEST, Path(debug.__file__),
                 HERE / "closure_scorecard.py", HERE / "capture_operand_debug.tcl"):
        pin(path)
    targets = sum(r["target"] for s in config["plan"]["scopes"].values() for r in s["branch"])
    protected = sum(not r["target"] for s in config["plan"]["scopes"].values() for r in s["branch"])
    require(targets == (2 if mode == "pilot" else 1832) and protected > 0, "Wrong branch population")
    config.update(schema="operand-debug-branch-native-v1", mode=mode, output=str(output),
                  targets={"branch": targets}, protected={"branch": protected}, line="HOLD_NO_RAW_BLOCK_API",
                  conditions="HOLD_NO_NATIVE_ID_QUALIFICATION", application_approval=False)
    output.mkdir()
    selection = debug.selection(config["plan"])
    selection += "set dbg_driver " + capture.literal(str(Path(__file__).resolve())) + "\n"
    (output / "selection.tcl").write_text(selection)
    pin(output / "selection.tcl")
    config["command"] = capture.tool.launch_command(config["plan"]["tool_identity"], TCL)
    write(output / "config.json", config)
    capture.check_inputs(config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, mode=mode,
                                      targets=config["targets"], protected=config["protected"], application_approval=False))
    print("BRANCH_PREPARED " + seal, flush=True)


def config_read(output, seal):
    require(re.fullmatch(r"[a-f0-9]{64}", seal or "") and sha(output / "config.json") == seal, "External config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "operand-debug-branch-native-v1" and config["output"] == str(output) and
            config["mode"] in ("pilot", "full") and config["line"] == "HOLD_NO_RAW_BLOCK_API" and
            all(set(s) == {"branch"} for s in config["plan"]["scopes"].values()), "Not branch-only config")
    capture.check_inputs(config)
    return config


def audit_states(path, config, stage, previous=None):
    identities = debug.audit_states(path, config, stage, previous)
    for (scope, metric, coordinate), (meta, native_path) in identities.items():
        sid, vid = coordinate.split(",")
        require(metric == "branch" and re.fullmatch(r"(Branch|MISSING_ELSE|MISSING_DEFAULT)" +
                re.escape(sid) + r"\." + re.escape(vid), meta) is not None and
                native_path == "Item" + sid + "." + meta, "Native branch identity differs")
    return identities


def verify_artifacts(output, config):
    # Frozen verifier binds all native checksums/expressions and both saved signatures.
    result = debug.verify_artifacts(output, config)
    previous = None
    for stage in debug.STAGES:
        previous = audit_states(output / ("states_%s.tsv" % stage), config, stage, previous)
    require(result["records"] == (2 if config["mode"] == "pilot" else 1832), "Wrong native record count")
    result.update(status=("DEBUG_BRANCH_PILOT_EXACT2_ROUNDTRIP_NOT_AGGREGATE_APPROVAL" if config["mode"] == "pilot"
                          else "DEBUG_BRANCH_1832_ROUNDTRIP_NOT_AGGREGATE_APPROVAL"),
                  line_qualified=False, mode=config["mode"], functional_default_protected=True,
                  full_native_branch_inventory=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "first", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    parser.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    parser.add_argument("--pilot", type=Path)
    parser.add_argument("--pilot-seal")
    parser.add_argument("--pilot-result-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve() == debug.OUT.resolve() and not output.is_symlink(), "Unsafe output")
    if args.command == "prepare":
        prepare(output, args.mode, args.pilot, args.pilot_seal, args.pilot_result_seal)
        return
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
        rows = debug.bind_native((output / "first.el").read_bytes(), config)
        print("DBG_FIRST_EXACT " + str(len(rows)), flush=True)
    else:
        print(json.dumps(verify_artifacts(output, config_read(output, args.seal)), indent=2))


if __name__ == "__main__":
    main()
