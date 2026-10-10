#!/usr/bin/env python3
"""Opt-in sealed gap65 admission for the unchanged composed-native workflow."""
import argparse
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import signal
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "reviewed_operand_20261004"))
import operand_guard as guard
import operand_workflow as workflow
import recover_gap65_report_only as recovery

sealed = recovery.sealed
require, sha, jread = guard.require, guard.sha, guard.jread
SCRIPT = Path(__file__).resolve()
TEST = HERE / "test_operand_native_651.py"
RUNTIME = guard.OUT / "gap65-late-fault-runtime-20261004-02"
BASELINE = guard.OUT / "gap67-current-20261004-01"
REPORTS = guard.OUT / "gap65-report-only-recovery-20261005-01/reports"
COMPLETION_SHA = "5057d845a6d75d070fcef33f92a106719b9b361fdfa6bdeecfda39af35f95209"
CHECKPOINT_SHA = "1a4e556c0e87775338cf0eaded88c79135e61916ceee4136ff7175fa16fb9771"
SCHEMA = "operand-native-651-admission-v1"
FROZEN = {
    "run_reviewed_dve_20261004.py": "49e96563068e99d4bfbe78bae24b47a569e4eeec8e501a6c5b28438703b1b802",
    "reviewed_csr_20261004/guard.py": "45de8e50c5d6090c97d972f43c558c3ef8302b92a1ef71f1fade89f1874bc47c",
    "reviewed_operand_20261004/operand_guard.py": "a9aeae8be2cfbe1de27f7073fe4f49ea64d9296f5b8eba234cf4c0a87e253fff",
    "reviewed_operand_20261004/operand_workflow.py": "2db6119a04c8b063619efe32d24e1617014be742c7d1d218258a1fb885099da1",
    "reviewed_operand_20261004/operand_support.py": "b1f5b9de5582aeec06f067e194756352b4e25fe73547e9fd892f80f568b0b74c",
    "reviewed_20261004/policy.json": "3c80137e57b735025dc80806184be224882466aa12796df235fedd4a2ac643f8",
    "coverage_evidence.py": "ef1e6682b91144e6f1ef438319e335a2a6ee8dd2f2c7beaa93588efc61df28a6",
    "finalize_gap65_observed.py": "af7050aa6010fc56cdca3c408574aa65277407035017bd338501af57eee0ee85",
    "recover_gap65_report_only.py": "4bce7a8bf02513cc6aeb548dd7da7114ae8a38b9a03f9487c38139ae1c5e9130",
}
LEGACY_ADMISSION = guard.csr_guard.legacy.admitted_inputs


@contextmanager
def timed_stage(name, timings, session=None):
    if timings is None:
        yield
        return
    started = time.monotonic()
    record = dict(stage=name, status="running")
    if session is not None:
        record["hash_before"] = session.stats()
    timings.append(record)
    print("NATIVE_OFFLINE_STAGE " + json.dumps(dict(event="start", **record)),
          file=sys.stderr, flush=True)
    try:
        yield
    except BaseException as error:
        record.update(status="failed", error_type=type(error).__name__)
        raise
    else:
        record["status"] = "complete"
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 6)
        if session is not None:
            record["hash_after"] = session.stats()
        print("NATIVE_OFFLINE_STAGE " + json.dumps(dict(event="end", **record)),
              file=sys.stderr, flush=True)


def exact_row(row):
    require(row.get("kind") == sealed.KIND and row.get("name") == sealed.ROW
            and row.get("schema") == sealed.SCHEMA and row.get("producer") == str(RUNTIME)
            and row.get("coverage_test") == sealed.observed.NAME,
            "Only the exact sealed gap65 versioned row is adaptable")
    require(row.get("status") == "PASS" and row.get("passed_only") is True
            and row.get("vdb_valid") is True and row.get("reused") is False
            and type(row.get("returncode")) is int and row["returncode"] == 0,
            "Gap65 row is not an independent PASS")
    require("vdb_rejection" not in row or row["vdb_rejection"] is None,
            "Gap65 has a VDB rejection; absence is never normalized into the ledger")


def require_bound(files, required):
    require(isinstance(files, dict) and files, "Empty recovery receipt hash map")
    require(all(files.get(path) == digest for path, digest in required.items()),
            "Recovery receipt omits or contradicts replay evidence")


