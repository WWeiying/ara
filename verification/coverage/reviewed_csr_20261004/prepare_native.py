#!/usr/bin/env python3
"""Runtime snapshot adapter; only publishes success after fresh-session proofs."""
import argparse
import importlib.util
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from support import *


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def check_snapshot(reviewed_sha256):
    return verify_snapshot(HERE, reviewed_sha256)


def check_raw(output, context, name="summary.csv.partial"):
    require(sha(context["raw_reference"]) == context["raw_reference_sha256"], "Raw baseline changed")
    require(csv_rows(output / name) == csv_rows(context["raw_reference"]), "Raw report differs from frozen corpus")


def verify_inputs(context):
    verify_hashes(context["pins"])
    for directory, expected in context["input_membership"].items():
        require(sorted(str(p) for p in Path(directory).rglob("*") if p.is_file()) == expected, "VDB membership changed")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--mode", choices=("auto",), default="auto")
    parser.add_argument("--finalize", action="store_true")
    parser.add_argument("--session", choices=("raw", "saved", "reset"))
    args = parser.parse_args(argv)
    context = check_snapshot(args.snapshot_sha256)
    require(args.design.resolve() == Path(context["design"]), "Foreign compiled design")
    output = args.output.resolve()
    require(str(output) == context["output"], "Foreign output")
    audit = load("audit_readonly")
    if args.session:
        if args.session == "raw":
            require((output / "initial-empty.el").read_bytes() == b"", "Fresh session has pre-existing exclusions")
            check_raw(output, context)
        elif args.session == "saved":
            validate_union((output / "exclusions.el").read_bytes(), context, audit, True)
        else:
            require((output / "final-empty.el").read_bytes() == b"", "Final reset not empty")
            check_raw(output, context, "summary_after_reset.csv.partial")
        check_snapshot(args.snapshot_sha256)
        print("CSR_RUNTIME_CHECK_OK " + args.session)
        return
    verify_inputs(context)
    if args.finalize:
        check_raw(output, context, "summary.csv")
        check_raw(output, context, "summary_after_reset.csv.partial")
        csv_rows(output / "summary_waived.csv")
        validate_union((output / "exclusions.el").read_bytes(), context, audit, True)
        states = fresh_state((output / "DVEfiles/dve_gui.log").read_text(), context)
        require((output / "initial-empty.el").read_bytes() == (output / "final-empty.el").read_bytes() == b"", "Empty states changed")
        actual_tests = (output / "selected_tests.txt").read_text().splitlines()
        expected_tests = []
        for vdb in context["inputs"][1:]:
            tests = list((Path(vdb) / "snps/coverage/db/testdata").iterdir())
            require(len(tests) == 1, "VDB gained extra tests")
            expected_tests.append(str(Path(vdb).with_suffix("") / tests[0].name))
        require(actual_tests == expected_tests, "DVE loaded a different test population")
        raw_dir = output / "raw"
        raw_dir.mkdir()
        import shutil
        for source, target in ((output / "summary.csv", "summary.csv"),
                               (output / "summary_after_reset.csv.partial", "summary_after_reset.csv"),
                               (Path(context["raw_reference"]), "baseline.csv")):
            shutil.copyfile(source, raw_dir / target)
        status = dict(status="SUPPLEMENTAL_CSR_REPORT_VERIFIED_NOT_FINAL_SIGNOFF", tests=context["tests"],
            existing_points=94, csr_points=107, observers=10, fresh_session=states,
            raw_report="raw/summary.csv", supplemental_report="summary_waived.csv",
            original_vdbs_unchanged=True, old_strict_status=context["old_strict_status"],
            final_coverage_application=False, files={name: sha(output / name) for name in
                ("summary.csv", "summary_waived.csv", "exclusions.el", "raw/summary.csv", "raw/summary_after_reset.csv")})
        # The outer wrapper still must reject a newly completed corpus or changed
        # approval. It alone publishes success after those final gates.
        check_snapshot(args.snapshot_sha256)
        return status
    base, adapter = load("waiver_base"), load("legacy_adapter")
    adapter.configure(context, base, audit)

    def exclusions(text):
        validate_union(text.encode(), context, audit, False)
        return {(p["scope"], p["point"]) for p in context["policy"]["allowed_points"]}

    base.exclusion_items = exclusions
    status = base.prepare(args.design, output, args.mode)["status"]
    check_snapshot(args.snapshot_sha256)
    print(status)


if __name__ == "__main__":
    main()
