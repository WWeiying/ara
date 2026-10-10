#!/usr/bin/env python3
"""Derive a sealed VCS SoC package using the current Ara RTL sources."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fpga.derive_sim_linux_candidate import check_seal
from fpga.prepare_linux_bundle import file_record, plain_path
from fpga.prepare_soc_candidate import PRESERVE, ROOT, seal


RTL_PREFIX = "rtl/ara/hardware/src/"
INCLUDE_PREFIX = "rtl/ara/hardware/include/"
EXPECTED_DIFFERENCES = frozenset({
    "sldu/sldu.sv",
    "vlsu/akv/akv_engine.sv",
    "vlsu/qbs/qbs_engine.sv",
})
HOST_ONLY = frozenset({"accel_dispatcher_ideal.sv", "ara_soc.sv", "ara_system.sv"})


def audit_rtl_tree(package_rtl: Path, current_rtl: Path,
                   expected_differences: frozenset[str] = EXPECTED_DIFFERENCES,
                   host_only: frozenset[str] = HOST_ONLY
                   ) -> dict[str, dict[str, str]]:
    frozen = {path.relative_to(package_rtl).as_posix(): path
              for path in package_rtl.rglob("*") if path.is_file()}
    current = {path.relative_to(current_rtl).as_posix(): path
               for path in current_rtl.rglob("*") if path.is_file()}
    if set(frozen) - set(current) or set(current) - set(frozen) != host_only:
        raise ValueError("Ara RTL file inventory differs from the reviewed SoC package")
    changed = {}
    for name, source in current.items():
        if name not in frozen:
            continue
        new_sha = file_record(source)["sha256"]
        old_sha = file_record(frozen[name])["sha256"]
        if new_sha != old_sha:
            changed[name] = {"old_sha256": old_sha, "new_sha256": new_sha,
                             "source": str(source.resolve())}
    if set(changed) != expected_differences:
        raise ValueError(f"unreviewed Ara RTL changes: {sorted(set(changed) ^ expected_differences)}")
    return changed


def check_base_source_record(target: str, record: dict[str, str],
                             source_sha: str) -> None:
    if source_sha in {record["old_sha256"], record["new_sha256"]}:
        return
    if PRESERVE.get(target) != record["old_sha256"]:
        raise ValueError(f"base source manifest differs: {target}")
    record["pre_integration_source_sha256"] = source_sha


def derive(base: Path, output: Path, root: Path = ROOT,
           expected_differences: frozenset[str] = EXPECTED_DIFFERENCES,
           expected_include_differences: frozenset[str] = frozenset()) -> dict:
    base, output, root = map(plain_path, (base, output, root))
    out_root = root / "verification/out"
    if (not base.is_relative_to(out_root) or not output.is_relative_to(out_root)
            or output == out_root or output.exists() or output.is_relative_to(base)):
        raise ValueError("base and new output must be distinct verification/out paths")
    check_seal(base)
    changed = audit_rtl_tree(base / RTL_PREFIX, root / "hardware/src",
                             expected_differences)
    changed_include = audit_rtl_tree(base / INCLUDE_PREFIX, root / "hardware/include",
                                     expected_include_differences, frozenset())
    base_manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    source_hashes = {row["file"]: row for row in base_manifest["source_hashes_before_integration"]}
    for name, record in changed.items():
        target = RTL_PREFIX + name
        check_base_source_record(target, record, source_hashes[target]["source_sha256"])
    for name, record in changed_include.items():
        target = INCLUDE_PREFIX + name
        check_base_source_record(target, record, source_hashes[target]["source_sha256"])
    package = output / "package"
    package.parent.mkdir(parents=True)
    shutil.copytree(base, package, symlinks=False)
    for name, record in changed.items():
        shutil.copyfile(record["source"], package / RTL_PREFIX / name)
    for name, record in changed_include.items():
        shutil.copyfile(record["source"], package / INCLUDE_PREFIX / name)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_hashes = {row["file"]: row for row in manifest["source_hashes_before_integration"]}
    for name, record in changed.items():
        target = RTL_PREFIX + name
        source_hashes[target]["source_sha256"] = record["new_sha256"]
    for name, record in changed_include.items():
        target = INCLUDE_PREFIX + name
        source_hashes[target]["source_sha256"] = record["new_sha256"]
    manifest["simulation_only_current_rtl_overlay"] = {
        "base_manifest_sha256": file_record(base / "manifest.json")["sha256"],
        "base_seal_sha256": file_record(base / "SHA256SUMS")["sha256"],
        "changed_sources": {**{RTL_PREFIX + name: record for name, record in changed.items()},
                            **{INCLUDE_PREFIX + name: record for name, record in changed_include.items()}},
        "scope": "VCS SoC simulation only; not FPGA or Linux signoff",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    seal(package)
    check_seal(package)
    if audit_rtl_tree(package / RTL_PREFIX, root / "hardware/src", frozenset()):
        raise ValueError("derived package still differs from current Ara RTL")
    if audit_rtl_tree(package / INCLUDE_PREFIX, root / "hardware/include",
                      frozenset(), frozenset()):
        raise ValueError("derived package still differs from current Ara includes")
    report = {"status": "PREPARED_NOT_RUN", "package": str(package),
              "changed_sources": {**{RTL_PREFIX + name: record for name, record in changed.items()},
                                  **{INCLUDE_PREFIX + name: record for name, record in changed_include.items()}},
              "manifest_sha256": file_record(manifest_path)["sha256"],
              "seal_sha256": file_record(package / "SHA256SUMS")["sha256"]}
    (output / "derivation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                             encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expect-difference", action="append", default=[],
                        help="exact Ara RTL relative path expected to differ from the base; "
                             "repeat for multiple files")
    parser.add_argument("--expect-include-difference", action="append", default=[],
                        help="exact Ara include relative path expected to differ from the base")
    args = parser.parse_args()
    expected = (frozenset(args.expect_difference) if args.expect_difference
                else EXPECTED_DIFFERENCES)
    print(json.dumps(derive(args.base_package, args.output,
                            expected_differences=expected,
                            expected_include_differences=frozenset(args.expect_include_difference)),
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
