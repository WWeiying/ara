#!/usr/bin/env python3
"""Capture or recheck the source files used by a Verilator Ara build."""

import argparse
import hashlib
import json
from pathlib import Path


INCLUDE_SUFFIXES = {".h", ".hpp", ".v", ".vh", ".sv", ".svh"}
TESTBENCH_SUFFIXES = INCLUDE_SUFFIXES | {".c", ".cc", ".cpp"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect(filelist: Path, repo_root: Path, build_dir: Path) -> list[dict[str, str]]:
    hardware = repo_root / "hardware"
    paths = {filelist, build_dir / ".build-signature", hardware / "Makefile",
             repo_root / "Bender.yml", repo_root / "Bender.lock",
             repo_root / "config" / "default.mk", repo_root / "config" / "sram.mk"}
    include_dirs = set()
    for raw in filelist.read_text().splitlines():
        token = raw.strip()
        if token.startswith("+incdir+"):
            include_dirs.add(Path(token[len("+incdir+"):]).resolve())
        elif token and not token.startswith(("+", "-", "#")):
            source = Path(token).resolve()
            if source.is_file():
                paths.add(source)
    for directory in include_dirs:
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        paths.update(path for path in directory.rglob("*")
                     if path.is_file() and path.suffix.lower() in INCLUDE_SUFFIXES)
    for directory in (hardware / "src", hardware / "deps"):
        paths.update(path for path in directory.rglob("*")
                     if path.is_file() and path.suffix.lower() in {".svh", ".vh"})
    testbench = hardware / "tb" / "verilator"
    paths.update(path for path in testbench.rglob("*")
                 if path.is_file() and path.suffix.lower() in TESTBENCH_SUFFIXES)
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("missing build inputs: " + ", ".join(sorted(missing)))
    return [{"path": str(path.resolve()), "sha256": sha256(path)}
            for path in sorted(paths)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filelist", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--build-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        saved = json.loads(args.output.read_text())
        filelist = Path(saved["filelist"])
        repo_root = Path(saved["repo_root"])
        build_dir = Path(saved["build_dir"])
    else:
        if not all((args.filelist, args.repo_root, args.build_dir)):
            parser.error("capture requires --filelist, --repo-root and --build-dir")
        filelist = args.filelist.resolve(strict=True)
        repo_root = args.repo_root.resolve(strict=True)
        build_dir = args.build_dir.resolve(strict=True)
    records = collect(filelist, repo_root, build_dir)
    if args.check:
        if records != saved["files"]:
            old = {item["path"]: item["sha256"] for item in saved["files"]}
            new = {item["path"]: item["sha256"] for item in records}
            changed = sorted(path for path in old.keys() | new.keys()
                             if old.get(path) != new.get(path))
            print(json.dumps({"status": "FAIL", "changed": changed}, indent=2))
            return 1
        print(json.dumps({"status": "PASS", "file_count": len(records)}))
        return 0
    if args.output.exists():
        parser.error(f"output already exists: {args.output}")
    data = {"schema_version": 1, "filelist": str(filelist),
            "repo_root": str(repo_root), "build_dir": str(build_dir),
            "files": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"status": "CAPTURED", "file_count": len(records),
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
