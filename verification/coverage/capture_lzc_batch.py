#!/usr/bin/env python3
"""Native LZC format capture on one admitted test, never a 687-test application.

The capture command is for separately scheduled DVE use. Verification is offline;
neither command issues review receipts or qualifies structural exclusions.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import old_image_waiver_admission as admission
import lzc_padding_candidates as shape
from lzc_native_records import parse_records, bind_records

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "verification/out"
BASELINE = OUT / "gap80-old-image-20261006-01"
CANDIDATES = BASELINE / "lzc-padding-candidates-native-bound.json"
PILOT = OUT / "lzc-native-singleton-20261006-03"
CASE = OUT / "gap79-old-image-20261006-01/results/vgap79_add16"
SCRIPT = Path(__file__).resolve()
TCL = HERE / "capture_lzc_batch.tcl"
TEST = HERE / "test_capture_lzc_batch.py"
STAGES = ("before", "selected", "reset", "reloaded", "final")
AUDIT_COLUMNS = ["Stage", "Scope", "Expression", "NativeNames", "Targets", "Retained",
                 "TargetExcluded", "RetainedExcluded"]
require = admission.require


def key(point):
    return point["scope"], point["expression"], point["vector"]


def groups(bound):
    """Preserve vector names (including leading zeros), never XML row IDs."""
    candidates, retained = bound["candidates"], bound["retained"]
    require(type(bound.get("candidate_count")) is int and bound["candidate_count"] == 180
            and len(candidates) == 180 and len(retained) == bound["retained_count"] == 142,
            "Wrong candidate/retained population")
    require(len({key(c["point"]) for c in candidates}) == 180
            and len({key(c["point"]) for c in retained}) == 142, "Duplicate coordinates")
    require(not ({key(c["point"]) for c in candidates} & {key(c["point"]) for c in retained}),
            "Candidate/retained overlap")
    result = {}
    for is_target, rows in ((True, candidates), (False, retained)):
        for row in rows:
            p = row["point"]
            require(p["module"] == "lzc" and p["metric"] == "cond", "Foreign point")
            table = p["truth_table"]
            cols, count = int(table["ncols"]), int(table["nrows"])
            require(cols in (1, 2) and count in (2, 3) and len(table["vecs"]) == cols * count
                    and set(table["vecs"]) <= {"0", "1"}, "Malformed vector table")
            names = [table["vecs"][i * cols:(i + 1) * cols] for i in range(count)]
            require(len(set(names)) == count and p["vector"] in names, "Invalid vector name")
            if is_target:
                require(p.get("line") == "93" and p["vector"] in ("01", "10") and names == ["00", "01", "10"]
                        and p["vector"] in row["structural_proof"]["unreachable_child_vectors"],
                        "Unproved/non-OR target")
            coord = p["scope"], p["expression"]
            group = result.setdefault(coord, dict(scope=coord[0], expression=coord[1],
                                                 names=names, targets=[]))
            require(group["names"] == names, "Conflicting vector table")
            if is_target:
                group["targets"].append(p["vector"])
    for group in result.values():
        group["targets"].sort()
        group["retained"] = sorted(set(group["names"]) - set(group["targets"]))
        require(group["retained"], "No retained neighbor")
    require(sum(len(g["targets"]) for g in result.values()) == 180, "Lost target")
    native = [result[k] for k in sorted(result) if result[k]["targets"]]
    require(len(native) == 120, "Wrong target-bearing OR expression population")
    return native


def tcl_word(value):
    text = str(value)
    require("\x00" not in text, "NUL in Tcl data")
    for old, new in (("\\", "\\\\"), ('"', '\\"'), ("$", "\\$"), ("[", "\\["),
                     ("]", "\\]"), ("\n", "\\n"), ("\r", "\\r")):
        text = text.replace(old, new)
    return '"' + text + '"'


def group_script(rows):
    def words(items):
        return "[list " + " ".join(tcl_word(v) for v in items) + "]"
    entries = ["[list %s %s %s %s %s]" %
               (tcl_word(g["scope"]), tcl_word(g["expression"]), words(g["names"]),
                words(g["targets"]), words(g["retained"])) for g in rows]
    return "set lzc_batch_groups [list \\\n " + " \\\n ".join(entries) + "]\n"


def read_pinned(seal, path):
    return seal.read(path)


def load_evidence(seal):
    bound = read_pinned(seal, CANDIDATES)
    rows = groups(bound)
    require(bound["status"] == "DIAGNOSTIC_CANDIDATES_NOT_EXCLUSIONS", "Not diagnostic candidates")
    seal.hashes(bound["input_sha256"])
    state = read_pinned(seal, BASELINE / "status.json")
    require(state.get("status") == "COMPLETE" and state.get("phase") == "complete"
            and state.get("coverage_status") == "COMPLETE"
            and type(state.get("aggregate_passed")) is int and state["aggregate_passed"] == 687
            and state.get("live_rtl_reverted") is False, "Completed fixed687 required")
    seal.pin(admission.old.CURRENT / "plan.json", admission.old.IDENTITY["plan.json"])
    plan = read_pinned(seal, admission.old.CURRENT / "plan.json")
    require(state["image"] == plan["simv"], "Foreign frozen image")
    seal.hashes(plan["image"])
    inputs_path = seal.pin(BASELINE / "combined-inputs.txt")
    inputs = inputs_path.read_text().splitlines()
    require(len(inputs) == 688 and len(set(inputs)) == 688
            and inputs[0] == plan["design_vdb"] and inputs[1:] == bound["tests"],
            "Candidate population/design not fixed687")
    database = Path(plan["design_vdb"]) / "snps/coverage/db"
    seal.hashes({str(database / p): h for p, h in bound["design"].items()})
    bitmap = read_pinned(seal, BASELINE / "combined-bits.json")
    inventory_path = OUT / "closure90-zero-inventory-654-20261005-01/inventory.json"
    require(str(inventory_path) in bound["input_sha256"], "Unbound inventory")
    inventory = read_pinned(seal, inventory_path)
    require(bitmap["tests"] == bound["tests"] and bitmap["design"] == bound["design"],
            "Candidate bitmap differs")
    bindings = shape.shape_bindings(inventory["source_points"], bitmap, database)
    recomputed = shape.classify(inventory["source_points"], bitmap, bindings)
    require(recomputed["candidates"] == bound["candidates"]
            and recomputed["retained"] == bound["retained"], "Independent shape/proof differs")
    audit = read_pinned(seal, CASE / "audit.json")
    require(audit.get("status") == "PASS" and type(audit.get("checks")) is int and audit["checks"] > 0
            and audit["vdb"] == str(CASE / "code.vdb") and audit["vdb"] in inputs[1:],
            "Sample is not an admitted PASS")
    sourcepins = read_pinned(seal, CASE.parents[1] / "source-pins.json")
    seal.pin(CASE / "input.elf", sourcepins[str(CASE / "input.elf")])
    seal.tree(Path(plan["design_vdb"]))
    seal.tree(Path(audit["vdb"]))
    pilot_pins = read_pinned(seal, PILOT / "pins.json")
    seal.hashes(pilot_pins)
    pilot_first = parse_records(seal.pin(PILOT / "first.el").read_text())
    pilot_second = parse_records(seal.pin(PILOT / "second.el").read_text())
    require(len(pilot_first) == 1 and pilot_first == pilot_second
            and pilot_first[0]["vector"] == "01" and pilot_first[0]["vector_id"] == "2",
            "Verified singleton03 identity differs")
    pilot_candidates = [c for c in bound["candidates"] if key(c["point"]) == key(pilot_first[0])]
    bind_records(pilot_first, pilot_candidates)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        bind_records(parse_records(seal.pin(PILOT / name).read_text()), [])
    pilot_log = seal.pin(PILOT / "DVEfiles/dve_gui.log").read_text()
    require("LZC_READ_ONLY_DISCOVERY_DONE 1" in pilot_log and "DVE_COVERAGE_EXPORT_DONE" in pilot_log
            and "DVE_COVERAGE_EXPORT_FAILED" not in pilot_log, "Singleton03 incomplete")
    for p in (SCRIPT, TCL, TEST, HERE / "export_dve_coverage.tcl", HERE / "lzc_native_records.py",
              HERE / "lzc_padding_candidates.py", HERE / "lzc_padding_proof.py",
              HERE / "closure_point_inventory.py", admission.SCRIPT):
        seal.pin(p)
    for name, expected in admission.old.PROTECTED.items():
        seal.pin(HERE / name, expected)
    return bound, rows, audit


def prepare(output):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == OUT.resolve(strict=True),
            "Fresh direct output under verification/out required")
    seal = admission.FileSeal()
    bound, rows, audit = load_evidence(seal)
    inputs = (BASELINE / "combined-inputs.txt").read_text().splitlines()
    output.mkdir()
    (output / "inputs.txt").write_text(inputs[0] + "\n" + audit["vdb"] + "\n")
    (output / "groups.tcl").write_text(group_script(rows))
    for p in (output / "inputs.txt", output / "groups.tcl"):
        seal.pin(p)
    pins = dict(seal.files)
    (output / "pins.json").write_text(json.dumps(pins, indent=2) + "\n")
    return seal, bound, rows, audit


def verify_artifacts(output, bound, rows, sample_vdb):
    output = Path(output)
    required = [output / name for name in ("first.el", "second.el", "initial-empty.el", "reset-empty.el",
        "final-empty.el", "neighbor-audit.csv", "selected_tests.txt", "summary.csv.partial", "DVEfiles/dve_gui.log")]
    require(all(p.is_file() and not p.is_symlink() for p in required)
            and not (output / "DVEfiles").is_symlink(), "Missing/aliased capture artifacts")
    records = []
    for filename in ("first.el", "second.el"):
        parsed = parse_records((output / filename).read_text())
        bind_records(parsed, bound["candidates"])
        records.append(sorted(parsed, key=key))
    require(records[0] == records[1], "Capture/reimport compiled records or captured IDs differ")
    for filename in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        bind_records(parse_records((output / filename).read_text()), [])
    with (output / "neighbor-audit.csv").open(newline="") as stream:
        reader = csv.DictReader(stream)
        actual = list(reader)
        require(reader.fieldnames == AUDIT_COLUMNS, "Wrong neighbor audit header")
    expected = []
    for stage in STAGES:
        for g in rows:
            active = stage in ("selected", "reloaded")
            expected.append(dict(zip(AUDIT_COLUMNS, [stage, g["scope"], g["expression"],
                " ".join(g["names"]), " ".join(g["targets"]), " ".join(g["retained"]),
                str(len(g["targets"]) if active else 0), "0"])))
    require(actual == expected, "Neighbor/target audit incomplete or changed")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    lines = log.splitlines()
    require(lines.count("LZC_BATCH_CAPTURE_DONE 180") == 1
            and lines.count("DVE_COVERAGE_EXPORT_DONE") == 1
            and not re.search(r"EXPORT_FAILED|checksum.*mismatch|(?:^|\s)(?:Error|Fatal):", log, re.I),
            "DVE capture missing/ambiguous/error completion")
    selected = (output / "selected_tests.txt").read_text().splitlines()
    testroot = Path(sample_vdb) / "snps/coverage/db/testdata"
    tests = sorted(p.name for p in testroot.iterdir() if p.is_dir())
    require(tests == ["vgap79_add16"] and selected == [str(Path(sample_vdb).with_suffix("") / tests[0])],
            "Capture must load exactly one admitted sample, not full687")
    require((output / "summary.csv.partial").stat().st_size > 0
            and not (output / "summary.csv").exists(), "Unexpected applied summary")
    return dict(status="NATIVE_CAPTURE_VERIFIED_NOT_REVIEW_APPROVAL", candidate_count=180,
                captured_tests=1, baseline_tests=687, final_reset=True, application_approval=False,
                native_qualified=False, exclusions_applied=False,
                retained_inventory_count=142,
                retained_inventory_verification="complete offline shape/proof recomputation; exact180 EL records prohibit extras",
                native_neighbor_audit=dict(scope="target-bearing line93 internal OR only; not all142 retained expressions",
                    expressions=len(rows), retained_vectors=sum(len(g["retained"]) for g in rows),
                    stages=list(STAGES), covers_full_retained_inventory=False),
                captured_vector_ids=[dict(scope=r["scope"], expression=r["expression"],
                                          vector=r["vector"], vector_id=r["vector_id"]) for r in records[0]],
                artifact_sha256={str(p): admission.sha_bytes(p.read_bytes()) for p in required})


def verify(output):
    output = Path(output).resolve(strict=True)
    require(output.parent == OUT.resolve(strict=True), "Capture output outside verification/out")
    seal = admission.FileSeal()
    pins = seal.read(output / "pins.json")
    seal.hashes(pins)
    bound, rows, audit = load_evidence(seal)
    require(all(pins.get(p) == h for p, h in seal.files.items() if p != str(output / "pins.json")),
            "Capture evidence missing from pins")
    required = [output / "inputs.txt", output / "groups.tcl", output / "command.json"]
    require(all(str(p) in pins for p in required), "Incomplete capture pins")
    require((output / "groups.tcl").read_text() == group_script(rows), "Generated selector data differs")
    listing = (output / "inputs.txt").read_text().splitlines()
    design = (BASELINE / "combined-inputs.txt").read_text().splitlines()[0]
    require(listing == [design, audit["vdb"]], "Wrong capture inputs")
    command = seal.read(output / "command.json")
    require(isinstance(command, list) and len(command) == 7
            and command[1] == "-a" and command[3:] == ["-full64", "-cov", "-script",
                                                       str(HERE / "export_dve_coverage.tcl")],
            "Wrong native capture command")
    require(all(str(Path(command[i]).resolve(strict=True)) in pins for i in (0, 2)),
            "Unpinned capture tools")
    for p in listing:
        seal.tree(Path(p))
        require(all(pins.get(n) == h for n, h in seal.files.items() if n.startswith(p + "/")),
                "Capture VDB membership changed")
    result = verify_artifacts(output, bound, rows, listing[1])
    seal.hashes(result["artifact_sha256"])
    seal.finish()
    result["input_sha256"] = pins
    return result


def capture(output):
    tools = [shutil.which(n) for n in ("xvfb-run", "dve")]
    require(all(tools), "Host DVE/Xvfb missing")
    seal, bound, rows, audit = prepare(output)
    output = Path(output).absolute()
    command = [tools[0], "-a", tools[1], "-full64", "-cov", "-script", str(HERE / "export_dve_coverage.tcl")]
    env = dict(os.environ, DVE_COVERAGE_OUTPUT=str(output), DVE_REVIEWED_WAIVERS=str(TCL))
    (output / "command.json").write_text(json.dumps(command) + "\n")
    for tool in tools:
        seal.pin(Path(tool).resolve(strict=True))
    seal.pin(output / "command.json")
    (output / "pins.json").write_text(json.dumps(seal.files, indent=2) + "\n")
    seal.pin(output / "pins.json")
    status = dict(status="RUNNING", capture_only=True, captured_tests=1, candidate_count=180,
                  application_approval=False, native_qualified=False, exclusions_applied=False)
    (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    try:
        for p, h in list(seal.files.items()):
            seal.pin(p, h)
        with (output / "dve.log").open("w") as log:
            subprocess.run(command, cwd=output, env=env, stdout=log, stderr=subprocess.STDOUT,
                           timeout=1200, check=True)
        result = verify_artifacts(output, bound, rows, audit["vdb"])
        seal.hashes(result["artifact_sha256"])
        seal.finish()
        status.update(result, input_sha256=dict(seal.files))
    except Exception as error:
        status.update(status="FAILED", reason=f"{type(error).__name__}: {error}")
        raise
    finally:
        (output / "status.json").write_text(json.dumps(status, indent=2) + "\n")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capture", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.output) if args.command == "capture" else verify(args.output)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
