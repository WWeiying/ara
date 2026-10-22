#!/usr/bin/env python3
"""Strict current654 native offline adapter. No EDA launch command exists."""
from contextlib import contextmanager, ExitStack
import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
import run_operand_native_651 as prior
from gap74_native_hash_session import NativeHashSession

HERE, ROOT, OUT = prior.HERE, prior.guard.ROOT, prior.guard.OUT
CURRENT = OUT / "closure90-current-20261005-01"
RUNNER = HERE / "run_closure91_batch.py"
SCRIPT = Path(__file__).resolve()
HELPER = HERE / "gap74_native_hash_session.py"
TEST = HERE / "test_gap74_native_offline.py"
SESSION_TEST = HERE / "test_gap74_native_hash_session.py"
SCHEMA = "gap74-native654-offline-v1"
NORMAL_PRECHECK = prior.sealed.evidence.precheck
NORMAL_VALIDATE = prior.sealed.evidence.validate
CATALOG3 = ("rvv:sv39_gap68_warm_permissions_pmp0", "rvv:vgap69_vf_odd_vd",
            "rvv:vgap70_indexed_fault_recover")
IDENTITY = {
    "checkpoint.json": "6306ddb1c4baa282b55a7588f8f2dcbcacbea45357daecfe1d5fcdad773bab88",
    "collection.json": "96c65e4344f75fcc44eb1286e6872285fad759e8143d692ae4c6867b19f5aef4",
    "plan.json": "7dba67ac552e0f0a65fa1df6f8f6e8ec2e3469da738ca88e9ee965e33a9ecf49",
    "plan.sha256.json": "cf8e4bca380a41172a4ebf904c0453d3de41b57ebd6f2291c0101a534f9b7139",
}
PROTECTED = {
    "coverage_hash_session.py": "171de4990fa8e0a3985e4f87dc1678eed1ede9c5533f7d25e840052dc07db22f",
    "run_closure90_batch.py": "6cf9784d654e1349529285a71bc8756b52512bd05ff1307b2c935b33f3de44e2",
    "run_operand_native_651.py": "0bfe26d3395ecf4835a6a6838db33fe5b7e04cf3a95b48e0df5368a4adb59768",
    "test_operand_native_651.py": "554537d5a33f0398a658566bf9ac6d7fe56ca0fee994f8fe01688d36ecf70dd4",
    **prior.FROZEN,
}


def bind_runner(expected):
    prior.require(isinstance(expected, str) and re.fullmatch("[0-9a-f]{64}", expected),
                  "Explicit reviewed closure91 source SHA256 required")
    raw = RUNNER.read_bytes()
    prior.require(hashlib.sha256(raw).hexdigest() == expected, "closure91 reviewed source SHA differs")
    spec = importlib.util.spec_from_file_location("gap74_bound_closure91", RUNNER)
    runner = importlib.util.module_from_spec(spec)
    # Execute exactly the reviewed bytes, not a possibly older imported module/pyc.
    exec(compile(raw, str(RUNNER), "exec"), runner.__dict__)
    prior.require(runner.BASELINE == CURRENT and runner.HISTORY == prior.RUNTIME
                  and runner.SCRIPT == RUNNER and set(runner.predecessor.CATALOG) == set(CATALOG3),
                  "Foreign closure91 predecessor/654 identity")
    prior.require(all(runner.BASELINE_IDENTITY.get(n) == h for n, h in IDENTITY.items()),
                  "closure91 changed final654 identity roots")
    return runner


@contextmanager
def no_tools():
    def refuse(*args, **kwargs):
        raise RuntimeError("Gap74 offline scope forbids processes/EDA")
    with ExitStack() as stack:
        stack.enter_context(patch.object(subprocess, "Popen", refuse))
        stack.enter_context(patch.object(prior.sealed.full.batch, "invoke", refuse))
        for name in ("system", "execv", "execve", "execvp", "execvpe", "execl", "execlp", "execlpe",
                     "posix_spawn", "posix_spawnp", "fork"):
            if hasattr(os, name):
                stack.enter_context(patch.object(os, name, refuse))
        yield


