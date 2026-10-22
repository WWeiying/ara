#!/usr/bin/env python3
"""Build the merged product RTL without replacing its FPGA-related changes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

VERIFY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(VERIFY / "verification"))
from ara_verify.model import TestCase
from ara_verify.runner import RegressionRunner, RunOptions

NAMES = (
    "rvv:vsegment_emul_edges", "rvv:villegal_segment_recovery",
    "rvv:vslide1up_vredand", "rvv:vrvv_gap29_fp16_rne_m4",
    "rvv:vfredmax_boundary", "app:qbs_akv_handoff_smoke",
)


def save(path, record):
    path.write_text(json.dumps(record, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root, output = args.root.resolve(strict=True), args.output.resolve(strict=True)
    save(output / "smoke.status.json", {"status": "BUILDING"})
    reference = VERIFY / "verification/out/full-recollection-20260928-02/plan.json"
    plan = json.loads(reference.read_text())
    selected = [next(c for c in plan["cases"] if c.get("source_name") == n and c["kind"] == "directed")
                for n in NAMES]
    for case in selected:
        if hashlib.sha256(Path(case["frozen_elf"]).read_bytes()).hexdigest() != case["elf_sha256"]:
            raise RuntimeError("Frozen regression ELF changed")
    original = json.loads((VERIFY / "verification/out/fp16-repaired-coverage-20260928-02/compile.command.json").read_text())
    command = []
    for arg in original["command"]:
        if arg.startswith("buildpath="):
            arg = "buildpath=" + str(output / "build")
        elif arg.startswith("sim_dir="):
            arg = "sim_dir=" + str(output / "sim")
        elif arg.startswith("verify_extra_sources="):
            # Keep verification observers in the sole verification worktree;
            # the product DUT and all dependency sources come from root.
            pass
        else:
            arg = arg.replace(str(VERIFY), str(root))
        command.append(arg)
    save(output / "compile.command.json", {"command": command, "cwd": str(root)})
    with (output / "compile.log").open("w") as stream:
        subprocess.run(command, cwd=root, stdout=stream, stderr=subprocess.STDOUT,
                       check=True, timeout=7200)
    save(output / "smoke.status.json", {"status": "RUNNING", "cases": list(NAMES), "jobs": 6})
    tests = [TestCase(**dict(c["directed_test"], binary=Path(c["frozen_elf"]))) for c in selected]
    options = RunOptions(repo_root=root, output_root=output / "regression", config="default",
                         jobs=6, seed=1, dry_run=False, build_only=False, skip_build=True,
                         simv=output / "sim/simv", commit_trace=True, timeout_s=600)
    results = RegressionRunner(options, tests, sys.argv).run()
    if len(results) != len(tests) or any(r.status != "PASS" for r in results):
        save(output / "smoke.status.json", {"status": "FAIL", "cases": [r.status for r in results]})
        return 1
    env = dict(os.environ, PYTHONPATH=str(VERIFY / "verification"))
    subprocess.run([sys.executable, str(VERIFY / "verification/verify.py"), "audit",
                    "--run", str(output / "regression"), "--require-trace",
                    "--output", str(output / "independent_audit.json")], check=True, env=env)
    before = json.loads((output / "merge.before.json").read_text())
    for name in before["protected_files"]:
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != before["before"][name]:
            raise RuntimeError("Protected main-branch file changed during merge")
    save(output / "smoke.status.json", {"status": "PASS", "cases": list(NAMES),
                                        "protected_main_changes": "UNCHANGED",
                                        "scope": "six representative cases; not a 600-case replay"})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        if "--output" in sys.argv:
            target = Path(sys.argv[sys.argv.index("--output") + 1])
            if target.is_dir():
                save(target / "smoke.status.json", {"status": "ERROR", "reason": str(error)})
        raise