def completed_recovery(proof, timings=None, session=None):
    completion_path, checkpoint_path = REPORTS / "completion.json", REPORTS / "checkpoint.json"
    require(REPORTS.resolve(strict=True) == REPORTS and not REPORTS.is_symlink(),
            "Recovery reports must be the exact independent directory")
    require(not (REPORTS / "rejected.json").exists(), "Recovery has a rejection")
    completion = jread(proof.pin(completion_path, COMPLETION_SHA))
    checkpoint = jread(proof.pin(checkpoint_path, CHECKPOINT_SHA))
    require(completion.get("status") == "PASS" and completion.get("schema") == recovery.SCHEMA
            and completion.get("source_runtime") == str(RUNTIME)
            and completion.get("baseline") == str(BASELINE)
            and type(completion.get("baseline_passed")) is int and completion["baseline_passed"] == 650
            and type(completion.get("aggregate_passed")) is int and completion["aggregate_passed"] == 651
            and completion.get("simulations_started") is False and completion.get("tools_launched") is False
            and completion.get("original_evidence_modified") is False,
            "Independent report-only recovery completion required")
    require(checkpoint == dict(status="PASS", phase="complete", coverage_status="COMPLETE",
            aggregate_passed=651, simulations_started=False, tools_launched=False,
            source_runtime=str(RUNTIME), completion_sha256=COMPLETION_SHA),
            "Independent recovery checkpoint is not COMPLETE or not bound to completion")
    require(type(checkpoint.get("aggregate_passed")) is int
            and checkpoint.get("simulations_started") is False and checkpoint.get("tools_launched") is False,
            "Recovery checkpoint types differ")
    files = completion.get("files")
    require(isinstance(files, dict) and files, "Empty recovery receipt hash map")
    stats = completion.get("hash_stats", {})
    require(type(stats.get("unique_files")) is int and type(stats.get("final_rehashed")) is int
            and stats["unique_files"] == stats["final_rehashed"] == len(files),
            "Full uncached recovery receipt rehash is incomplete")
    anchors = [RUNTIME / name for name in ("plan.json", "plan.sha256.json", "collection.json",
        "all-passed-outcomes.json", "outcomes/tests.json", "combined-bits.json", "combined-inputs.txt",
        "combined-dve/summary.csv", "combined-dve/inputs.txt", "combined-dve/selected_tests.txt",
        "combined-dve/waiver_status.json", "observed-recovery/result.json",
        "observed-recovery/independent_audit.json", "rejected.json")]
    anchors += [BASELINE / name for name in ("plan.json", "plan.sha256.json", "collection.json",
        "checkpoint.json", "all-passed-outcomes.json", "combined-dve/inputs.txt")]
    anchors += [HERE / name for name in ("finalize_gap65_observed.py", "recover_gap65_report_only.py")]
    require(all(str(p) in files for p in anchors), "Recovery receipt lacks required producer/report pins")
    require_bound(files, {str(HERE / name): FROZEN[name] for name in
                         ("finalize_gap65_observed.py", "recover_gap65_report_only.py")})
    with timed_stage("recovery_receipt_hashes", timings, session):
        proof.hashes(files)
    return files


def admission_adapter(receipt_files, receipt_pins, original=LEGACY_ADMISSION,
                      timings=None, session=None):
    def admitted_inputs(baseline, design):
        if baseline != RUNTIME:
            return original(baseline, design)
        # Run the original entire 650-case admission, not a copied/relaxed predicate.
        with timed_stage("ordinary650_legacy_admission", timings, session):
            old_rows, _, old_pins = original(BASELINE, design)
        require(len(old_rows) == 650, "Original ordinary650 population differs")
        proof = sealed.evidence.Evidence()
        plan = proof.plan(RUNTIME)
        require(Path(plan["design_vdb"]) == design and plan.get("gap65_report_only") == sealed.SCHEMA
                and plan.get("baseline") == str(BASELINE) and plan.get("source_selection", {}).get("baseline") == str(BASELINE),
                "Gap65 compiled design/producer ancestry differs")
        collection = proof.collection(RUNTIME, plan["image"])
        require(collection["status"] == "PASS" and collection["passed"] == collection["total"] == 651
                and collection["baseline_passed"] == 650 and collection["new_passed"] == 1
                and collection["cross_image_reuse"] is False and not collection["excluded"],
                "Published collection is not the scoped 650+1 aggregate")
        rows = proof.ledger(RUNTIME, plan["image"])
        require(len(rows) == 651 and rows[:650] == old_rows,
                "Ordinary650 ledger changed, omitted, reordered or replaced")
        row = rows[-1]
        exact_row(row)
        require(sum(r.get("kind") == sealed.KIND for r in rows) == 1
                and len({r["vdb"] for r in rows}) == 651, "Duplicate versioned row/VDB")
        inputs = proof.pin(RUNTIME / "combined-dve/inputs.txt")
        require(inputs.read_text().splitlines() == [str(design), *[r["vdb"] for r in rows]],
                "Corpus input membership differs from admitted ledger")
        # This includes the original rejection, exact source-echo recovery, oracle,
        # contract, logs, original artifact layout, siminfo and valid_vdb checks.
        with timed_stage("sealed_gap65_replay", timings, session):
            sealed.baseline_row(proof, row, plan["image"], plan["simv"])
            proof.hashes(row["vdb_files"])
        require_bound(receipt_files, old_pins)
        require_bound(receipt_files, proof.files)
        pins = dict(receipt_files)
        for entries in (receipt_pins, old_pins, proof.files):
            for path, digest in entries.items():
                require(path not in pins or pins[path] == digest, "Contradictory admission pin")
                pins[path] = digest
        return rows, inputs, pins
    return admitted_inputs


