#!/usr/bin/env python3
"""Snapshot-only callbacks. The receipt root is required on every invocation."""
import argparse
import shutil
import sys
from operand_support import *

sys.dont_write_bytecode = True


def raw_summary(output, context, name):
    require(sha(context["raw_reference"]) == context["raw_reference_sha256"], "Raw baseline drift")
    require(csr.csv_rows(output / name) == csr.csv_rows(context["raw_reference"]), "Raw summary drift")


def callback(output, context, stage, first_sha=None):
    audit = module("operand_runtime_native_audit", HERE / "audit_readonly.py")
    if stage == "raw":
        require((output / "initial-empty.el").read_bytes() == b"", "Initial state not empty")
        if context["stage"] == "report":
            raw_summary(output, context, "summary.csv.partial")
    elif stage == "first":
        data = (output / "first.el").read_bytes()
        if context["stage"] == "capture":
            validate_operand(data, context)
        else:
            validate_composed(data, context, audit, True)
        return sha(output / "first.el")
    elif stage == "empty":
        require((output / "reset-empty.el").read_bytes() == b"", "Intermediate reset not empty")
    elif stage == "second":
        require(re.fullmatch(r"[0-9a-f]{64}", first_sha or "") and sha(output / "first.el") == first_sha,
                "First export changed since fresh callback")
        pair((output / "first.el").read_bytes(), (output / "second.el").read_bytes(), context, audit)
    elif stage == "final":
        require((output / "final-empty.el").read_bytes() == b"", "Final reset not empty")
        if context["stage"] == "report":
            raw_summary(output, context, "summary.csv.partial")
    else:
        raise ValueError("Unknown callback")


def finish(output, context, reviewed_root):
    states = state_proof(output, context, reviewed_root)
    callback(output, context, "raw")
    callback(output, context, "empty")
    callback(output, context, "second", sha(output / "first.el"))
    callback(output, context, "final")
    actual_tests = (output / "selected_tests.txt").read_text().splitlines()
    expected_tests = []
    for root in context["inputs"][1:]:
        dirs = list((Path(root) / "snps/coverage/db/testdata").iterdir())
        require(len(dirs) == 1 and dirs[0].is_dir(), "Test population changed")
        expected_tests.append(str(Path(root).with_suffix("") / dirs[0].name))
    require(actual_tests == expected_tests, "DVE loaded different PASS population")
    if context["stage"] == "report":
        csr.csv_rows(output / "summary_waived.csv.partial")
    else:
        require(not (output / "summary_waived.csv.partial").exists(), "Capture must not publish adjusted report")
    raw = output / "raw"
    raw.mkdir()
    if context["stage"] == "report":
        shutil.copyfile(output / "summary.csv.partial", raw / "summary.csv")
        shutil.copyfile(context["raw_reference"], raw / "baseline.csv")
    (output / "state-audit.json").write_text(json.dumps(dict(points=states, count=len(states)), indent=2) + "\n")
    return dict(status="NATIVE_1144_CAPTURE_VERIFIED_NOT_APPLICATION_APPROVAL" if context["stage"] == "capture"
                else "SUPPLEMENTAL_1345_REPORT_VERIFIED_NOT_FINAL_SIGNOFF", stage=context["stage"],
                operand_points=1144, baseline_points=201, observers=10, tests=context["session_tests"], corpus_tests=context["tests"],
                observed_leaf_count=len(states), retained_review_coordinates=1269,
                retained_current_missing=context["retained_current_missing_count"], final_coverage_application=False,
                native_file=str(output / "first.el"), native_sha256=sha(output / "first.el"),
                byte_identical=(output / "first.el").read_bytes() == (output / "second.el").read_bytes(),
                complete_record_semantic_equal=True, post_reset_full_raw_export=False,
                raw_integrity=("Initial full raw matches pinned published baseline; final global native empty, exact branch states and byte-identical input VDBs. No post-reset full score remeasurement."
                    if context["stage"] == "report" else "No full score exports; final global native empty, exact branch states and byte-identical input VDBs."))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--session", choices=("raw", "first", "empty", "second", "final"))
    parser.add_argument("--first-sha256")
    args = parser.parse_args(argv)
    context = verify_snapshot(HERE, args.snapshot_sha256)
    require(str(args.output.resolve()) == context["output"], "Foreign session output")
    require(args.session is not None, "Callbacks only; outer reviewed runner finalizes")
    result = callback(args.output, context, args.session, args.first_sha256)
    verify_snapshot(HERE, args.snapshot_sha256)
    print("OQ_CALLBACK " + args.session)
    if result:
        print("OQ_FIRST_SHA " + result)


if __name__ == "__main__":
    main()
