#!/usr/bin/env python3
"""One bounded retry on the frozen coverage image; old failure is preserved."""
import argparse
from pathlib import Path
import sys

import run_repair_closure_coverage as campaign
from ara_verify.artifacts import sha256, simulation_image
from ara_verify.model import TestCase
from ara_verify.runner import RegressionRunner, RunOptions

ROOT = campaign.ROOT
SOURCE = ROOT / "verification/out/repair-closure-coverage-20260927-01"
RESULT = SOURCE / "results/vlsseg_retry1800"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = campaign.base.checked_output(args.output)
    campaign.base.check_service()
    if output.exists() or RESULT.exists():
        raise RuntimeError("retry output exists; refusing overwrite")
    plan = campaign.frozen(SOURCE, True)
    spec = plan["jobs"]["vlsseg"]
    wrapper = SOURCE / "inputs/coverage_simv"
    pins = campaign.pins([Path(__file__).resolve(), Path(spec["elf"]),
                          SOURCE / "plan.json", SOURCE / "runtime.json"])
    output.mkdir(parents=True)
    campaign.save(output / "replay-inputs.json", {
        "source": str(SOURCE), "result": str(RESULT), "elf": spec["elf"],
        "elf_sha256": spec["elf_sha256"], "wrapper": str(wrapper),
        "wrapper_image": simulation_image(wrapper), "pins": pins,
        "timeout_s": 1800, "original_timeout_s": spec["timeout_s"],
        "test": spec["test"], "coverage_test": spec["coverage_test"],
        "scope": "same ELF/image, wall timeout only; original TIMEOUT preserved",
    })
    state = {"status": "RUNNING", "phase": "VCS", "timeout_s": 1800,
             "result": str(RESULT), "coverage_verified": False}
    campaign.save(output / "replay-status.json", state)
    try:
        options = RunOptions(repo_root=ROOT, output_root=RESULT, config="default",
                             jobs=1, seed=1, dry_run=False, build_only=False,
                             skip_build=True, simv=wrapper, commit_trace=True,
                             timeout_s=1800, code_coverage=False)
        test = TestCase(name=spec["test"], kind="rvv", build_target="unused-no-build",
                        binary=Path(spec["elf"]), testcase=spec["coverage_test"], timeout_s=1800)
        results = RegressionRunner(options, [test], sys.argv).run()
        campaign.check(pins)
        campaign.frozen(SOURCE, True)
        if len(results) != 1 or results[0].status != "PASS":
            raise RuntimeError("retry did not complete PASS")
        state.update(status="PASS", phase="AWAIT_INDEPENDENT_AUDIT",
                     summary_sha256=sha256(RESULT / "summary.json"))
    except Exception as error:
        state.update(status="FAIL", reason=f"{type(error).__name__}: {error}")
        raise
    finally:
        campaign.save(output / "replay-status.json", state)


if __name__ == "__main__":
    main()