@contextmanager
def installed_hooks(runner):
    evidence = prior.sealed.evidence
    modules = [importlib.import_module(n) for n in runner.predecessor.CATALOG.values()]
    with ExitStack() as stack:
        stack.enter_context(patch.object(evidence.Evidence, "baseline_row", prior.sealed._NORMAL_ROW))
        stack.enter_context(patch.object(evidence, "precheck", NORMAL_PRECHECK))
        stack.enter_context(patch.object(evidence, "validate", NORMAL_VALIDATE))
        for module in modules:
            prior.require(Path(module.__file__).resolve().parent == HERE, "Foreign predecessor adapter")
            for flag, initial in (("_installed", False), ("_hooks", None)):
                if hasattr(module, flag):
                    stack.enter_context(patch.object(module, flag, initial))
        # Install the COMPLETE three-case chain, never report_only's gap65-only hook.
        runner.predecessor.install(dict(cases=[dict(name=n) for n in CATALOG3]))
        gap69 = next(m for m in modules if m.__name__ == "run_gap69_vf_checked_extension")
        prior.require(gap69._hooks is not None and
                      evidence.Evidence.baseline_row is gap69._hooks["baseline_row"] and
                      evidence.Evidence.baseline_row is not prior.sealed.baseline_row,
                      "Gap69 runtime byte-audit chain was clobbered")
        yield


@contextmanager
def hash_reads_only(session):
    aliases = (prior.sha, prior.workflow.sha, prior.guard.csr_guard.sha,
               prior.guard.csr_guard.legacy.audit.sha, prior.recovery.RAW_SHA256,
               prior.sealed.targeted.bitmaps.digest)
    modules = list(sys.modules.values()) + [prior.guard.csr, prior.guard.csr_guard,
        prior.guard.csr_guard.legacy, prior.guard.csr_guard.legacy.audit]
    with ExitStack() as stack:
        for module in {id(m): m for m in modules}.values():
            path = getattr(module, "__file__", None)
            if not path or not Path(path).resolve().is_relative_to(ROOT / "verification"):
                continue
            for name, value in list(vars(module).items()):
                if not name.startswith("RAW_") and any(value is f for f in aliases):
                    stack.enter_context(patch.object(module, name, session.digest))
        yield


@contextmanager
def row_costs(stats):
    evidence = prior.sealed.evidence
    delegate = evidence.Evidence.baseline_row
    def measured(proof, row, image, simv):
        name = row.get("name")
        group = ("gap65" if row.get("kind") == prior.sealed.KIND else
                 name if name in {n.split(":")[1] for n in CATALOG3} else "ordinary650")
        record = stats.setdefault(group, dict(calls=0, completed=0, failed=0, seconds=0.0))
        record["calls"] += 1
        started = time.monotonic()
        try:
            result = delegate(proof, row, image, simv)
            record["completed"] += 1
            stats.setdefault("completed_rows", []).append([row.get("name"), row.get("vdb")])
            return result
        except BaseException:
            record["failed"] += 1
            raise
        finally:
            record["seconds"] += time.monotonic() - started
    with patch.object(evidence.Evidence, "baseline_row", measured):
        yield


def merge_pins(*maps):
    result = {}
    for entries in maps:
        for path, digest in entries.items():
            prior.require(path not in result or result[path] == digest, "Contradictory input SHA: " + path)
            result[path] = digest
    return result


def read_seed(runner):
    completion = prior.jread(prior.REPORTS / "completion.json")
    plan = prior.jread(CURRENT / "plan.json")
    rows = prior.jread(CURRENT / "all-passed-outcomes.json")
    collection = prior.jread(CURRENT / "collection.json")
    prior.require(len(rows) == 654, "Only exact current654 is supported")
    # Scheduling hints only: all hashes, rows and sources are validated below.
    files = merge_pins(completion["files"], plan["files"], collection["reports"],
        *[part for row in rows for part in (row["files"], row["vdb_files"])],
        {str(CURRENT / n): h for n, h in runner.BASELINE_IDENTITY.items()})
    return files, plan, rows


def make_session(outputs, files, plan, rows, runner_sha):
    own = [SCRIPT, HELPER, TEST, SESSION_TEST]
    seals = merge_pins({str(HERE / n): h for n, h in PROTECTED.items()},
        {str(RUNNER): runner_sha, str(prior.REPORTS / "completion.json"): prior.COMPLETION_SHA,
         str(prior.REPORTS / "checkpoint.json"): prior.CHECKPOINT_SHA},
        {str(CURRENT / n): h for n, h in IDENTITY.items()})
    session = NativeHashSession(outputs, immutable_files=[*files, *seals, *own],
        immutable_trees=[plan["design_vdb"], *[r["vdb"] for r in rows]])
    return session, seals, own


