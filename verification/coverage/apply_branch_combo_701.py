#!/usr/bin/env python3
"""Exact4328 historical701 Branch application; isolated frozen group validators."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "verification/out"
SCRIPT = Path(__file__).resolve()
TCL = SCRIPT.with_suffix(".tcl")
TEST = SCRIPT.with_name("test_apply_branch_combo_701.py")
QBS = OUT / "qbs-rooted-report-701-20261006-01"
QBS_SEAL = "1baa5053809cce9376a0dac10f21893f62e2a6d75b9207a4f9b35f44f5a157d7"
DEBUG = OUT / "operand-debug-1832-product701-parent-qualified-20261006-01/qualification.json"
DEBUG_SEAL = "25968f6335a1d62b3b6fdbeb69db0b0ae2258a8c7ebcf8c278caf9c4d8ead3f2"
REBIND = OUT / "operand-native1144-rebound-701-parentcheck-20261006-01.json"
FF1 = OUT / "ff1-native904-capture-20261006-02"
FF1_SEAL = "43d28c2145a33638d9d6adbc9d22d4f30b90e102b3d6471b1c669b09492aa032"
FF1_RESULT_SEAL = "15c65c3f1e6a43079ea64dc73fe388004c596a32dadc59d8be33cbe6d911baf7"
GROUPS = ("qbs", "debug", "operand", "ff1")
COUNTS = {"qbs": (448, 3790), "debug": (1832, 1176), "operand": (1144, 2492), "ff1": (904, 824)}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def scope_groups(configs):
    owners = {}
    for group in GROUPS:
        for scope in configs[group]["plan"]["scopes"]:
            require(scope not in owners, "Overlapping target/protected scope inventories")
            owners[scope] = group
    require(len(owners) == 74, "Not exact74 compiled scopes")
    return owners


def partition(raw, owners):
    require(raw.endswith(b"\n") and not re.search(rb"[^\x0a\x20-\x7e]", raw), "Invalid aggregate EL bytes")
    text = raw.decode("ascii")
    chunks = re.split(r"(?m)(?=^CHECKSUM:)", text)
    result = {group: [] for group in GROUPS}
    for chunk in chunks:
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        require(len(lines) >= 4 and re.fullmatch(r'CHECKSUM: "[0-9]+ [0-9]+"', lines[0]), "Unknown EL prefix/header")
        instance = re.fullmatch(r"INSTANCE: ?([A-Za-z_][A-Za-z0-9_.\[\]]*)", lines[1])
        require(instance is not None and instance[1] in owners, "Extra/unknown aggregate scope")
        result[owners[instance[1]]].append(chunk)
    require(all(result.values()), "Missing native group")
    return {group: "".join(chunks).encode("ascii") for group, chunks in result.items()}


def worker(group, config_path, native_path, states=None):
    config = json.loads(Path(config_path).read_bytes())
    raw = Path(native_path).read_bytes()
    identities = None
    if group == "qbs":
        import apply_qbs_rooted_701 as q
        rows = q.base.qualification.bind_native(raw, config)
        audit = q.base.q.audit_states
    elif group == "debug":
        import apply_operand_debug_1832 as debug
        rows = debug.qualification.bind_native(raw, config)
        audit = debug.base.audit_states
    elif group == "ff1":
        import capture_ff1_native904 as ff1
        ff1_latest(config, ff1)
        rows = ff1.bind_native(raw, config)
        audit = ff1.audit_states
    else:
        import capture_operand_1144 as operand
        rows = operand.parse_native(raw)
        expected = {r["scope"] + "|" + r["point"]: r for r in config["qualified"]}
        require(set(rows) == set(expected) and len(rows) == 1144, "Not exact1144 group")
        for key, row in rows.items():
            native = expected[key]["native"]
            require(row["checksum"] == native["checksum"] and row["directive"] == native["native_directive"]
                    and row["signature"] == native["native_signature"] and row["annotation"] == operand.ANNOTATION,
                    "Operand native signature differs")
        audit = lambda path, c, stage, prior: operand.states(path, c["plan"], stage, prior)
    if states is not None:
        for stage in ("before", "selected", "reset", "final"):
            identities = audit(Path(states) / ("states_" + stage + ".tsv"), config, stage, identities)
        require(len(identities) == sum(COUNTS[group]), "Protected audit population differs")
    dependencies = {}
    for module in tuple(sys.modules.values()):
        name = getattr(module, "__file__", None)
        if name and Path(name).resolve().parent == HERE and Path(name).suffix == ".py":
            dependencies[str(Path(name).resolve())] = sha(name)
    return dict(records=len(rows), binding_sha256=hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(),
                audited=len(identities) if identities is not None else 0, dependencies=dependencies)


def ff1_latest(config, ff1):
    bitmap = json.loads((OUT / "gap94-offline-admitted-701-20261006-01/combined-bits.json").read_bytes())
    require(len(bitmap["tests"]) == len(set(bitmap["tests"])) == 701, "FF1 latest population differs")
    design = ff1.prep.compiled.Design(Path(config["plan"]["design_vdb"]))
    static = json.loads(ff1.flags.STATIC.read_bytes())
    targets, protected = 0, 0
    for scope, metrics in config["plan"]["scopes"].items():
        original = static["scopes"][scope]
        require(design.source(scope) == original["source"], "FF1 source ownership differs")
        inner = re.search(r"\.gen_num_lanes\[([0-3])\]\.", scope)
        require(inner is not None, "FF1 physical position differs")
        rows = metrics["branch"]
        definition = design.definition(scope, "branch")
        record = bitmap["metrics"]["branch"][scope]
        require(record["width"] == 54 and record["checksum"] == definition.get("chksum") == original["metric_checksum"],
                "FF1 latest compiled shape differs")
        require(ff1.prep.compiled.points("branch", definition, 54) == [r["point"] for r in rows], "FF1 exact compiled coordinates differ")
        bits = int(record["bits"], 16)
        require(0 <= bits < 1 << 54, "FF1 latest bitmap out of range")
        for row in rows:
            bit = row["calibrated_input_bit"]
            wanted = 0 <= bit < (0, 29, 42, 42)[int(inner[1])]
            require(row["target"] == wanted, "FF1 zero/default/WIDTH64 protection changed")
            if wanted:
                targets += 1
                require(not bits & (1 << (53 - row["point"]["raw_index"])), "FF1 latest hit contradicts width proof")
            else:
                protected += 1
    require((targets, protected) == (904, 824), "FF1 latest target/protected inventory differs")


def invoke(group, config, raw, states=None):
    with tempfile.TemporaryDirectory(prefix="branch-combo-bind-") as directory:
        directory = Path(directory)
        write(directory / "config.json", config)
        (directory / "native.el").write_bytes(raw)
        command = [sys.executable, "-B", str(SCRIPT), "worker", "--group", group,
                   "--group-config", str(directory / "config.json"), "--native", str(directory / "native.el")]
        if states is not None:
            command += ["--states", str(states)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=180, check=True)
        return json.loads(result.stdout)


def check_group_bindings(raw, config, output=None):
    parts = partition(raw, config["scope_owners"])
    results = {}
    for group in GROUPS:
        results[group] = invoke(group, config["groups"][group], parts[group], output / group if output else None)
        expected = config["bindings"][group]
        require(results[group]["records"] == COUNTS[group][0]
                and results[group]["binding_sha256"] == expected["binding_sha256"]
                and results[group]["dependencies"] == expected["dependencies"], "Independent group binding/dependency changed")
    require(sum(r["records"] for r in results.values()) == 4328, "Not exact4328 native EL")
    return results


def pin(pins, path, expected=None):
    path = Path(path).absolute()
    require(path.is_file() and not path.is_symlink(), "Missing/aliased combo evidence: " + str(path))
    value = sha(path)
    require(expected is None or value == expected, "Combo pin differs: " + str(path))
    require(str(path) not in pins or pins[str(path)] == value, "Combo pin collision")
    pins[str(path)] = value
    return path


def prepare(output, qbs_result_seal, rebind_seal):
    import apply_qbs_rooted_701 as q
    import capture_operand_1144 as operand
    require(output.parent.resolve() == OUT.resolve() and not output.exists(), "Fresh combo output required")
    require(re.fullmatch(r"[0-9a-f]{64}", qbs_result_seal or "") and
            re.fullmatch(r"[0-9a-f]{64}", rebind_seal or ""), "External application/rebind seals required")
    pins = {}
    qc = q.base.read_config(QBS, QBS_SEAL)
    qr = json.loads(pin(pins, QBS / "capture-result.json", qbs_result_seal).read_bytes())
    # Only the completed, independently regenerated QBS701 application gates this run.
    verified = q.verify_artifacts(QBS, qc)
    require(qr["config_sha256"] == QBS_SEAL and qr["status"] == "QBS_ROOTED_REPORT_EXACT448_HISTORICAL701_PRODUCT_ONLY"
            and all(qr.get(k) == v for k, v in verified.items() if k != "files")
            and all(qr["files"].get(k) == v for k, v in verified["files"].items()), "QBS701 application not independently qualified")
    for path, expected in {**qc["pins"], **qr["files"]}.items():
        pin(pins, path, expected)
    pin(pins, QBS / "config.json", QBS_SEAL)
    dr = json.loads(pin(pins, DEBUG, DEBUG_SEAL).read_bytes())
    require(dr["status"] == "FULL701_EXACT1832_ARA_TB_PRODUCT_REPORT_OFFLINE_QUALIFIED"
            and dr["tests"] == 701 and dr["targets"] == 1832 and dr["protected"] == 1176 and dr["final_reset"] is True,
            "Debug701 application unqualified")
    for path, expected in dr["pins"].items():
        pin(pins, path, expected)
    dc = json.loads(pin(pins, q.vendor.ATTEMPT / "config.json", q.vendor.SEAL).read_bytes())
    require(type(dc["corpus_tests"]) is int and dc["corpus_tests"] == len(qc["inputs"]) - 1 == 701
            and dc["selected_tests"] == qc["selected_tests"]
            and set(dc["membership"]) == set(qc["inputs"])
            and dc["membership"] == qc["plan"]["input_membership"], "Different701 group population")
    rebound = json.loads(pin(pins, REBIND, rebind_seal).read_bytes())
    require(rebound["status"] == "NATIVE1144_REBOUND_TO_RAW701_NOT_APPLIED" and rebound["tests"] == 701
            and rebound["target_count"] == len(rebound["records"]) == 1144 and rebound["target_hits"] == 0
            and rebound["application_approval"] is False, "Operand rebind not qualified")
    for path, expected in rebound["pins"].items():
        pin(pins, path, expected)
    qualification_path = OUT / "operand-native-static-qualification-690-20261006-01/qualification.json"
    static = json.loads(qualification_path.read_bytes())
    oc = json.loads(pin(pins, Path(static["native_file"]).parent / "config.json", static["config_sha256"]).read_bytes())
    ff1_check = subprocess.run([sys.executable, "-B", str(HERE / "capture_ff1_native904_v2.py"), "verify",
                               "--output", str(FF1), "--seal", FF1_SEAL, "--result-seal", FF1_RESULT_SEAL],
                              text=True, capture_output=True, timeout=180, check=True)
    require(ff1_check.stdout.strip() == "FF1_NATIVE904_V2_REVERIFIED", "FF1 independent qualification differs")
    fc = json.loads(pin(pins, FF1 / "config.json", FF1_SEAL).read_bytes())
    fr = json.loads(pin(pins, FF1 / "capture-result.json", FF1_RESULT_SEAL).read_bytes())
    for path, expected in {**fc["pins"], **fr["files"]}.items():
        pin(pins, path, expected)
    groups = dict(qbs=qc, debug=dc["native_config"], operand=dict(plan=oc["plan"], qualified=rebound["records"]), ff1=fc)
    owners = scope_groups(groups)
    require(qc["inputs"][0] == dc["native_config"]["plan"]["design_vdb"] == oc["plan"]["design_vdb"] == fc["plan"]["design_vdb"], "Mixed compiled designs")
    native_files = dict(qbs=QBS / "applied.el", debug=q.vendor.ATTEMPT / "applied.el", operand=Path(static["native_file"]), ff1=FF1 / "first.el")
    bindings = {g: invoke(g, groups[g], pin(pins, native_files[g]).read_bytes()) for g in GROUPS}
    for group, binding in bindings.items():
        require(binding["records"] == COUNTS[group][0], "Wrong exact group population")
        for path, expected in binding["dependencies"].items():
            pin(pins, path, expected)
    # Add the two source-derived helpers absent from the static rebind pins.
    for name in ("inventory_operand_debug.py", "closure_point_inventory.py"):
        pin(pins, HERE / name)
    bitmap = json.loads((q.BASE701 / "combined-bits.json").read_bytes())
    require(rebound["records"] == json.loads((qualification_path.parent / "qualified-records.json").read_bytes())["records"],
            "Rebound qualification records differ")
    import rebind_operand_1144_701 as rebind
    design = rebind.Design(Path(qc["inputs"][0]))
    definitions, seen, null = {}, set(), set()
    for item in rebound["records"]:
        scope = item["scope"]
        record = bitmap["metrics"]["branch"][scope]
        if scope not in definitions:
            definition = design.definition(scope, "branch")
            require([design.hierarchy[scope].get("chksum"), definition.get("chksum")] == item["checksum"], "Operand compiled shape differs")
            definitions[scope] = {p["raw_index"]: p for p in rebind.points("branch", definition, record["width"])}
        point = definitions[scope][item["raw_index"]]
        spec, vector = re.fullmatch(r"Branch (\d+) \((\d+)\)", item["point"]).groups()
        require((point["native_id"], point["vector"], point["attributes"]["chksum"]) == (spec, vector, item["spec_checksum"])
                and record["checksum"] in (None, item["checksum"][1]), "Operand native coordinate differs")
        require((scope, item["raw_index"]) not in seen and not int(record["bits"], 16) &
                (1 << (record["width"] - item["raw_index"] - 1)), "Operand target duplicate/hit")
        seen.add((scope, item["raw_index"]))
        if record["checksum"] is None:
            null.add(scope)
    require(len(seen) == 1144 and len(definitions) == 36 and sorted(null) == rebound["compiled_bound_null_checksum_scopes"],
            "Incomplete operand rebind")
    for path, expected in bitmap["input_hashes"].items():
        pin(pins, path, expected)
    for path in (SCRIPT, TCL, TEST, HERE / "capture_operand_1144.tcl", q.vendor.app.HOOK, HERE / "rebind_operand_1144_701.py",
                 HERE / "capture_ff1_native904.tcl", HERE / "capture_ff1_native904_v2.py"):
        pin(pins, path)
    config = copy.deepcopy(qc)
    config.update(output=str(output), pins=pins, groups=groups, scope_owners=owners, bindings=bindings,
                  combo_seals=dict(qbs_config=QBS_SEAL, qbs_result=qbs_result_seal, debug_result=DEBUG_SEAL, operand_rebind=rebind_seal,
                                   ff1_config=FF1_SEAL, ff1_result=FF1_RESULT_SEAL))
    roots = {"ara_tb", "ara_tb.dut.i_ara_soc.i_system", "ara_tb.dut.i_ara_soc.i_system.i_ara"}
    for scope in owners:
        parts = scope.split(".")
        roots.update(".".join(parts[:i]) for i in range(1, len(parts) + 1))
    config["root_refresh_scopes"] = sorted(roots)
    config["plan"]["scopes"] = {**groups["qbs"]["plan"]["scopes"], **groups["debug"]["plan"]["scopes"]}
    config["plan"]["scopes"].update(groups["ff1"]["plan"]["scopes"])
    # Include operand scopes for report ancestry only; their own audit uses the exact original plan.
    config["plan"]["scopes"].update({s: {} for s in groups["operand"]["plan"]["scopes"]})
    config["plan"]["tool_identity"] = q.base.tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve", "/usr/bin/xvfb-run")
    config["command"] = q.base.tool.launch_command(config["plan"]["tool_identity"], TCL)
    joined = b"\n".join(native_files[g].read_bytes() for g in GROUPS)
    check_group_bindings(joined, config)
    output.mkdir()
    for group in GROUPS:
        (output / group).mkdir()
    (output / "combined.el").write_bytes(joined)
    for name in ("root-helpers.tcl", "capture-helpers.tcl"):
        (output / name).write_bytes((QBS / name).read_bytes())
    selection = (QBS / "selection.tcl").read_text()
    selection += "set qbsapp_native " + q.base.capture.literal(str(output / "combined.el")) + "\n"
    (output / "selection.tcl").write_text(selection)
    (output / "qbs-selection.tcl").write_text(selection)
    (output / "debug-selection.tcl").write_bytes((q.vendor.ATTEMPT / "selection.tcl").read_bytes())
    (output / "ff1-selection.tcl").write_bytes((FF1 / "selection.tcl").read_bytes())
    (output / "operand-selection.tcl").write_text(operand.selection(oc["plan"]))
    (output / "root-selection.tcl").write_text("set qbsrefresh_scopes {" + " ".join(q.base.capture.literal(s) for s in sorted(roots)) + "}\n")
    (output / "inputs.txt").write_text("\n".join(qc["inputs"]) + "\n")
    for name in ("combined.el", "selection.tcl", "qbs-selection.tcl", "debug-selection.tcl", "operand-selection.tcl", "ff1-selection.tcl",
                 "root-selection.tcl", "root-helpers.tcl", "capture-helpers.tcl", "inputs.txt"):
        pin(pins, output / name)
    q.base.capture.check_inputs(config)
    write(output / "config.json", config)
    value = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE", config_sha256=value, aggregate_admission=False))
    print("BRANCH_COMBO701_PREPARED " + value)


def read_config(output, seal):
    import apply_qbs_rooted_701 as q
    require(re.fullmatch(r"[0-9a-f]{64}", seal or "") and sha(output / "config.json") == seal, "Combo config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["output"] == str(output) and config["mode"] == "report" and len(config["selected_tests"]) == 701
            and len(set(config["selected_tests"])) == 701 and config["aggregate_admission"] is False, "Wrong combo population")
    require(config["scope_owners"] == scope_groups(config["groups"]), "Combined scope owners differ")
    require(config["inputs"] == (q.BASE701 / "combined-inputs.txt").read_text().splitlines()
            and config["selected_tests"] == (q.RAW701 / "selected_tests.txt").read_text().splitlines(), "Different aggregate701 inputs")
    q.base.capture.check_inputs(config)
    return config


def verify_artifacts(output, config):
    import apply_qbs_rooted_701 as q
    paths = [output / n for n in ("applied.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
        "summary_raw.csv", "summary_applied.csv", "summary_reset.csv", "rooted-metrics.csv", "gui-contract.tsv",
        "live-identity.json", "execution.json", "integrity-before.json", "integrity-after.json", "DVEfiles/dve_gui.log", "launcher.log")]
    paths += [output / g / ("states_" + s + ".tsv") for g in GROUPS for s in ("before", "selected", "reset", "final")]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing/aliased combined evidence")
    results = check_group_bindings((output / "applied.el").read_bytes(), config, output)
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Aggregate reset is not globally empty")
    require((output / "selected_tests.txt").read_text().splitlines() == config["selected_tests"], "Actual selected701 differs")
    raw, applied, reset = [q.previous.pilot.corrected.summary(output / ("summary_" + s + ".csv")) for s in ("raw", "applied", "reset")]
    require(raw == reset and set(raw) == set(applied), "Combined hierarchy/reset differs")
    q.product_match(raw, q.reference_rows(q.RAW701 / "summary.csv"))
    changes = []
    for scope, row in raw.items():
        require(set(row) == set(applied[scope]), "Aggregate report columns changed")
        for metric, value in row.items():
            other = applied[scope][metric]
            if other != value:
                require(metric in ("Branch", "Score") and any(s == scope or s.startswith(scope + ".") for s in config["scope_owners"]),
                        "Unexpected combined report change")
                changes.append(dict(scope=scope, metric=metric, raw=value, applied=other))
    rooted = q.previous.pilot.rooted_rows(output / "rooted-metrics.csv", config["root_refresh_scopes"])
    log = (output / "DVEfiles/dve_gui.log").read_text()
    for marker in ("QBSAPP_CANONICAL_INPUTS", "QBSAPP_LOAD_GATE_PASSED", "COMBO_DONE_EXACT4328"):
        require(log.splitlines().count(marker) == 1, "Missing exact combined completion")
    for stage in ("before", "selected", "reset", "final"):
        for prefix, count in (("QBS_AUDIT", 4238), ("OBD_AUDIT", 3008), ("OP1144_AUDIT", 3636), ("FF1_AUDIT", 1728)):
            require(log.splitlines().count("%s %s %s" % (prefix, stage, count)) == 1, "Missing protected audit marker")
    for name in ("launcher.log", "DVEfiles/dve_gui.log"):
        require(not re.search(r"COMBO_FAILED|UCAPI-DLMA|DVCDT136|Load Failed|EK-CMD-|checksum.*mismatch|(?:^|\s)(Warning|Error|Fatal)(?:[\s:-]|$)",
                              (output / name).read_text(), re.I | re.M), "Combined DVE diagnostic")
    live, execution = [json.loads((output / n).read_bytes()) for n in ("live-identity.json", "execution.json")]
    require(live["executable_verified"] is True and live["executable"] == config["plan"]["tool_identity"]["executable"]
            and live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"]
            and execution["returncode"] == 0 and execution["launch_count"] == 1, "Unproven combined tool execution")
    for name, key in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / name).read_bytes()) == {key: True, "pins": config["pins"], "membership": config["plan"]["input_membership"]},
                "Combined integrity differs")
    return dict(status="HISTORICAL701_EXACT4328_PRODUCT_BRANCH_REPORT_NOT_AGGREGATE_SIGNOFF", tests=701,
                records=4328, protected=8282, audited=12610, final_reset=True, aggregate_admission=False,
                new_RTL_signoff=False, official_denominator_verified=False, group_results=results,
                summary_changes=changes, rooted_metrics=rooted, allowed_report_absence=config["reviewed_external_root"],
                files={str(p): sha(p) for p in paths})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("prepare", "run", "verify", "worker"))
    p.add_argument("--output", type=Path)
    p.add_argument("--seal")
    p.add_argument("--qbs-result-seal")
    p.add_argument("--rebind-seal")
    p.add_argument("--group", choices=GROUPS)
    p.add_argument("--group-config", type=Path)
    p.add_argument("--native", type=Path)
    p.add_argument("--states", type=Path)
    a = p.parse_args()
    if a.command == "worker":
        print(json.dumps(worker(a.group, a.group_config, a.native, a.states)))
        return
    require(a.output is not None, "Output required")
    output = a.output.absolute()
    require(output.parent.resolve() == OUT.resolve() and not output.is_symlink(), "Unsafe combo output")
    if a.command == "prepare":
        prepare(output, a.qbs_result_seal, a.rebind_seal)
    elif a.command == "verify":
        print(json.dumps(verify_artifacts(output, read_config(output, a.seal)), indent=2))
    else:
        import capture_operand_1144 as capture
        capture.TCL, capture.config_read, capture.verify_artifacts = TCL, read_config, verify_artifacts
        original = capture.environment
        def environment(identity, directory):
            env = original(identity, directory)
            for name in ("DVE_REVIEWED_WAIVERS", "DEBUG_CAPTURE_SEAL", "OP1144_BASE_HOOK", "OBD_SELECTION"):
                env.pop(name, None)
            return env
        capture.environment = environment
        capture.capture(output, a.seal)


if __name__ == "__main__":
    main()
