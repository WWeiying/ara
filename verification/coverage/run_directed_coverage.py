#!/usr/bin/env python3
"""Replay independently audited directed RVV cases on one coverage image."""

import argparse
import json
import shutil
import sys
from pathlib import Path

from run_passed_matrix import (
    COVERAGE, ROOT, collect_cases, digest, elf_fit_command, reuse_passed_cases, run,
)


def load_passed_cases(summary_path: Path, audit_path: Path, inputs: Path,
                      term_cycles: int, timeout_s: int,
                      random_source: bool = False) -> list[dict]:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if not isinstance(summary, list) or not summary:
        raise ValueError("directed summary is empty or malformed")
    if (audit.get("status") != "PASS" or audit.get("errors") or
            audit.get("failed_cases") != 0 or
            audit.get("case_count") != len(summary) or
            audit.get("passed_cases") != len(summary)):
        raise ValueError("independent directed audit is not complete PASS")
    if random_source and not all(audit.get("policy", {}).get(key) is True for key in
                                 ("require_complete", "require_full_match", "require_vector")):
        raise ValueError("random source requires independently audited complete vector match")
    audited = {case["name"]: case for case in audit["cases"]}
    if len(audited) != len(summary):
        raise ValueError("directed audit case count or names differ")

    cases = []
    names = set()
    for record in summary:
        name = record["name"]
        source = Path(record["artifact_dir"]).resolve(strict=True)
        case_name = source.name
        if (record.get("status") != "PASS" or
                audited.get(name, {}).get("status") != "PASS" or
                audited[name].get("errors") or
                Path(audited[name]["artifact_dir"]).resolve() != source or
                not case_name.isidentifier() or case_name in names):
            raise ValueError(f"directed case lacks matching PASS audit: {name}")
        names.add(case_name)
        metadata = json.loads((source / "inputs.json").read_text(encoding="utf-8"))
        elf = (source / "input.elf").resolve(strict=True)
        expected_hash = metadata["binary"]["sha256"]
        if Path(metadata["binary"]["path"]).resolve() != elf or digest(elf) != expected_hash:
            raise ValueError(f"directed ELF hash mismatch: {name}")
        console = source / ("rtl_console.log" if random_source else "console.log")
        marker = "Core Test *** SUCCESS ***" if random_source else \
                 "Core Test *** SUCCESS *** (tohost = 0)"
        if marker not in console.read_text(errors="replace"):
            raise ValueError(f"directed self-check marker missing: {name}")
        tohost_addr = None
        if random_source:
            command_record = json.loads((source / "rtl.command.json").read_text(encoding="utf-8"))
            tohost_args = [arg for arg in command_record["command"]
                           if arg.startswith("+COMMIT_TOHOST=")]
            if len(tohost_args) != 1:
                raise ValueError(f"random source needs exactly one COMMIT_TOHOST address: {name}")
            try:
                tohost_addr = int(tohost_args[0].split("=", 1)[1], 16)
            except ValueError as exc:
                raise ValueError(f"invalid COMMIT_TOHOST address: {name}") from exc
            if tohost_addr < 0x80000000 or tohost_addr & 7:
                raise ValueError(f"unaligned or out-of-range COMMIT_TOHOST address: {name}")
        frozen = inputs / f"{case_name}.elf"
        shutil.copyfile(elf, frozen)
        if digest(frozen) != expected_hash:
            raise ValueError(f"frozen directed ELF hash mismatch: {name}")
        cases.append({
            "name": case_name,
            "source_kind": "random_vcs_spike" if random_source else "directed_vcs",
            "source_dir": str(source),
            "source_elf_sha256": expected_hash,
            "source_console_sha256": digest(console),
            "source_command_sha256": digest(source / "rtl.command.json") if random_source else None,
            "frozen_elf": str(frozen),
            "term_cycles": term_cycles,
            "timeout_s": timeout_s,
            "tohost_addr": tohost_addr,
        })
    return cases


