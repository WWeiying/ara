#!/usr/bin/env python3
"""Replay audited Verilator inputs on one instrumented image and merge coverage."""

import argparse
import concurrent.futures
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from audit_merged import audit as audit_coverage


ROOT = Path(__file__).resolve().parents[2]
COVERAGE = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def run(*argv: str) -> None:
    subprocess.run(argv, cwd=ROOT, check=True)


def prepare_case(case: dict, inputs: Path) -> dict:
    name = case["name"]
    source = ROOT / case["source_result"]
    record = json.loads(source.read_text(encoding="utf-8"))
    source_kind = case.get("source_kind", "verilator")
    if source_kind == "verilator":
        if record.get("status") != "PASS" or record.get("self_check_pass") is not True:
            raise ValueError(f"source case is not a passing self-check: {source}")
        elf = Path(record["elf"])
        if digest(source.parent / "coverage.dat") != record["coverage_sha256"]:
            raise ValueError(f"source coverage hash mismatch: {source}")
    elif source_kind == "uvm":
        if record.get("status") != "PASS" or record.get("issues"):
            raise ValueError(f"source UVM case did not pass: {source}")
        elf = source.parent / "work/input.elf"
        log = source.parent / "work/run.vcs.log"
        if digest(log) != record["log_sha256"]:
            raise ValueError(f"source UVM log hash mismatch: {log}")
        if "Core Test *** SUCCESS *** (tohost = 0)" not in log.read_text(errors="replace"):
            raise ValueError(f"source UVM self-check marker is missing: {log}")
    else:
        raise ValueError(f"unknown source_kind {source_kind!r}: {source}")
    if digest(elf) != record["elf_sha256"]:
        raise ValueError(f"source ELF hash mismatch: {elf}")
    frozen = inputs / f"{name}.elf"
    shutil.copyfile(elf, frozen)
    if digest(frozen) != record["elf_sha256"]:
        raise ValueError(f"frozen ELF hash mismatch: {frozen}")
    return {
        "name": name,
        "source_kind": source_kind,
        "source_result": str(source),
        "source_result_sha256": digest(source),
        "source_elf": str(elf),
        "elf_sha256": record["elf_sha256"],
        "frozen_elf": str(frozen),
        "term_cycles": case["term_cycles"],
        "timeout_s": case["timeout_s"],
    }


def run_case(case: dict, simv: Path, reporter: Path, output: Path) -> Path:
    if case.get("reuse_result"):
        return Path(case["reuse_result"])
    target = output / case["name"]
    command = [sys.executable, str(COVERAGE / "run_verilator_coverage.py"),
        "--simv", str(simv), "--elf", case["frozen_elf"],
        "--output", str(target), "--verilator-coverage", str(reporter),
        "--term-cycles", str(case["term_cycles"]),
        "--timeout", str(case["timeout_s"])]
    if case.get("tohost_addr") is not None:
        command += ["--tohost-addr", f"0x{case['tohost_addr']:016x}"]
    run(*command)
    result = target / "result.json"
    if json.loads(result.read_text(encoding="utf-8")).get("status") != "PASS":
        raise ValueError(f"new-image coverage case did not pass: {result}")
    return result


