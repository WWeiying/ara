#!/usr/bin/env python3
"""Freeze the reviewed dirty MVP, compile once, and audit one bounded VCS run."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = Path("/home/wangwy/openproject/ara_dsa/hardware/deps")
MVP_HEAD = "86e1f558b3c95e91577c41b2fc452c86b04e85ac"
PATCH_HASH = "3cc6ec1c27eca277853d85e9c47fae317f0f0cd9cfc8589a95742117d6beaf6a"
MVP_MODULES = (
    "defs_div_sqrt_mvp.sv", "iteration_div_sqrt_mvp.sv", "control_mvp.sv",
    "norm_div_sqrt_mvp.sv", "preprocess_mvp.sv", "nrbd_nrsc_mvp.sv",
    "div_sqrt_top_mvp.sv",
)
SOURCES = (
    "common_cells/src/cf_math_pkg.sv", "common_cells/src/lzc.sv",
    *(f"fpu_div_sqrt_mvp/hdl/{name}" for name in MVP_MODULES),
)
HEADER = "common_cells/include/common_cells/assertions.svh"
SIM_ERROR = re.compile(r"HARNESS_ERROR|Fatal(?:-|:)|Error(?:-|:)|ASSERT FAILED")


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(content):
    return hashlib.sha256(content).hexdigest()


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args])


def dependency_fingerprint(root):
    return {name: digest((root / name).read_bytes()) for name in SOURCES + (HEADER,)}


def finite_value(bits, width):
    fraction_bits, exponent_bits = (52, 11) if width == 64 else (23, 8)
    if width == 32 and bits >> 32 != 0xffffffff:
        raise ValueError("FP32 operand is not NaN-boxed")
    exponent = (bits >> fraction_bits) & ((1 << exponent_bits) - 1)
    if not 0 < exponent < (1 << exponent_bits) - 1:
        raise ValueError("audit oracle only accepts finite normal operands")
    significand = (1 << fraction_bits) | (bits & ((1 << fraction_bits) - 1))
    scale = exponent - ((1 << (exponent_bits - 1)) - 1) - fraction_bits
    value = Fraction(significand) * (Fraction(2) ** scale)
    return -value if bits & (1 << (width - 1)) else value


def architectural_oracle(case):
    """Exact-rational oracle restricted to this audit's exact-one/overflow cases."""
    width, rm = case["format"], case["rm"]
    if width not in (32, 64) or rm not in range(5):
        raise ValueError("unsupported format or rounding mode")
    fraction_bits, exponent_bits = (52, 11) if width == 64 else (23, 8)
    boxing = 0 if width == 64 else 0xffffffff00000000
    infinity = ((1 << exponent_bits) - 1) << fraction_bits
    maximum = infinity - 1
    ratio = finite_value(int(case["a"], 16), width) / finite_value(int(case["b"], 16), width)
    sign = int(ratio < 0)
    if abs(ratio) > finite_value(boxing | maximum, width):
        to_inf = rm in (0, 4) or (rm == 3 and not sign) or (rm == 2 and sign)
        value = infinity if to_inf else maximum
        return boxing | (sign << (width - 1)) | value, 0x05
    if ratio == 1:
        return boxing | (((1 << (exponent_bits - 1)) - 1) << fraction_bits), 0
    raise ValueError("oracle intentionally does not implement arbitrary FP division")


def load_cases(path):
    cases = json.loads(path.read_text())
    if len(cases) != 8 or len({case["name"] for case in cases}) != 8:
        raise ValueError("audit requires eight uniquely named cases")
    for case in cases:
        expected = int(case["expected_result"], 16), int(case["expected_flags"], 16)
        if architectural_oracle(case) != expected:
            raise ValueError(f"fixed oracle disagrees with rational oracle: {case['name']}")
    return cases


def parse_csv(text):
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows or any(None in row or None in row.values() for row in rows):
        raise ValueError("missing or malformed CSV evidence")
    return rows


def classify(case, row):
    observed = int(row["result"], 16), int(row["flags"], 16)
    expected = architectural_oracle(case)
    predicted = int(case["predicted_result"], 16), int(case["predicted_flags"], 16)
    if observed == expected:
        return "CONTROL_MATCH" if predicted == expected else "HYPOTHESIS_NOT_REPRODUCED"
    return "DEFECT_REPRODUCED" if observed == predicted else "UNEXPECTED_DUT_MISMATCH"


