"""Read-only admission. Legacy branch assumptions are confined to legacy points."""
import copy
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
COVERAGE = HERE.parent
ROOT = HERE.parents[2]
OUT = ROOT / "verification/out"
sys.path.insert(0, str(COVERAGE))
from support import *

QUALIFIED = OUT / "gap50-csr-roundtrip-review-20261004-01"
QUALIFIED_SHA = "49816946caf281487776abe1473a93cd3192386e85e2740137214e180680f9c1"


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


legacy = module("csr_legacy_wrapper", COVERAGE / "run_reviewed_dve_20261004.py")


def latest_tip(records):
    """Unique completed descendant, not a filename, largest count, or mtime guess."""
    require(records, "No completed frozen-image corpus")
    ancestors = set()
    for name in records:
        seen, current = set(), name
        while current in records:
            require(current not in seen, "Cyclic corpus lineage")
            seen.add(current)
            current = records[current]["parent"]
            if current in records:
                ancestors.add(current)
    tips = set(records) - ancestors
    require(len(tips) == 1, "Ambiguous completed corpus tips; independent reconciliation required")
    return next(iter(tips))


def latest_corpus(design, image, requested=None):
    records, pins = {}, {}
    for path in sorted(OUT.glob("*/collection.json")):
        collection = jread(path)
        if collection.get("image") != image or collection.get("status") not in ("PASS", "COMPLETE_WITH_FAILURES"):
            continue
        plan_path = path.parent / "plan.json"
        plan = jread(plan_path)
        require(plan["image"] == image and Path(plan["design_vdb"]) == design, "Frozen-image candidate design mismatch")
        # Aggregate extension corpora have this report layout. Original build/test
        # campaigns are admitted through Evidence's historical baseline chain.
        raw = path.parent / "combined-dve/summary.csv"
        if str(raw) not in collection["reports"]:
            continue
        require(raw.is_file(), "Completed corpus missing raw report")
        parent = (plan.get("source_selection") or {}).get("baseline")
        records[str(path.parent)] = dict(parent=parent, passed=collection["passed"])
        pins[str(path)], pins[str(plan_path)] = sha(path), sha(plan_path)
    selected = Path(latest_tip(records))
    require(requested is None or Path(requested).resolve() == selected, "Requested baseline is stale/not latest")
    return selected, pins


def qualify_csr():
    require(sha(QUALIFIED / "manifest.sha256.json") == QUALIFIED_SHA, "Gap50 qualifier seal differs")
    manifest = jread(QUALIFIED / "manifest.sha256.json")
    require(manifest["status"] == "PASS_SCOPED_SEMANTIC_ROUNDTRIP_NOT_APPLICATION_AUTHORIZATION" and
            manifest["application_authorized"] is False, "Gap50 is not scoped identity evidence")
    pins = {str(QUALIFIED / p): h for p, h in manifest["files"].items()}
    pins[str(QUALIFIED / "manifest.sha256.json")] = QUALIFIED_SHA
    verify_hashes(pins)
    qualifier = module("csr_gap50_qualifier", QUALIFIED / "qualifier.py")
    qualified = qualifier.qualify()
    pins.update(qualified["pins"])
    accepted = [p for p in jread(qualifier.REVIEW / "accepted-coordinates.json")["accepted"]
                if p["metric"] == "branch" and p["eligibility"] == "ACCEPT_CONSTANT_GUARD"]
    native_path = qualifier.PILOT / "dve/branches.saved.el"
    data = native_path.read_bytes()
    parsed = qualifier.parse_native(data)
    native_points, blocks = [], {}
    for key, row in parsed["records"].items():
        scope, metric, modsum, metricsum, sid, vid = key
        point = f"Branch {sid} ({vid})"
        native_points.append(dict(scope=scope, point=point, checksum=[modsum, metricsum],
            native_directive=row["raw"].decode().splitlines()[1], nativepointchecksum=row["spec_checksum"],
            native_signature=row["signature"]))
        blocks[point] = row["raw"].decode()
    return qualified, accepted, native_points, blocks, native_path, pins


def raw_zero_scan(rows, targets, scope, checksum):
    union, evidence, inherited = 0, [], 0
    for row in rows:
        vdb = Path(row["vdb"])
        files = list(vdb.glob("snps/coverage/db/testdata/*/branch.verilog.data.xml"))
        require(len(files) == 1, "Expected one branch testdata file per VDB")
        path = files[0]
        digest = row["vdb_files"].get(str(path))
        require(digest and sha(path) == digest, "Raw branch file not bound to admitted PASS")
        bits, missing_checksum = raw_csr_bits(path.read_bytes(), scope, checksum, 626)
        zero_targets(bits, targets)
        union |= int(bits, 2)
        inherited += missing_checksum
        evidence.append(dict(path=str(path), sha256=digest))
    require(evidence, "No admitted raw samples")
    bits = format(union, "0626b")
    zero_targets(bits, targets)
    return dict(samples=len(evidence), width=626, bits=bits, selected_hits=0,
        inherited_checksum_samples=inherited, files=evidence, source="raw branch XML, not cached zero assumption")


