#!/usr/bin/env python3
"""Sealed exact round/SRT exponent capture input; no DVE launch and no pack targets."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

sys.dont_write_bytecode = True
import capture_ff1_native904 as ff1
import test_narrow_exponent_mux_scope as mux
from test_divsqrt_narrow_exponent_scope import NarrowExponentScopeTests, CORE

prep, flags = ff1.prep, ff1.flags
require, sha, write = ff1.require, ff1.sha, ff1.write
HERE = Path(__file__).resolve().parent
INVENTORY = prep.OUT / "narrow-exponent-candidates-701-20261006-01.json"
INVENTORY_SHA = "f04964c22487387d0acd667033edfc6012b8703af4d1e4f896bb2689f2e10046"
OWNERS = {"x_ct_vfdsu_srt": ("ct_vfdsu_srt.v", "423", "vfdsu_ex2_expnt_rst[12:0]"),
          "x_ct_vfdsu_round": ("ct_vfdsu_round.v", "414", "vfdsu_ex3_doub_expnt_rst[12:0]")}


def connection(text, module, instance, port, expected):
    clean = flags.scrub(text)
    matches = list(re.finditer(r'\b' + re.escape(module) + r'\s+' + re.escape(instance) + r'\s*\(', clean))
    require(len(matches) == 1, "Missing/duplicate exact source instance")
    start, end, depth = matches[0].end(), matches[0].end(), 1
    while depth and end < len(clean):
        depth += (clean[end] == '(') - (clean[end] == ')')
        end += 1
    require(depth == 0, "Unterminated source instance")
    block = clean[start:end - 1]
    values = re.findall(r'\.' + re.escape(port) + r'\s*\(([^()]*)\)', block)
    require(len(values) == 1 and mux.compact(values[0]) == expected, "Source connection differs")
    return dict(module=module, instance=instance, port=port, net=expected)


def classify(point, spec, inner, hit, owner):
    require(inner in range(4), "Unknown parent position")
    if point["line"] != owner[1]:
        return False, None
    require(point["expression"] == owner[2] and spec.get("type") == "0" and spec.get("totalbranches") == "54" and
            spec.get("width") == "1" and point["attributes"] == dict(spec.attrib), "Double exponent table identity differs")
    expressions = spec.findall("branch_cexpr")
    require(len(expressions) == 1 and expressions[0].get("exprstr") == owner[2], "Unexpected case expression tree")
    items = expressions[0].findall("branch_citem")
    require(len(items) == 54 and len({n.get("index") for n in items}) == 54, "Incomplete case/default inventory")
    by_index = {int(n.get("index")): dict(n.attrib) for n in items}
    require(set(by_index) == set(range(1, 55)) and by_index[54]["name"] == "default", "Explicit default missing")
    constants = []
    for index in range(1, 54):
        item = by_index[index]
        match = re.fullmatch(r"13'h([0-9a-f]+) ", item["name"])
        require(match is not None and item["file_id"] == point["file_id"], "Foreign/unknown case constant")
        value = int(match[1], 16)
        constants.append(value - 8192 if value & 4096 else value)
    require(set(constants) == set(range(-1074, -1021)) and len(set(constants)) == 53,
            "Case constants outside reviewed exact set")
    vector = int(point["vector"])
    require(0 <= vector < 54 and point["native_vector"]["id"] == point["vector"] and
            point["native_vector"]["vector"] == "0" * (53-vector) + "1" + "0" * vector,
            "Compiled case vector ordering differs")
    item = by_index[vector + 1]
    target = inner != 0 and item["name"] != "default"
    require(not (target and hit), "Observed hit contradicts exponent bound")
    require(hit == (inner == 0 or item["name"] == "default"), "Exact701 table hit pattern differs")
    return target, item


def prepare(output):
    require(output.parent == prep.OUT and not output.exists() and not output.is_symlink(), "Fresh direct output required")
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(c)
                               for c in (NarrowExponentScopeTests, mux.NarrowExponentMuxScopeTests))
    require(unittest.TextTestRunner().run(suite).wasSuccessful(), "Frozen range/mux proof failed")
    require(sha(ff1.FLAGFILE) == ff1.FLAGSEAL, "External effective flags seal differs")
    audit = json.loads(ff1.FLAGFILE.read_bytes())
    require(audit == flags.audit(), "Independent effective flags audit differs")
    pins = dict(audit["pins"])
    def pin(path, expected=None):
        path = Path(path).absolute()
        require(path.is_file() and not path.is_symlink(), "Missing/aliased proof input")
        value = sha(path)
        require(expected is None or value == expected, "Proof pin differs: " + str(path))
        require(str(path) not in pins or pins[str(path)] == value, "Conflicting proof pin")
        pins[str(path)] = value
        return path
    pin(ff1.FLAGFILE, ff1.FLAGSEAL)
    inventory = json.loads(pin(INVENTORY, INVENTORY_SHA).read_bytes())
    require(inventory["status"] == "NARROW_DOUBLE_EXPONENT_1272_DIAGNOSTIC_CANDIDATES" and inventory["tests"] == 701 and
            inventory["target_count"] == 1272 and inventory["protected_count"] == 4344, "Wrong diagnostic population")
    for path, expected in inventory["pins"].items():
        pin(path, expected)
    static = json.loads(flags.STATIC.read_bytes())
    bitmap = json.loads((prep.CORPUS / "combined-bits.json").read_bytes())
    design = prep.compiled.Design(Path(static["design_vdb"]))
    build = json.loads(prep.BUILD.read_bytes())
    sources = {}
    for name in ("ct_vfdsu_prepare.v", "ct_vfdsu_srt.v", "ct_vfdsu_round.v", "ct_vfdsu_ff1.v", "ct_vfdsu_double.v"):
        path = prep.ROOT / CORE / name
        sources[name] = pin(path, build[str(path)]).read_text()
    links = []
    for op in (0, 1):
        links.append(connection(sources["ct_vfdsu_prepare.v"], "ct_vfdsu_ff1", "x_frac%d_expnt" % op,
                                "frac_bin_val", "ex1_oper%d_id_expnt[12:0]" % op))
        for module, instance in (("ct_vfdsu_prepare", "x_ct_vfdsu_prepare"), ("ct_vfdsu_srt", "x_ct_vfdsu_srt")):
            port = "vfdsu_ex2_expnt_add%d" % op
            links.append(connection(sources["ct_vfdsu_double.v"], module, instance, port, port))
    for module, instance in (("ct_vfdsu_srt", "x_ct_vfdsu_srt"), ("ct_vfdsu_round", "x_ct_vfdsu_round")):
        port = "vfdsu_ex3_doub_expnt_rst"
        links.append(connection(sources["ct_vfdsu_double.v"], module, instance, port, port))
    review_path = ff1.lifecycle.proof.REVIEW / "review.py"
    spec = importlib.util.spec_from_file_location("narrow_exponent_parameter_review", pin(review_path))
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    top_variants = review.signature(design.definition(top, "tgl"))
    require(len(top_variants) == 1 and all(top_variants[0].get(k) == v for k, v in
            dict(NrLanes=4, VLEN=1024, FPUSupport=56).items()), "Compiled Ara parameters differ")
    scopes, positions, targets, protected = {}, set(), [], []
    wrapper_parameters = {}
    for scope, record in bitmap["metrics"]["branch"].items():
        name = scope.rsplit(".", 1)[-1]
        if ".i_ara." not in scope or name not in OWNERS:
            continue
        outer = re.search(r'\.gen_lanes\[([0-3])\]\.i_lane\.', scope)
        inner = re.search(r'\.gen_num_lanes\[([0-3])\]\.', scope)
        require(outer and inner, "Ambiguous generated parent")
        pos = int(outer[1]), int(inner[1]), name
        require(pos not in positions, "Duplicate physical instance")
        positions.add(pos)
        wrapper = scope.split(".i_fpnew_divsqrt_th_64_c910.")[0] + ".i_fpnew_divsqrt_th_64_c910"
        wrapper_parameters[wrapper] = ff1.bind_parameters(review.signature(design.definition(wrapper, "tgl")),
                                                        (64, 32, 16, 16)[pos[1]], (56, 40, 8, 8)[pos[1]])
        source = design.source(scope)
        require(source["resolved_path"] == str(prep.ROOT / CORE / OWNERS[name][0]), "Compiled source owner differs")
        definition = design.definition(scope, "branch")
        require(definition.get("chksum") == record["checksum"], "Metric checksum differs")
        points = prep.compiled.points("branch", definition, record["width"])
        require(len(points) == record["width"], "Incomplete module branch inventory")
        specs = {n.get("id"): n for n in definition.iter("branch_spec")}
        rows, table_count, default_count = [], 0, 0
        for point in points:
            hit = bool(int(record["bits"], 16) & (1 << (record["width"]-1-point["raw_index"])))
            target, case = classify(point, specs[point["native_id"]], pos[1], hit, OWNERS[name])
            table_count += case is not None
            default_count += case is not None and case["name"] == "default"
            original = dict(scope=scope, checksum=record["checksum"], point=point, hit=hit)
            (targets if target else protected).append(original)
            rows.append(dict(point=point, coordinate=point["native_id"] + "," + point["vector"], target=target,
                             hit=hit, case_item=case, module_checksum=source["definition_checksum"],
                             metric_checksum=record["checksum"]))
        require(table_count == 54 and default_count == 1 and len({r["coordinate"] for r in rows}) == record["width"],
                "Table/default/coordinate inventory differs")
        scopes[scope] = dict(source=source, physical_position=list(pos), branch=rows, table_positions=54,
                             default_protected=True, module_width=record["width"])
    require(positions == {(o, i, n) for o in range(4) for i in range(4) for n in OWNERS}, "Incomplete physical population")
    order = lambda row: (row["scope"], row["point"]["raw_index"])
    require(len(targets) == 1272 and len(protected) == 4344 and sorted(targets, key=order) == sorted(inventory["targets"], key=order) and
            sorted(protected, key=order) == sorted(inventory["protected"], key=order), "Exact diagnostic reconstruction differs")
    for path in (Path(__file__), HERE / "test_prepare_narrow_exponent_native1272.py", Path(mux.__file__),
                 HERE / "test_divsqrt_narrow_exponent_scope.py", Path(ff1.__file__), Path(flags.__file__),
                 HERE / "DIVSQRT_NARROW_EXPONENT_SCOPE.md"):
        pin(path)
    for path, expected in pins.items():
        require(sha(path) == expected, "Input changed during coordinate preparation")
    result = dict(status="NARROW_EXPONENT1272_EXACT_CAPTURE_PLAN_REQUIRES_PARENT_REVIEW_NO_DVE", tests=701,
                  targets=1272, protected=4344, all_branch_positions=5616, scopes=scopes, pins=pins,
                  source_connections=links, compiled_top_parameters=top_variants[0], compiled_wrapper_parameters=wrapper_parameters,
                  flags_sha256=ff1.FLAGSEAL, inventory_sha256=INVENTORY_SHA, design_vdb=static["design_vdb"],
                  selected_test_vdb=static["selected_test_vdb"], selected_test=static["selected_test"],
                  tool_identity=static["tool_identity"], source_mux_review="Exact sealed source muxes plus 8 explicit instance-net links",
                  reachable_case_input_interval=[-307, 307], excluded_constant_interval=[-1074, -1022],
                  default_protected=True, WIDTH64_all_protected=True, pack_included=False, X_or_default_excluded=False,
                  native_selector_binding=False, launch_allowed=False, application_approval=False,
                  required_native_contract="Observe all5616 selectors; only1272 exact signed constant arms; protect4344 including default/WIDTH64; export/reset/import/export and finally globally empty")
    output.mkdir()
    write(output / "capture-plan.json", result)
    selection_plan = dict(design_vdb=result["design_vdb"], selected_test_vdb=result["selected_test_vdb"],
                          scopes={s: {"branch": m["branch"]} for s, m in scopes.items()})
    (output / "selection.tcl").write_text(ff1.common.selection(selection_plan))
    manifest = {str(output / name): sha(output / name) for name in ("capture-plan.json", "selection.tcl")}
    write(output / "manifest.json", manifest)
    print(result["status"] + " manifest_seal=" + sha(output / "manifest.json"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    prepare(parser.parse_args().output.absolute())
