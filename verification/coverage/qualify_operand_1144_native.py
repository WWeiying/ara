#!/usr/bin/env python3
"""Bind actual native capture to sealed static proof; never launch or report DVE."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
import seal_operand_1144_preflight as preflight
import capture_operand_1144_v3 as capture

ROOT = preflight.ROOT
OUT = preflight.OUT
CAPTURE = OUT / "operand-native-1144-capture-20261006-03-ready"
CONFIG_SEAL = "720329af55eaa0995c65016af5560f8a071c14b5ed213099e8012f7a22a8de8a"
RESULT_SEAL = "fa21606b250932e2c8e524d71877dd8e8ec0e67ea3f630be807a947affbe833a"
CORPUS = OUT / "gap83-offline-admitted-690-20261006-02"
require = preflight.require


def module(path, pins, name):
    preflight.read_bound(path, pins)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def prove_point(point, definition, parameters, text, review):
    queue = point["scope"].rsplit("i_operand_queue_", 1)[1]
    require(point["parameters"] == parameters[queue], "Point parameters differ from source")
    inv = preflight.inventory(definition)
    preflight.validate_point(point, inv)
    sid, vid = re.fullmatch(r"Branch (\d+) \((\d+)\)", point["point"]).groups()
    specs = [s for s in definition.iter("branch_spec") if s.get("id") == sid]
    require(len(specs) == 1, "Ambiguous branch spec")
    spec = specs[0]
    expressions = [n for n in spec if n.tag in ("branch_expr", "branch_cexpr")]
    reasons = []
    for expr in expressions:
        line = int(expr.get("id"))
        if expr.tag != "branch_expr" or line not in review.GUARDS:
            continue
        guard = review.source_guard(text, line)
        require(expr.get("file_id") == "551" and expr.get("totalbranches") == "-1" and
                review.norm(expr.get("exprstr")) == review.norm(review.GUARDS[line]) and
                review.norm(guard["text"]) == review.norm(review.GUARDS[line]), "Source/XML guard differs")
        index, parent = int(expr.get("index")), int(expr.get("parent_bit"))
        require(1 <= index <= len(point["vector"]), "Guard index outside vector")
        if point["vector"][-index] == "1":
            require(not parent or point["vector"][-parent] == "1", "TRUE under inactive parent")
            if not review.value(line, parameters[queue]):
                reasons.append(dict(expression_index=index, expression=expr.get("exprstr"),
                                    constant_value=0, demanded_value="1", source_guard=guard))
    require(reasons and reasons == point["proof"], "Reconstructed constant proof differs")
    return dict(scope=point["scope"], point=point["point"], raw_index=point["raw_index"],
                checksum=[preflight.MODULE, preflight.METRIC], spec_checksum=point["spec_checksum"],
                vector=point["vector"], parameters=parameters[queue], proof=reasons,
                expression=expressions[0].get("exprstr"))


def native_binding(rows, proven):
    expected = {(p["scope"], p["point"]): p for p in proven}
    require(set(rows) == set(expected), "Native/static coordinate set differs")
    for key, row in rows.items():
        p = expected[key]
        require(row["checksum"] == p["checksum"] and row["nativepointchecksum"] == p["spec_checksum"] and
                row["expression"] == p["expression"], "Native/static definition binding differs")
    return [dict(p, native=rows[key]) for key, p in sorted(expected.items())]


def audit():
    driver = capture.original
    config = driver.config_read(CAPTURE, CONFIG_SEAL)
    pins = dict(config["pins"])
    result = preflight.load_bound(CAPTURE / "capture-result.json", pins, RESULT_SEAL)
    require(result["config_sha256"] == CONFIG_SEAL, "Wrong captured config")
    for path, sha in result["files"].items():
        preflight.read_bound(path, pins, sha)
    checked = driver.verify_artifacts(CAPTURE, config)
    require(all(result[k] == v for k, v in checked.items() if k != "files") and
            all(result["files"].get(k) == v for k, v in checked["files"].items()), "Capture verification differs")
    preflight.read_bound(Path(__file__), pins)
    preflight.read_bound(Path(__file__).with_name("test_qualify_operand_1144_native.py"), pins)
    historical = preflight.load_bound(preflight.REVIEW / "checked-hashes.json", pins)
    build = preflight.load_bound(preflight.BUILD / "build-source-pins.json", pins)
    texts = {}
    for rel in ("hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv",
                "hardware/include/ara_pkg.sv", "hardware/src/ara.sv", "hardware/src/lane/lane.sv", "config/default.mk"):
        path = ROOT / rel
        require(historical[str(path)] == build[str(path)], "Historical/build source differs")
        texts[rel] = preflight.read_bound(path, pins, historical[str(path)]).decode()
    review = module(preflight.REVIEW / "review.py", pins, "sealed_independent_operand_review")
    legacy = module(driver.HERE / "reviewed_20261004/audit_readonly.py", pins, "qualification_design")
    support = module(driver.HERE / "reviewed_operand_20261004/operand_support.py", pins, "qualification_native_parser")
    preflight.read_bound(driver.HERE / "reviewed_csr_20261004/support.py", pins)
    parameters, origins = review.queue_parameters(texts["hardware/src/lane/operand_queues_stage.sv"],
        texts["hardware/src/lane/operand_queue.sv"], texts["hardware/include/ara_pkg.sv"])
    package = review.strip_comments(texts["hardware/include/ara_pkg.sv"])
    for name, bit in (("RVVD", 5), ("RVVF", 4), ("RVVH", 3), ("RVVHA", 2), ("RVVB", 1), ("RVVBA", 0)):
        require(re.findall(r"function automatic logic " + name + r"\(fpu_support_e e\);\s*return e\[(\d)\];\s*endfunction", package)
                == [str(bit)], "FP predicate semantics differ")
    design = legacy.Design(Path(config["plan"]["design_vdb"]))
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    top_variant = review.signature(design.definition(top, "tgl"))
    require(len(top_variant) == 1 and all(top_variant[0][k] == v for k, v in
            dict(NrLanes=4, VLEN=1024, FPUSupport=56).items()), "Compiled top parameters differ")
    proven, scope_bindings = [], {}
    for scope, group in config["plan"]["scopes"].items():
        definition = preflight.bind_definition(design.hierarchy[scope], design.shapes["branch"],
                                               design.info["branch"].get(scope))
        queue = scope.rsplit("i_operand_queue_", 1)[1]
        variants = review.signature(design.definition(scope, "tgl"))
        matching = [v for v in variants if all(v.get(k) == value or
                    (k == "SupportNtrVal" and k in v and v[k] is None) for k, value in parameters[queue].items())]
        require(len(matching) == 1, "Compiled queue parameters contradict source")
        require(design.source(scope)["source_path"] == str(ROOT / "hardware/src/lane/operand_queue.sv"), "Wrong source file")
        scope_bindings[scope] = dict(parameters=parameters[queue], origins=origins[queue],
            compiled_signature=matching[0], source_resolved_fields=[k for k in parameters[queue] if matching[0][k] is None],
            metric_definition_sha256=legacy.tree_digest(definition), native_checksum=[preflight.MODULE, preflight.METRIC])
        for point in group["targets"]:
            proven.append(prove_point(point, definition, parameters, texts["hardware/src/lane/operand_queue.sv"], review))
    require(len(proven) == 1144, "Wrong proof population")
    first = support.blocks(preflight.read_bound(CAPTURE / "first.el", pins))
    second = support.blocks(preflight.read_bound(CAPTURE / "second.el", pins))
    support.equal_records(first, second)
    records = native_binding(first, proven)
    old_cache = preflight.load_bound(preflight.CACHE, pins)
    bitmap = preflight.load_bound(CORPUS / "combined-bits.json", pins)
    status = preflight.load_bound(CORPUS / "status.json", pins)
    require(status["status"] == "PASS_RAW_UNION_HISTORICAL_ONLY" and status["aggregate_passed"] == 690 and
            status["official_DVE_report"] is False, "Not the offline690 corpus")
    upstream = preflight.load_bound(CORPUS / "evidence-pins.json", pins)
    for path, sha in upstream.items():
        preflight.read_bound(path, pins, sha)
    require(bitmap["design"] == old_cache["design"] and len(bitmap["tests"]) == 690 and
            len(set(bitmap["tests"])) == 690 and bitmap["tests"][:-1] == old_cache["tests"], "Not exact689+one/design")
    listing = preflight.read_bound(CORPUS / "combined-inputs.txt", pins).decode().splitlines()
    require(listing == [config["plan"]["design_vdb"]] + bitmap["tests"], "690 selected input membership differs")
    last = Path(bitmap["tests"][-1])
    raw_files = list((last / "snps/coverage/db/testdata").glob("*/branch.verilog.data.xml"))
    require(len(raw_files) == 1, "Ambiguous new branch file")
    new = preflight.raw_scopes(preflight.read_bound(raw_files[0], pins, bitmap["input_hashes"][str(raw_files[0])]),
                               config["plan"]["scopes"])
    union = {}
    for scope in scope_bindings:
        n = int(old_cache["metrics"]["branch"][scope]["bits"], 16) | new[scope]
        row = bitmap["metrics"]["branch"][scope]
        require(row["width"] == 101 and row["checksum"] in (None, preflight.METRIC) and int(row["bits"], 16) == n,
                "690 does not equal sealed689 plus fresh new raw branch")
        union[scope] = n
    preflight.check_zero(proven, union)
    prior = [p for g in config["plan"]["scopes"].values() for p in g["prior_reviewed"]]
    evidence = dict(status="NATIVE_STATIC_1144_QUALIFIED_FOR_EXACT_OLD_DESIGN_NOT_APPLIED",
        native_capture_tests=1, target_corpus_tests=690, target_corpus_is_offline_raw_union=True,
        full690_DVE_report_verified=False, application_authorized=False, application_started=False,
        config_sha256=CONFIG_SEAL, capture_result_sha256=RESULT_SEAL,
        native_file=str(CAPTURE / "first.el"), native_sha256=pins[str(CAPTURE / "first.el")],
        points=1144, selected_hits_690=0, scope_bindings=scope_bindings, pins=pins,
        protection=dict(capture_unselected=2492, retained=1269, previously_reviewed=16,
                        never_newly_exclude_complement=2476, prior16=prior),
        required_application_gates=["exact 690 selected test membership, not the singleton capture sample",
            "same pinned Design/module/metric/spec checksums; review-empty native import",
            "consume exact captured native signatures, never generate substitute directives",
            "preserve separate existing policy; only these1144 branch coordinates may be new exclusions",
            "all2492 unselected branch states match baseline; prior16 may retain existing separately authorized state",
            "full690 raw/applied summaries and scope/metric deltas independently checked",
            "fresh tool environment/ELF gate and before/after pins; reset and empty final state"],
        corpus_input_list=str(CORPUS / "combined-inputs.txt"), corpus_design=bitmap["design"],
        corpus_tests=bitmap["tests"])
    for path, sha in pins.items():
        require(capture.original.hash_file(path) == sha, "Qualification input drift: " + path)
    return evidence, dict(status="EXACT_NATIVE_AND_STATIC_RECORD_BINDINGS_NOT_AN_APPLICATION_RECEIPT", records=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists() and args.output.absolute().parent == OUT, "Fresh direct out required")
    evidence, records = audit()
    args.output.mkdir()
    for name, data in (("qualification.json", evidence), ("qualified-records.json", records)):
        preflight.write_json(args.output / name, data)
    preflight.write_json(args.output / "manifest.sha256.json", {name: capture.original.hash_file(args.output / name)
                        for name in ("qualification.json", "qualified-records.json")})
    print("QUALIFICATION_SEAL " + capture.original.hash_file(args.output / "manifest.sha256.json"))


if __name__ == "__main__":
    main()