def full_raw_reports(proof, plan, rows, bits):
    # Exact existing read-only DVE log/diagnostic/waiver/membership proof.
    prior.sealed.report_callback(CURRENT, plan, rows, proof)
    inputs = proof.pin(CURRENT / "combined-inputs.txt")
    prior.require(inputs.read_text().splitlines() == [plan["design_vdb"], *[r["vdb"] for r in rows]],
                  "Full654 raw bitmap input membership differs")
    fresh = prior.sealed.targeted.bitmaps.collect(inputs)
    proof.hashes(fresh["input_hashes"])
    prior.require(fresh == bits, "Full654 uncached raw bitmap union differs")
    old = proof.read(prior.RUNTIME / "combined-bits.json")
    delta = prior.sealed.targeted.bitmaps.delta(old, fresh)
    prior.require(proof.read(CURRENT / "raw-bitmap-delta.json") == delta, "654 raw bitmap delta differs")


def admission654(runner, runner_sha, timings, session, audits, original=prior.LEGACY_ADMISSION):
    def admitted(baseline, design):
        prior.require(baseline != prior.RUNTIME, "Stale651 native admission is forbidden")
        if baseline != CURRENT:
            return original(baseline, design)
        with prior.timed_stage("unchanged_original650_admission", timings, session):
            ordinary, _, original_pins = original(prior.BASELINE, design)
        prior.require(len(ordinary) == 650, "Original650 population differs")
        proof = prior.sealed.evidence.Evidence()
        proof.pin(RUNNER, runner_sha)
        with prior.timed_stage("complete_gap65_recovery_receipt", timings, session):
            prior.completed_recovery(proof, timings, session)
        with prior.timed_stage("strict654_all_oracles_prechecks_runtime_audits", timings, session):
            replay_start = len(audits.get("completed_rows", []))
            with row_costs(audits):
                rows, bits = runner.completed(proof)
        prior.require({tuple(pair) for pair in audits.get("completed_rows", [])[replay_start:]} >=
                      {(r["name"], r["vdb"]) for r in rows},
                      "A full654 independent row replay was omitted")
        prior.require(len(rows) == 654 and rows[:650] == ordinary,
                      "Strict654 ledger changed ordinary650 row/files/VDB membership")
        prior.exact_row(rows[650])
        prior.require(sum(r.get("kind") == prior.sealed.KIND for r in rows) == 1
                      and len({r["vdb"] for r in rows}) == 654, "Duplicate versioned row/VDB")
        prior.require({r["name"] for r in rows[651:]} == {n.split(":")[1] for n in CATALOG3},
                      "Wrong exact three-case suffix")
        for row in rows[651:]:
            prior.require(row["status"] == "PASS" and row["passed_only"] is True
                          and row["vdb_valid"] is True and row["vdb_rejection"] is None
                          and row["reused"] is False and type(row["returncode"]) is int
                          and row["returncode"] == 0, "Non-independent new654 row")
        plan = proof.plan(CURRENT)
        prior.require(Path(plan["design_vdb"]) == design, "654 compiled design differs")
        inputs = proof.pin(CURRENT / "combined-dve/inputs.txt")
        prior.require(inputs.read_text().splitlines() == [str(design), *[r["vdb"] for r in rows]],
                      "654 ordered native VDB membership differs")
        with prior.timed_stage("every654_row_and_vdb_content_pin", timings, session):
            for row in rows:
                proof.hashes(row["files"])
                proof.hashes(row["vdb_files"])
            prior.require_bound(proof.files, original_pins)
        with prior.timed_stage("ancestor651_full_raw_report_and_delta", timings, session):
            recovery_plan, recovery_rows, old = prior.recovery.validate_completed_reports(proof, prior.RUNTIME)
            prior.require(rows[:651] == recovery_rows, "Strict654 changed completed651 prefix")
            prior.recovery.validate_producers(proof, recovery_plan)
            prior.recovery.validate_deltas(proof, prior.RUNTIME, recovery_plan, recovery_rows, old)
        with prior.timed_stage("full654_report_and_fresh_raw_bitmap", timings, session):
            full_raw_reports(proof, plan, rows, bits)
        return rows, inputs, merge_pins(original_pins, proof.files)
    return admitted


