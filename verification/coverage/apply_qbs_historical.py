#!/usr/bin/env python3
"""QBS exact448 historical application; minimal contract gates full699 reporting."""
import argparse
import csv
import copy
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_qbs_pending_metadata_v2 as qualification

q = qualification.base
capture, tool, require, sha, write = q.capture, q.tool, q.require, q.sha, q.write
HERE, ROOT, OUT = q.HERE, q.ROOT, q.OUT
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix(".tcl")
TEST = HERE / "test_apply_qbs_historical.py"
QUALIFIED = OUT / "qbs-pending-native448-20261006-02"
QUALIFIED_SEAL = "33ef2f845e91ee8fdac3de5d659fcb3cedd744d22750852c93549113d2903106"
BASE = OUT / "gap92-offline-admitted-699-20261006-01"
RAW = OUT / "raw699-dve-20261006-01"
EVENTS = OUT / "operand-root-events-single-20261006-01"
HELPERS = HERE / "apply_operand_1144_690_v2.tcl"
REVIEW_DOC = HERE / "QBS_PENDING_METADATA_REACHABILITY.md"


def historical_review(raw, expected):
    require(len(raw) <= 1024 * 1024 and re.fullmatch(r"[a-f0-9]{64}", expected), "Invalid review document")
    if hashlib.sha256(raw).hexdigest() == expected:
        return raw
    matches = [i + 1 for i, value in enumerate(raw) if value == 10
               and hashlib.sha256(raw[:i + 1]).hexdigest() == expected]
    require(len(matches) == 1, "No exact historical review bytes")
    prefix = raw[:matches[0]]
    require(raw[matches[0]:].decode("utf-8").startswith("\n## 完整原生资格核验结果\n"), "Not the known append-only qualification note")
    return prefix


def qualified_config():
    require(sha(QUALIFIED / "config.json") == QUALIFIED_SEAL, "External qualification config seal differs")
    qc = json.loads((QUALIFIED / "config.json").read_bytes())
    require(qc["schema"] == "qbs-pending-native-v1" and qc["output"] == str(QUALIFIED) and qc["mode"] == "full",
            "Wrong full448 config")
    historical = historical_review(REVIEW_DOC.read_bytes(), qc["pins"][str(REVIEW_DOC)])
    # The sole changed input is prose appended after the capture. Every other
    # pin remains exact; neither code nor receipts get substitutions.
    pins = dict(qc["pins"])
    del pins[str(REVIEW_DOC)]
    capture.check_inputs({**qc, "pins": pins})
    return qc, historical


def latest_scopes(qc, bitmap):
    require(len(bitmap["tests"]) == len(set(bitmap["tests"])) == 699, "Not exact699 bitmap")
    old = json.loads((q.BASE / "combined-bits.json").read_bytes())
    require(bitmap["design"] == old["design"] and bitmap["tests"][:690] == old["tests"], "Foreign design/690 prefix")
    design = q.native.inventory.Design(Path(qc["plan"]["design_vdb"]))
    inventory = json.loads(q.INVENTORY.read_bytes())
    scopes = q.build_scopes(design, old, inventory, "full")
    require(scopes == qc["plan"]["scopes"], "Independent qualified source inventory differs")
    for scope, metrics in scopes.items():
        record = bitmap["metrics"]["branch"][scope]
        original = old["metrics"]["branch"][scope]
        require(record["checksum"] == original["checksum"] and record["width"] == original["width"], "Newest shape differs")
        value = int(record["bits"], 16)
        require(0 <= value < 1 << record["width"], "Malformed newest bits")
        for row in metrics["branch"]:
            if row["target"]:
                index = row["point"]["raw_index"]
                require(not value & (1 << (record["width"] - index - 1)), "Newest hit contradicts QBS invariant")
    return scopes


def selected(inputs, bitmap, design):
    require(inputs == [design, *bitmap["tests"]] and len(inputs) == len(set(inputs)) == 700,
            "Not exact ordered699 membership")
    require(len({str(Path(p).resolve(strict=True)) for p in inputs}) == 700, "Aliased membership")
    names = []
    for p in inputs:
        require(Path(p).is_absolute() and not re.search(r"[\s{}]", p) and not Path(p).is_symlink(), "Unsafe canonical VDB path")
    for p in inputs[1:]:
        dirs = list((Path(p) / "snps/coverage/db/testdata").iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir() and not dirs[0].is_symlink(), "Ambiguous testdata VDB")
        name = str(Path(p).with_suffix("") / dirs[0].name)
        require(not re.search(r"[\s{}]", name), "Unsafe GUI test name")
        names.append(name)
    require(len(names) == len(set(names)) == 699, "Duplicate GUI tests")
    return names


