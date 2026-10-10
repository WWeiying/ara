#!/usr/bin/env python3
"""Fresh current-checker diagnostics for the fixed 33 old-image extensions.

Reuse the producer-specific audit, never simulate or approve an aggregate.
32 cases use the unchanged bit-exact gate. red32 stays explicitly unclosed:
its bounded integer mathematics is not proof of captured VRF writeback bits.
PASS_DIAGNOSTIC_ONLY means current comparator success, not historical source
closure. Historical source revisions are recorded separately and never renamed
to current hashes; every runtime input retains its strict expected hash.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import multiprocessing
from pathlib import Path
import signal
import struct
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]/"verification"))
import old_image_waiver_admission as admission
from ara_verify.plan import _full_architecture_match, _full_vector_match
from ara_verify.trace import validate_trace

ROOT, OUT = admission.ROOT, admission.OUT
SCRIPT = Path(__file__).resolve()
TEST = HERE/"test_current_extension_trace_replay.py"
SCHEMA = "current-extension33-diagnostics-v1"
RED32 = "vgap76_red32"
HISTORICAL_MUTABLE_SOURCES = {
    str(HERE/"run_gap76_old_image.py"),
    str(ROOT/"apps/riscv-tests/isa/rv64uv/vgap76_wide_body.h"),
}
require = admission.require


def save(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def merge_pins(destination, entries):
    require(isinstance(entries, dict) and entries, "Empty pins")
    for path, digest in entries.items():
        require(path not in destination or destination[path] == digest, "Conflicting pins: "+path)
        destination[path] = digest


def sourcepins():
    paths = [SCRIPT, TEST, admission.SCRIPT, Path(admission.helpers.__file__),
             Path(admission.old.__file__), HERE/"gap74_native_hash_session.py",
             *sorted((ROOT/"verification/ara_verify").glob("*.py")),
             *[HERE/name for name in admission.old.PROTECTED], Path(sys.executable).resolve()]
    return {str(p):admission.sha_bytes(p.read_bytes()) for p in paths}


def partition_source_pins(pins):
    """Only two identified historical source revisions can be held, never runtime inputs."""
    verified, held = {}, {}
    for path, expected in pins.items():
        if path in HISTORICAL_MUTABLE_SOURCES:
            current = admission.sha_bytes(Path(path).read_bytes())
            if current != expected:
                held[path] = dict(historical_sha256=expected, current_sha256=current,
                    historical_bytes_verified=False, reason="Historical source revision unavailable; not executed by this replay")
                continue
        verified[path] = expected
    return verified, held


def check_state(state, gap, names, population, previous, parent, simv):
    require(state.get("status") == state.get("coverage_status") == "COMPLETE"
            and state.get("phase") == "complete" and state.get("live_rtl_reverted") is False
            and state.get("image") == simv, "Incomplete/foreign old-image extension")
    require(type(state.get("baseline_passed")) is int and state["baseline_passed"] == previous
            and type(state.get("aggregate_passed")) is int and state["aggregate_passed"] == population
            and set(state.get("cases", {})) == set(names), "Wrong population/membership")
    require((gap == 76 and "baseline_directory" not in state)
            or state.get("baseline_directory") == str(parent), "Wrong ancestor")
    accepted = []
    for name in names:
        row = state["cases"][name]
        if name == "vgap76_red16":
            require(row.get("status") == "FAIL", "Known FAIL was reclassified")
        else:
            require(row.get("status") == "PASS", "Extension is not PASS-only")
            accepted.append(name)
    require(type(state.get("new_passed")) is int and state["new_passed"] == len(accepted)
            and previous+len(accepted) == population, "Wrong PASS increment")
    return accepted


def select_cases(profiles, names):
    require(len(profiles) == 33 and len({p["name"] for p in profiles}) == 33, "Not exact 33")
    available = [p for p in profiles if p["name"] != RED32]
    require(len(available) == 32, "Missing separately held red32")
    if not names:
        return available
    require(len(set(names)) == len(names), "Duplicate selected case")
    lookup = {p["name"]:p for p in available}
    require(all(name in lookup for name in names), "Unknown or held case selected")
    return [lookup[name] for name in names]


def red32_integer_math():
    """Value-level order-independence, not native-byte or signed-zero approval."""
    records = []
    for full in (32, 64):
        for iteration in range(7):
            active = (1, 3, 5, full-1, full, full, full)[iteration]
            mask = 0 if iteration == 4 else 0xa5 if iteration == 5 else 0xff
            operands = [i % 5-2 for i in range(active) if mask >> (i % 8) & 1]
            require(all(struct.unpack("<f", struct.pack("<f", x))[0] == x for x in operands),
                    "Input integer not exactly FP32")
            bound = 2+sum(abs(x) for x in operands)
            require(bound <= 130 and bound < 2**53, "Not exact FP64 partial-sum domain")
            records.append(dict(lmul="m1" if full == 32 else "m2", iteration=iteration,
                active=active, mask=mask, expected_integer=2+sum(operands), partial_sum_abs_bound=bound))
    return dict(status="VALUE_LEVEL_PROOF_ONLY_NOT_ADMITTED", reduction_instances=14,
        rounding_tolerance=None, order_independent_integer_values=True,
        reason="FP32 operands and every FP64 partial sum are exact small integers; native writes, signed zero and flags still require independent binding",
        bit_exact_writeback_proven=False, admitted=False, cases=records)


def prepare(output, names):
    output = Path(output).absolute()
    require(not output.exists() and output.parent.resolve(strict=True) == OUT.resolve(strict=True),
            "Fresh direct-child sidecar output required")
    seal = admission.FileSeal()
    base = admission.old.CURRENT
    seal.pin(base/"plan.json", admission.old.IDENTITY["plan.json"])
    plan = seal.read(base/"plan.json")
    seal.pin(base/"collection.json", admission.old.IDENTITY["collection.json"])
    collection = seal.read(base/"collection.json")
    ledger = base/"all-passed-outcomes.json"
    seal.pin(ledger, collection["reports"][str(ledger)])
    rows = seal.read(ledger)
    require(len(rows) == 654 and len({r["vdb"] for r in rows}) == 654
            and all(r["status"] == "PASS" for r in rows), "Invalid historical prefix inventory")
    expected = [plan["design_vdb"], *[r["vdb"] for r in rows]]
    previous, parent = 654, base
    shared, profiles, historical_holds = {}, [], {}
    merge_pins(shared, plan["image"])
    for gap, declared, population in admission.EXTENSIONS:
        directory = OUT/("gap%d-old-image-20261006-01" % gap)
        state = seal.read(directory/"status.json")
        accepted = check_state(state, gap, declared, population, previous, parent, plan["simv"])
        pins = seal.read(directory/"source-pins.json")
        require(all(pins.get(p) == h for p,h in plan["image"].items()), "Foreign image sourcepins")
        for relative in ("combined-inputs.txt", "combined-bits.json"):
            require(str(parent/relative) in pins, "Missing ancestor sourcepin")
        verified, held_sources = partition_source_pins(pins)
        merge_pins(shared, verified)
        historical_holds[str(directory)] = held_sources
        for name in accepted:
            case_dir = directory/"results"/name
            row = state["cases"][name]
            require(row.get("directory") == str(case_dir) and row.get("vdb") == str(case_dir/"code.vdb"),
                    "Foreign case layout")
            profiles.append(dict(name=name, directory=str(case_dir), state_row=row, source_pins=pins,
                                 historical_source_holds=held_sources))
            expected.append(str(case_dir/"code.vdb"))
        require(seal.pin(directory/"combined-inputs.txt").read_text().splitlines() == expected,
                "Ordered extension membership differs")
        previous, parent = population, directory
    code = sourcepins()
    merge_pins(shared, code)
    seal.hashes(shared)
    chosen = select_cases(profiles, names)
    for profile in chosen:
        private = admission.FileSeal()
        private.tree(Path(profile["directory"]))
        private.finish()
        profile["input_sha256"] = dict(private.files)
        profile["tree_root"] = profile["directory"]
        merge_pins(seal.files, private.files)
        seal.trees.update(private.trees)
    held = next(p for p in profiles if p["name"] == RED32)
    red_dir = Path(held["directory"])
    saved = seal.read(red_dir/"vector-comparison.json")
    command = seal.read(red_dir/"compile.command.json")["command"]
    require(not any(arg.startswith("-DG_PATTERN") or arg.startswith("-DG_SEW")
                    or arg.startswith("-DG_KIND") or arg.startswith("-include") for arg in command),
            "red32 source configuration changed")
    red = dict(name=RED32, status="HELD_NOT_REPLAYED_NOT_ADMITTED", saved_status=saved["status"],
        saved_non_bit_exact=saved["non_bit_exact_instructions"], saved_skipped_unknown=saved["skipped_unknown_bytes"],
        source=str(ROOT/"apps/riscv-tests/isa/rv64uv/vgap76_red32.c"), mathematical_analysis=red32_integer_math(),
        historical_source_holds=held["historical_source_holds"],
        mathematical_analysis_historical_source_binding_complete=not held["historical_source_holds"])
    seal.finish()
    manifest = dict(schema=SCHEMA, status="PREPARED_NOT_REPLAYED", profiles=chosen, plan=plan,
        input_sha256=dict(seal.files), current_checker_sourcepins=code, red32=red,
        historical_source_holds=historical_holds, historical_source_chain_closed=not any(historical_holds.values()),
        replay_tests=len(chosen), available_strict_cases=32, extension_population=33,
        admitted687=False, application_approval=False, simulations_started=False)
    output.mkdir()
    save(output/"manifest.json", manifest)
    return admission.sha_bytes((output/"manifest.json").read_bytes())


def timeout(signum, frame):
    raise TimeoutError("Bounded extension replay deadline exhausted")


def replay(profile, plan, seconds):
    require(type(seconds) is int and 1 <= seconds <= 600, "Invalid bounded worker deadline")
    previous = signal.signal(signal.SIGALRM, timeout)
    signal.alarm(seconds)
    try:
        with admission.old.no_tools():
            seal = admission.FileSeal()
            seal.hashes(profile["input_sha256"])
            seal.tree(Path(profile["tree_root"]))
            require(set(seal.files) == set(profile["input_sha256"]), "Private inventory changed")
            computed = {}
            scalar_api, vector_api = admission.helpers.compare_commit_prefix, admission.helpers.compare_vector_commits
            def scalar(*args, **kwargs):
                computed["scalar"] = scalar_api(*args, **kwargs)
                return computed["scalar"]
            def vector(*args, **kwargs):
                computed["vector"] = vector_api(*args, **kwargs)
                return computed["vector"]
            with patch.object(admission.helpers, "compare_commit_prefix", scalar), \
                 patch.object(admission.helpers, "compare_vector_commits", vector):
                row = admission.audit_case(seal, Path(profile["directory"]), profile["name"],
                                           profile["state_row"], plan, profile["source_pins"])
            require(_full_architecture_match(computed["scalar"]) and _full_vector_match(computed["vector"]),
                    "Partial scalar/vector accounting")
            trace = validate_trace(Path(profile["directory"])/"commit_trace.csv")
            seal.finish()
            return dict(schema=SCHEMA, status="PASS_DIAGNOSTIC_ONLY", name=profile["name"],
                scalar=computed["scalar"], vector=computed["vector"], trace=trace,
                historical_source_holds=profile.get("historical_source_holds", {}),
                historical_source_chain_closed=not profile.get("historical_source_holds", {}),
                audit_row=row, input_sha256=dict(seal.files), admitted687=False, application_approval=False)
    except Exception as error:
        return dict(schema=SCHEMA, status="FAILED_DIAGNOSTIC_ONLY", name=profile["name"],
            reason=f"{type(error).__name__}: {error}", admitted687=False, application_approval=False)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def check(output, manifest_sha, workers=8, seconds=300):
    require(type(workers) is int and 1 <= workers <= 8 and type(seconds) is int and 1 <= seconds <= 600,
            "Invalid workers/deadline")
    output = Path(output).resolve(strict=True)
    require(output.parent == OUT.resolve(strict=True), "Foreign output")
    seal = admission.FileSeal()
    seal.pin(output/"manifest.json", manifest_sha)
    manifest = seal.read(output/"manifest.json")
    require(manifest["schema"] == SCHEMA and manifest["status"] == "PREPARED_NOT_REPLAYED"
            and 1 <= len(manifest["profiles"]) <= 32 and manifest["admitted687"] is False,
            "Invalid diagnostic manifest")
    require(manifest["current_checker_sourcepins"] == sourcepins(), "Current checker sourcepins drift")
    seal.hashes(manifest["input_sha256"])
    for profile in manifest["profiles"]:
        root = Path(profile["tree_root"])
        seal.tree(root)
        actual = {p:h for p,h in seal.files.items() if Path(p).is_relative_to(root)}
        require(actual == profile["input_sha256"], "Prepared private inventory changed")
    require(not (output/"cases").exists() and not (output/"diagnostic.json").exists(), "Existing check results")
    (output/"cases").mkdir()
    results = {}
    with ProcessPoolExecutor(max_workers=min(workers,len(manifest["profiles"])),
                             mp_context=multiprocessing.get_context("spawn")) as pool:
        jobs = {pool.submit(replay,p,manifest["plan"],seconds):i for i,p in enumerate(manifest["profiles"])}
        for future in as_completed(jobs):
            i = jobs[future]
            try:
                result = future.result()
            except Exception as error:
                result = dict(status="FAILED_DIAGNOSTIC_ONLY", name=manifest["profiles"][i]["name"],
                              reason=f"Worker failure: {error}", admitted687=False)
            results[i] = result
            save(output/"cases"/("%03d.json" % i), result)
            print(json.dumps(dict(phase="CASE_COMPLETE",name=result["name"],status=result["status"])),flush=True)
    seal.finish()
    passed = sum(r["status"] == "PASS_DIAGNOSTIC_ONLY" for r in results.values())
    source_closed = sum(r["status"] == "PASS_DIAGNOSTIC_ONLY" and r["historical_source_chain_closed"]
                        for r in results.values())
    report = dict(schema=SCHEMA, status="STRICT_SUBSET_DIAGNOSTICS_COMPLETE" if passed == len(results) else "STRICT_SUBSET_DIAGNOSTICS_FAILED",
        passed=passed, failed=len(results)-passed, replay_tests=len(results), extension_population=33,
        red32=manifest["red32"], current_comparator_unclosed_extensions=33-passed,
        source_closed_replayed_cases=source_closed, unclosed_extensions=33-source_closed, admitted687=False,
        historical_source_holds=manifest["historical_source_holds"],
        historical_source_chain_closed=manifest["historical_source_chain_closed"],
        application_approval=False, simulations_started=False,
        manifest_sha256=manifest_sha, current_checker_sourcepins=manifest["current_checker_sourcepins"])
    save(output/"diagnostic.json",report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare","check","run"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--case-timeout", type=int, default=300)
    parser.add_argument("--manifest-sha256")
    args = parser.parse_args()
    if args.command in ("prepare","run"):
        print(json.dumps(dict(phase="PREPARING",simulations_started=False)),flush=True)
        digest = prepare(args.output,args.case)
        print(json.dumps(dict(phase="PREPARED",manifest_sha256=digest)),flush=True)
        if args.command == "prepare":
            return 0
    else:
        digest = args.manifest_sha256
        require(isinstance(digest,str) and admission.SHA_RE.fullmatch(digest), "Reviewed manifest SHA required")
    result = check(args.output,digest,args.workers,args.case_timeout)
    print(json.dumps(result,indent=2),flush=True)
    return int(result["failed"] != 0)


if __name__ == "__main__":
    raise SystemExit(main())
