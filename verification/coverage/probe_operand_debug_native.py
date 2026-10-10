#!/usr/bin/env python3
"""Bounded native API tree probe. No exclusion or aggregate qualification."""
import argparse
import copy
import csv
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_operand_debug as debug
import capture_operand_1144 as capture

HERE = Path(__file__).resolve().parent
TCL = HERE / "probe_operand_debug_native.tcl"
TEST = HERE / "test_probe_operand_debug_native.py"
FAILED = debug.OUT / "operand-debug-native-capture-20261006-02"
SEAL = "c89c058f19b9339af8902c2f059624c25faf22b0ca9d0676a4210c9b81b2d752"
require = debug.require
write = debug.write
sha = debug.sha


def prepare(output):
    require(output.parent.resolve() == debug.OUT.resolve() and not output.exists(), "Fresh direct output required")
    config = copy.deepcopy(debug.config_read(FAILED, SEAL))
    status = json.loads((FAILED / "status.json").read_bytes())
    require(status["status"] == "FAILED" and status["config_sha256"] == SEAL, "Prior failure not terminal")
    config.update(schema="operand-debug-readonly-api-probe-v1", output=str(output), prior_failure=str(FAILED),
                  parent_config_sha256=SEAL, exclusions_generated=False, application_approval=False,
                  limits=dict(parents=5, children=6, grandchildren=3))
    config["scope"] = sorted(config["plan"]["scopes"])[0]
    for p in (Path(__file__).resolve(), TCL, TEST, FAILED / "config.json", FAILED / "status.json",
              FAILED / "DVEfiles/dve_gui.log", Path(debug.__file__)):
        config["pins"][str(p)] = sha(p)
    config["command"] = capture.tool.launch_command(config["plan"]["tool_identity"], TCL)
    output.mkdir()
    literal = capture.literal
    selection = "\n".join("set probe_%s %s" % (k, literal(v)) for k, v in (
        ("scope", config["scope"]), ("design", config["plan"]["design_vdb"]),
        ("test", config["plan"]["selected_test_vdb"]))) + "\n"
    (output / "selection.tcl").write_text(selection)
    config["pins"][str(output / "selection.tcl")] = sha(output / "selection.tcl")
    write(output / "config.json", config)
    capture.check_inputs(config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal,
                                      exclusions_generated=False, application_approval=False))
    print("PROBE_PREPARED " + seal, flush=True)


def config_read(output, seal):
    require(re.fullmatch(r"[a-f0-9]{64}", seal or "") and sha(output / "config.json") == seal, "Wrong external seal")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "operand-debug-readonly-api-probe-v1" and config["output"] == str(output), "Wrong config")
    capture.check_inputs(config)
    return config


def read_tree(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames == ["metric", "depth", "handle", "meta", "path", "child_count",
                                     "col0", "col1", "col2", "col3"], "Wrong native probe header")
        rows = list(reader)
    require(rows and len(rows) <= 2 * 5 * (1 + 6 + 6 * 3), "Unbounded/empty native probe")
    seen = set()
    for row in rows:
        key = row["metric"], row["handle"]
        require(row["metric"] in ("branch", "line") and row["depth"] in ("0", "1", "2") and
                key not in seen and row["meta"] and row["path"] and int(row["child_count"]) >= 0,
                "Invalid/duplicate native probe record")
        seen.add(key)
    return rows


def verify_artifacts(output, config):
    names = ["native-tree.tsv", "view-types.tsv", "probe-empty.el", "selected_tests.txt",
             "live-identity.json", "execution.json", "DVEfiles/dve_gui.log",
             "integrity-before.json", "integrity-after.json"]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing probe artifacts")
    rows = read_tree(output / "native-tree.tsv")
    require((output / "probe-empty.el").read_bytes() == b"", "Probe changed exclusions")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("DBG_PROBE_DONE") == 1 and "DBG_PROBE_FAILED" not in log,
            "Probe incomplete")
    execution = json.loads((output / "execution.json").read_bytes())
    live = json.loads((output / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and live["executable_verified"] is True and
            live["launch_pid"] == execution["launch_pid"] and
            live["launch_starttime"] == execution["launch_starttime"], "Unproven runtime")
    return dict(status="READONLY_NATIVE_API_PROBE_COMPLETE_NOT_QUALIFICATION", nodes=len(rows),
                exclusions_generated=False, application_approval=False,
                files={str(p): sha(p) for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "verify"))
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent.resolve() == debug.OUT.resolve() and not output.is_symlink(), "Unsafe output")
    if args.command == "prepare":
        prepare(output)
    elif args.command == "capture":
        capture.TCL = TCL
        capture.config_read = config_read
        capture.verify_artifacts = verify_artifacts
        capture.capture(output, args.seal)
    else:
        print(json.dumps(verify_artifacts(output, config_read(output, args.seal)), indent=2))


if __name__ == "__main__":
    main()
