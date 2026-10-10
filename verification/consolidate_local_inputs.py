#!/usr/bin/env python3
"""Snapshot linked build inputs without changing RTL or removing source trees."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tree_hashes(root):
    return {str((Path(folder) / name).relative_to(root)): digest(Path(folder) / name)
            for folder, _, names in os.walk(root, followlinks=True)
            for name in names if (Path(folder) / name).is_file()}


def relocate_venvs(root):
    changed = []
    for venv in ("plic-venv", "soc-venv"):
        target = root / "verification/tools" / venv
        prefixes = [str(root.parent / old / "verification/tools" / venv)
                    for old in ("ara_dsa_verification", "ara_dsa_masked_indexed_fix",
                                "ara_dsa_store_fault_fix_20260925")]
        for script in (target / "bin").iterdir():
            if not script.is_file():
                continue
            try:
                original = script.read_text()
            except UnicodeDecodeError:
                continue
            content = original
            for old in prefixes:
                content = content.replace(old, str(target))
            if content != original:
                script.write_text(content)
                changed.append(str(script.relative_to(root)))
        subprocess.run([str(target / "bin/python"), "-c",
                        "import sys; print(sys.prefix)"], check=True)
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--resume", action="store_true",
                        help="verify and finish an existing staging copy")
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.record.exists():
        parser.error("record already exists; use a new filename")
    records = []
    for relative in ("apps/bin", "hardware/bender", "verification/tools"):
        target = root / relative
        if not target.is_symlink():
            backup = args.record.parent / (relative.replace("/", "_") + ".old-link")
            entry = {"path": relative, "action": "already_local"}
            if backup.is_symlink():
                entry["original_link"] = os.readlink(backup)
                entry["saved_link"] = str(backup)
            records.append(entry)
            continue
        source = target.resolve(strict=True)
        entry = {"path": relative, "source": str(source),
                 "original_link": os.readlink(target), "action": "planned"}
        records.append(entry)
        if not args.apply:
            continue
        staging = target.with_name(target.name + ".consolidating")
        exists = staging.exists() or staging.is_symlink()
        if exists and not args.resume:
            raise RuntimeError(f"staging path exists: {staging}; use --resume to verify it")
        if not exists and source.is_dir():
            # Dereference nested tool/venv links too, so old worktree deletion
            # cannot break the copied inputs. No RTL dependencies are copied.
            shutil.copytree(source, staging, symlinks=False)
        elif not exists:
            shutil.copy2(source, staging)
        old_files = tree_hashes(source) if source.is_dir() else None
        if old_files is not None:
            new_files = tree_hashes(staging)
            if old_files != new_files:
                raise RuntimeError(f"copy hash mismatch: {relative}")
            entry["copied_files"] = len(old_files)
        elif digest(source) != digest(staging):
            raise RuntimeError(f"copy hash mismatch: {relative}")
        # A directory cannot replace a symlink with rename on Linux. Retain
        # the old link alongside the journal, and restore it on failure.
        args.record.parent.mkdir(parents=True, exist_ok=True)
        backup = args.record.parent / (relative.replace("/", "_") + ".old-link")
        if backup.exists() or backup.is_symlink():
            raise RuntimeError(f"backup already exists: {backup}")
        target.rename(backup)
        try:
            staging.rename(target)
        except OSError:
            backup.rename(target)
            raise
        entry["saved_link"] = str(backup)
        entry["action"] = "copied_and_hash_verified"
    relocated = relocate_venvs(root) if args.apply else []
    args.record.parent.mkdir(parents=True, exist_ok=True)
    args.record.write_text(json.dumps({"root": str(root), "applied": args.apply,
                                      "relocated_venv_scripts": relocated,
                                      "inputs": records}, indent=2) + "\n")
    print(args.record)


if __name__ == "__main__":
    main()
