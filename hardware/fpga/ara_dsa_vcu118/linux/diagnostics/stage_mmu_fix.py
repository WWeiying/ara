#!/usr/bin/env python3
"""Freeze an MMU-only repair against a verified, unchanged build package."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

MMU = "rtl/cva6/core/cva6_mmu/cva6_mmu.sv"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def stage(source, target, replacement):
    source = source.resolve(strict=True)
    target = target.absolute()
    if target.exists() or source == target or source in target.parents:
        raise ValueError("Use a new output outside the sealed source package")
    inventory = (source / "SHA256SUMS").read_bytes()
    files = {}
    for row in inventory.decode().splitlines():
        expected, name = row.split("  ", 1)
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Unsafe inventory path")
        data = (source / name).read_bytes()
        if digest(data) != expected:
            raise ValueError("Input hash mismatch: " + name)
        if name in files:
            raise ValueError("Duplicate inventory path")
        files[name] = data
    before = files[MMU]
    after = replacement.read_bytes()
    if before == after:
        raise ValueError("Replacement does not change MMU")
    files[MMU] = after
    record = "provenance/mmu_ppn_fix.json"
    if record in files:
        raise ValueError("Already contains MMU repair provenance")
    files[record] = (json.dumps({
        "source_package": str(source),
        "source_inventory_sha256": digest(inventory),
        "changed_rtl": MMU,
        "before_sha256": digest(before), "after_sha256": digest(after),
        "reason": "Current-lookup superpage PPN uses PA bits shifted by 12",
        "hardware_validated": False,
    }, indent=2) + "\n").encode()
    target.mkdir(parents=True)
    for name, data in files.items():
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
    (target / "SHA256SUMS").write_text("".join(
        f"{digest(files[name])}  {name}\n" for name in sorted(files)))
    print(f"STAGED {target}; {len(files)} sealed files; only changed RTL: {MMU}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("target", type=Path)
    p.add_argument("replacement", type=Path)
    a = p.parse_args()
    stage(a.source, a.target, a.replacement)
