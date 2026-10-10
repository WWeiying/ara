#!/usr/bin/env python3
"""One unchanged-image replay; preserve the original timed-out campaign."""
import sys
import os
from pathlib import Path

import recollect_current_coverage as current

b = current.batch
root = current.ROOT
parent = current.OUTPUT
output = root / "verification/out/vcs-current-q5k-retry600-20260927-02"
name = "extra-app-llama_qwen25_q5k_decode_attn_q_qbs"


def main():
    output.mkdir(parents=True, exist_ok=False)
    b.save(output / "status.json", {"status": "CHECKING_INPUTS"})
    plan = current.frozen(parent, all_cases=True)
    case = next(c for c in plan["cases"] if c["name"] == name)
    b.check(case["source_files"])
    b.check({case["frozen_elf"]: case["elf_sha256"]})
    b.save(output / "provenance.json", {
        "parent": str(parent), "case": case, "image": plan["image"],
        "old_timeout_s": case["timeout_s"], "timeout_s": 600,
        "wrapper": plan["wrapper"], "rtl_and_elf_unchanged": True})
    test = b.TestCase(**dict(case["directed_test"], binary=Path(case["frozen_elf"])))
    target = output / "result"
    config = b.read(parent / "inputs/coverage-wrapper.json")
    config["results"] = str(target)
    b.save(output / "coverage-wrapper.json", config)
    options = b.RunOptions(repo_root=root, output_root=target, config="default",
        jobs=1, seed=1, dry_run=False, build_only=False, skip_build=True,
        simv=Path(__file__).with_name("retry_current_q5k_simv.sh"), commit_trace=True, timeout_s=600)
    b.save(output / "status.json", {"status": "RUNNING", "timeout_s": 600})
    results = b.RegressionRunner(options, [test], sys.argv).run()
    if len(results) != 1 or results[0].status != "PASS":
        b.save(output / "status.json", {"status": "NOT_PASSED", "summary": str(target / "summary.json")})
        return 1
    command = [sys.executable, str(root / "verification/verify.py"), "audit",
        "--run", str(target), "--require-trace", "--output", str(target / "independent_audit.json")]
    current.require(b.invoke(command, output / "audit.log", 180) == 0, "independent audit failed")
    artifact = target / "tests" / b._safe_name(case["source_name"])
    b.audit_ok(b.read(target / "independent_audit.json"), case, artifact)
    b.check({str(artifact / "input.elf"): case["elf_sha256"]})
    current.frozen(parent, all_cases=True)
    vdb = artifact / "work/code.vdb"
    files = b.valid_vdb(vdb, case["coverage_test"], plan["simv"])
    b.save(output / "status.json", {"status": "PASS", "coverage_valid": True,
        "vdb": str(vdb), "vdb_files": files, "elf_sha256": case["elf_sha256"],
        "audit": str(target / "independent_audit.json"), "original_timeout_preserved": True})
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--coverage-exec":
        command = b.adapter_command(b.read(output / "coverage-wrapper.json"), sys.argv[2:], Path.cwd().resolve())
        os.execv(command[0], command)
    try:
        sys.exit(main())
    except Exception as exc:
        if output.exists():
            b.save(output / "error.json", {"status": "INFRA_ERROR", "error": str(exc)})
        raise
