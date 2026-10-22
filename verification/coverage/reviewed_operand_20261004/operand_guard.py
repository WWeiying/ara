"""Compose immutable old94+CSR107 admission with the sealed1144 review."""
import copy
import sys
import time
from operand_support import *

ROOT = HERE.parents[2]
COVERAGE = HERE.parent
OUT = ROOT / "verification/out"
sys.dont_write_bytecode = True
sys.path.insert(0, str(COVERAGE / "reviewed_csr_20261004"))
csr_guard = module("operand_immutable_csr_guard", COVERAGE / "reviewed_csr_20261004/guard.py")
sys.path.pop(0)
REVIEW = OUT / "gap56-operand-independent-review-20261004-01"
PILOT = OUT / "gap58-operand-native-pilot-20261004-02"
DVE = Path("/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/bin/dve")


def review_pins():
    pins = {}
    for directory, seal in ((REVIEW, "bc0479a32db09131b11806aa77e6307c87908a739867f4e7be7c2b90129c8479"),
                            (PILOT, "e9d59a34fb400a9d703c2fec4a55fc1a16ac5b95d8508a3c8a2592189914e97e")):
        manifest = directory / "manifest.sha256.json"
        require(sha(manifest) == seal, "Independent review/pilot seal changed")
        pins[str(manifest)] = seal
        pins.update(jread(manifest))
    pins.update(jread(REVIEW / "checked-hashes.json"))
    verify_hashes(pins)
    return pins


def bind_operand(context, targets, retained):
    design = csr_guard.legacy.audit.Design(Path(context["design"]))
    scopes = sorted({p["scope"] for p in targets})
    require(len(targets) == len({point_key(p) for p in targets}) == 1144 and len(scopes) == 36, "Wrong1144/36 authority")
    require(len(retained["retained"]) == 1269 and len(retained["prior_reviewed"]) == 16, "Retained/prior review differs")
    new_keys, keep_keys, prior_keys = ({point_key(p) for p in rows} for rows in
                                    (targets, retained["retained"], retained["prior_reviewed"]))
    old_keys = {point_key(p) for p in context["policy"]["allowed_points"]}
    require(len(old_keys) == 201 and not new_keys & old_keys and not new_keys & keep_keys and
            not prior_keys & keep_keys and prior_keys <= old_keys, "Composition overlap/dedup ambiguity")
    old_queue_branches = {k for k in old_keys if k[0] in scopes and k[1].startswith("Branch ")}
    require(old_queue_branches == prior_keys, "Old queue branch baseline differs from prior16")
    for observer in context["observers"]:
        require(all(s != observer["scope"] and not s.startswith(observer["scope"] + ".") for s in scopes),
                "Observer masks operand product hierarchy")
    inventory, specs, masks = None, {}, {s: 0 for s in scopes}
    for scope in scopes:
        definition = design.definition(scope, "branch")
        require(design.source(scope)["definition_checksum"] == "1532764271" and definition.get("chksum") == "1417162425",
                "Operand compiled definition differs")
        actual, width = csr.exact_inventory(definition)
        require(width == 101 and (inventory is None or inventory == actual), "Different operand branch layout")
        inventory = actual
        for spec in definition.iter("branch_spec"):
            expressions = [n for n in spec if n.tag in ("branch_expr", "branch_cexpr")]
            specs[spec.get("id")] = dict(expression=expressions[0].get("exprstr"), checksum=spec.get("chksum"))
    for p in targets:
        m = inventory[csr.point_id(p["point"])]
        require(p["decision"] == "ELIGIBLE_STATIC_NOT_APPLIED" and p["raw_index"] == m["raw_index"] and
                p["vector"] == m["vector"]["vector"] and p["spec_checksum"] == m["xml_point_checksum"] and
                p["module_checksum"] == "1532764271" and p["metric_checksum"] == "1417162425", "Operand coordinate mapping differs")
        require(p["proof"] and all(q["constant_value"] == 0 and q["demanded_value"] == "1" and
                p["vector"][-q["expression_index"]] == "1" for q in p["proof"]), "Not a FALSE parameter requiring TRUE")
        masks[p["scope"]] |= 1 << (100 - p["raw_index"])
    universe = {(scope, f"Branch {sid} ({vid})") for scope in scopes for sid, vid in inventory}
    require(keep_keys | prior_keys | new_keys <= universe, "Retained point outside branch universe")
    require(len(universe - new_keys - prior_keys) == 2476, "Complement differs")
    return scopes, inventory, specs, masks


