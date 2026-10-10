#!/usr/bin/env python3
"""Offline operand proof/689 raw binding and native capture preparation only."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "verification/out"
BUILD = OUT / "repaired-aligned-build-20260930-01"
REVIEW = OUT / "gap56-operand-independent-review-20261004-01"
CACHE = OUT / "gap82-raw-union-689-20261006-01/combined-bits.json"
REVIEW_SEAL = "bc0479a32db09131b11806aa77e6307c87908a739867f4e7be7c2b90129c8479"
MODULE = "1532764271"
METRIC = "1417162425"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read_bound(path, pins, expected=None):
    path = Path(path)
    raw = path.read_bytes()
    value = digest(raw)
    require(expected is None or value == expected, "Hash differs: " + str(path))
    require(str(path) not in pins or pins[str(path)] == value, "Conflicting pin")
    pins[str(path)] = value
    return raw


def load_bound(path, pins, expected=None):
    return json.loads(read_bound(path, pins, expected))


def bind_definition(module, shape, checksum):
    require(module.get("name") == "operand_queue" and module.get("chksum") == MODULE,
            "Wrong source definition")
    require(checksum in (None, METRIC), "Wrong explicit metric checksum")
    candidates = [n for n in shape.findall("branch_def")
                  if n.get("id") == module.get("id") and
                  (checksum is None or n.get("chksum") == checksum)]
    require(len(candidates) == 1 and candidates[0].get("chksum") == METRIC,
            "Missing/ambiguous metric definition")
    require(sum(len(s.findall("branch_vector")) for s in candidates[0].iter("branch_spec")) == 101,
            "Wrong branch width")
    return candidates[0]


def inventory(definition):
    result, offset = {}, 0
    for spec in definition.iter("branch_spec"):
        vectors = spec.findall("branch_vector")
        for pos, vector in enumerate(vectors):
            key = "Branch %s (%s)" % (spec.get("id"), vector.get("id"))
            require(key not in result, "Duplicate vector")
            result[key] = dict(raw_index=offset + len(vectors) - 1 - pos,
                               vector=vector.get("vector"), spec_checksum=spec.get("chksum"),
                               selector="%s,%s" % (spec.get("id"), vector.get("id")))
        offset += len(vectors)
    return result


def validate_point(point, inv):
    require(point["decision"] == "ELIGIBLE_STATIC_NOT_APPLIED", "Wrong decision")
    require(point["module_checksum"] == MODULE and point["metric_checksum"] == METRIC,
            "Wrong point checksums")
    row = inv[point["point"]]
    require(all(point[k] == row[k] for k in ("raw_index", "vector", "spec_checksum")),
            "Coordinate differs")
    require(bool(point["proof"]), "Missing proof")
    for proof in point["proof"]:
        i = proof["expression_index"]
        require(isinstance(i, int) and 1 <= i <= len(point["vector"]), "Invalid expression index")
        require(proof["constant_value"] == 0 and proof["demanded_value"] == "1" and
                point["vector"][-i] == "1", "Wrong constant proof")


def raw_scopes(raw, scopes):
    tree = ET.fromstring(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    rows = {}
    for node in tree.iter("instance_data"):
        scope = node.get("name")
        if scope not in scopes:
            continue
        require(scope not in rows, "Duplicate raw scope")
        bits = node.get("value", "")
        require(len(bits) == 101 and set(bits) <= {"0", "1"}, "Invalid raw width/value")
        require(node.get("chksum") in (None, METRIC), "Raw checksum differs")
        rows[scope] = int(bits, 2)
    require(set(rows) == set(scopes), "Missing exact raw scope")
    return rows


def check_zero(points, union):
    require(not any(union[p["scope"]] & (1 << (100 - p["raw_index"])) for p in points),
            "Accepted static point has a contradictory hit")


def tree_members(directory):
    directory = Path(directory)
    require(directory.is_dir() and not directory.is_symlink(), "Unsafe VDB root")
    members = []
    for path in sorted(directory.rglob("*")):
        require(not path.is_symlink(), "Symlink in capture input")
        if path.is_dir():
            continue
        require(path.is_file(), "Nonregular capture input")
        members.append(str(path.relative_to(directory)))
    require(bool(members), "Empty capture input")
    return members


def audit():
    pins = {}
    read_bound(Path(__file__), pins)
    read_bound(HERE / "test_seal_operand_1144_preflight.py", pins)
    helper = HERE / "reviewed_20261004/audit_readonly.py"
    read_bound(helper, pins)
    spec = importlib.util.spec_from_file_location("operand_offline_design", helper)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    manifest = load_bound(REVIEW / "manifest.sha256.json", pins, REVIEW_SEAL)
    for path, sha in manifest.items():
        read_bound(path, pins, sha)
    historical = load_bound(REVIEW / "checked-hashes.json", pins)
    build_pins = load_bound(BUILD / "build-source-pins.json", pins)
    for rel in ("hardware/src/lane/operand_queue.sv", "hardware/src/lane/operand_queues_stage.sv",
                "hardware/include/ara_pkg.sv"):
        path = str(ROOT / rel)
        require(historical[path] == build_pins[path], "Historical/build source conflict")
        read_bound(path, pins, historical[path])
    cache = load_bound(CACHE, pins)
    db = BUILD / "sim/simv.vdb/snps/coverage/db"
    for path in sorted((db / "shape").glob("*.verilog.*.xml")):
        read_bound(path, pins)
    for rel in ("design/verilog.design.xml", "auxiliary/verilog.sourceinfo.xml"):
        read_bound(db / rel, pins)
    for rel, sha in cache["design"].items():
        read_bound(db / rel, pins, sha)
    for rel in ("design/verilog.design.xml", "shape/branch.verilog.shape.xml"):
        read_bound(db / rel, pins, historical[str(db / rel)])
    design = legacy.Design(BUILD / "sim/simv.vdb")
    points = load_bound(REVIEW / "accepted-coordinates.json", pins)["points"]
    keep = load_bound(REVIEW / "retained-and-prior.json", pins)
    require(len(points) == len({(p["scope"], p["point"]) for p in points}) == 1144, "Wrong targets")
    require(len(keep["retained"]) == 1269 and len(keep["prior_reviewed"]) == 16, "Wrong retained/prior")
    scopes = sorted({p["scope"] for p in points})
    require(len(scopes) == 36, "Wrong scope count")
    populations = [{(p["scope"], p["point"]) for p in rows}
                   for rows in (points, keep["retained"], keep["prior_reviewed"])]
    require(len(populations[1]) == 1269 and len(populations[2]) == 16 and
            not any(populations[i] & populations[j] for i in range(3) for j in range(i)),
            "Retained/prior duplicates or overlap")
    stats, selections = {}, {}
    for scope in scopes:
        checksum = design.info["branch"].get(scope)
        definition = bind_definition(design.hierarchy[scope], design.shapes["branch"], checksum)
        require(legacy.tree_digest(definition) == legacy.tree_digest(design.definition(scope, "branch")),
                "Resolver disagreement")
        inv = inventory(definition)
        targets = [p for p in points if p["scope"] == scope]
        for p in targets:
            validate_point(p, inv)
        for p in keep["retained"] + keep["prior_reviewed"]:
            if p["scope"] == scope:
                require(all(p[k] == inv[p["point"]][k] for k in ("raw_index", "vector", "spec_checksum"))
                        and p["module_checksum"] == MODULE and p["metric_checksum"] == METRIC,
                        "Protected coordinate mapping differs")
        selected = {p["point"] for p in targets}
        protected = [{"point": key, **value} for key, value in inv.items() if key not in selected]
        selections[scope] = dict(checksum=[MODULE, METRIC],
                                targets=[dict(p, selector=inv[p["point"]]["selector"]) for p in targets],
                                protected=protected,
                                retained=[p for p in keep["retained"] if p["scope"] == scope],
                                prior_reviewed=[p for p in keep["prior_reviewed"] if p["scope"] == scope])
        stats[scope] = dict(source=design.source(scope), source_definition_id=design.hierarchy[scope].get("id"),
                            metric_definition_id=definition.get("id"), metric_checksum=METRIC,
                            metric_tree_sha256=legacy.tree_digest(definition), explicit_checksum=checksum,
                            binding="explicit_checksum_and_definition" if checksum else "unique_definition_id",
                            width=101, targets=len(targets), protected=len(protected), samples=0)
    union, inputs = {s: 0 for s in scopes}, []
    require(len(cache["tests"]) == len(set(cache["tests"])) == 689, "Wrong corpus population")
    seen = set()
    for test in cache["tests"]:
        candidates = list((Path(test) / "snps/coverage/db/testdata").glob("*/branch.verilog.data.xml"))
        require(len(candidates) == 1, "Ambiguous branch input")
        path = candidates[0]
        require(str(path.resolve()) not in seen, "Alias/duplicate raw input")
        seen.add(str(path.resolve()))
        raw = read_bound(path, pins, cache["input_hashes"][str(path)])
        rows = raw_scopes(raw, scopes)
        for scope, bits in rows.items():
            union[scope] |= bits
            stats[scope]["samples"] += 1
        inputs.append(dict(test=test, path=str(path), sha256=pins[str(path)]))
    check_zero(points, union)
    for scope, bits in union.items():
        row = cache["metrics"]["branch"][scope]
        require(row["width"] == 101 and row["checksum"] in (None, METRIC) and int(row["bits"], 16) == bits,
                "Cache/raw union differs")
        stats[scope].update(bits=format(bits, "0101b"), hit_count=bin(bits).count("1"),
                            zero_count=101-bin(bits).count("1"), selected_hits=0)
    explicit = sum(s["targets"] for s in stats.values() if s["explicit_checksum"] is not None)
    require(explicit == 72, "Explicit binding population differs")
    require(all(p["scope"] in scopes for p in keep["retained"] + keep["prior_reviewed"]),
            "Protected scope outside universe")
    require(sum(len(s["protected"]) for s in selections.values()) == 2492,
            "Wrong full complement")
    capture_roots = [BUILD / "sim/simv.vdb", Path(cache["tests"][0])]
    membership = {str(root): tree_members(root) for root in capture_roots}
    for root, members in membership.items():
        for name in members:
            read_bound(Path(root) / name, pins)
    tool_path = HERE / "dve_tool_identity.py"
    read_bound(tool_path, pins)
    read_bound(HERE / "test_dve_tool_identity.py", pins)
    tool_spec = importlib.util.spec_from_file_location("operand_capture_tool_identity", tool_path)
    tool = importlib.util.module_from_spec(tool_spec)
    tool_spec.loader.exec_module(tool)
    tool_record = tool.prepare("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve",
                               "/usr/bin/xvfb-run")
    tool.revalidate(tool_record)
    for row in tool_record["files"]:
        read_bound(row["path"], pins, row["sha256"])
    plan = dict(status="OFFLINE_PREPARED_NOT_NATIVE_QUALIFIED_NOT_AUTHORIZED", scopes=selections,
                expected_records=1144, protected_branch_points=2492, selected_tests=1,
                design_vdb=str(capture_roots[0]), selected_test_vdb=str(capture_roots[1]),
                input_membership=membership, tool_identity=tool_record,
                runtime_executable_verified=False, runner_prepared=False,
                requirements=["fresh tool identity and live DVE executable binding before any launch",
                              "exact old design and one selected test; input pins before and after",
                              "initial/reset/final empty; no first-save extra records",
                              "singleton selected-vector queries, never boolean-as-count",
                              "all 2492 unselected branch vectors stay unexcluded at all audit stages",
                              "first/second strict full native signatures and headers identical; exactly 1144 records",
                              "no corpus application, report merge, receipt, or review approval"])
    evidence = dict(status="OFFLINE_1144_BINDING_VERIFIED_NOT_NATIVE_APPROVAL", tests=689,
                    scope_samples=689*36, explicit_points=explicit, definition_bound_points=1144-explicit,
                    selected_hits=0, scopes=stats, inputs=inputs, pins=pins,
                    retained_count=1269, prior_reviewed_count=16, protected_branch_points=2492,
                    tool_host_preflight="PREPARE_REVALIDATE_ONLY_NO_LIVE_DVE",
                    proof_scope="Existing sealed GAP56 static proof; this audit rebinds coordinates, not a new reachability proof")
    for path, sha in pins.items():
        require(digest(Path(path).read_bytes()) == sha, "Input drift: " + path)
    for root, members in membership.items():
        require(tree_members(root) == members, "Capture input membership drift")
    tool.revalidate(tool_record)
    return evidence, plan


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--seal", help="Externally retained SHA256 of manifest.sha256.json")
    args = parser.parse_args()
    require(bool(args.output) != bool(args.verify), "Choose output or verify")
    if args.verify:
        require(bool(args.seal) and re.fullmatch("[0-9a-f]{64}", args.seal), "Require external seal")
        manifest = load_bound(args.verify / "manifest.sha256.json", {}, args.seal)
        require(set(manifest) == {"evidence.json", "capture-plan.json"}, "Wrong sealed members")
        for name, sha in manifest.items():
            read_bound(args.verify / name, {}, sha)
    evidence, plan = audit()
    if args.verify:
        require(json.loads((args.verify / "evidence.json").read_text()) == evidence, "Evidence differs")
        require(json.loads((args.verify / "capture-plan.json").read_text()) == plan, "Plan differs")
        print("OFFLINE_SEAL_REVERIFIED_NO_DVE")
    else:
        args.output.mkdir(parents=True, exist_ok=False)
        write_json(args.output / "evidence.json", evidence)
        write_json(args.output / "capture-plan.json", plan)
        write_json(args.output / "manifest.sha256.json", {name: digest((args.output / name).read_bytes())
                   for name in ("evidence.json", "capture-plan.json")})
        print("OFFLINE_PREPARED_NO_DVE seal=" + digest((args.output / "manifest.sha256.json").read_bytes()))


if __name__ == "__main__":
    main()
