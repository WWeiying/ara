#!/usr/bin/env python3
"""Bind generated RVV stimulus coverage to frozen final-image replay inputs."""

import argparse
import json
from pathlib import Path

from ara_verify.stimulus_coverage import collect_stimulus_coverage, merge_stimulus_coverage
from run_verilator_coverage import sha256


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
PROFILES = ("loadstore", "integer", "arithmetic", "fp32", "fp64", "mixed", "vtype_churn")
SOURCE = Path("/home/wangwy/openproject/ara_dsa_masked_indexed_fix/verification/out")


def audit_profile(profile: str, final_run: Path, prior_summary: Path) -> dict:
    manifest = json.loads((final_run / "replay_manifest.json").read_text())
    prior = json.loads(prior_summary.read_text())
    result = {"profile": profile, "final_run": str(final_run),
              "prior_summary": str(prior_summary), "issues": []}
    if len(manifest) != 10 or len(prior) != 10:
        result["issues"].append("expected ten frozen inputs in each manifest")
        return result
    prior_by_name = {row["name"]: row for row in prior}
    if len(prior_by_name) != 10 or {row["name"] for row in manifest} != set(prior_by_name):
        result["issues"].append("case names differ between replay and prior summary")
        return result

    sources = []
    hashes = {}
    generator_roots = set()
    for row in manifest:
        name = row["name"]
        source_elf = Path(prior_by_name[name]["source_elf"])
        generator = source_elf.parents[2]
        source = generator / "asm_test" / f"{name}.S"
        replay_elf = Path(row["elf"])
        final_elf = final_run / "tests" / name / "input.elf"
        try:
            original_hash = sha256(source_elf)
            if (row["elf"] != prior_by_name[name]["elf"] or
                    original_hash != sha256(replay_elf) or
                    original_hash != sha256(final_elf)):
                result["issues"].append(f"ELF provenance mismatch: {name}")
            if not source.is_file():
                result["issues"].append(f"generated assembly missing: {name}")
            sources.append(source)
            hashes[name] = {"elf_sha256": original_hash, "asm_sha256": sha256(source)}
            generator_roots.add(generator)
        except OSError as error:
            result["issues"].append(f"{name}: {error}")
    if result["issues"]:
        return result
    if len(generator_roots) != 1:
        result["issues"].append("cases came from different generator runs")
        return result

    generated = next(iter(generator_roots))
    recorded_path = generated / "stimulus_coverage.json"
    recorded = json.loads(recorded_path.read_text())
    recomputed = collect_stimulus_coverage(sorted(sources), recorded["test"])
    if recorded != recomputed:
        result["issues"].append("recorded stimulus coverage differs from generated assembly")
    result.update({"generator": str(generated),
                   "generator_coverage_sha256": sha256(recorded_path),
                   "case_hashes": hashes, "coverage": recomputed})
    final_audit = final_run / "independent_audit.json"
    if final_audit.is_file():
        audited = json.loads(final_audit.read_text())
        policy = audited.get("policy", {})
        if (audited.get("status") != "PASS" or audited.get("case_count") != 10 or
                any(policy.get(key) is not True for key in
                    ("require_trace", "require_vector", "require_full_match"))):
            result["issues"].append("final-image strict differential audit is not PASS")
        audited_cases = audited.get("cases", [])
        if (len(audited_cases) != 10 or
                {case.get("name") for case in audited_cases} != set(hashes)):
            result["issues"].append("final-image audit case inventory differs")
        else:
            for case in audited_cases:
                name = case["name"]
                directory = final_run / "tests" / name
                inputs = json.loads((directory / "inputs.json").read_text())
                binary = inputs.get("binary", {})
                if (case.get("status") != "PASS" or case.get("errors") or
                        case.get("artifact_dir") != str(directory) or
                        binary.get("path") != str(directory / "input.elf") or
                        binary.get("sha256") != hashes[name]["elf_sha256"]):
                    result["issues"].append(f"final-image audit input mismatch: {name}")
        result["final_audit_sha256"] = sha256(final_audit)
    else:
        result["issues"].append("final-image strict differential audit is pending")
    return result


def run(profiles: tuple[str, ...]) -> dict:
    results = []
    report_paths = []
    for profile in profiles:
        final_run = OUT / f"integrated-random-{profile}-10seed-20260925-01"
        prior = SOURCE / f"final-mask-bundle-{profile}-10seed-20260925-01/summary.json"
        record = audit_profile(profile, final_run, prior)
        results.append(record)
        if not record["issues"]:
            report_paths.append(Path(record["generator"]) / "stimulus_coverage.json")
    merged = merge_stimulus_coverage(report_paths) if report_paths else None
    return {"status": "PASS" if all(not row["issues"] for row in results) else "INCOMPLETE",
            "profile_count": len(results), "audited_profile_count": len(report_paths),
            "profiles": results, "merged": merged,
            "scope": "generated assembly census bound by identical frozen ELF hashes; "
                     "not runtime instruction execution coverage"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profiles", nargs="+", choices=PROFILES, default=PROFILES)
    args = parser.parse_args()
    if args.output.exists():
        parser.error(f"output exists: {args.output}")
    result = run(tuple(args.profiles))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"{result['status']}: {result['audited_profile_count']}/{result['profile_count']} profiles")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
