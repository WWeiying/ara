"""Report static stimulus bins from strictly passing random RVV cases only."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ara_verify.stimulus_coverage import collect_stimulus_coverage


AXES = {
    "sew": "sew",
    "lmul": "lmul",
    "tail_policy": "tail_policy",
    "mask_policy": "mask_policy",
    "memory_mode": "memory_modes",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def audit(runs: list[Path], plan_path: Path,
          source_runs: list[Path] | None = None) -> dict:
    if source_runs is not None and len(source_runs) != len(runs):
        raise ValueError("each replay run needs one source run")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    sources = []
    accepted = []
    rejected = []
    seen = set()
    for index, run in enumerate(runs):
        summary = run / "summary.json"
        source_run = source_runs[index] if source_runs is not None else run
        replay_cases = None
        if source_runs is not None:
            independent = json.loads((run / "independent_audit.json").read_text())
            if independent.get("status") != "PASS":
                raise ValueError(f"replay independent audit is not PASS: {run}")
            replay = json.loads((run / "replay_manifest.json").read_text())
            replay_cases = {row["name"]: row for row in replay}
            if len(replay_cases) != len(replay):
                raise ValueError(f"duplicate replay case: {run}")
        for row in json.loads(summary.read_text(encoding="utf-8")):
            name = row["name"]
            if name in seen:
                raise ValueError(f"duplicate random case: {name}")
            seen.add(name)
            result_path = run / "tests" / name / "result.json"
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result["status"] != row["status"]:
                raise ValueError(f"summary/result status disagreement: {name}")
            vector_result = result.get("vector_commit", {})
            vector_pass = (result.get("vector_commit_compare") is True or
                           vector_result.get("status") == "PASS")
            if (row["status"] != "PASS" or
                    result.get("comparison", {}).get("status") != "TERMINAL_MATCH" or
                    not vector_pass or
                    result.get("trace", {}).get("status") != "VALID"):
                rejected.append({"name": name, "status": row["status"],
                                 "result": str(result_path)})
                continue
            source = source_run / "asm_test" / f"{name}.S"
            if not source.is_file():
                raise ValueError(f"missing passing stimulus: {source}")
            if replay_cases is not None:
                frozen_elf = source_run / "tests" / name / "input.elf"
                replay_elf = run / "tests" / name / "input.elf"
                if (name not in replay_cases or
                        Path(replay_cases[name]["elf"]).resolve() != frozen_elf.resolve() or
                        digest(frozen_elf) != digest(replay_elf)):
                    raise ValueError(f"replayed ELF differs from source case: {name}")
            sources.append(source)
            accepted.append({"name": name, "source": str(source),
                             "source_sha256": digest(source),
                             "elf_sha256": digest(run / "tests" / name / "input.elf"),
                             "result": str(result_path),
                             "result_sha256": digest(result_path)})
    activity = collect_stimulus_coverage(sources, "strictly-passing-random-rvv")
    dimensions = plan["coverage_dimensions"]
    observed = activity["aggregate"]
    missing = {
        target: sorted(set(dimensions[target]) - set(observed[source_axis]))
        for target, source_axis in AXES.items()
    }
    return {
        "kind": "static_source_activity_only",
        "dut_code_coverage": "not_measured",
        "dynamic_execution_coverage": "not_measured",
        "restart_and_operand_layout": "not_measured_by_static_parser",
        "plan": str(plan_path.resolve()),
        "plan_sha256": digest(plan_path),
        "runs": [str(run.resolve()) for run in runs],
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "accepted": accepted,
        "rejected": rejected,
        "instruction_count": activity["vector_instruction_count"],
        "aggregate": observed,
        "missing_planned_bins": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, action="append", required=True)
    parser.add_argument("--source-run", type=Path, action="append",
                        help="matching original run containing replayed ELF and assembly")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    report = audit(args.run, args.plan, args.source_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"{report['accepted_count']} accepted, {report['rejected_count']} rejected: "
          f"{args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
