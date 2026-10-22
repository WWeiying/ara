#!/usr/bin/env python3
"""Source-bound QBS older-path native qualification, never aggregate application."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import capture_operand_debug as native
import closure_point_inventory as shape

capture = native.capture
tool = native.tool
require, sha, write = native.require, native.sha, native.write
HERE, ROOT, OUT = native.HERE, native.ROOT, native.OUT
BASE = native.BASE
INVENTORY = OUT / "qbs-pending-metadata-inventory-690-20261006-01.json"
CALIBRATION = OUT / "qbs-side-path-semantics-20261006-01.json"
TCL = HERE / "capture_qbs_pending_metadata.tcl"
TEST = HERE / "test_capture_qbs_pending_metadata.py"
SCRIPT = Path(__file__).resolve()
ANNOTATION = "Reviewed QBS pending metadata older path; native qualification only; not aggregate approval"
SOURCE_PINS = {
    "hardware/include/qbs_pkg.sv": "f64946527f9f88608a1ab6fdfb19f9854f932ca0a84fa27f4a1aa55cece5234d",
    "hardware/src/vlsu/qbs/qbs_block_adapter.sv": "6038223062242987b6b6064ae85aa875199c5065429202843ac66c99f6336372",
    "hardware/src/vlsu/qbs/qbs_payload_buffer.sv": "664916dbe39405b316c1bff5e750d33b3fecffdfaf5a3c6385287d362ca0056e",
    "hardware/src/vlsu/qbs/qbs_compute_engine.sv": "a37865b05e1e48e19cfd0a1d75a657e9fc55cdc3adbdd389e17dbd90ddd42ad2",
}
frozen_bind = native.bind_native


def side_path(p):
    require(p["line"] in ("378", "403"), "Not metadata side write")
    e = p["expressions"]
    require(len(e) == 2 and e[0]["parent_bit"] == "0" and e[1]["parent_bit"] == "1"
            and e[0]["type"] == "1" and e[1]["type"] == "0" and e[1]["totalbranches"] == "-2",
            "Nested enable/ternary shape differs")
    kind = "weight" if p["line"] == "378" else "activation"
    match = re.fullmatch(r"gen_side_row\[([0-3])\]\.gen_" + kind + r"_byte\[([0-9]+)\]\.enable", e[0]["exprstr"])
    require(match is not None and e[1]["exprstr"] == e[0]["exprstr"][:-6] + "use_newer",
            "Exact side expression pairing differs")
    require(int(match[2]) < (20 if kind == "weight" else 36), "Foreign side byte")
    require(p["attributes"].get("generate_info") == "row=%s,b=%s" % (match[1], match[2]),
            "Compiled generate identity differs")
    require(p["native_vector"] in ({"id": "2", "vector": "1000"},
            {"id": "1", "vector": "0101"}, {"id": "0", "vector": "0011"}), "Unknown calibrated path")
    return kind, int(match[1]), int(match[2])


def build_scopes(design, bitmap, inventory, mode):
    require(mode in ("pilot", "full"), "Invalid mode")
    scopes, reproduced = {}, []
    names = sorted({r["scope"] for r in inventory["points"]})
    require(len(names) == 2 and all(s.endswith("i_block_adapter_bank%d.i_payload_buffer" % b)
            for b, s in enumerate(names)), "Wrong two-bank scope")
    for scope in names:
        owner = design.source(scope)
        require(owner["resolved_path"] == str(ROOT / "hardware/src/vlsu/qbs/qbs_payload_buffer.sv"), "Wrong compiled owner")
        rec = bitmap["metrics"]["branch"][scope]
        definition = design.definition(scope, "branch")
        require(rec["checksum"] == definition.get("chksum") == "3808980594" and rec["width"] == 2119,
                "Compiled branch checksum/population differs")
        rows = []
        for p in shape.points("branch", definition, rec["width"]):
            target = False
            pilot_audit = False
            if p["line"] in ("378", "403"):
                kind, row, byte = side_path(p)
                hit = bool(int(rec["bits"], 16) & (1 << (rec["width"] - 1 - p["raw_index"])))
                require(hit == (p["native_vector"]["vector"] != "0101"), "690 metadata path hit differs")
                reproduced.append(dict(scope=scope, metric_checksum=rec["checksum"], point=p,
                    hit=hit, decision="RETAIN_HIT" if hit else "HOLD_NATIVE_PATH_SEMANTICS_REQUIRED"))
                pilot_audit = kind == "weight" and row == byte == 0
                target = not hit and (mode == "full" or pilot_audit)
            rows.append(dict(point=p, coordinate=native.coordinate(p, "branch"), target=target,
                audit=mode == "full" or pilot_audit, module_checksum=owner["definition_checksum"],
                metric_checksum=rec["checksum"]))
        scopes[scope] = {"branch": rows}
    require(reproduced == inventory["points"] and len(reproduced) == 1344, "Independent1344 inventory differs")
    require(sum(r["target"] for s in scopes.values() for r in s["branch"]) == (2 if mode == "pilot" else 448),
            "Wrong target count")
    return scopes


def bind_native(raw, config):
    require(raw.endswith(b"\n") and not re.search(rb"[^\x0a\x20-\x7e]", raw), "Invalid native bytes")
    lines, scope, annotations = raw.decode("ascii").splitlines(), None, {}
    expected = {}
    for s, metrics in config["plan"]["scopes"].items():
        require(set(metrics) == {"branch"}, "Branch only")
        for r in metrics["branch"]:
            if r["target"]:
                side_path(r["point"])
                p = r["point"]
                require(p["native_vector"]["vector"] == "0101", "Only older path")
                key = s, "Branch %s (%s)" % (p["native_id"], p["vector"])
                require(key not in expected, "Duplicate target")
                expected[key] = "vcs_gen_start:" + p["attributes"]["generate_info"] + ":vcs_gen_end:" + ANNOTATION
    normalized = list(lines)
    for i, line in enumerate(lines):
        if line.startswith("INSTANCE:"):
            match = re.fullmatch(r"INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)", line)
            require(match is not None, "Bad instance")
            scope = match[1]
        if line.startswith("ANNOTATION:"):
            require(i + 1 < len(lines), "Dangling annotation")
            match = re.fullmatch(r'Branch (0|[1-9][0-9]*) "[0-9]+" ".*" \((0|[1-9][0-9]*)\) ".*"', lines[i + 1])
            require(match is not None, "Not a branch record")
            key = scope, "Branch %s (%s)" % (match[1], match[2])
            require(key in expected and key not in annotations and line == 'ANNOTATION: "' + expected[key] + '"',
                    "Exact compiled annotation differs")
            annotations[key] = line
            normalized[i] = 'ANNOTATION: "' + ANNOTATION + '"'
    # Frozen parser still checks exact population, checksums and source expression.
    rows = frozen_bind(("\n".join(normalized) + "\n").encode("ascii"), config)
    require(set(annotations) == set(expected), "Missing annotations")
    for r in rows:
        r["native_annotation"] = annotations[r["scope"], r["point"]]
    return sorted(rows, key=lambda r: (r["scope"], r["point"]))


def audit_states(path, config, stage, previous=None):
    subset = copy.deepcopy(config)
    for metrics in subset["plan"]["scopes"].values():
        metrics["branch"] = [r for r in metrics["branch"] if r["audit"]]
    identities = generic_audit(path, subset, stage, previous)
    for (scope, metric, coordinate), (meta, path) in identities.items():
        sid, vid = coordinate.split(",")
        require(metric == "branch" and re.fullmatch(r"(Branch|MISSING_ELSE|MISSING_DEFAULT)" + re.escape(sid)
                + r"\." + re.escape(vid), meta) and path == "Item" + sid + "." + meta, "Native leaf identity differs")
    return identities


def verify_artifacts(output, config):
    # Frozen verifier includes live identity, exact sample, pin integrity, all
    # five audit stages, complete record roundtrip and three globally empty ELs.
    original_audit = native.audit_states
    try:
        native.audit_states = audit_states
        result = native.verify_artifacts(output, config)
    finally:
        native.audit_states = original_audit
    require(result["records"] == (2 if config["mode"] == "pilot" else 448), "Wrong native population")
    result.update(status="QBS_%s_EXACT_ROUNDTRIP_NOT_APPLICATION_APPROVAL" % config["mode"].upper(),
        baseline_tests=690, pilot_protection_scope="two target-bearing specs; disable/newer four vectors",
        full_native_inventory=4238, native_audited_vectors=6 if config["mode"] == "pilot" else 4238,
        structural_normal_two_state_only=True, exclusions_applied_to_aggregate=False)
    return result


# Keep generic CSV validation accessible while the verifier uses this policy.
generic_audit = native.audit_states


def config_read(output, seal):
    require(re.fullmatch(r"[a-f0-9]{64}", seal or "") and sha(output / "config.json") == seal, "External seal differs")
    c = json.loads((output / "config.json").read_bytes())
    require(c["schema"] == "qbs-pending-native-v1" and c["output"] == str(output)
            and c["mode"] in ("pilot", "full") and c["application_approval"] is False, "Wrong config")
    capture.check_inputs(c)
    return c


def prepare(output, mode, pilot=None, pilot_seal=None, pilot_result_seal=None):
    require(output.parent.resolve() == OUT.resolve() and not output.exists(), "Fresh direct output")
    pins = {}
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased pin: " + str(path))
        value = pins.get(str(path)) or sha(path)
        require(expected is None or value == expected, "Pin mismatch: " + str(path))
        pins[str(path)] = value
        return path
    def read(path):
        return json.loads(pin(path).read_bytes())
    build = read(OUT / "repaired-aligned-build-20260930-01/build-source-pins.json")
    for name, expected in SOURCE_PINS.items():
        require(build[str(ROOT / name)] == expected, "Frozen source identity differs")
        pin(ROOT / name, expected)
    inv, calibration = read(INVENTORY), read(CALIBRATION)
    require(inv["native_qualified"] is False and inv["waivers_applied"] is False, "Not candidate inventory")
    for evidence, field in ((inv, "input_sha256"), (calibration, "pins")):
        for path, expected in evidence[field].items():
            pin(path, expected)
    require([(p["mode"], p["meaning"], p["point"]["native_vector"]["vector"]) for p in calibration["paths"]]
            == [(0, "disabled", "1000"), (1, "older_selected", "0101"), (2, "newer_selected", "0011")], "Calibration differs")
    old = read(native.PLAN)
    state, bitmap = read(BASE / "status.json"), read(BASE / "combined-bits.json")
    require(state["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and state["aggregate_passed"] == 690
            and state["new_RTL_signoff"] is False, "690 historical baseline required")
    inputs = pin(BASE / "combined-inputs.txt").read_text().splitlines()
    design_path = Path(old["design_vdb"])
    require(len(inputs) == len(set(inputs)) == 691 and inputs[0] == str(design_path)
            and inputs[1:] == bitmap["tests"] and str(native.SAMPLE) in inputs[1:], "Exact membership differs")
    for path, expected in read(BASE / "evidence-pins.json").items():
        pin(path, expected)
    scalar, vector = read(BASE / "scalar-comparison.json"), read(BASE / "vector-comparison.json")
    require(scalar["status"] == "TERMINAL_TOHOST_MATCH" and scalar["stopped_at_unobservable"] is None
            and scalar["matched_instructions"] == scalar["ara_retired_instructions"] == 4058
            and vector["status"] == "PASS" and vector["selected_index"] is None
            and vector["stopped_at_spike_index"] is None and vector["compared_instructions"] == 8
            and vector["compared_bytes"] == 2048 and not vector["incomplete_requests"]
            and not vector["unretired_requests"] and vector["first_mismatch"] is None, "Sample not fully admitted")
    for path, expected in old["image"].items():
        pin(path, expected)
    db = design_path / "snps/coverage/db"
    for rel, expected in bitmap["design"].items():
        pin(db / rel, expected)
    for path in sorted(db.rglob("*")):
        if path.is_file() and "testdata" not in path.relative_to(db).parts:
            pin(path)
    membership = {str(native.SAMPLE): capture.proof.tree_members(native.SAMPLE)}
    for path in sorted(native.SAMPLE.rglob("*")):
        if path.is_file():
            pin(path)
    scopes = build_scopes(native.inventory.Design(design_path), bitmap, inv, mode)
    if mode == "full":
        require(pilot is not None, "Qualified pilot required")
        pilot = Path(pilot).absolute()
        require(pilot.parent.resolve() == OUT.resolve() and not pilot.is_symlink(), "Unsafe pilot")
        require(re.fullmatch(r"[a-f0-9]{64}", pilot_result_seal or ""), "External pilot result seal")
        result = json.loads(pin(pilot / "capture-result.json", pilot_result_seal).read_bytes())
        pc = config_read(pilot, pilot_seal)
        require(pc["mode"] == "pilot" and result["config_sha256"] == pilot_seal
                and result["status"] == "QBS_PILOT_EXACT_ROUNDTRIP_NOT_APPLICATION_APPROVAL", "Pilot not complete")
        verified = verify_artifacts(pilot, pc)
        require(all(result[k] == v for k, v in verified.items() if k != "files"), "Independent pilot result differs")
        for path, expected in {**pc["pins"], **result["files"]}.items():
            pin(path, expected)
        require(all(result["files"].get(k) == v for k, v in verified["files"].items()), "Pilot files differ")
    identity = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    for path in (SCRIPT, TCL, TEST, Path(native.__file__), Path(capture.__file__), Path(tool.__file__),
        Path(capture.proof.__file__), Path(shape.__file__), Path(native.inventory.__file__),
        HERE / "capture_operand_debug.tcl", HERE / "reviewed_20261004/audit_readonly.py",
        HERE / "QBS_PENDING_METADATA_REACHABILITY.md"):
        pin(path)
    plan = dict(design_vdb=str(design_path), selected_test_vdb=str(native.SAMPLE), scopes=scopes,
                input_membership=membership, tool_identity=identity)
    output.mkdir()
    script = native.selection(plan) + "set dbg_driver " + capture.literal(str(SCRIPT)) + "\n"
    script += "array set qbs_native_keys {\n" + "\n".join(capture.literal(s) + " {" +
        " ".join(r["coordinate"] for r in m["branch"]) + "}" for s, m in scopes.items()) + "\n}\n"
    script += "array set qbs_audit_keys {\n" + "\n".join(capture.literal(s) + " {" +
        " ".join(r["coordinate"] for r in m["branch"] if r["audit"]) + "}" for s, m in scopes.items()) + "\n}\n"
    (output / "selection.tcl").write_text(script)
    pin(output / "selection.tcl")
    c = dict(schema="qbs-pending-native-v1", mode=mode, output=str(output), plan=plan, pins=pins,
        command=tool.launch_command(identity, TCL), targets={"branch": 2 if mode == "pilot" else 448},
        protected={"branch": 4 if mode == "pilot" else 3790}, application_approval=False,
        historical_only=True, compiled_input_pins=True, capture_only=True)
    write(output / "config.json", c)
    capture.check_inputs(c)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=seal, application_approval=False))
    print("QBS_PREPARED " + seal, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "capture", "first", "verify"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    p.add_argument("--seal")
    p.add_argument("--pilot", type=Path)
    p.add_argument("--pilot-seal")
    p.add_argument("--pilot-result-seal")
    a = p.parse_args()
    output = a.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), "Unsafe output")
    if a.command == "prepare":
        prepare(output, a.mode, a.pilot, a.pilot_seal, a.pilot_result_seal)
    elif a.command == "first":
        c = config_read(output, a.seal)
        print("QBS_FIRST_EXACT " + str(len(bind_native((output / "first.el").read_bytes(), c))), flush=True)
    elif a.command == "verify":
        print(json.dumps(verify_artifacts(output, config_read(output, a.seal)), indent=2))
    else:
        capture.TCL, capture.config_read, capture.verify_artifacts = TCL, config_read, verify_artifacts
        original_environment = capture.environment
        def environment(identity, directory):
            env = original_environment(identity, directory)
            env["DEBUG_CAPTURE_SEAL"] = a.seal
            return env
        capture.environment = environment
        capture.capture(output, a.seal)


native.ANNOTATION = ANNOTATION
native.bind_native = bind_native
if __name__ == "__main__":
    main()