@contextmanager
def offline_hashes(session):
    # Reuse the already-tested process-local cache; no validation/oracle is cached.
    # Supplement its artifact hash aliases with the frozen native-reader aliases.
    with recovery.report_only(session):
        functions = (sha, workflow.sha, guard.csr_guard.sha, guard.csr_guard.legacy.audit.sha)
        with ExitStack() as stack:
            # importlib-loaded frozen readers are deliberately not in sys.modules.
            modules = list(sys.modules.values()) + [guard.csr, guard.csr_guard,
                guard.csr_guard.legacy, guard.csr_guard.legacy.audit]
            for mod in {id(m): m for m in modules}.values():
                path = getattr(mod, "__file__", None)
                if not path or Path(path).resolve() in (SCRIPT, Path(recovery.__file__).resolve()):
                    continue
                if not Path(path).resolve().is_relative_to(guard.ROOT / "verification"):
                    continue
                for name, value in list(vars(mod).items()):
                    if any(value is f for f in functions):
                        stack.enter_context(patch.object(mod, name, session.digest))
            yield


def build_context(baseline, timings=None):
    require(baseline.resolve(strict=True) == RUNTIME, "This adapter only prepares the exact recovered651")
    require(sealed.RUNTIME == RUNTIME and sealed.BASELINE == BASELINE, "Sealed recovery identity changed")
    session = recovery.HashSession()
    with offline_hashes(session):
        proof = sealed.evidence.Evidence()
        with timed_stage("frozen_source_pins", timings, session):
            proof.hashes({str(HERE / name): digest for name, digest in FROZEN.items()})
        with timed_stage("completed_recovery", timings, session):
            receipt_files = completed_recovery(proof, timings, session)
        adapt = admission_adapter(receipt_files, proof.files, timings=timings, session=session)
        with timed_stage("guard_build_context", timings, session):
            with patch.object(guard.csr_guard.legacy, "admitted_inputs", adapt):
                context = guard.build_context(RUNTIME)
        context["pins"].update(proof.files)
        for path in (SCRIPT, TEST):
            context["pins"][str(path)] = session.digest(path)
        require(context["tests"] == 651 and len(context["policy"]["allowed_points"]) == 201
                and len(context["operand_targets"]) == 1144 and len(context["observers"]) == 10,
                "Adapter changed the composed population")
        context["recovered651_admission"] = dict(schema=SCHEMA,
            source_runtime=str(RUNTIME), ordinary650=str(BASELINE),
            completion=str(REPORTS / "completion.json"), completion_sha256=COMPLETION_SHA,
            checkpoint=str(REPORTS / "checkpoint.json"), checkpoint_sha256=CHECKPOINT_SHA,
            receipt_files=len(receipt_files), ordinary650_checks="unchanged legacy.admitted_inputs",
            gap65_checks="exact versioned row; complete sealed.baseline_row replay",
            completion_basis="independent recovery COMPLETE, not collection existence",
            original_runtime_checkpoints={name: (sha(RUNTIME / name) if (RUNTIME / name).exists() else None)
                for name in ("checkpoint.json", "gap65-complete-checkpoint.json")},
            policy_changed=False, denominator_changed=False)
        with timed_stage("verify_inputs", timings, session):
            guard.verify_inputs(context)
        with timed_stage("final_uncached_rehash_and_identity", timings, session):
            # reverify() already finishes with the full assert_unchanged() scan.
            session.reverify()
        with timed_stage("latest_tip_recheck", timings, session):
            guard.csr_guard.latest_corpus(Path(context["design"]), context["image"], RUNTIME)
        context["recovered651_admission"]["hash_stats"] = session.stats()
        return context


