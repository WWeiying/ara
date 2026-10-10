"""Static parameter-guard/six707 dedup against raw716; not exclusion approval."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re

import build_gap101_preflight as shared
from closure_point_inventory import points

ROOT, OUT, require = shared.ROOT, shared.OUT, shared.require
BASE = OUT / "gap101a-offline-admitted-716-20261006-01"
SIX = OUT / "branch-combo-six-policy-707-20261006-02/config.json"
SIX_SHA = "9412f766aa75e7099fb3c0b354db655b78b1b6bee3abf39032b81d651128acaa"
NAMES = ("st_mask_a", "slide_addrgen_a", "mask_m")
PARAMS = ("SupportIntExt2", "SupportIntExt4", "SupportIntExt8", "SupportReduct", "SupportNtrVal", "FPUSupport")
FALSE_EXPRESSIONS = set(PARAMS[:-1]) | {
    "(SupportNtrVal || SupportReduct)", "(FPUSupport != FPUSupportNone)",
    "(ara_pkg::RVVB(FPUSupport) || ara_pkg::RVVBA(FPUSupport))",
    "((ara_pkg::RVVH(FPUSupport) || ara_pkg::RVVB(FPUSupport)) || ara_pkg::RVVBA(FPUSupport))"}


def parameters(signature):
    result = {}
    for name in PARAMS:
        values = re.findall(r"\b" + name + r"=([0-9]+)(?=[,)])", signature)
        require(len(values) == 3 and set(values) == {"0"}, "Not all compiled variants zero: " + name)
        result[name] = 0
    return result


def guards(point):
    vector = point["native_vector"]["vector"]
    proofs = []
    for expression in point["expressions"]:
        if expression["exprstr"] not in FALSE_EXPRESSIONS:
            continue
        index = int(expression["index"])
        require(0 < index <= len(vector), "Guard index outside vector")
        if vector[-index] == "1":
            proofs.append(dict(expression=expression["exprstr"], source_line=expression["id"],
                               expression_index=index, constant_value=0, demanded_value=1))
    return proofs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    out = p.parse_args().output.absolute()
    require(out.parent == OUT and out.resolve() == out and not out.exists(), "Fresh direct output required")
    pins = {}
    def read(path, expected=None):
        path = Path(path).absolute()
        value = shared.shared.sha(path)
        require(expected is None or value == expected, "Evidence pin differs: " + str(path))
        pins.update(shared.shared.merge_pins(pins, {str(path): value}))
        return path.read_bytes()
    manifest = json.loads(read(BASE / "admission-manifest.json",
        "df9e35f425734bce6d22416acf3f91fbea85f007ceb1e45f2e1eee703da4fd8a"))
    before = json.loads(read(BASE / "combined-bits.json", manifest["output_pins"][str(BASE / "combined-bits.json")]))
    require(len(before["tests"]) == len(set(before["tests"])) == 716, "Not raw716")
    config = json.loads(read(SIX, SIX_SHA))
    build = json.loads(read(shared.BUILD / "build-source-pins.json",
        "6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b"))
    for relative in ("hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv",
                     "hardware/include/ara_pkg.sv"):
        read(ROOT / relative, build[str(ROOT / relative)])
    design = shared.shared.Design(shared.BUILD / "sim/simv.vdb")
    for relative, expected in before["design"].items():
        read(design.db / relative, expected)
    read(design.db / "shape/tgl.verilog.shape.xml")
    rows, scopes, counts = [], {}, Counter()
    for lane in range(4):
        for name in NAMES:
            scope = ("ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[%d].i_lane.i_operand_queues."
                     "i_operand_queue_%s" % (lane, name))
            require(design.source(scope)["resolved_path"] == str(ROOT / "hardware/src/lane/operand_queue.sv"),
                    "Wrong compiled source owner")
            signature = design.definition(scope, "tgl").get("name")
            parameters(signature)
            record = before["metrics"]["branch"][scope]
            definition = design.definition(scope, "branch")
            require(record["width"] == 101 and definition.get("chksum") == "1417162425" and
                    record["checksum"] in (None, "1417162425"), "Compiled branch shape differs")
            old = config["groups"]["operand"]["plan"]["scopes"][scope]
            targets = {r["raw_index"]: r for r in old["targets"]}
            protected = {r["raw_index"]: r for r in old["protected"]}
            require(not targets.keys() & protected.keys() and len(targets) + len(protected) == 101,
                    "Incomplete six707 inventory")
            stat = Counter()
            for point in points("branch", definition, 101):
                index = point["raw_index"]
                approved = targets.get(index, protected.get(index))
                require(approved["selector"] == point["native_id"] + "," + point["vector"] and
                        approved["spec_checksum"] == point["attributes"]["chksum"], "Native coordinate drift")
                hit = bool(int(record["bits"], 16) & (1 << (100-index)))
                proof = guards(point)
                if proof:
                    require(not hit, "Hit contradicts constant-false guard")
                    category = "PARAMETER_FALSE_BODY_ALREADY_SIX707_TARGET" if index in targets else "NEW_PARAMETER_FALSE_BODY"
                elif not hit:
                    category = "PROTECTED_ZERO_NO_PARAMETER_TRUE_DEMAND_PROOF"
                else:
                    category = "HIT_PROTECTED"
                stat[category] += 1
                counts[category] += 1
                rows.append(dict(scope=scope, point=point, hit716=hit, classification=category, proof=proof,
                                 six707_target=index in targets, metric_checksum=definition.get("chksum")))
            scopes[scope] = dict(compiled_tgl_signature=signature, parameters=parameters(signature),
                                 bitmap_checksum=record["checksum"], compiled_branch_checksum=definition.get("chksum"),
                                 counts=dict(stat))
    require(counts["PARAMETER_FALSE_BODY_ALREADY_SIX707_TARGET"] == 720 and
            counts["NEW_PARAMETER_FALSE_BODY"] == 0, "Dedup result differs")
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_audit_operand_parameter_dedup_716.py")):
        read(path)
    shared.shared.check(pins)
    shared.shared.save(out, dict(status="RAW716_PARAMETER_GUARDS_DEDUPED_NOT_NEW_WAIVER", tests=716,
        scopes=scopes, counts=dict(counts), rows=rows, pins=pins, exclusions_generated=False,
        application_approval=False, official_percentages=False,
        limit="Parameter guards requiring TRUE are false without producer proof. Protected conv entries/false arms require separate producer/reachability proof; never inferred here."))
    print(json.dumps(dict(output=str(out), seal=shared.shared.sha(out), counts=dict(counts))))


if __name__ == "__main__":
    main()
