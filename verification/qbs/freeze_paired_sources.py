#!/usr/bin/env python3
"""Freeze the source inputs needed to re-audit a completed QBS/AKV pair run."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


INCBIN = re.compile(r'\.incbin "([^"]+)"')
INPUTS = ("source_weight.bin", "activation_f32.bin", "golden_f32.bin")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze(manifest: Path, runner: Path, output: Path) -> dict:
    manifest = manifest.resolve(strict=True)
    runner = runner.resolve(strict=True)
    output = output.resolve()
    if output.exists():
        raise ValueError(f"output already exists: {output}")
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError("unsupported paired manifest")

    # Resolve every input before creating output so a missing source leaves no partial snapshot.
    apps = {}
    for pair in spec["qbs_pairs"]:
        for key in ("qbs_app", "rvv_app"):
            source = Path(pair[key]).resolve(strict=True)
            apps[source.name] = source
            for name in ("case.json", *(f"generated/{item}" for item in INPUTS)):
                (source / name).resolve(strict=True)
    akv = spec["akv_pair"]
    captures = {}
    for key in ("rvv_asm", "akv_asm"):
        asm = Path(akv[key]).resolve(strict=True)
        for path in INCBIN.findall(asm.read_text(encoding="utf-8")):
            source = Path(path).resolve(strict=True)
            previous = captures.get(source.name)
            if previous is not None and previous != source:
                raise ValueError(f"duplicate capture basename: {source.name}")
            captures[source.name] = source
    for key in ("rvv_elf", "akv_elf"):
        Path(akv[key]).resolve(strict=True)

    output.mkdir(parents=True)
    hashes = {}

    def copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        source_hash = digest(source)
        if digest(target) != source_hash:
            raise ValueError(f"copy differs from source: {source}")
        hashes[str(target.relative_to(output))] = source_hash

    for name, source in sorted(apps.items()):
        for relative in ("case.json", *(f"generated/{item}" for item in INPUTS)):
            copy(source / relative, output / "apps" / name / relative)
    for source in captures.values():
        copy(source, output / "captures" / source.name)
    for pair in spec["qbs_pairs"]:
        for key in ("qbs_app", "rvv_app"):
            pair[key] = str(output / "apps" / Path(pair[key]).name)

    for key in ("rvv_asm", "akv_asm"):
        source = Path(akv[key]).resolve(strict=True)
        target = output / "akv" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        text = source.read_text(encoding="utf-8")
        text = INCBIN.sub(lambda match: f'.incbin "{output / "captures" / Path(match[1]).name}"',
                          text)
        target.write_text(text, encoding="utf-8")
        hashes[str(target.relative_to(output))] = digest(target)
        akv[key] = str(target)
    for key in ("rvv_elf", "akv_elf"):
        source = Path(akv[key]).resolve(strict=True)
        target = output / "akv" / source.name
        copy(source, target)
        akv[key] = str(target)

    archived_runner = output / "run_real_dut_case.archived.sh"
    copy(runner, archived_runner)
    frozen_manifest = output / "paired_manifest.json"
    frozen_manifest.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    evidence = {
        "status": "PASS",
        "original_manifest": str(manifest),
        "original_manifest_sha256": digest(manifest),
        "frozen_manifest": str(frozen_manifest),
        "frozen_manifest_sha256": digest(frozen_manifest),
        "archived_runner": str(archived_runner),
        "files_sha256": hashes,
    }
    (output / "freeze.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n",
                                        encoding="utf-8")
    return evidence


def check(output: Path) -> list[str]:
    output = output.resolve(strict=True)
    evidence = json.loads((output / "freeze.json").read_text(encoding="utf-8"))
    issues = []
    for relative, expected in evidence["files_sha256"].items():
        path = output / relative
        if not path.is_file() or digest(path) != expected:
            issues.append(f"frozen file missing or changed: {relative}")
    manifest = output / "paired_manifest.json"
    if (not manifest.is_file() or
            digest(manifest) != evidence["frozen_manifest_sha256"]):
        issues.append("frozen manifest missing or changed")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--archived-runner", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        issues = check(args.output)
        print("frozen source integrity: " + ("PASS" if not issues else "FAIL"))
        for issue in issues:
            print(issue)
        return 0 if not issues else 1
    if args.manifest is None or args.archived_runner is None:
        parser.error("--manifest and --archived-runner are required when creating a snapshot")
    result = freeze(args.manifest, args.archived_runner, args.output)
    print(f"frozen {len(result['files_sha256'])} files under {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