def select_cases(cases: list[dict], names: list[str]) -> list[dict]:
    if not names:
        return cases
    requested = set(names)
    available = {case["name"] for case in cases}
    if len(requested) != len(names) or not requested <= available:
        raise ValueError("case names must be unique and present in the audited run")
    return [case for case in cases if case["name"] in requested]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--ram-bytes", type=int, default=2097152)
    parser.add_argument("--term-cycles", type=int, default=100000)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--case-name", action="append", default=[],
                        help="replay only this audited artifact name; repeatable")
    parser.add_argument("--random-source", action="store_true",
                        help="require independently audited full-match VCS/Spike random source")
    parser.add_argument("--reuse-audit", type=Path,
                        help="reuse identical passing cases from this audited same-image merge")
    parser.add_argument("--verilator-coverage", type=Path,
                        default=ROOT / "install/verilator/bin/verilator_coverage")
    args = parser.parse_args()

    output = args.output.resolve()
    output.relative_to(ROOT / "verification/out")
    if output.exists():
        parser.error(f"output must not exist: {output}")
    if args.jobs < 1 or args.timeout < 1 or args.term_cycles < 1:
        parser.error("jobs, timeout and term-cycles must be positive")
    simv = args.simv.resolve(strict=True)
    reporter = args.verilator_coverage.resolve(strict=True)
    source_manifest = args.source_manifest.resolve(strict=True)
    run(sys.executable, str(COVERAGE / "build_provenance.py"),
        "--output", str(source_manifest), "--check")

    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    shutil.copyfile(source_manifest, output / "source_manifest.json")
    source_run = args.summary.resolve(strict=True).parent
    reaudit_path = output / "source_reaudit.json"
    audit_cmd = [sys.executable, str(ROOT / "verification/verify.py"), "audit",
                 "--run", str(source_run), "--require-trace"]
    if args.random_source:
        audit_cmd += ["--require-vector", "--require-full-match"]
    run(*audit_cmd, "--output", str(reaudit_path))
    original_audit = json.loads(args.audit.read_text(encoding="utf-8"))
    fresh_audit = json.loads(reaudit_path.read_text(encoding="utf-8"))
    audit_cases = lambda report: sorted(
        (case["name"], case["status"], case["artifact_dir"])
        for case in report["cases"])
    if (fresh_audit.get("status") != "PASS" or
            fresh_audit.get("errors") or
            audit_cases(fresh_audit) != audit_cases(original_audit)):
        raise ValueError("fresh directed audit differs from the frozen PASS audit")
    cases = load_passed_cases(args.summary, args.audit, inputs,
                              args.term_cycles, args.timeout, args.random_source)
    cases = select_cases(cases, args.case_name)
    if args.reuse_audit:
        cases = reuse_passed_cases(cases, args.reuse_audit.resolve(strict=True), simv)
    provenance = {
        "schema_version": 1,
        "simv": str(simv),
        "simv_sha256": digest(simv),
        "source_manifest_sha256": digest(source_manifest),
        "summary_sha256": digest(args.summary),
        "audit_sha256": digest(args.audit),
        "source_reaudit_sha256": digest(reaudit_path),
        "ram_bytes": args.ram_bytes,
        "cases": cases,
        "reuse_audit": str(args.reuse_audit.resolve()) if args.reuse_audit else None,
        "reuse_audit_sha256": digest(args.reuse_audit) if args.reuse_audit else None,
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run(*elf_fit_command(cases, args.ram_bytes, output))

    results = collect_cases(cases, simv, reporter, output, args.jobs)
    if digest(simv) != provenance["simv_sha256"]:
        raise ValueError("simulator changed during directed coverage collection")
    for result in results:
        if json.loads(result.read_text(encoding="utf-8"))["simv_sha256"] != provenance["simv_sha256"]:
            raise ValueError(f"directed case used a different simulator: {result}")

    merged = output / "merged"
    merge = [sys.executable, str(COVERAGE / "merge_verilator_coverage.py")]
    for result in results:
        merge += ["--case", str(result)]
    run(*merge, "--output", str(merged), "--verilator-coverage", str(reporter),
        "--hierarchy-prefix", "ara_tb_verilator.dut.i_ara_soc",
        "--include-path", "/hardware/src/", "--include-path", "/hardware/deps/cva6/")
    run(sys.executable, str(COVERAGE / "audit_merged.py"),
        "--audit", str(merged / "audit.json"), "--minimum-cases", str(len(results)),
        "--report", str(merged / "independent_audit.json"))
    run(sys.executable, str(COVERAGE / "review_uncovered.py"),
        "--audit", str(merged / "audit.json"), "--minimum-cases", str(len(results)),
        "--output", str(merged / "review.json"))
    run(sys.executable, str(ROOT / "verification/run_signoff.py"),
        "--stage", "coverage-integrity", "--coverage-merge-audit", str(merged / "audit.json"),
        "--coverage-minimum-cases", str(len(results)), "--output", str(merged / "signoff"))
    print(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