def check_evidence(cases, log, result_text, trace_text):
    errors = []
    if SIM_ERROR.search(log):
        errors.append("simulator or harness error")
    if log.splitlines().count("AUDIT_COMPLETE cases=8 accepted=8 completed=8 pending=0") != 1:
        errors.append("missing/duplicate completion or invalid accounting")
    rows, trace = parse_csv(result_text), parse_csv(trace_text)
    if [row["name"] for row in rows] != [case["name"] for case in cases]:
        raise ValueError("missing, reordered, duplicate or extraneous case results")
    records = []
    for index, (case, row) in enumerate(zip(cases, rows)):
        if int(row["id"]) != index or int(row["format"]) != case["format"] or int(row["rm"]) != case["rm"]:
            errors.append(f"{case['name']}: case metadata mismatch")
        for key in ("a", "b", "expected_result", "expected_flags"):
            if int(row[key], 16) != int(case[key], 16):
                errors.append(f"{case['name']}: {key} mismatch")
        if not 1 <= int(row["latency"]) <= 64:
            errors.append(f"{case['name']}: invalid latency")
        phases = [entry for entry in trace if entry["case_id"] == str(index)]
        fires = [entry for entry in phases if entry["phase"] == "pre" and entry["fire"] == "1"]
        pre_done = [entry for entry in phases if entry["phase"] == "pre" and entry["done"] == "1"]
        post_done = [entry for entry in phases if entry["phase"] == "post_nba" and entry["done"] == "1"]
        if len(fires) != 1 or len(pre_done) != 1 or len(post_done) != 1:
            errors.append(f"{case['name']}: acceptance/completion trace cardinality")
        else:
            if int(post_done[0]["cycle"]) - int(fires[0]["cycle"]) != int(row["latency"]):
                errors.append(f"{case['name']}: latency disagrees with trace")
            if int(pre_done[0]["cycle"]) != int(post_done[0]["cycle"]) + 1:
                errors.append(f"{case['name']}: completion sampling phase disagreement")
            for entry in (pre_done[0], post_done[0]):
                for key in ("result", "flags", "remainder", "quotient", "denominator",
                            "norm_exp", "norm_mant", "explicit_round", "rounded_exp", "rounded_mant"):
                    if int(entry[key], 16) != int(row[key], 16):
                        errors.append(f"{case['name']}: {key} differs between evidence phases")
                for key in ("sticky", "round_up", "overflow", "remainder_nonzero"):
                    if entry[key] != row[key]:
                        errors.append(f"{case['name']}: {key} differs between evidence phases")
        classification = classify(case, row)
        if int(row["oracle_match"]) != int(classification in ("CONTROL_MATCH", "HYPOTHESIS_NOT_REPRODUCED")):
            errors.append(f"{case['name']}: bench/rational oracle classification disagreement")
        records.append({**row, "hypothesis": case["hypothesis"], "classification": classification})
    return records, errors


def stop_group(process):
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            continue
    process.wait()


