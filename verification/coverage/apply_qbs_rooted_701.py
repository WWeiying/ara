#!/usr/bin/env python3
"""Explicit701 QBS-only application, never a silent rebind of the sealed699 run."""
import copy
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import apply_qbs_rooted_699 as previous
import verify_operand_debug_1832_product701 as vendor

base = previous.base
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix(".tcl")
TEST = SCRIPT.with_name("test_apply_qbs_rooted_701.py")
BASE701 = base.OUT / "gap94-offline-admitted-701-20261006-01"
RAW701 = base.OUT / "raw701-dve-20261006-01"
PRIOR = base.OUT / "qbs-rooted-report-699-20261006-01"
PRIOR_SEAL = "2723de76588c0c1b055abb6c1111663fa13a03b619620a24ad02a9ba9303a7ad"
PRIOR_RESULT_SEAL = "151014b4cb2e71fded0a837cb4e3f2cc4ff63d24a5671e8d1b2051682c249c87"


def pin(pins, path, expected=None):
    path = Path(path).absolute()
    base.require(path.is_file() and not path.is_symlink(), "Missing/aliased701 evidence: " + str(path))
    value = base.sha(path)
    base.require(expected is None or value == expected, "701 evidence hash differs: " + str(path))
    base.require(str(path) not in pins or pins[str(path)] == value, "701 pin conflict")
    pins[str(path)] = value
    return path


def latest_scopes(qc, bitmap, predecessor):
    base.require(len(bitmap["tests"]) == len(set(bitmap["tests"])) == 701
                 and bitmap["tests"][:699] == predecessor["tests"] and bitmap["design"] == predecessor["design"],
                 "Not exact701 descendant of frozen699")
    old = json.loads((base.q.BASE / "combined-bits.json").read_bytes())
    base.require(bitmap["design"] == old["design"] and bitmap["tests"][:690] == old["tests"], "Foreign690 ancestor")
    design = base.q.native.inventory.Design(Path(qc["plan"]["design_vdb"]))
    scopes = base.q.build_scopes(design, old, json.loads(base.q.INVENTORY.read_bytes()), "full")
    base.require(scopes == qc["plan"]["scopes"], "Source-derived native inventory differs")
    zero_targets(scopes, bitmap, predecessor)
    return scopes, design


def zero_targets(scopes, bitmap, predecessor):
    targets, protected = 0, 0
    for scope, metrics in scopes.items():
        record = bitmap["metrics"]["branch"][scope]
        original = predecessor["metrics"]["branch"][scope]
        base.require(record["checksum"] == original["checksum"] and record["width"] == original["width"], "701 shape changed")
        base.require(base.re.fullmatch(r"(?:0x)?[0-9a-fA-F]+", record["bits"]), "Invalid701 bitmap encoding")
        value = int(record["bits"], 16)
        base.require(0 <= value < 1 << record["width"], "701 bits out of range")
        for row in metrics["branch"]:
            index = row["point"]["raw_index"]
            base.require(0 <= index < record["width"], "Invalid native coordinate")
            if row["target"]:
                targets += 1
                base.require(not value & (1 << (record["width"] - index - 1)), "701 hit contradicts QBS invariant")
            else:
                protected += 1
    base.require((targets, protected) == (448, 3790), "Not exact448/3790 inventory")


def selected701(inputs, bitmap, design):
    base.require(inputs == [design, *bitmap["tests"]] and len(inputs) == len(set(inputs)) == 702,
                 "Not exact ordered701 membership")
    base.require(len({str(Path(p).resolve(strict=True)) for p in inputs}) == 702, "Aliased701 membership")
    names = []
    for path in inputs:
        p = Path(path)
        base.require(p.is_absolute() and not p.is_symlink() and not base.re.search(r"[\s{}]", path), "Unsafe701 VDB")
    for path in inputs[1:]:
        dirs = list((Path(path) / "snps/coverage/db/testdata").iterdir())
        base.require(len(dirs) == 1 and dirs[0].is_dir() and not dirs[0].is_symlink(), "Ambiguous701 testdata")
        names.append(str(Path(path).with_suffix("") / dirs[0].name))
    base.require(len(names) == len(set(names)) == 701 and all(not base.re.search(r"[\s{}]", n) for n in names),
                 "Invalid701 GUI names")
    return names


