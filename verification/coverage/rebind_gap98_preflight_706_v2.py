"""Expand sealed GAP98 target evidence without compiling or executing software."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import build_gap98_preflight as old

ROOT, OUT = old.ROOT, old.OUT
PRE = OUT / "gap98-div16-pack-preflight-706-20261006-01"
PRE_SEAL = "42a0dd428c8ec2a1a671275c4836d5a04aab1a5b415c4370c72aa00338a60da0"


def select_scopes(scopes):
    top = "ara_tb.dut.i_ara_soc.i_system.i_ara"
    result = []
    for lane in range(4):
        for slot in (2, 3):
            matches = [s for s in scopes if s.startswith(top + ".gen_lanes[%d]." % lane)
                       and ".gen_num_lanes[%d]." % slot in s and s.endswith(".x_ct_vfdsu_pack")]
            old.require(len(matches) == 1, "Missing/ambiguous physical pack instance")
            result.append(matches[0])
    old.require(len(set(result)) == 8, "Duplicate instance")
    return result


def preserve_rows(original, expanded):
    old.require(len(original) == 4 and len(expanded) == 8, "Wrong scope population")
    index = {r["scope"]: r for r in expanded}
    old.require(len(index) == 8 and all(index.get(r["scope"]) == r for r in original),
                "Original target evidence changed")


def prepare(output):
    output = Path(output).absolute()
    old.require(output.parent == OUT and output.resolve() == output and not output.exists(),
                "Fresh direct output required")
    manifest_path = PRE / "preflight-manifest.json"
    old.require(old.sha(manifest_path) == PRE_SEAL, "Original manifest drift")
    pre = json.loads(manifest_path.read_bytes())
    old.require(pre["status"] == "GAP98_SPIKE_PREFLIGHT_PASS_NOT_VCS" and
                pre["baseline_tests"] == 706 and pre["target_unhit_count"] == 65 and
                pre["checks"] == 3112 and pre["expected_vector_instructions"] == 24 and
                pre["expected_vector_bytes"] == 6144 and not pre["coverage_admitted"],
                "Original software contract differs")
    pins = old.merge_pins(pre["pins"], {str(manifest_path): PRE_SEAL})
    for path in (Path(__file__).resolve(), Path(__file__).with_name("test_rebind_gap98_preflight_706_v2.py")):
        pins = old.merge_pins(pins, {str(path): old.sha(path)})
    old.check(pins)
    before = json.loads((PRE / "target-before.json").read_bytes())
    bitmap = json.loads(Path(before["baseline"]).read_bytes())
    old.require(before["baseline"] == str(old.BASE / "combined-bits.json") and
                before["baseline_sha256"] == old.sha(Path(before["baseline"])) and
                len(bitmap["tests"]) == len(set(bitmap["tests"])) == 706 and
                before["design"] == bitmap["design"], "Baseline706 binding differs")
    design = old.Design(OUT / "repaired-aligned-build-20260930-01/sim/simv.vdb")
    review_path = OUT / "gap56-operand-independent-review-20261004-01/review.py"
    old.require(str(review_path) in pins, "Unpinned parameter reader")
    spec = importlib.util.spec_from_file_location("gap98_rebind_parameters", review_path)
    review = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review)
    rows = []
    for scope in select_scopes(bitmap["metrics"]["branch"]):
        wrapper = scope.split(".i_fpnew_divsqrt_th_64_c910.")[0] + ".i_fpnew_divsqrt_th_64_c910"
        params = review.signature(design.definition(wrapper, "tgl"))
        old.require(len(params) == 1 and params[0].get("WIDTH") == 16 and
                    params[0].get("FpFmtConfig") == 8, "Not compiled FP16-only instance")
        old.require(design.source(scope)["resolved_path"] == str(old.CORE / "ct_vfdsu_pack.v"),
                    "Compiled source differs")
        record = bitmap["metrics"]["branch"][scope]
        definition = design.definition(scope, "branch")
        old.require(definition.get("chksum") == record["checksum"], "Compiled checksum differs")
        rows.append(dict(scope=scope, wrapper=wrapper, compiled_parameters=params[0],
                         checksum=record["checksum"], width=record["width"],
                         **old.table_targets(record, old.points("branch", definition, record["width"]))))
    preserve_rows(before["rows"], rows)
    evidence = copy.deepcopy(before)
    evidence.update(rows=rows, target_unhit_count=sum(len(r["missing_points"]) for r in rows),
                    physical_scope_count=8, original_preflight=str(manifest_path), original_seal=PRE_SEAL)
    old.require(evidence["target_unhit_count"] == 125, "Reviewed706 target count differs")
    old.check(pins)
    output.mkdir()
    old.save(output / "target-before.json", evidence)
    pins = old.merge_pins(pins, {str(output / "target-before.json"): old.sha(output / "target-before.json")})
    result = copy.deepcopy(pre)
    result.update(pins=pins, target_unhit_count=125, physical_scope_count=8,
                  target_before=str(output / "target-before.json"),
                  original_preflight=str(manifest_path), original_seal=PRE_SEAL,
                  software_reexecuted=False)
    old.check(pins)
    old.save(output / "preflight-manifest.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.output)
    print(json.dumps(dict(output=str(args.output), seal=old.sha(args.output / "preflight-manifest.json"),
                          scopes=8, target_unhit_count=125, software_reexecuted=False)))