def context654(runner, runner_sha, timings, session, audits):
    adapt = admission654(runner, runner_sha, timings, session, audits)
    with prior.timed_stage("unchanged_reviewed_source_native_and_raw_guard", timings, session):
        with patch.object(prior.guard.csr_guard.legacy, "admitted_inputs", adapt):
            context = prior.guard.build_context(CURRENT)
    required = merge_pins({str(HERE / n): h for n, h in PROTECTED.items()},
        {str(CURRENT / n): h for n, h in IDENTITY.items()},
        {str(RUNNER): runner_sha, str(prior.REPORTS / "completion.json"): prior.COMPLETION_SHA,
         str(prior.REPORTS / "checkpoint.json"): prior.CHECKPOINT_SHA})
    measured = {name: session.digest(name) for name in required}
    prior.require_bound(measured, required)
    context["pins"] = merge_pins(context["pins"], measured,
        {str(path): session.digest(path) for path in (SCRIPT, HELPER, TEST, SESSION_TEST)})
    context["gap74_offline"] = dict(schema=SCHEMA, source_runner=str(RUNNER), source_runner_sha256=runner_sha,
        current654=str(CURRENT), ancestor651=str(prior.RUNTIME), ordinary650=str(prior.BASELINE),
        completion=str(prior.REPORTS / "completion.json"), completion_sha256=prior.COMPLETION_SHA,
        checkpoint=str(prior.REPORTS / "checkpoint.json"), checkpoint_sha256=prior.CHECKPOINT_SHA,
        independent_rows_replayed=654, oracle_cached=False, latest_tip_relaxed=False,
        policy_changed=False, denominator_changed=False, native1345_qualified=False,
        exclusions_applied=False)
    with prior.timed_stage("all_input_and654_context_binding", timings, session):
        prior.guard.verify_inputs(context)
        validate_context(context, runner_sha)
    return context


