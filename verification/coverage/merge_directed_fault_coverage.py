#!/usr/bin/env python3
"""Append one independently checked directed fault test to a PASS-only report."""

import argparse
import json
import os
from pathlib import Path
import subprocess

import run_vcs_dve_batch as batch


ROOT = batch.ROOT
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--audit-run", type=Path, required=True)
    parser.add_argument("--vdb-run", type=Path, required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--elf-app")
    parser.add_argument("--pass-marker")
    parser.add_argument("--expected-passed", type=int, required=True)
    parser.add_argument("--expected-exceptions", type=int, required=True)
    parser.add_argument("--uvm-reset-read", action="store_true")
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    audit_run = args.audit_run.resolve()
    vdb_run = args.vdb_run.resolve()
    test = args.test
    elf_app = args.elf_app or test
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "verification/out") or output.exists():
        raise ValueError("output must be a fresh directory under verification/out")

    predecessor = batch.read(baseline / "collection.json")
    if (predecessor["status"] != "COMPLETE" or
            predecessor["passed"] != args.expected_passed or
            predecessor["current_rtl_claim"] is not False):
        raise ValueError("predecessor is not a verified original-image collection")
    batch.check(predecessor["reports"])
    image = Path(predecessor["image"])
    if image != ROOT / "verification/out/repair-closure-coverage-20260927-01/sim/simv":
        raise ValueError("unexpected simulator image")
    original_plan = batch.read(
        ROOT / "verification/out/vcs-original503-gap29-20260928-01/plan.json")
    batch.check(original_plan["image"])
    prior = (baseline / "dve/inputs.txt").read_text().splitlines()
    if len(prior) != args.expected_passed + 1 or len(prior) != len(set(prior)):
        raise ValueError("expected one design VDB and unique PASS VDBs")

    elf = ROOT / "apps/bin" / elf_app
    if args.uvm_reset_read:
        for run in (audit_run, vdb_run):
            result = batch.read(run / "uvm_result.json")
            work = run / "work" if run == audit_run else run
            if (result["status"] != "PASS" or result["issues"] or
                    result["reset_kind"] != "read" or
                    result["axi_read_counts"]["aborted"] < 1 or
                    result["backend_counts"]["aborted"] < 1):
                raise ValueError("UVM reset audit lacks read/VID cancellation")
            for recorded, path in (
                    ("elf_sha256", audit_run / "work/input.elf"),
                    ("simv_sha256", image),
                    ("log_sha256", work / "run.vcs.log"),
                    ("vector_trace_sha256", work / "vector_trace.csv")):
                if result[recorded] != batch.sha256(path):
                    raise ValueError(f"UVM audit hash mismatch: {recorded}")
        if batch.sha256(elf) != batch.sha256(audit_run / "work/input.elf"):
            raise ValueError("coverage ELF differs from audited reset ELF")
    else:
        summary = batch.read(audit_run / "summary.json")
        audit = batch.read(audit_run / "independent_audit.json")
        if (len(summary) != 1 or summary[0]["status"] != "PASS" or
                audit["status"] != "PASS" or audit["passed_cases"] != 1):
            raise ValueError("functional test lacks independent PASS audit")
        if batch.sha256(elf) != batch.sha256(
                audit_run / "tests" / f"app_{test}" / "input.elf"):
            raise ValueError("coverage ELF differs from audited ELF")
    log = (vdb_run / "run.vcs.log").read_text()
    for marker in (args.pass_marker or f"PASSED: {test}",
                   "Core Test *** SUCCESS *** (tohost = 0)",
                   "UVM_ERROR :    0", f"exceptions={args.expected_exceptions}",
                   "protocol_errors=0"):
        if marker not in log:
            raise ValueError(f"coverage replay lacks {marker}")
    if args.uvm_reset_read and ("[ARA_UVM_RESET_TEST] kind=read accepted=1" not in log or
                                "[ARA_UVM_RESET_TEST] kind=read released=1" not in log):
        raise ValueError("coverage replay lacks controlled reset markers")
    vdb = vdb_run / "code.vdb"
    vdb_files = batch.valid_vdb(vdb, test, str(image))
    if str(vdb) in prior:
        raise ValueError("duplicate VDB")

    output.mkdir(parents=True)
    inputs = output / "inputs.txt"
    inputs.write_text("\n".join(prior + [str(vdb)]) + "\n")
    report = output / "dve"
    command = ["bash", str(batch.HERE / "run_dve_coverage.sh"), str(report),
               "--inputs-file", str(inputs)]
    with (output / "dve.log").open("w") as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                env=dict(os.environ, DVE_COVERAGE_TIMEOUT="600",
                                         DVE_WAIVERS="auto"), timeout=720, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"DVE failed; see {output / 'dve.log'}")
    expected_rows = len((baseline / "dve/summary_waived.csv").read_text().splitlines())
    for name in ("summary.csv", "summary_waived.csv"):
        if len((report / name).read_text().splitlines()) != expected_rows:
            raise ValueError(f"incomplete DVE hierarchy: {name}")
    expected = [str(Path(path).with_suffix("") / next(
        item.name for item in (Path(path) / "snps/coverage/db/testdata").iterdir()
        if item.is_dir())) for path in prior[1:]] + [str(vdb.with_suffix("") / test)]
    if (report / "selected_tests.txt").read_text().splitlines() != expected:
        raise ValueError("selected tests differ from audited PASS VDBs")
    if batch.read(report / "waiver_status.json")["status"] != "APPLIED":
        raise ValueError("reviewed waivers were not applied")
    if batch.base.inventory(vdb) != vdb_files:
        raise ValueError("new VDB changed during DVE")
    metadata = {"status": "COMPLETE", "baseline_passed": args.expected_passed,
                "passed": args.expected_passed + 1,
                "added": test, "image": str(image), "current_rtl_claim": False,
                "baseline": str(baseline), "functional_run": str(audit_run),
                "functional_audit": str(audit_run / (
                    "uvm_result.json" if args.uvm_reset_read else "independent_audit.json")),
                "new_vdb": str(vdb), "new_vdb_files": vdb_files,
                "reports": batch.pins([report / "summary.csv", report / "summary_waived.csv"])}
    (output / "collection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"DVE PASS-only merge: {report / 'summary_waived.csv'}")


if __name__ == "__main__":
    main()