def build_context(requested=None):
    policy, record, pins = legacy.guard_review()
    require(len(policy["allowed_points"]) == 94 and len(record["observers"]) == 10, "Legacy policy population differs")
    qualified, targets, csr_native, blocks, csr_file, qualified_pins = qualify_csr()
    for path, digest in qualified_pins.items():
        require(path not in pins or pins[path] == digest, "Contradictory source/review pin")
        pins[path] = digest
    design = Path(record["identity"]["design_vdb"])
    proof = legacy.coverage_evidence.Evidence()
    original = proof.plan(OUT / "repaired-aligned-600-20260930-01")
    proof.hashes(original["image"])
    baseline, census = latest_corpus(design, original["image"], requested)
    rows, inputs, admitted = legacy.admitted_inputs(baseline, design)
    pins.update(proof.files)
    pins.update(census)
    pins.update(admitted)
    require(len({r["vdb"] for r in rows}) == len(rows), "Duplicate corpus VDB")
    require(jread(baseline / "collection.json")["cross_image_reuse"] is False, "Cross-image reuse forbidden")
    # The old vector0 / two-vector witness is valid ONLY for the original 94.
    old_points = copy.deepcopy(record["points"])
    legacy.audit.merge_selected([Path(r["vdb"]) for r in rows], old_points,
                               {p: h for r in rows for p, h in r["vdb_files"].items()})
    scope = qualified["validation"]["scope"]
    d = legacy.audit.Design(design)
    definition = d.definition(scope, "branch")
    inventory = bind_targets(definition, targets)
    checksum = [d.source(scope)["definition_checksum"], definition.get("chksum")]
    require(all(p["scope"] == scope and p["checksum"] == checksum for p in targets), "CSR scope/checksum drift")
    raw = raw_zero_scan(rows, targets, scope, checksum[1])
    collection = jread(baseline / "collection.json")
    cache_path = baseline / "combined-bits.json"
    require(str(cache_path) in collection["reports"], "Latest cache is not sealed to collection")
    cache = jread(cache_path)
    require(cache["tests"] == [r["vdb"] for r in rows], "Latest cache membership differs")
    cached = cache["metrics"]["branch"][scope]
    require(cached["width"] == 626 and cached["checksum"] == checksum[1] and
            format(int(cached["bits"], 16), "0626b") == raw["bits"], "Fresh raw union differs from latest cache")
    raw_paths = {p["path"]: p["sha256"] for p in raw["files"]}
    require(all(cache["input_hashes"].get(p) == h for p, h in raw_paths.items()), "Raw/cache provenance differs")
    membership = {}
    for path in [design] + [Path(r["vdb"]) for r in rows]:
        files = sorted(str(p) for p in path.rglob("*") if p.is_file())
        for file in files:
            digest = sha(file)
            require(file not in pins or pins[file] == digest, "VDB changed during admission")
            pins[file] = digest
        membership[str(path)] = files
    combined = copy.deepcopy(policy)
    combined["allowed_points"] += csr_native
    combined["status"] = "SUPPLEMENTAL_CANDIDATE_REQUIRES_INDEPENDENT_APPLICATION_REVIEW"
    require(len({(p["scope"], p["point"]) for p in combined["allowed_points"]}) == 201, "Overlapping old/CSR policy")
    for observer in record["observers"]:
        require(not (scope == observer["scope"] or scope.startswith(observer["scope"] + ".")), "Observer covers product CSR")
    metadata = {point_id(p["point"]): p["actual_gui"] for p in qualified["records"]}
    selection = [dict(spec=sid, vector=vid, meta=metadata[sid, vid]["meta"], path=metadata[sid, vid]["path"])
                 for sid, vid in sorted(metadata)]
    for mod in list(sys.modules.values()):
        file = getattr(mod, "__file__", None)
        if file and Path(file).suffix == ".py" and Path(file).resolve().is_relative_to(ROOT):
            pins[str(Path(file).resolve())] = sha(file)
    # Pin the complete new implementation and all borrowed reporting code.
    for path in [COVERAGE / "run_reviewed_csr_dve_20261004.py", COVERAGE / "run_reviewed_dve_20261004.py",
                 COVERAGE / "prepare_dve_waivers.py", COVERAGE / "dve_waivers.tcl",
                 COVERAGE / "dve_hierarchy/run_dve_coverage.sh", COVERAGE / "dve_hierarchy/export_dve_coverage.tcl",
                 COVERAGE / "reviewed_20261004/prepare_native.py", *HERE.glob("*.py"), *HERE.glob("*.tcl")]:
        pins[str(path)] = sha(path)
    shapes = {p.name: sha(p) for p in sorted((design / "snps/coverage/db/shape").iterdir()) if p.is_file()}
    context = dict(policy=combined, observers=record["observers"], pins=pins, design=str(design),
        shape_files=shapes, baseline=str(baseline), baseline_collection_sha256=sha(baseline / "collection.json"),
        image=original["image"], inputs=inputs.read_text().splitlines(), tests=len(rows),
        raw_reference=str(baseline / "combined-dve/summary.csv"), raw_reference_sha256=sha(baseline / "combined-dve/summary.csv"),
        csr_scope=scope, csr_checksum=checksum, csr_blocks=blocks, csr_native_path=str(csr_file),
        csr_header="".join(csr_file.read_text().splitlines(keepends=True)[:2]),
        csr_native_sha256=sha(csr_file), csr_targets=targets, csr_selection=selection,
        csr_all_keys=[f"{sid},{vid}" for sid, vid in sorted(inventory)], csr_raw_audit=raw,
        input_membership=membership, qualified_manifest_sha256=QUALIFIED_SHA,
        old_strict_status=qualified["validation"]["strict_status_unchanged"],
        authorization="PENDING_INDEPENDENT_APPLICATION_REVIEW", final_coverage_application=False)
    validate_union((legacy.native_points(policy) + csr_file.read_text()).encode(), context, legacy.audit, False)
    verify_hashes(pins)
    latest_corpus(design, original["image"], baseline)
    return context


def verify_membership(context):
    for directory, expected in context["input_membership"].items():
        actual = sorted(str(p) for p in Path(directory).rglob("*") if p.is_file())
        require(actual == expected, "VDB file membership changed")
