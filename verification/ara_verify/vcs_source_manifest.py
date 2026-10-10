"""Freeze and recheck the source inventory of an isolated VCS Ara build."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


HEADERS = {".h", ".hpp", ".vh", ".svh"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def collect(filelist: Path, root: Path, extra_sources: list[Path]) -> list[dict[str, str]]:
    hardware = root / "hardware"
    paths = {filelist, hardware / "Makefile", root / "Bender.yml",
             root / "Bender.lock", root / "config/default.mk",
             root / "config/sram.mk", *extra_sources}
    include_dirs = set()
    for raw in filelist.read_text().splitlines():
        token = raw.strip()
        if token.startswith("+incdir+"):
            include_dirs.add(Path(token[len("+incdir+"):]).resolve())
        elif token and not token.startswith(("+", "-", "#")):
            paths.add(Path(token).resolve())
    for directory in include_dirs:
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        paths.update(path for path in directory.rglob("*")
                     if path.is_file() and path.suffix.lower() in HEADERS)
    paths.update(path for path in (hardware / "tb/dpi").rglob("*")
                 if path.is_file() and path.suffix.lower() in HEADERS | {".c", ".cc", ".cpp"})
    missing = sorted(str(path) for path in paths if not path.is_file())
    if missing:
        raise FileNotFoundError("missing VCS build inputs: " + ", ".join(missing))
    return [{"path": str(path.resolve()), "sha256": digest(path)}
            for path in sorted(paths)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--filelist", type=Path)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--extra-source", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        saved = json.loads(args.output.read_text())
        if saved.get("schema_version") != 1:
            parser.error("unsupported VCS source manifest")
        filelist = Path(saved["filelist"])
        root = Path(saved["repo_root"])
        extra_sources = [Path(value) for value in saved["extra_sources"]]
    else:
        if args.filelist is None or args.repo_root is None:
            parser.error("capture requires --filelist and --repo-root")
        if args.output.exists():
            parser.error(f"output already exists: {args.output}")
        filelist = args.filelist.resolve(strict=True)
        root = args.repo_root.resolve(strict=True)
        extra_sources = [path.resolve(strict=True) for path in args.extra_source]
    records = collect(filelist, root, extra_sources)
    if args.check:
        previous = {row["path"]: row["sha256"] for row in saved["files"]}
        current = {row["path"]: row["sha256"] for row in records}
        changed = sorted(path for path in previous.keys() | current.keys()
                         if previous.get(path) != current.get(path))
        result = {"status": "PASS" if not changed else "FAIL",
                  "file_count": len(records), "changed": changed}
        print(json.dumps(result, sort_keys=True))
        return 0 if not changed else 1
    data = {"schema_version": 1, "filelist": str(filelist),
            "repo_root": str(root),
            "extra_sources": [str(path) for path in extra_sources],
            "files": records}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"status": "CAPTURED", "file_count": len(records),
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
