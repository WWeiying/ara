"""Audit one paired campaign with isolated reruns for truncated event traces."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from audit_paired_campaign import audit_campaign


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_hashes(run: Path) -> None:
    for name in ("INPUT_SHA256SUMS", "RUN_SHA256SUMS"):
        manifest = run / name
        if not manifest.is_file():
            raise ValueError(f"missing hash manifest: {manifest}")
        result = subprocess.run(
            ["sha256sum", "-c", "--status", name], cwd=run, check=False
        )
        if result.returncode:
            raise ValueError(f"hash check failed: {manifest}")


def resolve_source_paths(manifest: dict, source_root: Path) -> None:
    source_root = source_root.resolve(strict=True)
    if not source_root.is_dir():
        raise ValueError(f"source root is not a directory: {source_root}")
    records = [(row, ("qbs_app", "rvv_app")) for row in manifest["qbs_pairs"]]
    records.append((manifest["akv_pair"],
                    ("rvv_elf", "akv_elf", "rvv_asm", "akv_asm")))
    for record, names in records:
        for name in names:
            source = Path(record[name])
            if source.is_absolute():
                continue
            resolved = (source_root / source).resolve(strict=True)
            resolved.relative_to(source_root)
            record[name] = str(resolved)


def reconcile(plan_path: Path, overrides: dict[str, Path], output: Path,
              source_root: Path | None = None) -> dict:
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if plan.get("status") not in ("PASS", "FAIL"):
        raise ValueError("campaign is not terminal")
    cases = plan["cases"]
    by_key = {f"{case['name']}/{case['mode']}": case for case in cases}
    if len(by_key) != len(cases) or set(overrides) - set(by_key):
        raise ValueError("duplicate or unknown campaign case")
    manifest = json.loads(json.dumps(plan["output_manifest"]))
    if source_root is not None:
        resolve_source_paths(manifest, source_root)
    for key, case in by_key.items():
        if key not in overrides and case.get("status") != "PASS":
            raise ValueError(f"failed case has no verified override: {key}")
        if key not in overrides:
            continue
        if case.get("status") not in ("FAIL", None):
            raise ValueError(f"override is restricted to failed or untouched cases: {key}")
        run = overrides[key].resolve(strict=True)
        check_hashes(run)
        result = json.loads((run / "uvm_result.json").read_text(encoding="utf-8"))
        if result.get("status") != "PASS":
            raise ValueError(f"override did not pass UVM audit: {key}")
        if result.get("elf_sha256") != case["elf_sha256"]:
            raise ValueError(f"override ELF differs from frozen case: {key}")
        if result.get("simv_sha256") != plan["simv_sha256"]:
            raise ValueError(f"override simulator differs from campaign: {key}")
        name, mode = key.split("/", 1)
        if name == "akv_v2":
            manifest["akv_pair"][f"{mode}_run"] = str(run)
        else:
            pair = next(
                (row for row in manifest["qbs_pairs"] if
                 row["format"] + ("_" + row["variant"] if row.get("variant") else "") == name),
                None,
            )
            if pair is None:
                raise ValueError(f"pair is missing from manifest: {name}")
            pair[f"{mode}_run"] = str(run)
    output.mkdir(parents=True)
    manifest_path = output / "paired_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    audit = audit_campaign(manifest_path)
    (output / "audit.json").write_text(
        json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    provenance = {
        "plan": str(plan_path.resolve()),
        "plan_sha256": digest(plan_path),
        "overrides": {key: str(path.resolve()) for key, path in sorted(overrides.items())},
        "source_root": str(source_root.resolve()) if source_root is not None else None,
        "status": audit["status"],
    }
    (output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--override", action="append", default=[],
                        metavar="CASE/MODE=RUN_DIRECTORY")
    parser.add_argument("--source-root", type=Path,
                        help="root containing the frozen application and AKV inputs")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    overrides: dict[str, Path] = {}
    for item in args.override:
        key, separator, path = item.partition("=")
        if not separator or key in overrides or not path:
            parser.error(f"invalid override: {item}")
        overrides[key] = Path(path)
    try:
        audit = reconcile(args.plan, overrides, args.output, args.source_root)
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(f"{audit['status']}: {args.output / 'audit.json'}")
    return 0 if audit["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
