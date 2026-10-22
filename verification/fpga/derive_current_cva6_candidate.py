#!/usr/bin/env python3
"""Seal the current CVA6 STVEC source into an otherwise unchanged SoC package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from fpga.derive_current_rtl_candidate import audit_rtl_tree
from fpga.derive_sim_linux_candidate import check_seal
from fpga.prepare_linux_bundle import file_record, plain_path
from fpga.prepare_soc_candidate import ROOT, seal


CVA6_PREFIX = "rtl/cva6/"
ARA_PREFIX = "rtl/ara/hardware/src/"
STVEC_SOURCE = "core/csr_regfile.sv"


def cva6_differences(package: Path, source: Path) -> dict[str, dict[str, str]]:
    changed = {}
    for frozen in (package / CVA6_PREFIX).rglob("*"):
        if not frozen.is_file():
            continue
        name = frozen.relative_to(package / CVA6_PREFIX).as_posix()
        current = source / name
        if not current.is_file():
            continue
        old_sha = file_record(frozen)["sha256"]
        new_sha = file_record(current)["sha256"]
        if old_sha != new_sha:
            changed[name] = {"old_sha256": old_sha, "new_sha256": new_sha,
                             "source": str(current.resolve())}
    if set(changed) != {STVEC_SOURCE}:
        raise ValueError(f"unreviewed CVA6 differences: {sorted(changed)}")
    return changed


def derive(base: Path, output: Path, root: Path = ROOT) -> dict:
    base, output, root = map(plain_path, (base, output, root))
    out_root = root / "verification/out"
    if (not base.is_relative_to(out_root) or not output.is_relative_to(out_root)
            or output == out_root or output.exists() or output.is_relative_to(base)):
        raise ValueError("base and output must be distinct verification/out paths")
    check_seal(base)
    audit_rtl_tree(base / ARA_PREFIX, root / "hardware/src", frozenset())
    changed = cva6_differences(base, root / "hardware/deps/cva6")
    package = output / "package"
    package.parent.mkdir(parents=True)
    shutil.copytree(base, package, symlinks=False)
    name = STVEC_SOURCE
    target_name = CVA6_PREFIX + name
    shutil.copyfile(changed[name]["source"], package / target_name)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_rows = {row["file"]: row for row in manifest["source_hashes_before_integration"]}
    if source_rows[target_name]["source_sha256"] != changed[name]["old_sha256"]:
        raise ValueError("base source manifest does not match frozen STVEC RTL")
    source_rows[target_name]["source_sha256"] = changed[name]["new_sha256"]
    manifest["simulation_only_current_cva6_overlay"] = {
        "base_manifest_sha256": file_record(base / "manifest.json")["sha256"],
        "base_seal_sha256": file_record(base / "SHA256SUMS")["sha256"],
        "changed_sources": changed,
        "scope": "VCS SoC simulation only; not FPGA or Linux signoff",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    seal(package)
    check_seal(package)
    audit_rtl_tree(package / ARA_PREFIX, root / "hardware/src", frozenset())
    if file_record(package / target_name)["sha256"] != changed[name]["new_sha256"]:
        raise ValueError("current CVA6 STVEC source was not preserved")
    report = {"status": "PREPARED_NOT_RUN", "package": str(package),
              "changed_sources": changed,
              "manifest_sha256": file_record(manifest_path)["sha256"],
              "seal_sha256": file_record(package / "SHA256SUMS")["sha256"]}
    (output / "derivation.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(derive(args.base_package, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
