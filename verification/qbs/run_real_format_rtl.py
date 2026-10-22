#!/usr/bin/env python3
"""Run and audit short real-model QBS engine cases on one frozen VCS image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

try:
    from .capture_real_format import audit_existing, sha256
except ImportError:
    from capture_real_format import audit_existing, sha256


ROOT = Path(__file__).resolve().parents[2]
GENERATOR = ROOT / "verification/qbs/qbs_command_vectors"
PROFILES = {"q2_K": 7, "q4_0": 3, "q5_0": 8, "iq4_nl": 9}
CASE_RE = re.compile(
    r"^QBS end-to-end case 0 PASS profile=(\d+) M=1 N=16 "
    r"Kb=(\d+) layouts=2/1 cycles=(\d+)$", re.M)
ENGINE_PASS = "QBS engine PASS: 1 functional cases"


def image_hashes(simv: Path) -> dict[str, str]:
    libraries = sorted((simv.parent / "simv.daidir").rglob("*.so"))
    if not simv.is_file() or not libraries:
        raise ValueError("VCS image is missing its launcher or shared libraries")
    return {str(path.relative_to(simv.parent)): sha256(path)
            for path in (simv, *libraries)}


def case_result(log: str, profile: int, k_blocks: int) -> int:
    matches = CASE_RE.findall(log)
    if (len(matches) != 1 or tuple(map(int, matches[0][:2])) !=
            (profile, k_blocks) or log.count(ENGINE_PASS) != 1 or
            re.search(r"(?:^|\n)(?:Error:|Fatal:|UVM_ERROR|QBS engine FAIL|"
                      r"QBS end-to-end case 0 FAIL)", log)):
        raise ValueError("missing or inconsistent functional RTL PASS")
    return int(matches[0][2])


def cases_from_manifest(manifest: Path) -> list[dict[str, object]]:
    data = json.loads(manifest.read_text(encoding="utf-8"))
    entries = data.get("cases") if data.get("schema_version") == 1 else None
    if (not isinstance(entries, list) or len(entries) != len(PROFILES) or
            {entry.get("format") for entry in entries if isinstance(entry, dict)} !=
            set(PROFILES)):
        raise ValueError("manifest must contain the four distinct closure formats")
    return entries


def captured_case(entry: dict[str, object]) -> dict[str, object]:
    name, fmt, source = entry["name"], entry["format"], entry["capture"]
    if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name) or
            not isinstance(source, str)):
        raise ValueError("invalid case name or capture path")
    capture = (ROOT / source).resolve(strict=True)
    audit = audit_existing(capture)
    if audit["status"] != "PASS":
        raise ValueError(f"capture audit failed: {audit.get('error')}")
    result = json.loads((capture / "result.json").read_text(encoding="utf-8"))
    if result["format"] != fmt or result["m"] != 1:
        raise ValueError("capture format or M does not match manifest")
    weight_dir = capture / "capture/decode/operators" / result["operator"]
    k, n = result["k"], result["n"]
    block_elements = 256 if fmt == "q2_K" else 32
    if k % block_elements or n < 16:
        raise ValueError("capture cannot provide the required complete-K N16 slice")
    return {"name": name, "format": fmt, "capture": str(capture),
            "weight_dir": str(weight_dir), "k": k, "full_n": n,
            "k_blocks": k // block_elements,
            "capture_inputs_sha256": audit["inputs_sha256"],
            "capture_result_sha256": audit["result_sha256"]}


def generate_command(generator: Path, vector: Path, item: dict[str, object]) -> list[str]:
    return [str(generator), str(vector), "--real", str(item["format"]),
            str(item["weight_dir"]), str(item["full_n"]), str(item["k"]),
            "0", "1", "0", "16"]


def generate(generator: Path, vector: Path, item: dict[str, object]) -> str:
    result = subprocess.run(generate_command(generator, vector, item),
                            text=True, capture_output=True, timeout=60, check=False)
    if (result.returncode != 0 or
            f"reference PASS M=1 N=16 K={item['k']}" not in result.stderr):
        raise ValueError(f"reference vector generation failed: {result.stderr}")
    return result.stderr


def run(args: argparse.Namespace) -> int:
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be empty: {output}")
    manifest = args.manifest.resolve(strict=True)
    simv = args.simv.resolve(strict=True)
    generator = args.generator.resolve(strict=True)
    inputs = [captured_case(entry) for entry in cases_from_manifest(manifest)]
    image = image_hashes(simv)
    output.mkdir(parents=True, exist_ok=True)
    summary = {"status": "RUNNING", "scope": "QBS engine only; no RVV or full-DUT pair",
               "runner_sha256": sha256(Path(__file__)),
               "manifest": str(manifest), "manifest_sha256": sha256(manifest),
               "generator": str(generator), "generator_sha256": sha256(generator),
               "simv": str(simv), "image_sha256": image, "cases": []}
    for item in inputs:
        name = str(item["name"])
        vector = output / f"{name}.vectors"
        log = output / f"{name}.log"
        try:
            reference = generate(generator, vector, item)
            argv = [str(simv), "-l", str(log), "+QBS_FUNCTIONAL_ONLY",
                    "+QBS_COMMAND_VECTOR_FILE=" + str(vector)]
            record = {**item, "vector_command": generate_command(generator, vector, item),
                      "reference_result": reference.strip(), "sim_command": argv,
                      "vector_sha256": sha256(vector)}
            summary["cases"].append(record)
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
            process = subprocess.run(argv, cwd=ROOT, text=True, capture_output=True,
                                     timeout=args.timeout, check=False)
            record["returncode"] = process.returncode
            record["console_sha256"] = sha256(log) if log.is_file() else None
            if process.returncode != 0 or not log.is_file():
                raise ValueError(f"VCS failed with returncode {process.returncode}")
            record["cycles"] = case_result(log.read_text(errors="replace"),
                                           PROFILES[str(item["format"])],
                                           int(item["k_blocks"]))
            record["status"] = "PASS"
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            if not summary["cases"] or summary["cases"][-1].get("name") != name:
                summary["cases"].append({**item})
            summary["cases"][-1].update(status="FAIL", error=str(error))
            summary["status"] = "FAIL"
            break
        finally:
            (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print(f"{name}: PASS, {record['cycles']} cycles", flush=True)
    if summary["status"] != "FAIL":
        summary["status"] = "PASS" if len(summary["cases"]) == len(PROFILES) else "FAIL"
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["status"] == "PASS" else 1


def audit(args: argparse.Namespace) -> int:
    output = args.output.resolve(strict=True)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    errors = []
    if summary.get("status") != "PASS" or len(summary.get("cases", [])) != len(PROFILES):
        errors.append("run summary is not a complete four-case PASS")
    if summary.get("runner_sha256") != sha256(Path(__file__)):
        errors.append("runner source hash mismatch")
    manifest = Path(summary["manifest"])
    generator = Path(summary["generator"])
    simv = Path(summary["simv"])
    for path, expected in ((manifest, summary["manifest_sha256"]),
                           (generator, summary["generator_sha256"])):
        if not path.is_file() or sha256(path) != expected:
            errors.append(f"input hash mismatch: {path}")
    if image_hashes(simv) != summary["image_sha256"]:
        errors.append("VCS image hash mismatch")
    for item in summary["cases"]:
        name = item["name"]
        vector, log = output / f"{name}.vectors", output / f"{name}.log"
        try:
            fresh = captured_case(item)
            if (fresh["capture_inputs_sha256"] != item["capture_inputs_sha256"] or
                    fresh["capture_result_sha256"] != item["capture_result_sha256"]):
                raise ValueError("capture provenance changed")
            if not vector.is_file() or sha256(vector) != item["vector_sha256"]:
                raise ValueError("vector hash mismatch")
            with tempfile.TemporaryDirectory() as temporary:
                regenerated = Path(temporary) / "case.vectors"
                generate(generator, regenerated, item)
                if sha256(regenerated) != item["vector_sha256"]:
                    raise ValueError("captured input no longer regenerates the vector")
            if not log.is_file() or sha256(log) != item["console_sha256"]:
                raise ValueError("VCS log hash mismatch")
            if (case_result(log.read_text(errors="replace"), PROFILES[item["format"]],
                            item["k_blocks"]) != item["cycles"] or
                    item["returncode"] != 0 or item["status"] != "PASS"):
                raise ValueError("functional result or process status changed")
            expected_command = [str(simv), "-l", str(log), "+QBS_FUNCTIONAL_ONLY",
                                "+QBS_COMMAND_VECTOR_FILE=" + str(vector)]
            if (item["sim_command"] != expected_command or
                    item["vector_command"] != generate_command(generator, vector, item)):
                raise ValueError("frozen command differs")
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
            errors.append(f"{name}: {error}")
    result = {"status": "PASS" if not errors else "FAIL", "errors": errors,
              "scope": summary.get("scope")}
    (output / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "verification/qbs/captured_real_cases_20260923.json")
    parser.add_argument("--generator", type=Path, default=GENERATOR)
    parser.add_argument("--simv", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--audit-existing", action="store_true")
    args = parser.parse_args()
    if not args.audit_existing and args.simv is None:
        parser.error("--simv is required for a new RTL run")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    return audit(args) if args.audit_existing else run(args)


if __name__ == "__main__":
    raise SystemExit(main())
