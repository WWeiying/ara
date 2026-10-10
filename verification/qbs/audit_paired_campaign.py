"""Re-audit representative QBS/AKV pairs and reject mixed VCS images."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from compare_akv_real_dut_pair import audit_pair as audit_akv_pair
from compare_real_dut_pair import audit_pair as audit_qbs_pair


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FORMATS = {
    "q2_K", "q3_K", "q4_K", "q4_0", "q5_K", "q5_0", "q6_K", "q8_0",
    "iq4_nl",
}


def source_path(value: object) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError("pair input path must be a nonempty string")
    path = Path(value)
    return (path if path.is_absolute() else ROOT / path).resolve()


def pair_paths(record: object, names: tuple[str, ...]) -> list[Path]:
    if not isinstance(record, dict):
        raise ValueError("pair record must be an object")
    return [source_path(record.get(name)) for name in names]


def audit_campaign(manifest: Path, archived_runner: Path | None = None) -> dict[str, object]:
    raw = manifest.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict) or spec.get("schema_version") != 1:
        raise ValueError("unsupported paired campaign manifest")
    pairs = spec.get("qbs_pairs")
    if not isinstance(pairs, list):
        raise ValueError("qbs_pairs must be a list")
    results: dict[str, object] = {}
    issues: list[str] = []
    images: dict[str, dict[str, str]] = {}
    seen: set[str] = set()
    seen_keys: set[str] = set()
    for record in pairs:
        if not isinstance(record, dict) or record.get("format") not in REQUIRED_FORMATS:
            issues.append("unexpected QBS format or malformed pair")
            continue
        name = record["format"]
        variant = record.get("variant")
        if variant is not None and (not isinstance(variant, str) or
                                    not re.fullmatch(r"[A-Za-z0-9_+-]+", variant)):
            issues.append(f"{name}: invalid pair variant")
            continue
        key = f"{name}@{variant}" if variant is not None else name
        if key in seen_keys:
            issues.append(f"duplicate QBS pair: {key}")
            continue
        seen_keys.add(key)
        seen.add(name)
        try:
            qbs_run, rvv_run, qbs_app, rvv_app = pair_paths(
                record, ("qbs_run", "rvv_run", "qbs_app", "rvv_app"))
            result = audit_qbs_pair(qbs_run, rvv_run, qbs_app, rvv_app,
                                    archived_runner)
        except (OSError, ValueError, KeyError) as error:
            issues.append(f"{name}: {error}")
            continue
        results[key] = result
        case = result.get("case")
        if (result.get("status") != "PASS" or not isinstance(case, dict) or
                case.get("weight_type") != name):
            issues.append(f"{key}: paired source audit failed or format differs")
        components = result.get("vcs_image_components")
        if not isinstance(components, dict) or not components:
            issues.append(f"{key}: VCS image identity is missing")
        else:
            images[key] = components
    missing = sorted(REQUIRED_FORMATS - seen)

    akv_record = spec.get("akv_pair")
    if akv_record is not None:
        try:
            rvv_run, akv_run, rvv_elf, akv_elf, rvv_asm, akv_asm = pair_paths(
                akv_record, ("rvv_run", "akv_run", "rvv_elf", "akv_elf",
                             "rvv_asm", "akv_asm"))
            result = audit_akv_pair(rvv_run, akv_run, rvv_elf, akv_elf,
                                    rvv_asm, akv_asm, archived_runner)
        except (OSError, ValueError, KeyError) as error:
            issues.append(f"AKV: {error}")
        else:
            results["akv_v2"] = result
            if result.get("status") != "PASS":
                issues.append("AKV: paired source audit failed")
            components = result.get("vcs_image_components")
            if not isinstance(components, dict) or not components:
                issues.append("AKV: VCS image identity is missing")
            else:
                images["akv_v2"] = components

    image_ids = {name: hashlib.sha256(json.dumps(components, sort_keys=True).encode()).hexdigest()
                 for name, components in images.items()}
    image_match = (akv_record is not None and len(image_ids) == len(results) and
                   len(image_ids) == len(seen_keys) + 1 and
                   len(set(image_ids.values())) == 1)
    shapes: dict[str, list[dict[str, int | str]]] = {}
    for key, result in results.items():
        if key == "akv_v2":
            continue
        name = key.split("@", 1)[0]
        case = result.get("case")
        if (result.get("status") != "PASS" or not isinstance(case, dict) or
                any(type(case.get(field)) is not int or case[field] <= 0
                    for field in ("k", "rows", "inputs"))):
            continue
        shapes.setdefault(name, []).append(
            {"pair_key": key, **{field: case[field] for field in ("k", "rows", "inputs")}})
    multi_input = sorted(name for name, cases in shapes.items()
                         if any(case["inputs"] > 1 for case in cases))
    row_tail = sorted(name for name, cases in shapes.items()
                      if any(case["rows"] % 4 != 0 for case in cases))
    return {
        "status": "FAIL" if issues else ("PASS" if not missing and akv_record is not None
                                        and image_match else "INCOMPLETE"),
        "scope": "representative real-model QBS/RVV and AKV/RVV pairs; not all profiles or full-model signoff",
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "required_qbs_formats": sorted(REQUIRED_FORMATS),
        "missing_qbs_formats": missing,
        "image_match": image_match,
        "qbs_pair_count": len(results) - int("akv_v2" in results),
        "image_ids": image_ids,
        "campaign_shape_coverage": {
            "scope": "only the pairs listed by this manifest; missing here does not prove untested globally",
            "valid_shape_formats": sorted(shapes),
            "shapes": shapes,
            "multi_input_formats": multi_input,
            "row_tail_formats": row_tail,
            "missing_multi_input_formats": sorted(REQUIRED_FORMATS - set(multi_input)),
            "missing_row_tail_formats": sorted(REQUIRED_FORMATS - set(row_tail)),
        },
        "issues": issues,
        "pairs": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archived-runner", type=Path,
                        help="historical run_real_dut_case.sh; its hash must match frozen manifests")
    args = parser.parse_args()
    try:
        archived_runner = args.archived_runner.resolve(strict=True) if args.archived_runner else None
        result = audit_campaign(args.manifest.resolve(), archived_runner)
        if archived_runner is not None:
            result["archived_runner"] = str(archived_runner)
            result["archived_runner_sha256"] = hashlib.sha256(archived_runner.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError) as error:
        result = {"status": "FAIL", "issues": [str(error)]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"representative paired campaign: {result['status']}")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
