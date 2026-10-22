"""Audit planned RVV activity dimensions against completed DUT retirements."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache, partial
import hashlib
from itertools import product
import json
from pathlib import Path

from .artifacts import simulation_image
from .dynamic_coverage import audit_case, digest
from .terminal_reaudit import audit as audit_terminal_tohost


ACCEPTED_EVIDENCE = {
    "random_spike_complete_result", "random_spike_complete_reaudit",
    "directed_program_selfcheck",
}
LMUL_EIGHTHS = {"mf8": 1, "mf4": 2, "mf2": 4, "m1": 8,
               "m2": 16, "m4": 32, "m8": 64}


@lru_cache(maxsize=None)
def image_fingerprint(simv: Path) -> tuple[str, int, str | None]:
    components = {
        str(Path(path).relative_to(simv.parent)): value
        for path, value in simulation_image(simv).items()
    }
    config = simv.parent / "simulator.conf"
    config_hash = digest(config) if config.is_file() else None
    components["simulator.conf"] = config_hash
    fingerprint = hashlib.sha256(json.dumps(
        components, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()
    return fingerprint, len(components), config_hash


def case_image_identity(case: Path) -> dict:
    command_file = case / "rtl.command.json"
    if command_file.is_file():
        command = json.loads(command_file.read_text(encoding="utf-8"))["command"]
        if not isinstance(command, list) or not command:
            raise ValueError(f"RTL command is missing its simulator: {case}")
        simv = Path(command[0])
        provenance = "invocation_path_rehashed"
    else:
        inputs = json.loads((case / "inputs.json").read_text(encoding="utf-8"))
        recorded = inputs["simv"]
        simv = Path(recorded["path"])
        if simulation_image(simv) != recorded["image_sha256"]:
            raise ValueError(f"recorded simulator image changed: {case}")
        provenance = "recorded_input_manifest"
    if not simv.is_file():
        raise ValueError(f"simulator image is missing: {simv}")
    fingerprint, component_count, config_hash = image_fingerprint(simv)
    return {"fingerprint": fingerprint, "simv_path": str(simv.resolve()),
            "provenance": provenance, "component_count": component_count,
            "config_sha256": config_hash}


def legal_type(sew: str, lmul: str, elen_bits: int) -> bool:
    if not sew.startswith("e") or not sew[1:].isdigit() or lmul not in LMUL_EIGHTHS:
        raise ValueError(f"invalid coverage type: {sew}/{lmul}")
    sew_bits = int(sew[1:])
    return sew_bits <= elen_bits and LMUL_EIGHTHS[lmul] * elen_bits >= sew_bits * 8


def reaudit_prefix_case(record: dict, readelf: Path) -> dict:
    if record["evidence_kind"] != "random_spike_prefix":
        return record
    checked = audit_terminal_tohost(Path(record["case"]), readelf)
    if checked["status"] != "PASS":
        raise ValueError(f"terminal re-audit failed for {record['case']}: {checked['issues']}")
    return {**record, "evidence_kind": "random_spike_complete_reaudit",
            "comparison_status": checked["comparison"]["status"],
            "terminal_reaudit": {"status": checked["status"],
                                 "input_sha256": checked["input_sha256"],
                                 "simv_image_sha256": checked["simv_image_sha256"]}}


def audit_cases(paths: list[Path], objdump: Path, jobs: int) -> list[dict]:
    if jobs < 1:
        raise ValueError("jobs must be positive")
    resolved = [path.resolve() for path in paths]
    if jobs == 1:
        return [audit_case(path, objdump) for path in resolved]
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        return list(pool.map(partial(audit_case, objdump=objdump), resolved))


def summarize_activity(cases: list[dict], plan: dict) -> dict:
    dimensions = plan["coverage_dimensions"]
    elen_bits = plan["coverage_constraints"]["elen_bits"]
    if not isinstance(elen_bits, int) or elen_bits <= 0:
        raise ValueError("coverage_constraints.elen_bits must be positive")
    targets = {
        "sew": dimensions["sew"],
        "lmul": dimensions["lmul"],
        "memory_mode": dimensions["memory_mode"],
        "policy_pair": [f"{tail}/{mask}" for tail in dimensions["tail_policy"]
                        for mask in dimensions["mask_policy"]],
    }
    cross_combinations = list(product(dimensions["sew"], dimensions["lmul"],
                                      dimensions["tail_policy"], dimensions["mask_policy"]))
    cross_targets = ["/".join(values) for values in cross_combinations
                     if legal_type(values[0], values[1], elen_bits)]
    excluded_illegal = ["/".join(values) for values in cross_combinations
                        if not legal_type(values[0], values[1], elen_bits)]
    if any(not isinstance(values, list) or not values or
           len(values) != len(set(values)) for values in targets.values()):
        raise ValueError("coverage plan contains empty or duplicate activity bins")
    seen_cases = set()
    accepted = []
    excluded = []
    counts = {axis: Counter() for axis in targets}
    case_hits = {axis: {name: [] for name in names} for axis, names in targets.items()}
    cross_counts: Counter[str] = Counter()
    cross_case_hits = {name: [] for name in cross_targets}
    unknown_policy = 0
    unknown_type = 0
    runtime_inferred_type = 0
    writeback_checked_bytes = 0
    writeback_skipped_bytes = 0
    writeback_cases = []
    image_groups: dict[str, dict] = {}
    unknown_images = []
    for case in cases:
        name = case["case"]
        if name in seen_cases:
            raise ValueError(f"duplicate case: {name}")
        seen_cases.add(name)
        if case["status"] != "PASS" or case["evidence_kind"] not in ACCEPTED_EVIDENCE:
            excluded.append({"case": name, "evidence_kind": case["evidence_kind"]})
            continue
        accepted.append({"case": name, "evidence_kind": case["evidence_kind"],
                         "sha256": case["sha256"],
                         **({"terminal_reaudit": case["terminal_reaudit"]}
                            if "terminal_reaudit" in case else {})})
        image = case.get("image_identity")
        if image is None:
            unknown_images.append(name)
        else:
            group = image_groups.setdefault(image["fingerprint"], {
                "cases": [], "simv_paths": [], "provenance": [],
                "component_count": image["component_count"],
                "config_sha256": image["config_sha256"],
            })
            group["cases"].append(name)
            if image["simv_path"] not in group["simv_paths"]:
                group["simv_paths"].append(image["simv_path"])
            if image["provenance"] not in group["provenance"]:
                group["provenance"].append(image["provenance"])
        unknown_policy += case["retired_nonconfig_with_unknown_policy"]
        unknown_type += case["configurations_without_static_type"]
        runtime_inferred_type += case.get("configurations_inferred_from_committed_gpr", 0)
        writeback = case.get("vector_writeback_comparison") or {}
        if writeback.get("status") == "PASS":
            writeback_cases.append(name)
            writeback_checked_bytes += writeback["compared_bytes"]
            writeback_skipped_bytes += writeback["skipped_unknown_bytes"]
        observed = {
            "sew": Counter(), "lmul": Counter(),
            "memory_mode": Counter(case["memory_modes"]),
            "policy_pair": Counter(case.get(
                "resolved_policy_for_retired_nonconfig",
                case["statically_selected_policy_for_retired_nonconfig"])),
        }
        observed_cross = case.get("resolved_sew_lmul_policy", {})
        unexpected_cross = set(observed_cross) - set(cross_targets)
        if unexpected_cross:
            raise ValueError(f"{name} has unplanned sew/lmul/policy bins: {sorted(unexpected_cross)}")
        cross_counts.update(observed_cross)
        for bin_name, value in observed_cross.items():
            if value > 0:
                cross_case_hits[bin_name].append(name)
        for pair, count in case["sew_lmul_known"].items():
            sew, lmul = pair.split("/", 1)
            observed["sew"][sew] += count
            observed["lmul"][lmul] += count
        for axis, values in observed.items():
            unexpected = set(values) - set(targets[axis])
            if unexpected:
                raise ValueError(f"{name} has unplanned {axis} bins: {sorted(unexpected)}")
            counts[axis].update(values)
            for bin_name, value in values.items():
                if value > 0:
                    case_hits[axis][bin_name].append(name)
    axes = {}
    for axis, names in targets.items():
        bins = {name: {"retired_instructions": counts[axis][name],
                       "case_count": len(case_hits[axis][name]),
                       "cases": case_hits[axis][name]} for name in names}
        axes[axis] = {
            "observed_bins": sum(bool(counts[axis][name]) for name in names),
            "target_bins": len(names),
            "unobserved_bins": [name for name in names if not counts[axis][name]],
            "single_case_bins": [name for name in names if len(case_hits[axis][name]) == 1],
            "bins": bins,
        }
    cross_bins = {name: {"retired_instructions": cross_counts[name],
                         "case_count": len(cross_case_hits[name]),
                         "cases": cross_case_hits[name]} for name in cross_targets}
    axes_observed = bool(accepted) and all(not axis["unobserved_bins"] for axis in axes.values())
    cross_observed = bool(accepted) and all(cross_counts[name] for name in cross_targets)
    return {
        "status": "ACTIVITY_OBSERVED" if axes_observed and cross_observed else "INCOMPLETE",
        "axis_status": "ACTIVITY_OBSERVED" if axes_observed else "INCOMPLETE",
        "scope": "DUT-retired activity only; not functional or RTL code coverage signoff",
        "accepted_cases": accepted,
        "excluded_cases": excluded,
        "unresolved_policy_instructions": unknown_policy,
        "configurations_without_static_type": unknown_type,
        "configurations_inferred_from_committed_gpr": runtime_inferred_type,
        "unresolved_vtype_configurations": unknown_type - runtime_inferred_type,
        "vector_writeback_evidence": {
            "scope": "destination writeback byte positions with at least one compared bit; skipped positions and stores are not functional coverage",
            "case_count": len(writeback_cases), "cases": writeback_cases,
            "compared_bytes": writeback_checked_bytes,
            "skipped_unknown_bytes": writeback_skipped_bytes,
        },
        "image_groups": {
            "status": ("SINGLE_IMAGE" if len(image_groups) == 1 and not unknown_images
                       else "MIXED_OR_UNKNOWN"),
            "scope": "currently available complete VCS image; random runs rehash the invocation path, directed runs also verify their recorded input manifest",
            "group_count": len(image_groups),
            "unknown_cases": unknown_images,
            "groups": {key: {**group, "case_count": len(group["cases"])}
                       for key, group in sorted(image_groups.items())},
        },
        "axes": axes,
        "crosses": {"sew_lmul_policy": {
            "status": "OBSERVED" if cross_observed else "INCOMPLETE",
            "scope": "DUT-retired activity, including directed selfchecks; not a functional cross-coverage claim",
            "observed_bins": sum(bool(cross_counts[name]) for name in cross_targets),
            "target_bins": len(cross_targets),
            "excluded_illegal_bins": excluded_illegal,
            "elen_bits": elen_bits,
            "unobserved_bins": [name for name in cross_targets if not cross_counts[name]],
            "bins": cross_bins,
        }},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=1,
                        help="parallel offline disassembly and trace analysis")
    parser.add_argument("--reaudit-prefix", action="store_true",
                        help="recompute complete tohost and vector match before counting PREFIX cases")
    parser.add_argument("--require-same-image", action="store_true",
                        help="reject a matrix that mixes VCS images or lacks image identity")
    parser.add_argument("--readelf", type=Path,
                        default=Path(__file__).resolve().parents[2] /
                        "install/riscv-gcc/bin/riscv64-unknown-elf-readelf")
    parser.add_argument("--plan", type=Path,
                        default=Path(__file__).resolve().parents[1] / "verification_plan.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    if args.jobs < 1:
        parser.error("jobs must be positive")
    cases = audit_cases(args.case, args.objdump.resolve(), args.jobs)
    for record, case in zip(cases, args.case):
        record["image_identity"] = case_image_identity(case.resolve())
    if args.reaudit_prefix:
        cases = [reaudit_prefix_case(case, args.readelf.resolve()) for case in cases]
    report = summarize_activity(cases, plan)
    if args.require_same_image and (
        report["image_groups"]["status"] != "SINGLE_IMAGE" or
        any(group["config_sha256"] is None
            for group in report["image_groups"]["groups"].values())
    ):
        parser.error("single complete VCS image is required")
    report["plan"] = {"path": str(args.plan.resolve()), "sha256": digest(args.plan)}
    report["inputs"] = {
        "cases": [str(case.resolve()) for case in args.case],
        "objdump": str(args.objdump.resolve()),
        "readelf": str(args.readelf.resolve()) if args.reaudit_prefix else None,
        "reaudit_prefix": args.reaudit_prefix,
        "require_same_image": args.require_same_image,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(f"RVV activity matrix: {len(report['accepted_cases'])} accepted cases, "
          f"{len(report['excluded_cases'])} excluded, {report['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
