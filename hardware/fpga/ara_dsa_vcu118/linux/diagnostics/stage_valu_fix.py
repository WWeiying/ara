#!/usr/bin/env python3
"""Clone sealed inputs only, replacing one hash-pinned VALU source."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

VALU = "rtl/ara/hardware/src/lane/valu.sv"
BASELINE = "6102c8979bf0b21786e512bb10a8985f7e8c0cd45a498dae3a7e266e32c1be5e"


def stage(source, target, replacement, replacement_sha, sync):
    source = source.resolve(strict=True)
    target = target.absolute()
    if target.exists() or source == target or source in target.parents:
        raise RuntimeError("Use a new directory outside the original package")
    hashes = sync.read_hashes(source)
    sync.check_case_collisions(source, hashes)
    if hashes.get(VALU) != BASELINE:
        raise RuntimeError("Not the reviewed original VALU baseline")
    data = replacement.read_bytes()
    if hashlib.sha256(data).hexdigest() != replacement_sha:
        raise RuntimeError("Replacement SHA256 mismatch")
    for name, expected in hashes.items():
        if sync.digest(sync.safe_path(source, name)) != expected:
            raise RuntimeError(f"Original input changed: {name}")
    target.mkdir(parents=True)
    for name, expected in hashes.items():
        payload = sync.safe_path(source, name).read_bytes()
        if hashlib.sha256(payload).hexdigest() != expected:
            raise RuntimeError(f"Original input changed during copy: {name}")
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data if name == VALU else payload)
    record = "provenance/valu_queue_fix.json"
    if record in hashes:
        raise RuntimeError("Fix provenance already present")
    path = target / record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "source_package": str(source),
        "source_inventory_sha256": sync.digest(source / "SHA256SUMS"),
        "changed_input": VALU,
        "before": BASELINE,
        "after": replacement_sha,
        "reason": "Entry-local queue writes preserve held payload after synthesis",
        "board_validation": "pending",
    }, indent=2) + "\n", encoding="utf-8")
    hashes[VALU] = replacement_sha
    hashes[record] = sync.digest(path)
    (target / "SHA256SUMS").write_text(
        "".join(f"{hashes[n]}  {n}\n" for n in sorted(hashes)), encoding="utf-8")
    for name, expected in sync.read_hashes(target).items():
        if sync.digest(sync.safe_path(target, name)) != expected:
            raise RuntimeError(f"Staged input mismatch: {name}")
    print(f"STAGED {target}; {len(hashes)} inputs; only RTL change: {VALU}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("target", type=Path)
    p.add_argument("replacement", type=Path)
    p.add_argument("--sha256", required=True)
    p.add_argument("--sync-helper", required=True, type=Path)
    a = p.parse_args()
    spec = importlib.util.spec_from_file_location("fpga_sync", a.sync_helper)
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    stage(a.source, a.target, a.replacement, a.sha256, sync)


if __name__ == "__main__":
    main()