def reuse_passed_cases(cases: list[dict], audit_path: Path, simv: Path) -> list[dict]:
    """Reuse audited, completed executions only when the exact input contract matches."""
    checked = audit_coverage(audit_path)
    if checked["status"] != "PASS":
        raise ValueError(f"reuse audit failed: {checked.get('issues')}")
    previous = json.loads(audit_path.read_text(encoding="utf-8"))
    image_hash = digest(simv)
    if previous["simv_sha256"] != image_hash:
        raise ValueError("reuse audit uses a different simulator image")
    available = {}
    for record in previous["cases"]:
        result_path = Path(record["result"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        key = (result["elf_sha256"], result.get("tohost_addr"))
        available.setdefault(key, str(result_path.resolve()))
    selected = []
    for case in cases:
        item = dict(case)
        key = (digest(Path(case["frozen_elf"])), case.get("tohost_addr"))
        if key in available:
            item["reuse_result"] = available[key]
        selected.append(item)
    return selected


def collect_cases(cases: list[dict], simv: Path, reporter: Path,
                  output: Path, jobs: int) -> list[Path]:
    results = []
    records = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = [pool.submit(run_case, case, simv, reporter, output)
                   for case in cases]
        for case, future in zip(cases, futures):
            result = output / case["name"] / "result.json"
            error = None
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                error = str(exc)
            record = {"name": case["name"], "result": str(result),
                      "status": "PASS" if error is None else "FAIL",
                      "reused": bool(case.get("reuse_result"))}
            if result.is_file():
                record["result_sha256"] = digest(result)
                try:
                    payload = json.loads(result.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    payload = {}
                    error = error or f"cannot read case result: {exc}"
                    record["status"] = "FAIL"
                if error is not None:
                    record["reason"] = payload.get("reason", error)
                    record["sim_log_tail"] = payload.get("sim_log_tail", [])
            elif error is not None:
                record["reason"] = error
            records.append(record)

    failures = [record for record in records if record["status"] == "FAIL"]
    summary = {"status": "FAIL" if failures else "PASS", "cases": records,
               "first_error": failures[0] if failures else None}
    (output / "case_replay.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failures:
        raise RuntimeError(f"coverage case replay failed: {failures[0]['name']}: "
                           f"{failures[0]['reason']}")
    return results


def elf_fit_command(cases: list[dict], ram_bytes: int, output: Path) -> list[str]:
    command = [sys.executable, str(COVERAGE / "check_elf_fit.py")]
    for case in cases:
        command += ["--elf", case["frozen_elf"]]
    return command + ["--ram-bytes", str(ram_bytes), "--ram-word-bytes", "16",
                      "--output", str(output / "elf_fit.json")]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--simv", type=Path, required=True)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--ram-bytes", type=int, default=1048576,
                        help="RAM capacity compiled into the Verilator image (default: 1 MiB)")
    parser.add_argument("--verilator-coverage", type=Path,
                        default=ROOT / "install/verilator/bin/verilator_coverage")
    args = parser.parse_args()

    output = args.output.resolve()
    output.relative_to(ROOT / "verification/out")
    if output.exists():
        parser.error(f"output must not exist: {output}")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.ram_bytes < 16 or args.ram_bytes % 16:
        parser.error("--ram-bytes must be a positive multiple of 16")
    matrix = json.loads(args.matrix.read_text(encoding="utf-8"))
    cases = matrix["cases"]
    names = [case["name"] for case in cases]
    if not cases or len(names) != len(set(names)) or any(not name.isidentifier() for name in names):
        parser.error("matrix needs unique identifier-style case names")
    simv = args.simv.resolve(strict=True)
    reporter = args.verilator_coverage.resolve(strict=True)
    source_manifest = args.source_manifest.resolve(strict=True)
    run(sys.executable, str(COVERAGE / "build_provenance.py"),
        "--output", str(source_manifest), "--check")

    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    shutil.copyfile(source_manifest, output / "source_manifest.json")
    paired_manifest = matrix.get("paired_manifest")
    archived_runner = matrix.get("archived_runner")
    frozen_sources = matrix.get("frozen_sources")
    if frozen_sources is not None:
        frozen_root = (ROOT / frozen_sources).resolve(strict=True)
        run(sys.executable, str(ROOT / "verification/qbs/freeze_paired_sources.py"),
            "--check", "--output", str(frozen_root))
    else:
        frozen_root = None
    if paired_manifest is not None:
        manifest = (ROOT / paired_manifest).resolve(strict=True)
        audit_command = [sys.executable, str(ROOT / "verification/qbs/audit_paired_campaign.py"),
                         "--manifest", str(manifest),
                         "--output", str(output / "source_pair_audit.json")]
        if archived_runner is not None:
            runner = (ROOT / archived_runner).resolve(strict=True)
            audit_command += ["--archived-runner", str(runner)]
        else:
            runner = None
        run(*audit_command)
        source_audit = json.loads((output / "source_pair_audit.json").read_text())
        if source_audit.get("status") != "PASS":
            raise ValueError(f"source paired campaign did not pass: {manifest}")
    else:
        runner = None
    frozen_cases = [prepare_case(case, inputs) for case in cases]
    provenance = {
        "schema_version": 1,
        "matrix_sha256": digest(args.matrix),
        "simv": str(simv),
        "simv_sha256": digest(simv),
        "source_manifest_sha256": digest(source_manifest),
        "paired_manifest_sha256": digest(manifest) if paired_manifest is not None else None,
        "archived_runner_sha256": digest(runner) if runner is not None else None,
        "frozen_source_freeze_sha256": digest(frozen_root / "freeze.json")
            if frozen_root is not None else None,
        "source_pair_audit_sha256": digest(output / "source_pair_audit.json")
            if paired_manifest is not None else None,
        "ram_bytes": args.ram_bytes,
        "cases": frozen_cases,
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    run(*elf_fit_command(frozen_cases, args.ram_bytes, output))

    results = collect_cases(frozen_cases, simv, reporter, output, args.jobs)
    if digest(simv) != provenance["simv_sha256"]:
        raise ValueError("simulator changed during coverage collection")
    for result in results:
        if json.loads(result.read_text(encoding="utf-8"))["simv_sha256"] != provenance["simv_sha256"]:
            raise ValueError(f"coverage case used a different simulator: {result}")

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
        "--coverage-minimum-cases", str(len(results)),
        "--output", str(merged / "signoff"))
    print(merged)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
