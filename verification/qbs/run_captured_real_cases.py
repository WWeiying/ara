#!/usr/bin/env python3
"""Re-audit captured model tensors and compare QBS C reference with GGML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

try:
    from .capture_real_format import FORMATS, audit_existing, sha256
except ImportError:
    from capture_real_format import FORMATS, audit_existing, sha256


ROOT = Path(__file__).resolve().parents[2]
EXPECTED = set(FORMATS)


def parse_result(line: str, name: str, weight_type: str, n: int, k: int) -> dict[str, object]:
    lines = line.strip().splitlines()
    if len(lines) != 1:
        raise ValueError("expected one C reference result line")
    fields = dict(token.split("=", 1) for token in lines[0].split() if "=" in token)
    required = {"case", "profile", "M", "N", "K", "max_abs", "checksum", "mismatches"}
    if not required.issubset(fields):
        raise ValueError("C reference output is incomplete")
    match = re.fullmatch(r"(\d+)/(\d+)", fields["mismatches"])
    if (match is None or fields["case"] != name or
            fields["profile"] != weight_type.upper() or
            (int(fields["M"]), int(fields["N"]), int(fields["K"])) != (1, n, k) or
            (int(match.group(1)), int(match.group(2))) != (0, n)):
        raise ValueError("C reference result differs from requested case or captured golden")
    return {"mismatches": 0, "outputs": n, "max_abs": float(fields["max_abs"]),
            "checksum": float(fields["checksum"])}


def run_case(entry: dict[str, object], binary: Path, output: Path) -> dict[str, object]:
    name = entry.get("name")
    weight_type = entry.get("format")
    source = entry.get("capture")
    if (not isinstance(name, str) or not re.fullmatch(r"[a-z0-9_]+", name) or
            weight_type not in FORMATS or not isinstance(source, str)):
        raise ValueError("invalid real-model case manifest entry")
    capture = (ROOT / source).resolve()
    audit = audit_existing(capture)
    if audit["status"] != "PASS":
        raise ValueError(f"capture re-audit failed: {audit.get('error')}")
    frozen = json.loads((capture / "result.json").read_text(encoding="utf-8"))
    if frozen.get("format") != weight_type:
        raise ValueError("captured weight type differs from manifest")
    n, k = frozen["n"], frozen["k"]
    operator_dir = capture / "capture/decode/operators" / frozen["operator"]
    command = [str(binary), name, weight_type, "1", str(n), str(k),
               str(operator_dir), "captured"]
    try:
        process = subprocess.run(command, text=True, capture_output=True,
                                 timeout=60, check=False)
        console = process.stdout + process.stderr
        returncode = process.returncode
    except subprocess.TimeoutExpired:
        console, returncode = "C reference exceeded 60 seconds\n", -1
    (output / f"{name}.log").write_text(console, encoding="utf-8")
    if returncode != 0:
        raise ValueError(f"{name}: C reference failed with {returncode}")
    result = parse_result(console, name, weight_type, n, k)
    return {"status": "PASS", "name": name, "format": weight_type,
            "k": k, "n": n, "m": 1, "command": command,
            "capture_input_sha256": audit["inputs_sha256"],
            "capture_result_sha256": audit["result_sha256"],
            "log_sha256": sha256(output / f"{name}.log"), **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output must be new or empty: {output}")
    manifest = args.manifest.resolve(strict=True)
    binary = args.binary.resolve(strict=True)
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    entries = spec.get("cases") if spec.get("schema_version") == 1 else None
    if (not isinstance(entries, list) or len(entries) != len(EXPECTED) or
            {entry.get("format") for entry in entries if isinstance(entry, dict)} != EXPECTED):
        parser.error("manifest must contain each of the four closure formats exactly once")
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for entry in entries:
        try:
            cases.append(run_case(entry, binary, output))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            cases.append({"status": "FAIL", "name": entry.get("name"),
                          "format": entry.get("format"), "error": str(error)})
    result = {
        "status": "PASS" if all(case["status"] == "PASS" for case in cases) else "FAIL",
        "scope": "four real-model QBS C reference cases; no standard RVV or RTL evidence",
        "manifest": str(manifest), "manifest_sha256": sha256(manifest),
        "binary": str(binary), "binary_sha256": sha256(binary),
        "source_sha256": {
            name: sha256(ROOT / name) for name in (
                "verification/qbs/qbs_real_test.c", "verification/qbs/qbs_ref.c",
                "verification/qbs/qbs_ref.h", "apps/common/qbs_abi.h")
        },
        "cases": cases,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"captured QBS C reference: {result['status']} ({sum(c['status'] == 'PASS' for c in cases)}/4)")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