def summary(path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)) and
            {"Name", "Depth", "GUIPath", "Scope", "Score", "Line", "Toggle", "FSM", "Condition", "Branch"}
            <= set(reader.fieldnames), "Incomplete summary columns")
        rows = list(reader)
    result = {}
    for row in rows:
        require(None not in row and all(v is not None and v != "" for v in row.values()), "Partial CSV row")
        require(row["Scope"] == row["GUIPath"] and row["Scope"].startswith("ara_tb") and
            row["Name"] == row["Scope"].split(".")[-1] and int(row["Depth"]) == row["Scope"].count("."),
            "Relative or inconsistent GUI scope")
        require(row["Scope"] not in result, "Duplicate summary scope")
        result[row["Scope"]] = row
    require("ara_tb" in result and "ara_tb.dut.i_ara_soc.i_system" in result, "Missing root/system rows")
    return result


def verify_artifacts(output, config):
    required = ["applied.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
        "DVEfiles/dve_gui.log", "live-identity.json", "execution.json", "integrity-before.json", "integrity-after.json",
        "summary_raw.csv", "summary_applied.csv", "summary_reset.csv", "gui-contract.tsv"]
    required += ["states_%s.tsv" % s for s in ("before", "selected", "reset", "final")]
    paths = [output / n for n in required]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing/aliased application evidence")
    rows = qualification.bind_native((output / "applied.el").read_bytes(), config)
    require(rows == config["qualified_records"] and len(rows) == 448, "Applied not exact native448")
    for n in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / n).read_bytes() == b"", "Not globally empty")
    identities = None
    for stage in ("before", "selected", "reset", "final"):
        identities = q.audit_states(output / ("states_%s.tsv" % stage), config, stage, identities)
    require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Actual GUI membership differs")
    raw, applied, reset = [summary(output / ("summary_%s.csv" % s)) for s in ("raw", "applied", "reset")]
    require(raw == reset and set(raw) == set(applied), "Raw/reset or hierarchy differs")
    with (output / "gui-contract.tsv").open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        require(reader.fieldnames == ["stage", "root", "rows"] and list(reader) == [
            dict(stage=stage, root="ara_tb", rows=str(len(raw))) for stage in ("raw", "applied", "reset")],
            "Incomplete full-root contract")
    changes = []
    for scope, row in raw.items():
        require(set(row) == set(applied[scope]), "Summary schema changed")
        affected = any(target == scope or target.startswith(scope + ".") for target in config["plan"]["scopes"])
        for field, value in row.items():
            if value != applied[scope][field]:
                require(affected and field in ("Branch", "Score"), "Unexpected report metric change")
                changes.append(dict(scope=scope, metric=field, raw=value, applied=applied[scope][field]))
    require(any(c["scope"] == "ara_tb" and c["metric"] == "Branch" for c in changes), "No root branch report change")
    for value in (raw["ara_tb"]["Branch"], applied["ara_tb"]["Branch"]):
        require(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", value), "Nonpercent root branch result")
    require(Decimal(applied["ara_tb"]["Branch"][:-1]) > Decimal(raw["ara_tb"]["Branch"][:-1]), "Root branch score did not increase")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    for marker in ("QBSAPP_CANONICAL_INPUTS", "QBSAPP_LOAD_GATE_PASSED", "QBSAPP_DONE_EXACT448"):
        require(log.splitlines().count(marker) == 1, "Missing/ambiguous contract completion")
    for stage in ("before", "selected", "reset", "final"):
        require(log.splitlines().count("QBS_AUDIT %s 4238" % stage) == 1, "Missing exact audit marker")
    for name in ("launcher.log", "DVEfiles/dve_gui.log"):
        require(not re.search(r"QBSAPP_FAILED|DVCDT136|UCAPI-DLMA|Load Failed|EK-CMD-|checksum.*mismatch|"
            r"(?:^|\s)(Warning|Error|Fatal)(?:[\s:-]|$)", (output / name).read_text(), re.I | re.M), "DVE diagnostic")
    live, execution = [json.loads((output / n).read_bytes()) for n in ("live-identity.json", "execution.json")]
    require(live["executable_verified"] is True and live["executable"] == config["plan"]["tool_identity"]["executable"]
        and live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"]
        and execution["returncode"] == 0 and execution["launch_count"] == 1, "Unproven execution identity")
    for n, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / n).read_bytes()) == {field: True, "pins": config["pins"],
            "membership": config["plan"]["input_membership"]}, "Integrity mismatch")
    return dict(status="QBS_%s_EXACT448_HISTORICAL_ONLY" % config["mode"].upper(), tests=len(config["selected_tests"]),
        records=448, protected=3790, final_reset=True, application_approval=False, aggregate_admission=False,
        new_RTL_signoff=False, legacy_waivers_imported=False, official_denominator_verified=False,
        child_cached_percentages_not_interpreted_as_zero_gain=True, summary_changes=changes,
        files={str(p): sha(p) for p in paths})