def execute(command, cwd, timeout):
    cwd.mkdir()
    record = {"argv": list(map(str, command)), "cwd": str(cwd), "timeout_s": timeout,
              "started_at": now(), "status": "RUNNING"}
    save_json(cwd / "command.json", record)
    start = time.monotonic()
    with (cwd / "console.log").open("wb") as log:
        process = subprocess.Popen(record["argv"], cwd=cwd, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
            record.update(returncode=code, status="COMPLETED" if code == 0 else "ERROR")
        except subprocess.TimeoutExpired:
            record.update(status="TIMEOUT")
        finally:
            stop_group(process)
    record.update(elapsed_s=time.monotonic() - start, completed_at=now(),
                  console_sha256=digest((cwd / "console.log").read_bytes()))
    save_json(cwd / "command_result.json", record)
    return record


def freeze(output):
    repo = ORIGINAL / "fpu_div_sqrt_mvp"
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    patch = git(repo, "diff", "HEAD", "--full-index", "--no-ext-diff")
    if head != MVP_HEAD or digest(patch) != PATCH_HASH:
        raise ValueError("original MVP no longer matches the reviewed snapshot")
    inputs = output / "inputs"
    records = {}
    files = [(ORIGINAL / name, name) for name in SOURCES + (HEADER,)]
    files += [(HERE / name, f"audit/{name}") for name in
              ("mvp_audit_tb.sv", "cases.json", "run_mvp_audit.py", "README.md")]
    files.append((ROOT / "verification/tests/test_mvp_audit.py", "audit/test_mvp_audit.py"))
    for source, relative in files:
        content = source.read_bytes()
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        target.chmod(0o444)
        records[relative] = {"source": str(source), "sha256": digest(content), "bytes": len(content)}
    (inputs / "original-mvp-full-index.patch").write_bytes(patch)
    (inputs / "original-mvp-full-index.patch").chmod(0o444)
    if patch != git(repo, "diff", "HEAD", "--full-index", "--no-ext-diff"):
        raise ValueError("original patch changed during snapshot")
    if any(digest(Path(value["source"]).read_bytes()) != value["sha256"] for value in records.values()):
        raise ValueError("source changed during snapshot")
    manifest = {"mvp_head": head, "patch_sha256": digest(patch), "files": records,
                "common_cells_head": git(ORIGINAL / "common_cells", "rev-parse", "HEAD").decode().strip(),
                "created_at": now()}
    save_json(output / "inputs.json", manifest)
    return manifest


def run(output, vcs):
    if output.is_symlink() or output.exists():
        raise ValueError("output must be new; refusing overwrite/retry")
    output.mkdir(parents=True, exist_ok=False)
    output = output.resolve()
    report = {"status": "RUNNING", "started_at": now(), "dut_status": "NOT_EVALUATED",
              "compile_count": 0, "run_count": 0, "errors": []}
    save_json(output / "summary.json", report)
    before = {"original": dependency_fingerprint(ORIGINAL),
              "verification": dependency_fingerprint(ROOT / "hardware/deps")}
    try:
        manifest = freeze(output)
        report["patch_sha256"] = manifest["patch_sha256"]
        inputs = output / "inputs"
        cases = load_cases(inputs / "audit/cases.json")
        stimulus = "\n".join(
            f'run_case({i}, "{case["name"]}", 2\'d{int(case["format"] == 64)}, '
            f'3\'d{case["rm"]}, 64\'h{case["a"]}, 64\'h{case["b"]}, '
            f'64\'h{case["expected_result"]}, 5\'h{case["expected_flags"]});'
            for i, case in enumerate(cases)) + "\n"
        (inputs / "audit/cases.svh").write_text(stimulus)
        (inputs / "audit/cases.svh").chmod(0o444)
        report["stimulus_sha256"] = digest(stimulus.encode())
        report["oracles"] = "eight fixed bit/flag oracles validated by exact rational arithmetic"
        command = [vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
                   f"+incdir+{inputs / 'common_cells/include'}", f"+incdir+{inputs / 'audit'}",
                   *[str(inputs / name) for name in SOURCES],
                   str(inputs / "audit/mvp_audit_tb.sv"), "-top", "mvp_audit_tb",
                   "-o", "simv", "-l", "compile.log"]
        report["compile_count"] = 1
        report["compile"] = execute(command, output / "build", 180)
        if report["compile"]["status"] != "COMPLETED":
            raise ValueError("compile failed; no retry and no simulation")
        report["run_count"] = 1
        report["run"] = execute([output / "build/simv", "-l", "run.log"], output / "sim", 30)
        if report["run"]["status"] != "COMPLETED":
            raise ValueError("simulation did not complete; analyze preserved trace before any rerun")
        report["cases"], errors = check_evidence(
            cases, (output / "sim/console.log").read_text(),
            (output / "sim/results.csv").read_text(), (output / "sim/trace.csv").read_text())
        report["errors"].extend(errors)
        classifications = [case["classification"] for case in report["cases"]]
        report["dut_status"] = ("FAIL_ARCHITECTURAL_ORACLE" if any(
            value in ("DEFECT_REPRODUCED", "UNEXPECTED_DUT_MISMATCH") for value in classifications)
            else "NO_MISMATCH_IN_BOUNDED_CASES")
        report["status"] = ("AUDIT_REPRODUCED_DUT_FAILURES" if
                            classifications == ["DEFECT_REPRODUCED"] * 5 + ["CONTROL_MATCH"] * 3
                            else "AUDIT_UNEXPECTED_ANALYZE_WITHOUT_RERUN")
        report["evidence_sha256"] = {name: digest((output / "sim" / name).read_bytes())
                                      for name in ("results.csv", "trace.csv", "probes.vcd", "run.log")}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report["errors"].append(str(error))
    finally:
        after = {"original": dependency_fingerprint(ORIGINAL),
                 "verification": dependency_fingerprint(ROOT / "hardware/deps")}
        report["dependencies_unchanged"] = before == after
        save_json(output / "dependency_fingerprints.json", {"before": before, "after": after})
        if before != after:
            report["errors"].append("dependency sources changed during audit")
        if report["errors"]:
            report["status"] = "HARNESS_ERROR"
        report["completed_at"] = now()
        save_json(output / "summary.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    vcs = shutil.which(args.vcs)
    if not vcs:
        parser.error("VCS executable not found")
    report = run(args.output, vcs)
    print(json.dumps({key: report[key] for key in
                      ("status", "dut_status", "compile_count", "run_count", "errors")}, indent=2))
    return 0 if report["status"] == "AUDIT_REPRODUCED_DUT_FAILURES" else 1


if __name__ == "__main__":
    raise SystemExit(main())