def build_context(requested=None):
    started = time.monotonic()
    context = csr_guard.build_context(requested)
    require(len(context["policy"]["allowed_points"]) == 201 and len(context["observers"]) == 10, "Need exact immutable201/10 baseline")
    pins = review_pins()
    targets = jread(REVIEW / "accepted-coordinates.json")["points"]
    retained = jread(REVIEW / "retained-and-prior.json")
    scopes, inventory, specs, masks = bind_operand(context, targets, retained)
    union, files = {scope: 0 for scope in scopes}, context["csr_raw_audit"]["files"]
    for row in files:
        require(context["pins"].get(row["path"]) == row["sha256"] and sha(row["path"]) == row["sha256"], "Operand raw witness drift")
        bits = scan_raw(Path(row["path"]).read_bytes(), scopes, masks)
        for scope, n in bits.items():
            union[scope] |= n
    cache = jread(Path(context["baseline"]) / "combined-bits.json")
    require(len(files) == context["tests"], "Operand witness population differs")
    for scope, n in union.items():
        row = cache["metrics"]["branch"][scope]
        require(row["width"] == 101 and row["checksum"] in (None, "1417162425") and int(row["bits"], 16) == n,
                "All36 fresh raw union/cache mismatch")
    for p, h in pins.items():
        require(p not in context["pins"] or context["pins"][p] == h, "Contradictory review pin")
        context["pins"][p] = h
    for path in [COVERAGE / "run_reviewed_operand_dve_20261004.py", *HERE.glob("*.py"), *HERE.glob("*.tcl")]:
        context["pins"][str(path)] = sha(path)
    tool_paths = [DVE, DVE.parent.parent / "gui/dve/linux64/bin/dve.exe", Path("/usr/bin/xvfb-run")]
    tool_pins = {str(p): sha(p) for p in tool_paths}
    context["pins"].update(tool_pins)
    context.update(operand_targets=targets, operand_retained=retained["retained"], operand_prior16=retained["prior_reviewed"],
        operand_scopes=scopes, operand_specs=specs, operand_keys=[f"{sid},{vid}" for sid, vid in sorted(inventory)],
        operand_raw_audit=dict(samples=len(files), selected_hits=0, bits={s: format(n, "0101b") for s, n in union.items()}, files=files),
        pilot18=jread(PILOT / "native-handoff.json")["points"],
        pilot18_scope_limit="Observed18 only; never full1144 native approval",
        input_tree={p: tree(p) for p in context["input_membership"]}, native_capture_sha256=None,
        host_tool_pins=tool_pins, admission_elapsed_seconds=round(time.monotonic() - started, 3))
    context["retained_review_coordinate_count"] = len(retained["retained"])
    context["retained_current_missing_count"] = sum(format(union[p["scope"]], "0101b")[p["raw_index"]] == "0"
                                                    for p in retained["retained"])
    verify_inputs(context)
    csr_guard.latest_corpus(Path(context["design"]), context["image"], Path(context["baseline"]))
    return context


def session_population(context, stage):
    keys = {s: context["operand_keys"] for s in context["operand_scopes"]}
    chosen = {s: ["%d,%d" % csr.point_id(p["point"]) for p in context["operand_targets"] if p["scope"] == s] for s in keys}
    if stage == "report":
        for p in context["operand_prior16"]:
            chosen[p["scope"]].append("%d,%d" % csr.point_id(p["point"]))
        keys[context["csr_scope"]] = context["csr_all_keys"]
        chosen[context["csr_scope"]] = ["%d,%d" % csr.point_id(p["native"]) for p in context["csr_targets"]]
    return keys, chosen
