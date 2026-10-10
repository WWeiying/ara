#!/usr/bin/env python3
"""Inventory source differences without merging RTL or historical results."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def files(root):
    data = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root).decode()
    names = set(filter(None, data.split("\0")))
    # Directed C tests may be accidentally excluded by the application's
    # global generated-file ignore rules; include them explicitly.
    names.update(str(p.relative_to(root)) for p in
                 (root / "apps/riscv-tests/isa/rv64uv").glob("*.c"))
    excluded = {"out", "tools", "bin", "build", "__pycache__", ".git"}
    return sorted(p for p in names if not excluded.intersection(Path(p).parts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path,
                        help="preserve differing historical sources in a new tar.gz")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    records = []
    cache = {}
    for source in args.source:
        source = source.resolve(strict=True)
        entries = []
        for name in files(source):
            old, new = source / name, root / name
            if not old.is_file():
                continue
            old_sha = sha(old)
            if name not in cache:
                cache[name] = sha(new) if new.is_file() else None
            new_sha = cache[name]
            status = "identical" if old_sha == new_sha else (
                "missing" if new_sha is None else "different")
            if status != "identical":
                entries.append({"path": name, "status": status,
                                "source_sha256": old_sha, "target_sha256": new_sha})
        records.append({"source": str(source), "differences": entries,
                        "counts": dict(Counter(e["status"] for e in entries))})
    payload = {"target": str(root), "scope": "source inventory, not behavioral equivalence",
               "sources": records}
    if args.archive:
        if args.archive.exists():
            parser.error("archive already exists")
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.archive, "w:gz") as archive:
            for record in records:
                source = Path(record["source"])
                for entry in record["differences"]:
                    path = source / entry["path"]
                    if sha(path) != entry["source_sha256"]:
                        raise RuntimeError(f"source changed during archive: {path}")
                    archive.add(path, arcname=f"{source.name}/{entry['path']}", recursive=False)
        payload["historical_source_archive"] = {
            "path": str(args.archive.resolve()), "sha256": sha(args.archive)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    for item in records:
        print(item["source"], item["counts"])


if __name__ == "__main__":
    main()
