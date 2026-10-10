#!/usr/bin/env python3
"""Single-test FP16 pack208 native format capture; no corpus application."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import capture_narrow_exponent_native1272 as reference
import inventory_fp16_pack_lower_bound_705 as inventory

lifecycle, common, tool = reference.lifecycle, reference.common, reference.tool
require, sha, write = reference.require, reference.sha, reference.write
HERE = Path(__file__).resolve().parent
OUT = inventory.OUT
HOOK = HERE / "capture_fp16_pack_native208_v2.tcl"
INVENTORY = OUT / "fp16-pack-lower-bound-candidates-705-20261006-01.json"
INVENTORY_SEAL = "7f39b6b35939e1c0a0649d162be83de796b2ee76eb1e42a6156ce5338039783f"
ANNOTATION = "FP16 pack lower bound exact case native qualification only; not application approval"
STAGES = lifecycle.STAGES



OBSERVATION = OUT / "fp16-pack-native208-capture-prepare-20261006-01"
OBSERVATION_PINS = {
    "config.json": "b97dc5a8e9d3bcd2d84a260d43641c7475b04fbabd84c160e34a5d22c6b5ec70",
    "first.el": "c7eea0f49ca13c021043f81c96c1d718337ec777228144d185e87b311bcf445e",
    "states_before.tsv": "974ec93fa08640b9586692fd9d7c1068643d006cfafa06bce534a45e1fbffe03",
    "states_selected.tsv": "6483f4f24b60c846c65f1cb706c53ebaf32a6c248be3396cab1a659fd44f7e3a",
    "states_final.tsv": "974ec93fa08640b9586692fd9d7c1068643d006cfafa06bce534a45e1fbffe03",
    "initial-empty.el": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "final-empty.el": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "status.json": "5bdb035829213d1027e31bc33240853288d3bc193206907bc2d1455c13f563b1",
}


def native_serialization(row):
    p = row["point"]
    require(row["target"] and p["native_id"] == "7" and row["case_item"] is not None,
            "Not a reviewed explicit case arm")
    expressions = p["expressions"]
    require(len(expressions) == 2, "Unexpected expression tree")
    root, child = expressions
    require(root == {"totalbranches": "54", "id": "178", "index": "1", "parent_bit": "0",
                     "exprstr": "vfdsu_ex4_expnt_rst[12:0]", "file_id": "370"},
            "Root case identity differs")
    require(child == {"totalbranches": "-2", "id": "232", "index": "55", "parent_bit": "54",
                      "exprstr": "vfdsu_ex4_denorm_to_tiny_frac", "file_id": "370",
                      "true_clause_line": "232", "false_clause_line": "232",
                      "type": "0", "is_ternary_leaf_node": "0"},
            "Nested default ternary identity differs")
    require(p["expression"] == root["exprstr"] + " ; " + child["exprstr"],
            "Complete diagnostic expression differs")
    vector = int(p["vector"])
    require(27 <= vector <= 52 and p["native_vector"] ==
            {"id": str(vector), "vector": format(1 << vector, "056b")},
            "Explicit arm does not leave default subtree inactive")
    require(row["case_item"]["index"] == str(vector + 1) and
            row["case_item"]["name"] == "13'h%04x " % ((1 - vector) & 8191),
            "Explicit source case constant differs")
    # Default owns bit54 and the ternary's two outcomes. An explicit one-hot
    # case arm bypasses that subtree; DVE serializes its unused column as '-'.
    expression = root["exprstr"]
    return dict(expression=expression, signature=expression + " " + row["case_item"]["name"] + ",-")


def load_serialization_observation():
    for name, expected in OBSERVATION_PINS.items():
        require(sha(OBSERVATION / name) == expected, "Frozen failed observation differs")
    old = json.loads((OBSERVATION / "config.json").read_bytes())
    require(old["inventory_sha256"] == INVENTORY_SEAL and
            json.loads((OBSERVATION / "status.json").read_bytes())["status"] == "FAILED",
            "Not preserved failed source-bound observation")
    for path, expected in old["pins"].items():
        require(sha(path) == expected, "Original observation input pin differs")
    validate_plan(old["plan"])
    records = bind_native((OBSERVATION / "first.el").read_bytes(), old)
    previous = None
    for stage in ("before", "selected", "final"):
        previous = audit_states(OBSERVATION / ("states_%s.tsv" % stage), old, stage, previous)
    require((OBSERVATION / "initial-empty.el").read_bytes() ==
            (OBSERVATION / "final-empty.el").read_bytes() == b"", "Original reset not empty")
    return dict(status="FAILED_CAPTURE_FIRST_EXPORT_SERIALIZATION_BOUND_NOT_ROUNDTRIP_APPROVAL",
                first_records=len(records), exact_selectors=1144, final_reset=True,
                expression_rule="root branch_cexpr, not aggregated diagnostic expressions",
                signature_rule="root + space + exact case_item.name + comma + inactive-default '-'",
                pins={str(OBSERVATION / n): h for n, h in OBSERVATION_PINS.items()},
                original_failure_preserved=True, native_roundtrip_qualified=False)


def load_inventory():
    require(sha(INVENTORY) == INVENTORY_SEAL, "External source inventory seal differs")
    saved = json.loads(INVENTORY.read_bytes())
    require(saved == inventory.build_inventory(), "Source/coordinate inventory reproduction differs")
    return saved


def make_plan(saved, selected, membership):
    design = inventory.Design(Path(selected["design_vdb"]))
    scopes = {}
    for scope in sorted({r["scope"] for r in saved["candidates"]}):
        source = design.source(scope)
        rows = sorted([r for r in saved["candidates"] + saved["protected"] if r["scope"] == scope],
                      key=lambda r: r["point"]["raw_index"])
        require(len(rows) == 143, "Incomplete pack scope")
        rows = [dict(point=r["point"], coordinate=common.coordinate(r["point"], "branch"),
                     target=r["decision"] == "SOURCE_PROOF_CANDIDATE_NATIVE_PENDING",
                     hit=r["raw_hit"], case_item=r["case"]["item"] if r["case"] else None,
                     module_checksum=source["definition_checksum"],
                     metric_checksum=r["metric_checksum"], decision=r["decision"]) for r in rows]
        require([r["point"] for r in rows] == inventory.points("branch", design.definition(scope, "branch"), 143),
                "Complete point reconstruction differs")
        require(sum(r["target"] for r in rows) == 26, "Wrong physical target count")
        scopes[scope] = {"branch": rows}
    return dict(design_vdb=selected["design_vdb"], selected_test_vdb=selected["selected_test_vdb"],
                tool_identity=selected["tool_identity"], input_membership=membership, scopes=scopes)


def validate_plan(plan):
    require(len(plan["scopes"]) == 8, "Wrong exact scope count")
    targets, protected = [], []
    for scope, metrics in plan["scopes"].items():
        require(scope.endswith(".x_ct_vfdsu_pack") and set(metrics) == {"branch"}, "Foreign scope/metric")
        rows = metrics["branch"]
        require(len(rows) == 143 and [r["point"]["raw_index"] for r in rows] == list(range(143)),
                "Incomplete/duplicate scope inventory")
        for row in rows:
            p = row["point"]
            require(row["coordinate"] == common.coordinate(p, "branch"), "Coordinate differs")
            if row["target"]:
                require(row["hit"] is False and p["native_id"] == "7" and p["raw_index"] in range(30, 56)
                        and p["vector"] == str(82 - p["raw_index"]) and row["case_item"] is not None,
                        "Default/boundary/foreign/hit target")
                value = int(row["case_item"]["name"].strip()[4:], 16) - 8192
                require(value == p["raw_index"] - 81 and -51 <= value <= -26,
                        "Wrong explicit source case constant")
                targets.append(row)
            else:
                protected.append(row)
    require(len(targets) == 208 and len(protected) == 936, "Target/protect set differs")


def check(config):
    validate_plan(config["plan"])
    require(config["command"] == tool.launch_command(config["plan"]["tool_identity"], HOOK),
            "Launch command differs")
    require(set(config["plan"]["input_membership"]) ==
            {config["plan"]["design_vdb"], config["plan"]["selected_test_vdb"]},
            "Not exactly one historical test")
    lifecycle.check_inputs(config)
    require(config["serialization_observation"] == load_serialization_observation(), "Serialization observation differs")


def read_config(output, seal):
    require(re.fullmatch(r"[0-9a-f]{64}", seal or "") and sha(output / "config.json") == seal,
            "External capture config seal differs")
    config = json.loads((output / "config.json").read_bytes())
    require(config["schema"] == "fp16-pack-native208-v2" and config["output"] == str(output) and
            config["inventory_sha256"] == INVENTORY_SEAL and config["targets"] == 208 and
            config["protected"] == 936 and config["capture_only"] is True and
            config["application_approval"] is False and config["product_VDB_admission"] is False,
            "Wrong capture config")
    check(config)
    return config


def prepare(output):
    require(output.parent == OUT and not output.exists() and output.resolve() == output, "Fresh direct output required")
    saved = load_inventory()
    selected = reference.load_plan()
    pins = dict(selected["pins"])
    pins.pop(str(reference.DOC))
    pins[str(reference.DOC_SNAPSHOT)] = reference.DOC_SHA
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased input")
        value = sha(path)
        require(expected is None or value == expected, "Expected pin differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Expected pin conflict")
        pins[str(path)] = value
    for path, expected in saved["pins"].items():
        pin(path, expected)
    pin(INVENTORY, INVENTORY_SEAL)
    for name in ("manifest.json", "capture-plan.json", "selection.tcl"):
        pin(reference.SEALED / name)
    bitmap = json.loads((inventory.BASE / "combined-bits.json").read_bytes())
    require(selected["selected_test_vdb"] in bitmap["tests"], "Sample absent from admitted705")
    membership = {root: lifecycle.proof.tree_members(root)
                  for root in (selected["design_vdb"], selected["selected_test_vdb"])}
    for root, names in membership.items():
        for name in names:
            pin(Path(root) / name)
    plan = make_plan(saved, selected, membership)
    observation = load_serialization_observation()
    for path, expected in observation["pins"].items():
        pin(path, expected)
    validate_plan(plan)
    # Bind every imported local dependency as well as the Tcl library.
    for module in list(sys.modules.values()):
        path = getattr(module, "__file__", None)
        if path and Path(path).suffix == ".py" and inventory.ROOT in Path(path).resolve().parents:
            pin(Path(path).resolve())
    for path in (Path(__file__), HOOK, HERE / "test_capture_fp16_pack_native208_v2.py",
                 HERE / "capture_operand_debug.tcl", reference.DOC_SNAPSHOT):
        pin(path)
    selection = common.selection(plan)
    selection += "set exp_python " + lifecycle.literal(sys.executable) + "\n"
    selection += "set exp_driver " + lifecycle.literal(str(Path(__file__).resolve())) + "\n"
    selection += "set exp_test_identity " + lifecycle.literal(selected["selected_test"]) + "\n"
    for path, expected in pins.items():
        require(sha(path) == expected, "Input drift before prepare")
    output.mkdir()
    (output / "selection.tcl").write_text(selection)
    pin(output / "selection.tcl")
    config = dict(schema="fp16-pack-native208-v2", output=str(output), inventory_sha256=INVENTORY_SEAL,
                  pins=pins, plan=plan, selected_test=selected["selected_test"], targets=208, protected=936,
                  command=tool.launch_command(plan["tool_identity"], HOOK), capture_only=True,
                  application_approval=False, product_VDB_admission=False,
                  all_same_scope_positions=1144, default_and_minus25_protected=True,
                  native_case_identity_pending=True, serialization_observation=observation)
    check(config)
    write(output / "config.json", config)
    seal = sha(output / "config.json")
    write(output / "status.json", dict(status="PREPARED_NO_DVE_REQUIRES_PARENT_CONFIG_REVIEW",
                                       config_sha256=seal, targets=208, protected=936, application_approval=False))
    print("PACK208_PREPARED seal=" + seal, flush=True)


def bind_native(raw, config):
    records = lifecycle.parse_native(raw)
    expected = {}
    for scope, metrics in config["plan"]["scopes"].items():
        require(scope.endswith(".x_ct_vfdsu_pack"), "Foreign native owner")
        for row in metrics["branch"]:
            if row["target"]:
                p = row["point"]
                key = scope + "|Branch %s (%s)" % (p["native_id"], p["vector"])
                require(key not in expected and row["case_item"] is not None and
                        row["case_item"]["name"] != "default" and row["hit"] is False,
                        "Invalid/duplicate/default/hit target")
                expected[key] = row
    require(len(expected) == config["targets"] == 208 and set(records) == set(expected),
            "Extra/missing native population")
    for key, row in expected.items():
        p, actual = row["point"], records[key]
        serialized = native_serialization(row)
        require(actual["checksum"] == [row["module_checksum"], row["metric_checksum"]] and
                actual["spec_checksum"] == p["attributes"]["chksum"] and
                actual["expression"] == serialized["expression"] and actual["annotation"] == ANNOTATION and
                actual["signature"] == serialized["signature"],
                "Complete native checksum/expression/explicit case signature differs")
    return records

def audit_states(path, config, stage, previous=None):
    require(stage in STAGES, "Unknown audit stage")
    got = common.audit_states(path, config, stage, previous)
    require(len(got) == 1144, "Incomplete full selector audit")
    for (scope, metric, coordinate), (meta, native_path) in got.items():
        sid, vid = coordinate.split(",")
        require(metric == "branch" and re.fullmatch(r'(Branch|MISSING_ELSE|MISSING_DEFAULT)' + re.escape(sid) + r'\.' + re.escape(vid), meta) and
                native_path == "Item%s.%s" % (sid, meta), "Observed native selector identity differs")
    return got


def verify(output, config):
    check(config)
    names = ["first.el", "second.el", "initial-empty.el", "reset-empty.el", "final-empty.el", "selected_tests.txt",
             "DVEfiles/dve_gui.log", "live-identity.json", "execution.json", "integrity-before.json", "integrity-after.json"]
    names += ["states_%s.tsv" % s for s in STAGES]
    paths = [output / n for n in names]
    require(all(p.is_file() and not p.is_symlink() for p in paths), "Missing/aliased native evidence")
    first, second = [bind_native((output / n).read_bytes(), config) for n in ("first.el", "second.el")]
    require(first == second, "Exact complete native roundtrip differs")
    for name in ("initial-empty.el", "reset-empty.el", "final-empty.el"):
        require((output / name).read_bytes() == b"", "Global exclusion reset not empty")
    previous = None
    for stage in STAGES:
        previous = audit_states(output / ("states_%s.tsv" % stage), config, stage, previous)
    require((output / "selected_tests.txt").read_text().splitlines() == [config["selected_test"]], "Selected test differs")
    log = (output / "DVEfiles/dve_gui.log").read_text()
    require(log.splitlines().count("PACK208_CAPTURE_DONE") == 1 and not re.search(
        r'PACK208_FAILED|PACK208_SESSION_ERROR|EK-CMD-|UCAPI-DLMA|DVCDT136|invalid command name|(?:^|\s)(Error|Fatal):|checksum.*mismatch',
        log, re.I), "GUI failed/incomplete")
    for stage in STAGES:
        require(log.splitlines().count("PACK208_AUDIT %s 1144" % stage) == 1, "GUI audit marker differs")
    execution = json.loads((output / "execution.json").read_bytes())
    live = json.loads((output / "live-identity.json").read_bytes())
    require(execution["returncode"] == 0 and execution["launch_count"] == 1 and live["executable_verified"] is True and
            live["executable"] == config["plan"]["tool_identity"]["executable"] and
            live["launch_pid"] == execution["launch_pid"] and live["launch_starttime"] == execution["launch_starttime"], "Live execution identity differs")
    for name, field in (("integrity-before.json", "checked"), ("integrity-after.json", "unchanged")):
        require(json.loads((output / name).read_bytes()) == {field: True, "pins": config["pins"],
                     "membership": config["plan"]["input_membership"]}, "Input integrity differs")
    return dict(status="FP16_PACK208_NATIVE_ROUNDTRIP_VERIFIED_NOT_APPLICATION_APPROVAL", captured_tests=1,
                records=208, targets=208, protected=936, exact_selectors=1144, final_reset=True,
                default_and_minus25_protected=True, pack_included=True, application_approval=False,
                product_VDB_admission=False, official_denominator_verified=False, files={str(p): sha(p) for p in paths})


def capture(output, seal):
    config = read_config(output, seal)
    require(json.loads((output / "status.json").read_bytes())["status"] == "PREPARED_NO_DVE_REQUIRES_PARENT_CONFIG_REVIEW" and
            not any((output / n).exists() for n in ("execution.json", "live-ready", "first.el", "DVEfiles")), "No repeat launch")
    status = dict(status="RUNNING", config_sha256=seal, application_approval=False)
    write(output / "status.json", status)
    write(output / "integrity-before.json", dict(checked=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
    process = None
    try:
        env = tool.controlled_environment(config["plan"]["tool_identity"], os.environ)
        env.pop("DVE", None)
        env.update(DVE_COVERAGE_OUTPUT=str(output), PACK208_CAPTURE_SEAL=seal)
        with (output / "launcher.log").open("w") as stream:
            process = subprocess.Popen(config["command"], cwd=output, env=env, stdout=stream,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            starttime = tool.process_info(process.pid)["starttime"]
            execution = dict(launch_pid=process.pid, launch_starttime=starttime, launch_count=1)
            write(output / "execution.json", execution)
            deadline, live = time.monotonic() + 60, None
            while process.poll() is None and time.monotonic() < deadline:
                live = lifecycle.find_live(process, config["plan"]["tool_identity"], starttime)
                if live:
                    break
                time.sleep(0.2)
            require(live is not None, "No launch-bound live DVE executable")
            write(output / "live-identity.json", live)
            check(config)
            (output / "live-ready").write_text("LIVE_EXECUTABLE_VERIFIED\n")
            print("PACK208_DVE_STARTED pid=%s launch_pid=%s" % (live["pid"], process.pid), flush=True)
            execution["returncode"] = process.wait(timeout=2400)
            write(output / "execution.json", execution)
        require(execution["returncode"] == 0, "DVE exited nonzero")
        check(config)
        write(output / "integrity-after.json", dict(unchanged=True, pins=config["pins"], membership=config["plan"]["input_membership"]))
        status.update(verify(output, config))
        status["files"].update({str(output / n): sha(output / n) for n in ("config.json", "selection.tcl")})
        write(output / "capture-result.json", status)
        status["capture_result_sha256"] = sha(output / "capture-result.json")
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
        write(output / "status.json", status)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "capture", "first", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seal")
    parser.add_argument("--result-seal")
    args = parser.parse_args()
    output = args.output.absolute()
    require(output.parent == OUT and not output.is_symlink(), "Unsafe output")
    if args.command == "prepare":
        prepare(output)
    elif args.command == "capture":
        capture(output, args.seal)
    elif args.command == "first":
        print("PACK208_FIRST_EXACT " + str(len(bind_native((output / "first.el").read_bytes(), read_config(output, args.seal)))))
    else:
        require(sha(output / "capture-result.json") == args.result_seal, "External result seal differs")
        saved = json.loads((output / "capture-result.json").read_bytes())
        require(saved["config_sha256"] == args.seal, "Result/config binding differs")
        for path, expected in saved["files"].items():
            require(sha(path) == expected, "Captured artifact differs")
        fresh = verify(output, read_config(output, args.seal))
        require(all(saved.get(k) == v for k, v in fresh.items() if k != "files") and
                all(saved["files"].get(k) == v for k, v in fresh["files"].items()), "Result regeneration differs")
        print("PACK208_NATIVE_REVERIFIED")


