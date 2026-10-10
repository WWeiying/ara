#!/usr/bin/env python3
"""Merge audited final-image coverage matrices without replaying simulation."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from audit_merged import audit
from run_verilator_coverage import sha256


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "verification/out"
MATRICES = (
    ("integrated-coverage-first-matrix-20260925-01", 5),
    ("integrated-coverage-directed-20260925-02", 6),
    ("integrated-coverage-corners-20260925-01", 35),
    ("integrated-coverage-masked-indexed-20260925-01", 3),
)


def source_cases() -> tuple[list[Path], list[dict]]:
    cases = []
    sources = []
    image_hashes = set()
    for name, expected in MATRICES:
        merged = OUT / name / "merged"
        independent_path = merged / "independent_audit.json"
        independent = json.loads(independent_path.read_text(encoding="utf-8"))
        audited = audit(merged / "audit.json", expected)
        if (independent.get("status") != "PASS" or independent.get("case_count") != expected or
                independent.get("merge_audit_sha256") != sha256(merged / "audit.json") or
                audited.get("status") != "PASS" or audited.get("case_count") != expected):
            raise ValueError(f"source matrix is not independently audited PASS: {name}")
        record = json.loads((merged / "audit.json").read_text(encoding="utf-8"))
        image_hashes.add(record["simv_sha256"])
        cases.extend(Path(case["result"]) for case in record["cases"])
        sources.append({"matrix": name, "cases": expected,
                        "independent_audit": str(independent_path),
                        "independent_audit_sha256": sha256(independent_path)})
    if len(image_hashes) != 1 or len(cases) != sum(count for _, count in MATRICES):
        raise ValueError("source matrices differ in simulator identity or case count")
    if len({str(path.resolve()) for path in cases}) != len(cases):
        raise ValueError("same case result appears in multiple matrices")
    return cases, sources


def input_diversity(cases: list[Path]) -> dict:
    by_elf = {}
    for path in cases:
        result = json.loads(path.read_text(encoding="utf-8"))
        elf_hash = result["elf_sha256"]
        if result.get("status") != "PASS" or not elf_hash:
            raise ValueError(f"invalid passing case for input diversity: {path}")
        by_elf.setdefault(elf_hash, []).append(str(path))
    return {"run_count": len(cases), "unique_elf_count": len(by_elf),
            "duplicate_elf_groups": [paths for paths in by_elf.values() if len(paths) > 1]}


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.relative_to(OUT)
    if output.exists():
        parser.error(f"output already exists: {output}")
    cases, sources = source_cases()
    coverage = ROOT / "verification/coverage"
    reporter = ROOT / "install/verilator/bin/verilator_coverage"
    command = [sys.executable, str(coverage / "merge_verilator_coverage.py")]
    for case in cases:
        command.extend(("--case", str(case)))
    run(*command, "--output", str(output), "--verilator-coverage", str(reporter),
        "--hierarchy-prefix", "ara_tb_verilator.dut.i_ara_soc",
        "--include-path", "/hardware/src/", "--include-path", "/hardware/deps/cva6/")
    (output / "source_audits.json").write_text(
        json.dumps({"sources": sources, "case_count": len(cases),
                    "input_diversity": input_diversity(cases)}, indent=2) + "\n",
        encoding="utf-8")
    run(sys.executable, str(coverage / "audit_merged.py"), "--audit", str(output / "audit.json"),
        "--minimum-cases", str(len(cases)), "--report", str(output / "independent_audit.json"))
    run(sys.executable, str(coverage / "review_uncovered.py"), "--audit", str(output / "audit.json"),
        "--minimum-cases", str(len(cases)), "--output", str(output / "review.json"))
    run(sys.executable, str(ROOT / "verification/run_signoff.py"),
        "--stage", "coverage-integrity", "--coverage-merge-audit", str(output / "audit.json"),
        "--coverage-minimum-cases", str(len(cases)), "--output", str(output / "signoff"))
    print(f"merged {len(cases)} final-image coverage runs: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