def reference_rows(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        base.require(reader.fieldnames == ["Name", "Depth", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"],
                     "Raw701 schema differs")
        rows = list(reader)
    stack, result = [], {}
    for row in rows:
        base.require(None not in row and all(row.values()) and base.re.fullmatch(r"0|[1-9][0-9]*", row["Depth"]),
                     "Invalid raw701 hierarchy row")
        depth = int(row["Depth"])
        base.require(depth <= len(stack) and depth <= 256 and all(base.re.fullmatch(
            r"[A-Za-z_$][A-Za-z0-9_$]*(?:\[[0-9]+\])*", n) for n in row["Name"].split(".")), "Raw701 depth/name differs")
        stack = stack[:depth] + [row["Name"]]
        scope = ".".join(stack)
        base.require(scope not in result, "Raw701 duplicate scope")
        result[scope] = row
    return result


def product_match(raw, reference):
    stripped = {scope: {k: v for k, v in row.items() if k not in ("GUIPath", "Scope")} for scope, row in raw.items()}
    vendor.compare_product(stripped, reference)


def population_gate(config):
    base.require(config["mode"] == "report" and config.get("latest_precheck_tests") == 701
                 and config["latest701"] == dict(baseline=str(BASE701), raw_reference=str(RAW701),
                                               prior_config_sha256=PRIOR_SEAL, prior_result_sha256=PRIOR_RESULT_SEAL),
                 "Explicit701 binding differs")
    inputs = (BASE701 / "combined-inputs.txt").read_text().splitlines()
    names = (RAW701 / "selected_tests.txt").read_text().splitlines()
    base.require(config["inputs"] == inputs and len(set(inputs)) == len(inputs) == 702
                 and config["selected_tests"] == names and len(set(names)) == len(names) == 701,
                 "701 exact population differs")
    base.require(config["root_refresh_scopes"] == previous.scopes_for(config), "701 root alias")


def verify_artifacts(output, config):
    if "latest701" not in config:
        return previous.verify_artifacts(output, config)
    population_gate(config)
    result = previous.pilot.original_verify(output, config)
    path = output / "rooted-metrics.csv"
    base.require(path.is_file() and not path.is_symlink(), "Missing701 rooted report")
    result["rooted_metrics"] = previous.pilot.rooted_rows(path, config["root_refresh_scopes"])
    product_match(previous.pilot.corrected.summary(output / "summary_raw.csv"), reference_rows(RAW701 / "summary.csv"))
    result["files"][str(path)] = base.sha(path)
    result["status"] = "QBS_ROOTED_REPORT_EXACT448_HISTORICAL701_PRODUCT_ONLY"
    result["allowed_report_absence"] = config["reviewed_external_root"]
    result["product_rows"] = 2988
    result["reference_rows"] = 2989
    result["limitation"] = "QBS-only historical701; no mixed exclusions, aggregate admission, new RTL signoff or official denominator validation"
    return result


def prepare(output, mode, qualification_result_seal, *args):
    base.require(mode == "report" and output.parent.resolve() == base.OUT.resolve() and not output.exists(), "Fresh701 report required")
    base.require(qualification_result_seal == "6a3957b6614a25dabb8b78e6d488644e9fec9a64bfce643a900ade2c793f0cdd",
                 "External native result required")
    pins = {}
    pin(pins, PRIOR / "config.json", PRIOR_SEAL)
    pin(pins, PRIOR / "capture-result.json", PRIOR_RESULT_SEAL)
    old_config = json.loads((PRIOR / "config.json").read_bytes())
    result = json.loads((PRIOR / "capture-result.json").read_bytes())
    base.require(result["status"] == "QBS_ROOTED_REPORT_EXACT448_HISTORICAL699_ONLY" and result["tests"] == 699
                 and result["records"] == 448 and result["protected"] == 3790 and result["final_reset"] is True
                 and result["config_sha256"] == PRIOR_SEAL and result["aggregate_admission"] is False,
                 "Sealed699 report not qualified")
    for p, h in {**old_config["pins"], **result["files"]}.items():
        pin(pins, p, h)
    qc, review = base.qualified_config()
    pin(pins, base.QUALIFIED / "capture-result.json", qualification_result_seal)
    bitmap = json.loads(pin(pins, BASE701 / "combined-bits.json").read_bytes())
    prior_bitmap = json.loads((base.BASE / "combined-bits.json").read_bytes())
    state = json.loads(pin(pins, BASE701 / "status.json").read_bytes())
    base.require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 701
                 and state["new_RTL_signoff"] is False and state["rtl_changed"] is False, "701 historical PASS-only gate failed")
    scopes, design = latest_scopes(qc, bitmap, prior_bitmap)
    inputs = pin(pins, BASE701 / "combined-inputs.txt").read_text().splitlines()
    names = selected701(inputs, bitmap, qc["plan"]["design_vdb"])
    for p, h in {**bitmap["input_hashes"], **json.loads(pin(pins, BASE701 / "evidence-pins.json").read_bytes())}.items():
        pin(pins, p, h)
    population = json.loads(pin(pins, RAW701 / "population-verification.json").read_bytes())
    base.require(population["status"] == "VERIFIED_HISTORICAL_RAW_REPORT" and population["admitted_tests"] == 701
                 and population["current_RTL_signoff"] is False, "Raw701 unqualified")
    for p, h in population["pins"].items():
        pin(pins, p, h)
    base.require((RAW701 / "inputs.txt").read_text().splitlines() == inputs
                 and (RAW701 / "selected_tests.txt").read_text().splitlines() == names
                 and (RAW701 / "diagnostics.txt").read_bytes() == b""
                 and json.loads((RAW701 / "waiver_status.json").read_bytes())["status"] == "DISABLED", "Raw701 actual inputs/waivers differ")
    reference = reference_rows(RAW701 / "summary.csv")
    definition = design.hierarchy[vendor.ROOT]
    source = design.source(vendor.ROOT)
    instances = [dict(n.attrib) for n in definition.findall("srcinst")]
    vendor.validate_owner(source, dict(definition.attrib), instances, design.hierarchy)
    pin(pins, vendor.SOURCE, vendor.SOURCE_SHA)
    base.require(vendor.SOURCE.read_text().splitlines()[41].strip() == "module " + vendor.ROOT + ";"
                 and vendor.SOURCE.read_text().splitlines()[330].strip().startswith("endmodule"), "Vendor boundaries differ")
    base.require(len(reference) == 2989 and set(reference) == {vendor.ROOT} | {
        s for s in reference if s == "ara_tb" or s.startswith("ara_tb.")}, "Unexpected raw701 top root")
    for path in (SCRIPT, TCL, TEST, Path(vendor.__file__), Path(vendor.app.__file__)):
        pin(pins, path)
    for module in tuple(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if filename:
            path = Path(filename).resolve()
            if path.parent == base.HERE and path.suffix == ".py":
                pin(pins, path)
    config = copy.deepcopy(old_config)
    config["pins"] = pins
    config["output"], config["inputs"], config["selected_tests"] = str(output), inputs, names
    config["latest_precheck_tests"] = 701
    config.pop("rooted_report_pilot")
    config["latest701"] = dict(baseline=str(BASE701), raw_reference=str(RAW701),
                               prior_config_sha256=PRIOR_SEAL, prior_result_sha256=PRIOR_RESULT_SEAL)
    config["reviewed_external_root"] = dict(scope=vendor.ROOT, source=source, definition=dict(definition.attrib),
                                            instances=instances, descendants=[], native_exclusion_authorized=False)
    config["plan"]["scopes"] = scopes
    config["plan"]["input_membership"] = {p: base.capture.proof.tree_members(Path(p)) for p in inputs}
    for root, members in config["plan"]["input_membership"].items():
        for member in members:
            pin(pins, Path(root) / member)
    config["plan"]["tool_identity"] = base.tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    config["command"] = base.tool.launch_command(config["plan"]["tool_identity"], TCL)
    base.require(config["qualified_records"] == base.qualification.bind_native((base.QUALIFIED / "first.el").read_bytes(), qc),
                 "Explicit701 native rebind differs")
    output.mkdir()
    # Copy exact frozen helpers, except population selection which is derived above.
    (output / "capture-helpers.tcl").write_bytes((PRIOR / "capture-helpers.tcl").read_bytes())
    (output / "root-selection.tcl").write_bytes((PRIOR / "root-selection.tcl").read_bytes())
    text = previous.pilot.TCL.read_text()
    marker = "set failed [catch {qbsapp_session} message]"
    base.require(text.count(marker) == 1, "Frozen root helper boundary differs")
    (output / "root-helpers.tcl").write_text(text.split(marker)[0])
    selection = (base.QUALIFIED / "selection.tcl").read_text()
    selection += "set qbsapp_native " + base.capture.literal(str(base.QUALIFIED / "first.el")) + "\n"
    for name, values in (("databases", inputs[1:]), ("tests", names)):
        selection += "set qbsapp_" + name + " {" + " ".join(base.capture.literal(p) for p in values) + "}\n"
    selection += "set qbsapp_count 701\n"
    (output / "selection.tcl").write_text(selection)
    (output / "inputs.txt").write_text("\n".join(inputs) + "\n")
    for name in ("capture-helpers.tcl", "root-selection.tcl", "root-helpers.tcl", "selection.tcl", "inputs.txt"):
        pin(pins, output / name)
    population_gate(config)
    base.capture.check_inputs(config)
    base.write(output / "config.json", config)
    seal = base.sha(output / "config.json")
    base.write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, aggregate_admission=False))
    print("QBS_ROOTED701_FINAL_SEAL " + seal, flush=True)


base.TCL, base.TEST = TCL, TEST
base.prepare, base.verify_artifacts = prepare, verify_artifacts
if __name__ == "__main__":
    base.main()
