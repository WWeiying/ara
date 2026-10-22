#!/usr/bin/env python3
"""Run the requirement-driven verification gates and record signoff evidence.

This is an orchestration layer, not a simulator.  It deliberately distinguishes
PASS, FAIL, and NOT_CONFIGURED so a missing VCS run, Linux console log, or FPGA
board result cannot be mistaken for a successful signoff.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence

from fpga.check_run import check_manifest
from fpga.check_soc_linux import audit as audit_soc_linux
from linux.check_boot import DEFAULT_MARKERS, USERSPACE_MARKERS, check_boot, check_stage_result
from ara_verify.plan import PlanError, load_plan
from ara_verify.uvm_coverage import collect as collect_uvm_coverage


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY = REPO_ROOT / "verification" / "verify.py"
CAMPAIGN = REPO_ROOT / "verification" / "run_full_campaign.py"
QBS_PAIR_AUDIT = REPO_ROOT / "verification" / "qbs" / "audit_paired_campaign.py"
COVERAGE_MERGE_AUDIT = REPO_ROOT / "verification" / "coverage" / "audit_merged.py"
PACKAGE_TEST = REPO_ROOT / "hardware" / "fpga" / "vcu118" / "tests" / "test_package.py"
PACKAGE_ROOT = REPO_ROOT / "hardware" / "fpga" / "ara_dsa_vcu118"
PLAN_PATH = REPO_ROOT / "verification" / "verification_plan.json"


def now() -> str:
    return datetime.now().astimezone().isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_signoff_policy() -> tuple[Optional[Dict[str, object]], Optional[str], Optional[str]]:
    try:
        plan = load_plan(PLAN_PATH)
    except PlanError as error:
        return None, None, str(error)
    policy = plan.get("fpga_signoff", {})
    required = policy.get("required_stages") if isinstance(policy, dict) else None
    if not isinstance(required, list) or not required or any(
        not isinstance(name, str) or not name for name in required
    ):
        return None, None, "verification plan fpga_signoff.required_stages is invalid"
    return plan, sha256(PLAN_PATH), None


def git_provenance() -> Dict[str, object]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        return result.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "branch": run("branch", "--show-current"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Ara DSA verification gates without accepting missing evidence"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--stage", action="append", choices=("preflight", "differential", "uvm", "qbs-pairs", "coverage-integrity", "linux", "fpga", "all"),
        default=None, help="gate to run; repeatable, or use all (default: preflight)",
    )
    parser.add_argument("--simv", type=Path, help="VCS executable for the full differential campaign")
    parser.add_argument("--spike", type=Path, help="Ara-compatible Spike executable")
    parser.add_argument("--generator-simv", type=Path)
    parser.add_argument("--uvm-audit", type=Path, action="append", default=[],
                        help="real-DUT UVM audit JSON; repeat for all cases in one image")
    parser.add_argument("--qbs-pair-manifest", type=Path,
                        help="QBS/RVV plus AKV/RVV real-DUT pair manifest to re-audit")
    parser.add_argument("--coverage-merge-audit", type=Path,
                        help="frozen Verilator merged audit.json to re-audit (integrity only)")
    parser.add_argument("--coverage-minimum-cases", type=int, default=3,
                        help="minimum passing cases in the merged coverage report")
    parser.add_argument("--linux-log", type=Path)
    parser.add_argument("--linux-soc-run", type=Path,
                        help="completed frozen run_soc_smoke.py Linux RTL directory")
    parser.add_argument(
        "--linux-stage-result", type=Path,
        help="stage_result.json emitted by linux/run_stage.py",
    )
    parser.add_argument(
        "--linux-stage", choices=("qemu", "rtl", "board"),
        help="expected stage when --linux-stage-result is provided",
    )
    parser.add_argument("--linux-artifact", action="append", default=[], metavar="NAME=PATH")
    parser.add_argument(
        "--linux-boot-profile", choices=("vcu118", "userspace"), default="vcu118",
        help="boot markers for the historical board init or isolated userspace test init",
    )
    parser.add_argument(
        "--linux-userspace-marker", action="append", default=[],
        help="marker emitted only after the RVV fallback/QBS/AKV user-space smoke passes",
    )
    parser.add_argument("--fpga-manifest", type=Path)
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--random-jobs", type=int, default=4)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--spike-timeout", type=int, default=300)
    parser.add_argument("--watchdog-cycles", type=int, default=1_000_000)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--strict", action="store_true",
        help="enforce clean source provenance and final-evidence requirements",
    )
    return parser.parse_args(argv)


def _command_record(command: Sequence[object], log: Path, status: str, returncode: Optional[int],
                    started: str, completed: Optional[str] = None, error: str = "") -> Dict[str, object]:
    return {
        "command": [str(item) for item in command],
        "log": str(log),
        "status": status,
        "returncode": returncode,
        "started_at": started,
        "completed_at": completed,
        "error": error,
    }


def run_command(name: str, command: Sequence[object], log: Path, dry_run: bool) -> Dict[str, object]:
    started = now()
    log.parent.mkdir(parents=True, exist_ok=True)
    if dry_run:
        return {"name": name, **_command_record(command, log, "NOT_RUN", None, started)}
    with log.open("w", encoding="utf-8") as stream:
        stream.write("$ " + " ".join(str(item) for item in command) + "\n")
        stream.flush()
        # The unit suite imports both the verification package and helper
        # scripts from ``verification/``.  Make the gate independent
        # of the caller's current PYTHONPATH while preserving any user paths.
        env = os.environ.copy()
        verification_path = str(REPO_ROOT / "verification")
        env["PYTHONPATH"] = os.pathsep.join(
            path for path in (verification_path, env.get("PYTHONPATH", "")) if path
        )
        result = subprocess.run(
            [str(item) for item in command], cwd=REPO_ROOT,
            stdout=stream, stderr=subprocess.STDOUT, check=False, env=env,
        )
    status = "PASS" if result.returncode == 0 else "FAIL"
    return {"name": name, **_command_record(command, log, status, result.returncode, started, now())}


def not_configured(name: str, reason: str, log: Path) -> Dict[str, object]:
    return {
        "name": name,
        "command": [],
        "log": str(log),
        "status": "NOT_CONFIGURED",
        "returncode": None,
        "started_at": now(),
        "completed_at": now(),
        "error": reason,
    }


def parse_artifacts(values: Sequence[str]) -> Dict[str, Path]:
    artifacts: Dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--linux-artifact requires NAME=PATH: {value}")
        name, path = value.split("=", 1)
        if not name or not path:
            raise ValueError(f"--linux-artifact requires NAME=PATH: {value}")
        artifacts[name] = Path(path)
    return artifacts


def run_python_check(name: str, payload: Mapping[str, object], log: Path, output: Path,
                     dry_run: bool) -> Dict[str, object]:
    """Persist an in-process checker result using the same gate record format."""
    started = now()
    log.parent.mkdir(parents=True, exist_ok=True)
    result_path = output / f"{name}.json"
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = str(payload.get("status", "FAIL")) if not dry_run else "NOT_RUN"
    log.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "name": name,
        "command": ["in-process-check", name],
        "log": str(log),
        "result": str(result_path),
        "status": status,
        "returncode": 0 if status == "PASS" else 1,
        "started_at": started,
        "completed_at": now(),
        "error": "",
    }


def stage_names(args: argparse.Namespace) -> List[str]:
    selected = set(args.stage or ["preflight"])
    if "all" in selected:
        return ["preflight", "differential", "uvm", "qbs-pairs", "coverage-integrity", "linux", "fpga"]
    return [name for name in ("preflight", "differential", "uvm", "qbs-pairs", "coverage-integrity", "linux", "fpga") if name in selected]


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    stages = stage_names(args)
    if not stages:
        raise SystemExit("at least one --stage is required")
    if args.jobs <= 0 or args.random_jobs <= 0:
        raise SystemExit("--jobs and --random-jobs must be positive")
    if args.coverage_minimum_cases <= 0:
        raise SystemExit("--coverage-minimum-cases must be positive")

    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise SystemExit(f"output directory must be new and empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    gates: List[Dict[str, object]] = []
    strict_mode = args.strict or "all" in set(args.stage or [])
    plan, plan_hash, plan_error = load_signoff_policy()
    required_fpga_tests = None
    if plan is not None:
        raw_policy = plan.get("fpga_signoff", {})
        if isinstance(raw_policy, dict):
            raw_required = raw_policy.get("required_stages")
            if isinstance(raw_required, list):
                required_fpga_tests = [str(item) for item in raw_required]
    if strict_mode and plan_error:
        gates.append({
            "name": "signoff_policy",
            "command": ["load_plan", str(PLAN_PATH)],
            "log": str(output / "logs" / "signoff_policy.log"),
            "status": "FAIL",
            "returncode": 1,
            "started_at": now(),
            "completed_at": now(),
            "error": plan_error,
        })

    provenance = git_provenance()
    if strict_mode and provenance["worktree_dirty"]:
        gates.append({
            "name": "source_cleanliness",
            "command": ["git", "status", "--porcelain"],
            "log": str(output / "logs" / "source_cleanliness.log"),
            "status": "FAIL",
            "returncode": 1,
            "started_at": now(),
            "completed_at": now(),
            "error": "strict signoff requires a clean parent worktree",
        })

    if "preflight" in stages:
        python = sys.executable
        preflight_commands = [
            ("environment", [python, VERIFY, "doctor", "--no-vcs"]),
            ("plan", [python, VERIFY, "plan", "--json"]),
            ("unit_tests", [python, "-m", "pytest", "-q", "verification/tests"]),
            ("fpga_package", [python, PACKAGE_TEST, PACKAGE_ROOT]),
        ]
        for name, command in preflight_commands:
            gates.append(run_command(name, command, output / "logs" / f"{name}.log", args.dry_run))

    if "differential" in stages:
        if args.simv is None or args.spike is None:
            gates.append(not_configured(
                "differential", "--simv and --spike are required for differential campaign",
                output / "logs" / "differential.log",
            ))
        elif not args.simv.is_file() or not args.spike.is_file():
            gates.append(not_configured(
                "differential", f"simv or Spike is missing: {args.simv}, {args.spike}",
                output / "logs" / "differential.log",
            ))
        elif args.dry_run:
            command = [sys.executable, CAMPAIGN, "--simv", args.simv,
                       "--spike", args.spike, "--output", output / "campaign",
                       "--jobs", args.jobs, "--random-jobs", args.random_jobs,
                       "--seed", args.seed, "--timeout", args.timeout,
                       "--spike-timeout", args.spike_timeout,
                       "--watchdog-cycles", args.watchdog_cycles, "--dry-run"]
            if args.generator_simv:
                command.extend(["--generator-simv", args.generator_simv])
            gates.append(run_command("differential", command, output / "logs" / "differential.log", True))
        else:
            command = [sys.executable, CAMPAIGN, "--simv", args.simv,
                       "--spike", args.spike, "--output", output / "campaign",
                       "--jobs", args.jobs, "--random-jobs", args.random_jobs,
                       "--seed", args.seed, "--timeout", args.timeout,
                       "--spike-timeout", args.spike_timeout,
                       "--watchdog-cycles", args.watchdog_cycles]
            if args.generator_simv:
                command.extend(["--generator-simv", args.generator_simv])
            gates.append(run_command("differential", command, output / "logs" / "differential.log", False))
            if gates[-1]["status"] == "PASS":
                audit_command = [
                    sys.executable, VERIFY, "audit",
                    "--run", output / "campaign",
                    "--output", output / "campaign" / "verification_audit.json",
                    "--require-trace", "--require-vector", "--require-coverage",
                    "--require-full-match",
                ]
                gates.append(run_command(
                    "differential_audit",
                    audit_command,
                    output / "logs" / "differential_audit.log",
                    False,
                ))

    if "uvm" in stages:
        if not args.uvm_audit:
            gates.append(not_configured(
                "uvm", "at least one --uvm-audit is required for real-DUT coverage",
                output / "logs" / "uvm.log",
            ))
        else:
            payload = collect_uvm_coverage(args.uvm_audit)
            gates.append(run_python_check("uvm", payload, output / "logs" / "uvm.log",
                                          output, args.dry_run))

    if "qbs-pairs" in stages:
        if args.qbs_pair_manifest is None or not args.qbs_pair_manifest.is_file():
            gates.append(not_configured(
                "qbs-pairs", "--qbs-pair-manifest must name an existing manifest",
                output / "logs" / "qbs-pairs.log",
            ))
        else:
            gates.append(run_command(
                "qbs-pairs",
                [sys.executable, QBS_PAIR_AUDIT, "--manifest",
                 args.qbs_pair_manifest.resolve(), "--output", output / "qbs_pairs.json"],
                output / "logs" / "qbs-pairs.log", args.dry_run,
            ))

    if "coverage-integrity" in stages:
        if args.coverage_merge_audit is None or not args.coverage_merge_audit.is_file():
            gates.append(not_configured(
                "coverage-integrity",
                "--coverage-merge-audit must name an existing merged audit.json",
                output / "logs" / "coverage-integrity.log",
            ))
        else:
            gates.append(run_command(
                "coverage-integrity",
                [sys.executable, COVERAGE_MERGE_AUDIT, "--audit",
                 args.coverage_merge_audit.resolve(), "--minimum-cases",
                 args.coverage_minimum_cases, "--report", output / "coverage_integrity.json"],
                output / "logs" / "coverage-integrity.log", args.dry_run,
            ))

    if "linux" in stages:
        if args.linux_soc_run is not None and (
                args.linux_stage_result is not None or args.linux_stage is not None or
                args.linux_userspace_marker or args.linux_boot_profile != "vcu118"):
            gates.append(not_configured(
                "linux", "--linux-soc-run cannot be combined with stage-result options",
                output / "logs" / "linux.log",
            ))
        elif args.linux_soc_run is not None and not args.linux_soc_run.is_dir():
            gates.append(not_configured(
                "linux", "--linux-soc-run must name an existing frozen run directory",
                output / "logs" / "linux.log",
            ))
        elif args.linux_soc_run is not None:
            payload = audit_soc_linux(args.linux_soc_run)
            gates.append(run_python_check("linux", payload, output / "logs" / "linux.log",
                                          output, args.dry_run))
        elif args.linux_stage_result is None:
            gates.append(not_configured(
                "linux",
                "strict Linux signoff requires --linux-stage-result; --linux-log is diagnostic only",
                output / "logs" / "linux.log",
            ))
        elif args.linux_stage is None or not args.linux_userspace_marker:
            gates.append(not_configured(
                "linux",
                "--linux-stage and at least one --linux-userspace-marker are required",
                output / "logs" / "linux.log",
            ))
        else:
            payload = check_stage_result(
                args.linux_stage_result,
                expected_stage=args.linux_stage,
                required_markers=[
                    *(USERSPACE_MARKERS if args.linux_boot_profile == "userspace"
                      else DEFAULT_MARKERS),
                    *args.linux_userspace_marker,
                ],
            )
            gates.append(run_python_check("linux", payload, output / "logs" / "linux.log", output, args.dry_run))

    if "fpga" in stages:
        if args.fpga_manifest is None:
            gates.append(not_configured(
                "fpga", "--fpga-manifest is required for board evidence",
                output / "logs" / "fpga.log",
            ))
        else:
            payload = check_manifest(
                args.fpga_manifest,
                require_signoff=True,
                required_tests=required_fpga_tests,
            )
            gates.append(run_python_check("fpga", payload, output / "logs" / "fpga.log", output, args.dry_run))

    statuses = {str(gate["status"]) for gate in gates}
    overall = "PASS" if gates and statuses == {"PASS"} else (
        "DRY_RUN" if args.dry_run else ("FAIL" if "FAIL" in statuses else "INCOMPLETE")
    )
    signoff = {
        "schema_version": 1,
        "status": overall,
        "created_at": now(),
        "completed_at": now(),
        "invocation": [str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])],
        "repo": git_provenance(),
        "verification_plan": {
            "path": str(PLAN_PATH),
            "sha256": plan_hash,
            "load_error": plan_error,
        },
        "stages": stages,
        "gates": gates,
        "policy": {
            "pass_requires_every_selected_gate_pass": True,
            "not_configured_is_not_pass": True,
            "fpga_is_required_for_board_and_long_system_signoff": True,
            "coverage_integrity_does_not_establish_coverage_closure": True,
        },
    }
    (output / "signoff.json").write_text(
        json.dumps(signoff, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": overall, "output": str(output / "signoff.json")}, sort_keys=True))
    return 0 if overall in {"PASS", "DRY_RUN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