def validate_context(context, runner_sha):
    record = context.get("gap74_offline", {})
    prior.require(type(context.get("tests")) is int and context["tests"] == 654
                  and context.get("baseline") == str(CURRENT)
                  and context.get("baseline_collection_sha256") == IDENTITY["collection.json"]
                  and len(context["policy"]["allowed_points"]) == 201
                  and len(context["operand_targets"]) == 1144 and len(context["observers"]) == 10,
                  "Not the exact654/1345/10 composed context")
    required = dict(schema=SCHEMA, source_runner=str(RUNNER), source_runner_sha256=runner_sha,
        current654=str(CURRENT), ancestor651=str(prior.RUNTIME), ordinary650=str(prior.BASELINE),
        completion=str(prior.REPORTS / "completion.json"), completion_sha256=prior.COMPLETION_SHA,
        checkpoint=str(prior.REPORTS / "checkpoint.json"), checkpoint_sha256=prior.CHECKPOINT_SHA,
        independent_rows_replayed=654)
    prior.require(all(record.get(k) == v for k, v in required.items())
                  and type(record.get("independent_rows_replayed")) is int
                  and all(record.get(k) is False for k in ("oracle_cached", "latest_tip_relaxed",
                      "policy_changed", "denominator_changed", "native1345_qualified", "exclusions_applied")),
                  "654 context admission identity/types/authority differ")
    pins = merge_pins({str(HERE / n): h for n, h in PROTECTED.items()},
        {str(CURRENT / n): h for n, h in IDENTITY.items()},
        {str(RUNNER): runner_sha, str(prior.REPORTS / "completion.json"): prior.COMPLETION_SHA,
         str(prior.REPORTS / "checkpoint.json"): prior.CHECKPOINT_SHA})
    prior.require_bound(context["pins"], pins)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("capability", "check", "prepare"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline", type=Path, default=CURRENT)
    parser.add_argument("--closure91-sha256", required=True)
    args = parser.parse_args(argv)
    prior.require(args.baseline.resolve(strict=True) == CURRENT, "Only current654; stale651 prepare forbidden")
    output, bundle = prior.workflow.locations(args.output)
    evidence = output if args.command != "prepare" else Path(str(output) + ".offline")
    prior.require(not any(p.exists() or p.is_symlink() for p in (output, bundle, evidence)), "Fresh output required; no retry")
    timings, audits, started = [], {}, time.monotonic()
    def expired(signum, frame):
        active = [r["stage"] for r in timings if r["status"] == "running"]
        raise TimeoutError("Frozen300s offline bound; no retry; stages=%s; interrupted=%s:%s:%s" %
            (active, frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name))
    old_handler = signal.signal(signal.SIGALRM, expired)
    signal.alarm(prior.workflow.PREPARE_MAX_SECONDS)
    session, context, owned_bundle, owned_evidence = None, None, False, False
    try:
        evidence.mkdir()
        owned_evidence = True
        with no_tools():
            with prior.timed_stage("bind_reviewed_runner_and_latest654", timings):
                runner = bind_runner(args.closure91_sha256)
                plan = prior.jread(CURRENT / "plan.json")
                prior.guard.csr_guard.latest_corpus(Path(plan["design_vdb"]), plan["image"], CURRENT)
            with prior.timed_stage("seed_and654_membership_snapshot", timings):
                files, plan, rows = read_seed(runner)
                session, seals, own = make_session([output, bundle, evidence], files, plan, rows, args.closure91_sha256)
            with installed_hooks(runner), hash_reads_only(session):
                with prior.timed_stage("protected_seals", timings, session):
                    for name, expected in seals.items():
                        prior.require(session.digest(name) == expected, "Protected source/root SHA differs: " + name)
                    for path in own:
                        session.digest(path)
                with prior.timed_stage("parallel_full_immutable_prehash", timings, session):
                    session.prehash(files)
                if args.command != "capability":
                    context = context654(runner, args.closure91_sha256, timings, session, audits)
                    if args.command == "prepare":
                        with prior.timed_stage("capture_snapshot_only_no_EDA", timings, session):
                            try:
                                prior.workflow.snapshot(output, context, "capture")
                            finally:
                                owned_bundle = bundle.is_dir()
                else:
                    # Hash-only capability does not claim row/oracle/report admission.
                    proof = prior.sealed.evidence.Evidence()
                    prior.completed_recovery(proof, timings, session)
                    with prior.timed_stage("full_immutable_cache_hit_pass", timings, session):
                        proof.hashes(files)
                with prior.timed_stage("final_uncached_all_content_and_membership", timings, session):
                    session.reverify()
            with prior.timed_stage("post_rehash_uncached_latest_tip_and_source_gate", timings):
                _, census = prior.guard.csr_guard.latest_corpus(Path(plan["design_vdb"]), plan["image"], CURRENT)
                prior.require(prior.sha(RUNNER) == args.closure91_sha256, "Runner changed after final hash")
                if context is not None:
                    prior.require(all(context["pins"].get(p) == h for p, h in census.items()),
                                  "Corpus census changed after full rehash")
            prior.require(session.finished and session.reverified == len(session.entries), "Final hash incomplete")
            result = dict(schema=SCHEMA, status=(
                "OFFLINE_HASH_CAPABILITY_ONLY_NOT_ADMISSION" if args.command == "capability" else
                "PREPARED_CAPTURE654_NOT_RUN" if args.command == "prepare" else "OFFLINE654_REPLAY_NOT_NATIVE_QUALIFICATION"),
                elapsed_seconds=round(time.monotonic() - started, 6), budget_seconds=300,
                stage_timings=timings, row_audit_costs=audits, hash_stats=session.stats(),
                simulations_started=False, tools_launched=False, exclusions_applied=False,
                native1345_qualified=False, oracle_cached=False, latest_tip_relaxed=False,
                baseline=str(CURRENT), baseline_collection_sha256=IDENTITY["collection.json"],
                closure91_sha256=args.closure91_sha256, protected_seals=seals,
                independent_rows_replayed=654 if context is not None else 0)
            if args.command == "prepare":
                result.update(snapshot=str(bundle / "snapshot.json"), snapshot_sha256=prior.sha(bundle / "snapshot.json"))
            result["files"] = {name: digest for name, (_, digest) in session.entries.items()}
            (evidence / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            print(json.dumps({k: v for k, v in result.items() if k != "files"}, indent=2))
            return result
    except BaseException as error:
        # Keep failed artifacts, but do not leave a consumable snapshot manifest.
        if owned_bundle and (bundle / "snapshot.json").is_file():
            (bundle / "snapshot.json").rename(bundle / "unqualified-snapshot.json")
        if owned_evidence:
            (evidence / "result.json").unlink(missing_ok=True)
            (evidence / "rejected.json").write_text(json.dumps(dict(status="REJECTED_NOT_ADMITTED",
                error_type=type(error).__name__, reason=str(error), stage_timings=timings,
                row_audit_costs=audits, hash_stats=session.stats() if session else None,
                native1345_qualified=False, tools_launched=False), indent=2) + "\n")
        raise
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TimeoutError, RuntimeError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        raise SystemExit(1)