def validate_adapter_context(context):
    record = context.get("recovered651_admission", {})
    require(context.get("tests") == 651 and context.get("baseline") == str(RUNTIME)
            and record.get("schema") == SCHEMA and record.get("source_runtime") == str(RUNTIME)
            and record.get("ordinary650") == str(BASELINE)
            and record.get("completion") == str(REPORTS / "completion.json")
            and record.get("checkpoint") == str(REPORTS / "checkpoint.json")
            and record.get("completion_sha256") == COMPLETION_SHA
            and record.get("checkpoint_sha256") == CHECKPOINT_SHA
            and record.get("policy_changed") is False and record.get("denominator_changed") is False,
            "Snapshot is not this exact recovered651 adapter admission")
    required = {str(HERE / n): h for n, h in FROZEN.items()}
    required.update({str(REPORTS / "completion.json"): COMPLETION_SHA,
                     str(REPORTS / "checkpoint.json"): CHECKPOINT_SHA,
                     str(SCRIPT): sha(SCRIPT), str(TEST): sha(TEST)})
    require_bound(context["pins"], required)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="Offline only; no tool process")
    check.add_argument("--baseline", type=Path, default=RUNTIME)
    prepare = commands.add_parser("prepare", help="New snapshot only; no DVE")
    prepare.add_argument("output", type=Path)
    prepare.add_argument("--baseline", type=Path, default=RUNTIME)
    prepare.add_argument("--stage", choices=("capture", "report"), required=True)
    prepare.add_argument("--capture", type=Path)
    prepare.add_argument("--capture-sha256")
    run = commands.add_parser("run", help="Only with a separately reviewed snapshot receipt")
    run.add_argument("output", type=Path)
    run.add_argument("--approval", type=Path, required=True)
    run.add_argument("--approval-sha256", required=True)
    args = parser.parse_args(argv)
    if args.command == "run":
        original_load = workflow.load_approval
        def load(*arguments):
            loaded = original_load(*arguments)
            validate_adapter_context(loaded[2])
            return loaded
        # Keep the adapter check inside the original absolute900s run deadline.
        with patch.object(workflow, "load_approval", load):
            return workflow.run(args.output, args.approval, args.approval_sha256)
    started = time.monotonic()
    timings = []
    def expired(signum, frame):
        active = [r["stage"] for r in timings if r["status"] == "running"]
        location = "%s:%s:%s" % (frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name)
        raise TimeoutError("Frozen300s offline admission/prepare budget exhausted; no retry; "
                           "active_stages=%s; interrupted=%s" % (active, location))
    old = signal.signal(signal.SIGALRM, expired)
    signal.alarm(workflow.PREPARE_MAX_SECONDS)
    try:
        with timed_stage("build_context", timings):
            context = build_context(args.baseline, timings)
        with timed_stage("adapter_context_validation", timings):
            validate_adapter_context(context)
        if args.command == "prepare":
            # Only the existing snapshot generator writes, in its fresh .tools.
            snapshot_session = recovery.HashSession()
            with timed_stage("snapshot_generation", timings, snapshot_session):
                with recovery.report_only(snapshot_session):
                    bundle = workflow.snapshot(args.output, context, args.stage, args.capture, args.capture_sha256)
            result = dict(status="PREPARED_RECOVERED651_NOT_RUN", snapshot=str(bundle),
                          snapshot_sha256=sha(bundle / "snapshot.json"),
                          baseline_collection_sha256=context["baseline_collection_sha256"])
        else:
            result = dict(status="CHECKED_RECOVERED651_NOT_RUN")
        result.update(tests=651, stage=getattr(args, "stage", None), operand_points=1144,
                      composed_points=1345, observers=10, DVE_launches=0,
                      elapsed_seconds=round(time.monotonic() - started, 3),
                      recovery=context["recovered651_admission"], stage_timings=timings)
        print(json.dumps(result, indent=2))
        return result
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TimeoutError) as error:
        print("REJECTED: " + str(error), file=sys.stderr)
        raise SystemExit(1)
