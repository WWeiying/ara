#!/usr/bin/env python3
"""Summarize final-source RTL signoff without accepting missing evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from ara_verify.artifacts import simulation_image
from ara_verify.coverage_matrix import image_fingerprint
from ara_verify.vcs_source_manifest import collect


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification/out"
VCS = OUT / "integrated-vcs-image-20260925-01/sim/simv"
PROFILES = ("loadstore", "integer", "arithmetic", "fp32", "fp64", "mixed", "vtype_churn")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def evidence(path: Path, check, expected: str) -> dict:
    entry = {"path": str(path), "expected": expected}
    if not path.is_file():
        return {**entry, "status": "PENDING", "reason": "evidence missing"}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        entry["sha256"] = digest(path)
        passed, detail = check(value)
    except (OSError, ValueError, KeyError, TypeError) as error:
        return {**entry, "status": "FAIL", "reason": str(error)}
    return {**entry, "status": "PASS" if passed else "FAIL", "detail": detail}


def count_audit(value: dict, count: int) -> tuple[bool, str]:
    matched = (value.get("status") == "PASS" and value.get("case_count") == count and
               value.get("passed_cases") == count and value.get("failed_cases") == 0 and
               not value.get("errors"))
    return matched, f"{value.get('passed_cases', 0)}/{count} cases; status={value.get('status')}"


def image_check(value: dict) -> tuple[bool, str]:
    rows = collect(Path(value["filelist"]), Path(value["repo_root"]),
                   [Path(name) for name in value["extra_sources"]])
    saved = {row["path"]: row["sha256"] for row in value["files"]}
    current = {row["path"]: row["sha256"] for row in rows}
    changed = sorted(name for name in saved.keys() | current.keys()
                     if saved.get(name) != current.get(name))
    return not changed and len(rows) >= 450, f"{len(rows)} sources; {len(changed)} changed"


def audited_cases(path: Path, count: int, image: dict[str, str],
                  required_policy: tuple[str, ...] = ("require_trace",)) -> dict:
    def check(value: dict) -> tuple[bool, str]:
        passed, detail = count_audit(value, count)
        policy = value.get("policy", {})
        if any(policy.get(name) is not True for name in required_policy):
            return False, f"{detail}; audit policy is weaker than required"
        cases = value.get("cases", [])
        if len(cases) != count:
            return False, f"{detail}; audit lists {len(cases)} cases"
        for case in cases:
            directory = Path(case["artifact_dir"])
            inputs = json.loads((directory / "inputs.json").read_text(encoding="utf-8"))
            binary = inputs["binary"]
            elf = directory / "input.elf"
            if (case.get("status") != "PASS" or case.get("errors") or
                    binary["path"] != str(elf) or digest(elf) != binary["sha256"] or
                    inputs["simv"]["path"] != str(VCS) or
                    inputs["simv"]["image_sha256"] != image):
                return False, f"{detail}; frozen input/image mismatch: {case.get('name')}"
        return passed, detail

    return evidence(path, check, f"{count} audited cases on the final VCS image")


def check_pair_campaign(value: dict, plan: dict, image: dict[str, str]) -> tuple[bool, str]:
    cases = plan.get("cases", [])
    passed = (value.get("status") == "PASS" and value.get("image_match") is True and
              not value.get("issues") and value.get("qbs_pair_count") == 10 and
              not value.get("missing_qbs_formats") and len(value.get("pairs", [])) == 11 and
              plan.get("status") == "PASS" and len(cases) == 22 and
              all(case.get("status") == "PASS" for case in cases) and
              plan.get("simv") == str(VCS) and plan.get("simv_sha256") == digest(VCS))
    expected_components = {str(Path(path).relative_to(VCS.parent)): sha
                           for path, sha in image.items()}
    for pair in value.get("pairs", {}).values():
        if pair.get("vcs_image_components") != expected_components:
            return False, "paired simulator image differs from final image"
    for case in cases:
        if digest(Path(case["elf"])) != case["elf_sha256"]:
            return False, f"frozen ELF changed: {case['name']}/{case['mode']}"
        if any(digest(Path(path)) != sha for path, sha in
               case.get("app_inputs_sha256", {}).items()):
            return False, f"frozen model input changed: {case['name']}/{case['mode']}"
        if "assembly" in case and digest(Path(case["assembly"])) != case["assembly_sha256"]:
            return False, f"frozen assembly changed: {case['name']}/{case['mode']}"
    return passed, f"{sum(case.get('status') == 'PASS' for case in cases)}/22 runs; image_match={value.get('image_match')}"


def check_coverage_closure(value: dict, review_path: Path) -> tuple[bool, str]:
    review = json.loads(review_path.read_text(encoding="utf-8"))
    required = {"axi_errors", "mmu_exceptions", "rvv_restart",
                "qbs_akv_fallback", "resource_backpressure"}
    decisions = value.get("risk_decisions", {})
    valid = (value.get("schema_version") == 1 and value.get("status") == "PASS" and
             value.get("review_sha256") == digest(review_path) and
             value.get("points_total") == review.get("points_total") and
             value.get("points_missed") == review.get("points_missed") and
             isinstance(decisions, dict) and set(decisions) == required and
             all(isinstance(item, dict) and item.get("disposition") in
                 {"COVERED", "JUSTIFIED_EXCLUSION"} and
                 isinstance(item.get("evidence"), str) and item["evidence"].strip() and
                 isinstance(item.get("rationale"), str) and item["rationale"].strip()
                 for item in decisions.values()) and
             isinstance(value.get("reviewer"), str) and value["reviewer"].strip())
    return bool(valid), (f"{len(decisions) if isinstance(decisions, dict) else 0}/"
                         f"{len(required)} risk areas reviewed; "
                         f"{review.get('points_missed')} missed points")


def check_incremental_coverage(value: dict, directory: Path,
                               coverage_simv: Path) -> tuple[bool, str]:
    merge_path = directory / "audit.json"
    merged = json.loads(merge_path.read_text(encoding="utf-8"))
    review = json.loads((directory / "review.json").read_text(encoding="utf-8"))
    cases = merged.get("cases", [])
    qbs_result = (directory.parent / "integrated-qbs-control-coverage-20260925-01" /
                  "app_qbs_control_smoke/result.json")
    valid = (value.get("status") == "PASS" and value.get("case_count") == 13 and
             not value.get("issues") and value.get("simv_sha256") == digest(coverage_simv) and
             value.get("merge_audit_sha256") == digest(merge_path) and
             merged.get("status") == "PASS" and len(cases) == 13 and
             any(Path(case.get("result", "")) == qbs_result for case in cases) and
             review.get("status") == "REVIEW_REQUIRED" and
             review.get("case_count") == 13 and
             review.get("merge_audit_sha256") == digest(merge_path))
    return valid, (f"{value.get('case_count')}/13 audited replays; "
                   f"{merged.get('hierarchy_coverage', {}).get('points_hit')} DUT points hit; "
                   "uncovered points not signed off")


def check_random_stimulus(value: dict) -> tuple[bool, str]:
    profiles = value.get("profiles", [])
    merged = value.get("merged") or {}
    aggregate = merged.get("aggregate") or {}
    valid = (value.get("status") == "PASS" and value.get("profile_count") == 7 and
             value.get("audited_profile_count") == 7 and len(profiles) == 7 and
             merged.get("source_count") == 70 and
             merged.get("vector_instruction_count", 0) > 0 and
             set(aggregate.get("sew", {})) == {"e8", "e16", "e32", "e64"} and
             set(aggregate.get("lmul", {})) ==
             {"mf8", "mf4", "mf2", "m1", "m2", "m4", "m8"})
    for profile in profiles:
        try:
            final_run = Path(profile["final_run"])
            generated = Path(profile["generator"])
            if (profile.get("issues") or
                    digest(final_run / "independent_audit.json") !=
                    profile["final_audit_sha256"] or
                    digest(generated / "stimulus_coverage.json") !=
                    profile["generator_coverage_sha256"] or
                    len(profile["case_hashes"]) != 10):
                valid = False
            for name, hashes in profile["case_hashes"].items():
                if (digest(final_run / "tests" / name / "input.elf") !=
                        hashes["elf_sha256"] or
                        digest(generated / "asm_test" / f"{name}.S") !=
                        hashes["asm_sha256"]):
                    valid = False
        except (KeyError, OSError, ValueError, TypeError):
            valid = False
    return bool(valid), (f"{merged.get('source_count')}/70 frozen stimuli; "
                         f"{merged.get('vector_instruction_count')} generated vector instructions; "
                         "policy scope is deterministic tu/mu")


def check_rvv_activity(value: dict) -> tuple[bool, str]:
    axes = value.get("axes", {})
    expected = {"sew": 4, "lmul": 7, "memory_mode": 7, "policy_pair": 4}
    cross = value.get("sew_lmul_policy", {})
    valid = (value.get("status") == "ACTIVITY_OBSERVED" and
             value.get("case_count") == 71 and
             value.get("random_case_count") == 70 and
             value.get("directed_case_count") == 1 and
             VCS.is_file() and value.get("image_fingerprint") == image_fingerprint(VCS)[0] and
             set(axes) == set(expected) and
             all(axes[name].get("target_bins") == count and
                 axes[name].get("observed_bins") == count and
                 not axes[name].get("unobserved_bins")
                 for name, count in expected.items()) and
             cross.get("target_bins") == 88 and cross.get("observed_bins") == 88 and
             not cross.get("unobserved_bins"))
    for label in ("random", "policy"):
        try:
            valid &= digest(Path(value[f"{label}_report"])) == value[f"{label}_report_sha256"]
        except (KeyError, OSError, ValueError, TypeError):
            valid = False
    return bool(valid), (f"71 DUT-retired cases; "
                         f"{cross.get('observed_bins', 0)}/88 legal type/policy bins; "
                         "not RTL code coverage")


def collect_report() -> dict:
    gates = {}
    image = simulation_image(VCS) if VCS.is_file() else {}
    gates["source_image"] = evidence(
        VCS.parent / "vcs_source_manifest.json", image_check,
        "at least 450 unchanged final-source build inputs")
    if not image:
        gates["source_image"]["status"] = "FAIL"
        gates["source_image"]["reason"] = "final VCS executable missing"
    for label, run, count in (
        ("rvv_corners", "integrated-rvv-corners-20260925-02", 35),
        ("rvv_reductions", "integrated-rvv-reductions-20260925-01", 18),
        ("rvv_failure_regression", "integrated-rvv-failure-regression-20260925-01", 14),
        ("rvv_masked_indexed", "integrated-rvv-masked-indexed-20260925-01", 3),
    ):
        gates[label] = audited_cases(OUT / run / "verification_audit_directed.json", count, image)
    for profile in PROFILES:
        gates[f"random_{profile}"] = audited_cases(
            OUT / f"integrated-random-{profile}-10seed-20260925-01/independent_audit.json",
            10, image, ("require_trace", "require_vector", "require_full_match"))
    gates["random_stimulus"] = evidence(
        OUT / "integrated-random-stimulus-audit-20260925-02.json",
        check_random_stimulus,
        "70 generated stimuli bound to final frozen ELFs and strict differential audits")
    gates["rvv_activity"] = evidence(
        OUT / "integrated-rvv-activity-union-20260925-01.json",
        check_rvv_activity,
        "71 final-image retired traces cover legal RVV types, policies and memory modes")

    uvm = OUT / "integrated-uvm-3case-signoff-20260925-01"
    def check_uvm(value: dict) -> tuple[bool, str]:
        runs = value.get("runs", [])
        valid = (value.get("status") == "PASS" and value.get("run_count") == 3 and
                 len(value.get("bin_hits", {})) == 24 and not value.get("missing_bins") and
                 not value.get("errors") and len(value.get("closed_images", [])) == 1 and
                 len(runs) == 3)
        for run in runs:
            audit = json.loads(Path(run["audit"]).read_text(encoding="utf-8"))
            valid &= audit.get("status") == "PASS" and audit.get("simv_sha256") == digest(VCS)
        signoff = json.loads((uvm / "signoff.json").read_text(encoding="utf-8"))
        valid &= signoff.get("status") == "PASS"
        return valid, f"{len(value.get('bin_hits', {}))}/24 bins; {len(runs)} final-image runs"

    gates["uvm"] = evidence(
        uvm / "uvm.json", check_uvm,
        "24 required protocol bins on one final VCS image")
    def check_pairs(value: dict) -> tuple[bool, str]:
        plan = json.loads((OUT / "integrated-final-qbs-akv-pairs-20260925-01/plan.json")
                          .read_text(encoding="utf-8"))
        return check_pair_campaign(value, plan, image)

    gates["qbs_akv_pairs"] = evidence(
        OUT / "integrated-final-qbs-akv-pairs-20260925-01/audit.json",
        check_pairs,
        "10 QBS/RVV and one AKV/RVV real-data pairs")

    coverage_simv = OUT / "integrated-verilator-coverage-20260925-01/build/verilator/Vara_tb_verilator"
    def coverage_check(value: dict, count: int, directory: Path) -> tuple[bool, str]:
        merge = Path(value["merge_audit"])
        signoff = json.loads((directory / "merged/signoff/signoff.json").read_text(encoding="utf-8"))
        passed = (value.get("status") == "PASS" and value.get("case_count") == count and
                  not value.get("issues") and coverage_simv.is_file() and
                  value.get("simv_sha256") == digest(coverage_simv) and
                  value.get("merge_audit_sha256") == digest(merge) and
                  signoff.get("status") == "PASS")
        return passed, f"{value.get('case_count')} cases; status={value.get('status')}"

    for label, run, count in (
        ("coverage_first", "integrated-coverage-first-matrix-20260925-01", 5),
        ("coverage_directed", "integrated-coverage-directed-20260925-02", 6),
        ("coverage_corners", "integrated-coverage-corners-20260925-01", 35),
        ("coverage_masked_indexed", "integrated-coverage-masked-indexed-20260925-01", 3),
    ):
        directory = OUT / run
        gates[label] = evidence(
            directory / "merged/independent_audit.json",
            lambda value, count=count, directory=directory: coverage_check(value, count, directory),
            f"{count} cases with merged Verilator DUT code coverage")

    incremental_coverage = OUT / "integrated-coverage-pass13-qbs-control-20260925-01"
    gates["coverage_incremental_integrity"] = evidence(
        incremental_coverage / "independent_audit.json",
        lambda value: check_incremental_coverage(value, incremental_coverage, coverage_simv),
        "13 passing Verilator replays with independent integrity audit; not coverage closure")

    global_coverage = OUT / "integrated-coverage-global-20260925-01"
    def check_global_coverage(value: dict) -> tuple[bool, str]:
        merged = json.loads((global_coverage / "audit.json").read_text(encoding="utf-8"))
        sources = json.loads((global_coverage / "source_audits.json").read_text(encoding="utf-8"))
        review = json.loads((global_coverage / "review.json").read_text(encoding="utf-8"))
        diversity = sources.get("input_diversity", {})
        valid = (value.get("status") == "PASS" and value.get("case_count") == 49 and
                 not value.get("issues") and value.get("merge_audit_sha256") ==
                 digest(global_coverage / "audit.json") and
                 value.get("simv_sha256") == digest(coverage_simv) and
                 merged.get("status") == "PASS" and
                 sources.get("case_count") == 49 and len(sources.get("sources", [])) == 4 and
                 diversity.get("run_count") == 49 and
                 isinstance(diversity.get("unique_elf_count"), int) and
                 0 < diversity["unique_elf_count"] <= 49 and
                 review.get("case_count") == 49 and
                 review.get("merge_audit_sha256") == digest(global_coverage / "audit.json"))
        return valid, (f"{value.get('case_count')}/49 runs; "
                       f"{diversity.get('unique_elf_count')} unique ELFs; "
                       f"DUT points={review.get('points_total')}")

    gates["coverage_global"] = evidence(
        global_coverage / "independent_audit.json", check_global_coverage,
        "49 final-image runs merged with intact DUT coverage evidence")
    gates["coverage_closure"] = evidence(
        global_coverage / "closure.json",
        lambda value: check_coverage_closure(value, global_coverage / "review.json"),
        "reviewed risk areas and justified uncovered points")

    linux = OUT / "integrated-linux-soc-compile-20260925-01"
    gates["linux_fast_prereq"] = audited_cases(
        OUT / "integrated-linux-fast-prereq-built-20260925-01/independent_audit.json",
        6, image,
        ("require_trace",))
    gates["linux_boot"] = evidence(
        linux / "independent_boot_audit.json",
        lambda value: (value.get("status") == "PASS", f"status={value.get('status')}"),
        "final-source SoC Linux init and RVV userspace markers")
    gates["store_b_error"] = evidence(
        OUT / "integrated-store-b-error/independent_audit.json",
        lambda value: (value.get("status") == "PASS" and value.get("case_count", 0) >= 1,
                       f"status={value.get('status')}; cases={value.get('case_count', 0)}"),
        "AXI B error causes precise vector-store architectural fault")

    statuses = {row["status"] for row in gates.values()}
    status = "FAIL" if "FAIL" in statuses else "INCOMPLETE" if "PENDING" in statuses else "PASS"
    git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=False,
                         text=True, capture_output=True)
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           cwd=ROOT, check=False, text=True, capture_output=True)
    return {"schema_version": 1, "status": status, "source_commit": git.stdout.strip(),
            "source_worktree_dirty": bool(dirty.stdout.strip()),
            "source_manifest_sha256": digest(VCS.parent / "vcs_source_manifest.json")
            if (VCS.parent / "vcs_source_manifest.json").is_file() else None,
            "vcs_simv": str(VCS), "vcs_simv_sha256": digest(VCS) if VCS.is_file() else None,
            "gates": gates}


def render_markdown(report: dict) -> str:
    lines = ["# Ara RTL verification signoff", "",
             f"Overall: **{report['status']}**", "",
             f"Source commit: `{report['source_commit']}`",
             f"Tracked worktree changes: `{report.get('source_worktree_dirty', 'unknown')}`",
             f"Build source manifest SHA-256: `{report.get('source_manifest_sha256')}`",
             f"Final VCS image: `{report['vcs_simv']}`",
             f"Image SHA-256: `{report['vcs_simv_sha256']}`", "",
             "| Gate | Status | Evidence | Detail |", "| --- | --- | --- | --- |"]
    for name, gate in report["gates"].items():
        detail = gate.get("reason", gate.get("detail", gate["expected"]))
        detail = str(detail).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| `{name}` | {gate['status']} | `{gate['path']}` | {detail} |")
    lines.extend(("", "A PASS requires every gate to pass on the final RTL image. "
                  "A passing directed test, QEMU run, or old-image result cannot waive a pending gate.", ""))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error(f"output exists: {output}")
    markdown = args.markdown_output.resolve() if args.markdown_output else None
    if markdown and markdown.exists():
        parser.error(f"Markdown output exists: {markdown}")
    report = collect_report()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if markdown:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(render_markdown(report), encoding="utf-8")
    print(f"{report['status']}: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
