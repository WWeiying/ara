#!/usr/bin/env python3
"""Admit one audited QBS fault VDB to the immutable original-image report."""

import argparse
import json
import os
from pathlib import Path
import subprocess

import run_vcs_dve_batch as batch


ROOT = batch.ROOT
BASELINE = ROOT / "verification/out/vcs-original503-gap29-20260928-01"
RUN = ROOT / "verification/out/qbs-descriptor-fault-cov-direct-20260928-01"
VDB_RUN = ROOT / "verification/out/qbs-descriptor-fault-cov-vdb-20260928-01"
TEST = "qbs_descriptor_fault_cov"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / "verification/out"):
        raise ValueError("output must be under verification/out")
    collection = batch.read(BASELINE / "collection.json")
    if not collection["coverage_verified"] or collection["passed"] != 504:
        raise ValueError("504-PASS predecessor is not verified")
    if collection.get("current_rtl_claim") is not False:
        raise ValueError("expected original RTL image, not current RTL")
    plan = batch.read(BASELINE / "plan.json")
    image = Path(plan["simv"])
    if image != ROOT / "verification/out/repair-closure-coverage-20260927-01/sim/simv":
        raise ValueError("unexpected simulator image")
    batch.check(plan["image"])
    prior = (BASELINE / "dve/inputs.txt").read_text().splitlines()
    if len(prior) != 505 or prior[0] != plan["design_vdb"]:
        raise ValueError("expected design VDB and exactly 504 passing tests")
    if len(prior) != len(set(prior)):
        raise ValueError("duplicate predecessor VDB")
    batch.check(collection["reports"])

    summary = batch.read(RUN / "summary.json")
    audit = batch.read(RUN / "independent_audit.json")
    if (len(summary) != 1 or summary[0]["status"] != "PASS" or
            audit["status"] != "PASS" or audit["passed_cases"] != 1):
        raise ValueError("independent functional audit is not PASS")
    elf = ROOT / "apps/bin/qbs_descriptor_fault_cov"
    if batch.sha256(elf) != batch.sha256(RUN / "tests/app_qbs_descriptor_fault_cov/input.elf"):
        raise ValueError("tested ELF differs from current test ELF")
    log = (VDB_RUN / "run.vcs.log").read_text()
    if ("PASSED: qbs_descriptor_fault_cov" not in log or
            "Core Test *** SUCCESS *** (tohost = 0)" not in log or
            "UVM_ERROR :    0" not in log or
            "exceptions=1" not in log or "protocol_errors=0" not in log):
        raise ValueError("coverage replay has not passed the functional contract")
    vdb = VDB_RUN / "code.vdb"
    vdb_files = batch.valid_vdb(vdb, TEST, str(image))
    if str(vdb) in prior:
        raise ValueError("new VDB was already present")

    output.mkdir(parents=True, exist_ok=False)
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
    expected_rows = len((BASELINE / "dve/summary_waived.csv").read_text().splitlines())
    for name in ("summary.csv", "summary_waived.csv"):
        if len((report / name).read_text().splitlines()) != expected_rows:
            raise ValueError(f"DVE {name} did not export the complete hierarchy")
    expected = [str(Path(path).with_suffix("") / next(
        item.name for item in (Path(path) / "snps/coverage/db/testdata").iterdir()
        if item.is_dir())) for path in prior[1:]] + [str(vdb.with_suffix("") / TEST)]
    if (report / "selected_tests.txt").read_text().splitlines() != expected:
        raise ValueError("DVE selected tests differ from the audited PASS set")
    if batch.read(report / "waiver_status.json")["status"] != "APPLIED":
        raise ValueError("reviewed waivers were not applied")
    if batch.base.inventory(vdb) != vdb_files:
        raise ValueError("QBS VDB changed during DVE")
    metadata = {"status": "COMPLETE", "baseline_passed": 504, "passed": 505,
                "added": TEST, "image": str(image), "current_rtl_claim": False,
                "baseline": str(BASELINE), "functional_run": str(RUN),
                "functional_audit": str(RUN / "independent_audit.json"),
                "new_vdb": str(vdb), "new_vdb_files": vdb_files,
                "reports": batch.pins([report / "summary.csv", report / "summary_waived.csv"])}
    (output / "collection.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"DVE PASS-only merge: {report / 'summary_waived.csv'}")


if __name__ == "__main__":
    main()