def read_config(output, seal):
    require(re.fullmatch(r"[a-f0-9]{64}", seal or "") and sha(output / "config.json") == seal, "External config seal differs")
    c = json.loads((output / "config.json").read_bytes())
    require(c["schema"] == "qbs-historical-application-v1" and c["output"] == str(output)
        and c["mode"] in ("contract", "report") and c["aggregate_admission"] is False, "Wrong config")
    capture.check_inputs(c)
    return c


def prepare(output, mode, qualification_result_seal, contract=None, contract_seal=None, contract_result_seal=None):
    require(mode in ("contract", "report") and output.parent.resolve() == OUT.resolve() and not output.exists(), "Fresh direct output")
    qc, review_bytes = qualified_config()
    pins = dict(qc["pins"])
    original_review_sha = pins.pop(str(REVIEW_DOC))
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased evidence: " + str(path))
        value = sha(path)
        require(expected is None or value == expected, "Evidence hash differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Pin collision")
        pins[str(path)] = value
        return path
    def read(path):
        return json.loads(pin(path).read_bytes())
    pin(REVIEW_DOC)
    require(re.fullmatch(r"[a-f0-9]{64}", qualification_result_seal or ""), "External qualification result seal required")
    result = json.loads(pin(QUALIFIED / "capture-result.json", qualification_result_seal).read_bytes())
    require(result["status"] == "QBS_FULL_EXACT_ROUNDTRIP_NOT_APPLICATION_APPROVAL"
        and result["config_sha256"] == QUALIFIED_SEAL, "Full448 not qualified")
    actual = q.verify_artifacts(QUALIFIED, qc)
    require(all(result[k] == v for k, v in actual.items() if k != "files"), "Qualification independently differs")
    for p, h in result["files"].items():
        pin(p, h)
    require(all(result["files"].get(p) == h for p, h in actual["files"].items()), "Qualified artifact mismatch")
    pin(QUALIFIED / "config.json", QUALIFIED_SEAL)
    state, bitmap = read(BASE / "status.json"), read(BASE / "combined-bits.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 699
        and state["new_RTL_signoff"] is False, "Historical699 not admitted")
    inputs = pin(BASE / "combined-inputs.txt").read_text().splitlines()
    names = selected(inputs, bitmap, qc["plan"]["design_vdb"])
    scopes = latest_scopes(qc, bitmap)
    for p, h in bitmap["input_hashes"].items():
        pin(p, h)
    for p, h in read(BASE / "evidence-pins.json").items():
        pin(p, h)
    root_evidence = read(EVENTS / "diagnostic-result.json")
    require(root_evidence["status"] == "SINGLE_TEST_ROOT_EVENT_DIAGNOSTIC_VERIFIED_NOT_APPLICATION_REPORT", "No proven root contract")
    for p, h in {**root_evidence["dependency_pins"], **root_evidence["files"]}.items():
        pin(p, h)
    if mode == "report":
        require(contract is not None and re.fullmatch(r"[a-f0-9]{64}", contract_result_seal or ""), "External contract result required")
        contract = Path(contract).absolute()
        require(contract.parent.resolve() == OUT.resolve() and not contract.is_symlink(), "Unsafe contract")
        cc = read_config(contract, contract_seal)
        cr = json.loads(pin(contract / "capture-result.json", contract_result_seal).read_bytes())
        require(cc["mode"] == "contract" and cr["config_sha256"] == contract_seal, "Not minimal contract")
        cv = verify_artifacts(contract, cc)
        require(all(cr[k] == v for k, v in cv.items() if k != "files"), "Contract independently differs")
        for p, h in {**cc["pins"], **cr["files"]}.items():
            pin(p, h)
        require(all(cr["files"].get(p) == h for p, h in cv["files"].items()), "Contract artifact drift")
        population = read(RAW / "population-verification.json")
        require(population["status"] == "VERIFIED_HISTORICAL_RAW_REPORT" and population["admitted_tests"] == 699,
                "Raw699 population unqualified")
        for p, h in population["pins"].items():
            pin(p, h)
        require((RAW / "inputs.txt").read_text().splitlines() == inputs
            and (RAW / "selected_tests.txt").read_text().splitlines() == names
            and (RAW / "diagnostics.txt").read_bytes() == b""
            and json.loads((RAW / "waiver_status.json").read_bytes())["status"] == "DISABLED", "Raw699 actual selection/waivers mismatch")
    plan = copy.deepcopy(qc["plan"])
    plan["scopes"] = scopes
    if mode == "contract":
        inputs = [inputs[0], str(q.native.SAMPLE)]
        names = [names[bitmap["tests"].index(str(q.native.SAMPLE))]]
    membership = {p: capture.proof.tree_members(Path(p)) for p in inputs}
    for root, members in membership.items():
        for p in members:
            pin(Path(root) / p)
    plan["input_membership"] = membership
    plan["tool_identity"] = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    for p in (SCRIPT, TCL, TEST, HELPERS):
        pin(p)
    text = q.TCL.read_text()
    marker = "set failed [catch {qbs_session} message]"
    require(text.count(marker) == 1, "Frozen helper boundary differs")
    output.mkdir()
    (output / "historical-review.md").write_bytes(review_bytes)
    pin(output / "historical-review.md", original_review_sha)
    (output / "capture-helpers.tcl").write_text(text.split(marker, 1)[0])
    selection = (QUALIFIED / "selection.tcl").read_text()
    selection += "set qbsapp_native " + capture.literal(str(QUALIFIED / "first.el")) + "\n"
    for name, rows in (("databases", inputs[1:]), ("tests", names)):
        selection += "set qbsapp_" + name + " {" + " ".join(capture.literal(p) for p in rows) + "}\n"
    selection += "set qbsapp_count " + str(len(names)) + "\n"
    (output / "selection.tcl").write_text(selection)
    (output / "inputs.txt").write_text("\n".join(inputs) + "\n")
    for p in (output / "selection.tcl", output / "capture-helpers.tcl", output / "inputs.txt"):
        pin(p)
    c = dict(schema="qbs-historical-application-v1", output=str(output), mode=mode, plan=plan, pins=pins,
        selected_tests=names, inputs=inputs, qualified_records=qualification.bind_native((QUALIFIED / "first.el").read_bytes(), qc),
        command=tool.launch_command(plan["tool_identity"], TCL), aggregate_admission=False,
        qualification_result_sha256=qualification_result_seal, latest_precheck_tests=699, legacy_waivers_imported=False,
        historical_document_binding=dict(original_path=str(REVIEW_DOC), original_sha256=original_review_sha,
            archived_exact_bytes=str(output / "historical-review.md"), current_sha256=pins[str(REVIEW_DOC)],
            append_only_recovery=True, no_code_pin_substitutions=True))
    capture.check_inputs(c)
    write(output / "config.json", c)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, aggregate_admission=False))
    print("QBSAPP_PREPARED " + seal, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "run", "verify"))
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--mode", choices=("contract", "report"), default="contract")
    p.add_argument("--seal")
    p.add_argument("--qualification-result-seal")
    p.add_argument("--contract", type=Path)
    p.add_argument("--contract-seal")
    p.add_argument("--contract-result-seal")
    a = p.parse_args()
    o = a.output.absolute()
    require(o.parent.resolve() == OUT.resolve() and not o.is_symlink(), "Unsafe output")
    if a.command == "prepare":
        prepare(o, a.mode, a.qualification_result_seal, a.contract, a.contract_seal, a.contract_result_seal)
    elif a.command == "verify":
        print(json.dumps(verify_artifacts(o, read_config(o, a.seal)), indent=2))
    else:
        capture.TCL, capture.config_read, capture.verify_artifacts = TCL, read_config, verify_artifacts
        original_environment = capture.environment
        def environment(identity, directory):
            env = original_environment(identity, directory)
            for name in ("DVE_REVIEWED_WAIVERS", "DEBUG_CAPTURE_SEAL", "OP1144_BASE_HOOK"):
                env.pop(name, None)
            return env
        capture.environment = environment
        capture.capture(o, a.seal)


if __name__ == "__main__":
    main()
