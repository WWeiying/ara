#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Optional

from ara_verify.catalog import ManifestError, load_catalog
from ara_verify.dependencies import DependencyError, sync_dependencies
from ara_verify.environment import doctor, has_errors
from ara_verify.random_rvv import (
    RandomRvvOptions,
    RandomRvvRunOptions,
    generate_random_rvv,
    run_random_rvv,
)
from ara_verify.runner import RegressionRunner, RunOptions, default_output
from ara_verify.rvv_replay import (
    RvvReplayOptions,
    failed_random_cases,
    replay_failed_cases,
)
from ara_verify.rvv_postprocess import RvvPostprocessOptions, postprocess_existing_run


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_MANIFEST = SCRIPT_DIR / "suites.json"


def _default_spike() -> Path:
    configured = os.environ.get("SPIKE")
    if configured:
        return Path(configured)
    candidates = (
        REPO_ROOT.parent / "riscv-isa-sim" / "build" / "spike",
        REPO_ROOT / "install" / "riscv-isa-sim" / "bin" / "spike",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ara functional verification regression runner")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor_parser = subparsers.add_parser("doctor", help="check tools, dependencies, and configurations")
    doctor_parser.add_argument("--config", default="default")
    doctor_parser.add_argument("--no-vcs", action="store_true")

    deps_parser = subparsers.add_parser(
        "deps", help="synchronize RTL dependencies and locked verification tools"
    )
    deps_parser.add_argument("--dry-run", action="store_true")

    list_parser = subparsers.add_parser("list", help="list discovered tests or suites")
    list_parser.add_argument("--suite")
    list_parser.add_argument("--suites", action="store_true")

    random_parser = subparsers.add_parser(
        "generate-rvv", help="generate deterministic RVV 1.0 random assembly"
    )
    random_parser.add_argument("--test", default="ara_dsa_rvv1_smoke")
    random_parser.add_argument(
        "--iterations", type=int,
        help="override the profile iteration count; omitted uses testlist.yaml",
    )
    random_parser.add_argument("--seed", type=int, default=1)
    random_parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "out" / "rvv1-generated")
    random_parser.add_argument("--simulator", default="vcs")
    random_parser.add_argument("--dry-run", action="store_true")

    random_run_parser = subparsers.add_parser(
        "run-rvv", help="generate, compile, and execute RVV 1.0 tests on Spike and Ara"
    )
    random_run_parser.add_argument("--test", default="ara_dsa_rvv1_smoke")
    random_run_parser.add_argument(
        "--iterations", type=int,
        help="override the profile iteration count; omitted uses testlist.yaml",
    )
    random_run_parser.add_argument("--seed", type=int, default=1)
    random_run_parser.add_argument(
        "--output", type=Path, default=SCRIPT_DIR / "out" / "rvv1-random"
    )
    random_run_parser.add_argument("--simulator", default="vcs")
    random_run_parser.add_argument("--simv", type=Path, required=True)
    random_run_parser.add_argument(
        "--generator-simv", type=Path,
        help="reuse a precompiled VCS riscv-dv instruction-generator executable",
    )
    random_run_parser.add_argument(
        "--spike", type=Path,
        default=_default_spike(),
    )
    random_run_parser.add_argument("--timeout", type=int, default=120)
    random_run_parser.add_argument("--spike-timeout", type=int, default=30)
    random_run_parser.add_argument("--watchdog-cycles", type=int, default=10000)
    random_run_parser.add_argument(
        "--vector-signature", action="store_true",
        help="compare all vector-register bytes at test exit using a deterministic signature",
    )
    random_run_parser.add_argument(
        "--vector-checkpoints", "--per-vector-instruction",
        dest="vector_checkpoints", action="store_true",
        help=(
            "diagnostically compare v0-v31 and vector/FP control CSRs after every generated "
            "RVV instruction; implies deterministic exit signature checking"
        ),
    )
    random_run_parser.add_argument(
        "--checkpoint-index", action="append", type=int, default=[],
        help=(
            "instrument only the selected one-based static RVV instruction index; "
            "repeatable and requires --vector-checkpoints"
        ),
    )
    random_run_parser.add_argument(
        "--checkpoint-mask-register", type=int,
        help=(
            "use vcpop.m checkpoints for one mask register instead of storing all vector "
            "registers; requires --vector-checkpoints"
        ),
    )
    random_run_parser.add_argument(
        "--vector-commit-compare", action="store_true",
        help=(
            "non-intrusively compare accepted Ara VRF writebacks with the matching "
            "Spike vector-instruction post-state"
        ),
    )
    random_run_parser.add_argument(
        "--vector-commit-index", type=int,
        help=(
            "compare only one one-based dynamic write-producing vector request; "
            "requires --vector-commit-compare"
        ),
    )
    random_run_parser.add_argument("--dry-run", action="store_true")

    replay_parser = subparsers.add_parser(
        "replay-failed-rvv",
        help="replay failed random-test ELFs with commit and accepted-VRF comparison",
    )
    replay_parser.add_argument("--summary", type=Path, required=True)
    replay_parser.add_argument(
        "--case", action="append", default=[],
        help="replay only this exact case name; repeatable",
    )
    replay_parser.add_argument("--output", type=Path, required=True)
    replay_parser.add_argument("--simv", type=Path, required=True)
    replay_parser.add_argument("--spike", type=Path, default=_default_spike())
    replay_parser.add_argument("--jobs", type=int, default=1)
    replay_parser.add_argument("--timeout", type=int, default=900)
    replay_parser.add_argument("--spike-timeout", type=int, default=900)
    replay_parser.add_argument("--watchdog-cycles", type=int, default=1000000)

    postprocess_parser = subparsers.add_parser(
        "postprocess-rvv",
        help="rebuild strict comparison results from an already completed RVV run",
    )
    postprocess_parser.add_argument("--output", type=Path, required=True)
    postprocess_parser.add_argument(
        "--case", action="append", default=[], help="process only this artifact case"
    )
    postprocess_parser.add_argument(
        "--force", action="store_true", help="recompute cases that already have result.json"
    )

    run_parser = subparsers.add_parser("run", help="build and run a regression suite")
    run_parser.add_argument("suite", nargs="?", default="smoke")
    run_parser.add_argument("--test", action="append", default=[], help="exact test or glob; overrides suite")
    run_parser.add_argument("--config", default="default")
    run_parser.add_argument("--jobs", type=int, default=1)
    run_parser.add_argument("--seed", type=int, default=1)
    run_parser.add_argument(
        "--timeout", type=int,
        help="override the manifest timeout for every selected test",
    )
    run_parser.add_argument("--output", type=Path)
    run_parser.add_argument("--simv", type=Path, help="reuse an existing VCS executable")
    run_parser.add_argument("--skip-build", action="store_true")
    run_parser.add_argument("--build-only", action="store_true")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--commit-trace", action="store_true", help="record RVFI and CVXIF events")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _parser().parse_args(argv)

    if args.command == "doctor":
        checks = doctor(REPO_ROOT, args.config, require_vcs=not args.no_vcs)
        for check in checks:
            print(f"[{check.level:5}] {check.name:28} {check.detail}")
        return 1 if has_errors(checks) else 0

    if args.command == "deps":
        try:
            actions = sync_dependencies(REPO_ROOT, dry_run=args.dry_run)
        except DependencyError as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        for name, action in actions:
            print(f"{name:24} {action}")
        return 0

    if args.command == "generate-rvv":
        try:
            return generate_random_rvv(RandomRvvOptions(
                repo_root=REPO_ROOT,
                test=args.test,
                iterations=args.iterations,
                seed=args.seed,
                output=args.output.resolve(),
                simulator=args.simulator,
                dry_run=args.dry_run,
            ))
        except (DependencyError, OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    if args.command == "run-rvv":
        generation = RandomRvvOptions(
            repo_root=REPO_ROOT,
            test=args.test,
            iterations=args.iterations,
            seed=args.seed,
            output=args.output.resolve(),
            simulator=args.simulator,
            dry_run=args.dry_run,
        )
        try:
            return run_random_rvv(RandomRvvRunOptions(
                generation=generation,
                simv=args.simv.resolve(),
                spike=args.spike.resolve(),
                generator_simv=(args.generator_simv.resolve()
                                if args.generator_simv is not None else None),
                timeout_s=args.timeout,
                watchdog_cycles=args.watchdog_cycles,
                spike_timeout_s=args.spike_timeout,
                vector_signature=args.vector_signature,
                vector_checkpoints=args.vector_checkpoints,
                checkpoint_indices=tuple(args.checkpoint_index),
                checkpoint_mask_register=args.checkpoint_mask_register,
                vector_commit_compare=args.vector_commit_compare,
                vector_commit_index=args.vector_commit_index,
            ))
        except (DependencyError, OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1

    if args.command == "replay-failed-rvv":
        try:
            cases = failed_random_cases(args.summary.resolve(), args.case)
            results = replay_failed_cases(RvvReplayOptions(
                output=args.output.resolve(),
                simv=args.simv.resolve(),
                spike=args.spike.resolve(),
                timeout_s=args.timeout,
                spike_timeout_s=args.spike_timeout,
                watchdog_cycles=args.watchdog_cycles,
                jobs=args.jobs,
            ), cases)
        except (OSError, RuntimeError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        return 0 if all(result["status"] == "PASS" for result in results) else 1

    if args.command == "postprocess-rvv":
        try:
            results = postprocess_existing_run(RvvPostprocessOptions(
                output=args.output.resolve(), cases=tuple(args.case), force=args.force,
            ), REPO_ROOT)
        except (OSError, ValueError) as error:
            print(f"error: {error}", file=sys.stderr)
            return 1
        return 0 if results and all(result["status"] == "PASS" for result in results) else 1

    try:
        catalog = load_catalog(REPO_ROOT, args.manifest.resolve())
    except ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if args.command == "list":
        if args.suites:
            for name, spec in catalog.suites.items():
                print(f"{name:18} {len(catalog.resolve_suite(name)):4}  {spec.get('description', '')}")
            return 0
        tests = catalog.resolve_suite(args.suite) if args.suite else list(catalog.tests.values())
        for test in tests:
            print(f"{test.name:36} {test.kind:5} {test.binary.relative_to(REPO_ROOT)}")
        return 0

    if args.jobs <= 0:
        print("error: --jobs must be positive", file=sys.stderr)
        return 2
    if args.timeout is not None and args.timeout <= 0:
        print("error: --timeout must be positive", file=sys.stderr)
        return 2
    try:
        tests = catalog.select(args.test) if args.test else catalog.resolve_suite(args.suite)
    except ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    output = args.output or default_output(REPO_ROOT, "selected" if args.test else args.suite)
    options = RunOptions(
        repo_root=REPO_ROOT,
        output_root=output,
        config=args.config,
        jobs=args.jobs,
        seed=args.seed,
        dry_run=args.dry_run,
        build_only=args.build_only,
        skip_build=args.skip_build,
        simv=args.simv,
        commit_trace=args.commit_trace,
        timeout_s=args.timeout,
    )
    runner = RegressionRunner(options, tests, [str(Path(sys.argv[0]).resolve()), *(argv or sys.argv[1:])])
    try:
        results = runner.run()
    except (OSError, RuntimeError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.build_only:
        print(f"build artifacts: {output.resolve()}")
        return 0
    print(f"results: {output.resolve()}")
    return 1 if any(result.status not in {"PASS", "DRY_RUN"} for result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
