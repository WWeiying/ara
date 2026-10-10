#!/usr/bin/env python3
"""Derive a sealed simulation-only SoC package with a matched Linux bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "verification"))
from fpga.prepare_linux_bundle import file_record, plain_path, tree_records
from fpga.prepare_soc_candidate import seal

ARTIFACTS = ("Image", "ara_vcu118.dtb", "fw_jump.elf", "initramfs.cpio")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_seal(package: Path) -> dict[str, str]:
    rows = {}
    for line in (package / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        sha, name = line.split("  ", 1)
        if name in rows or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("invalid package seal")
        rows[name] = sha
    actual = tree_records(package, exclude_build=False)
    if set(actual) != set(rows) | {"SHA256SUMS"}:
        raise ValueError("package seal has missing or extra files")
    if any(actual[name]["sha256"] != sha for name, sha in rows.items()):
        raise ValueError("package seal differs from files")
    return rows


def derive(base: Path, bundle: Path, output: Path) -> dict:
    base, bundle, output = map(plain_path, (base, bundle, output))
    out_root = plain_path(ROOT / "verification/out")
    if (not base.is_relative_to(out_root) or not bundle.is_relative_to(out_root)
            or not output.is_relative_to(out_root) or output == out_root
            or output.exists() or output.is_relative_to(base)
            or output.is_relative_to(bundle)):
        raise ValueError("base, bundle and new output must be distinct verification/out paths")
    check_seal(base)
    manifest_path = bundle / "manifest.json"
    bundle_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if bundle_manifest.get("status") != "PREPARED_NOT_BOOTED":
        raise ValueError("Linux bundle is not prepared")
    quiet_opensbi = bundle_manifest.get("quiet_opensbi", False)
    if type(quiet_opensbi) is not bool:
        raise ValueError("invalid OpenSBI boot-print setting")
    firmware_commands = [row["argv"] for row in bundle_manifest.get("commands", [])
                         if row.get("argv") and row.get("argv")[-1] == "all"]
    if quiet_opensbi and not any("FW_OPTIONS=0x1" in argv for argv in firmware_commands):
        raise ValueError("quiet OpenSBI was not built with FW_OPTIONS=0x1")
    if bundle_manifest.get("sim_ram_mib") not in (256, 512, 1024):
        raise ValueError("simulation-only Linux bundle requires reduced RAM")
    if bundle_manifest.get("dtb_properties", {}).get("/memory@80000000/reg") != [
            0, 0x80000000, 0, bundle_manifest["sim_ram_mib"] * 1024 * 1024]:
        raise ValueError("Linux DTB RAM geometry differs from declared simulation size")
    for name in ARTIFACTS:
        if file_record(bundle / name)["sha256"] != bundle_manifest["files"][name]["sha256"]:
            raise ValueError(f"Linux bundle artifact changed: {name}")
    dtb = (bundle / "ara_vcu118.dtb").read_bytes()
    firmware = (bundle / "fw_jump.elf").read_bytes()
    embedded = bundle_manifest["embedded_dtb"]
    offset = embedded["file_offset"]
    if (firmware[offset:offset + len(dtb)] != dtb or
            embedded["dtb_sha256"] != digest(dtb)):
        raise ValueError("OpenSBI embedded DTB differs from external DTB")
    initial_rtl = {name: row["sha256"] for name, row in
                   tree_records(base, exclude_build=False).items() if name.startswith("rtl/")}
    package = output / "package"
    package.parent.mkdir(parents=True)
    shutil.copytree(base, package, symlinks=False)
    old = {}
    new = {}
    for name in ARTIFACTS:
        target = package / "linux/artifacts" / name
        old[name] = file_record(target)["sha256"]
        shutil.copyfile(bundle / name, target)
        new[name] = file_record(target)["sha256"]
    (package / "linux/artifacts/SHA256SUMS").write_text(
        "".join(f"{new[name]}  {name}\n" for name in ARTIFACTS), encoding="ascii")
    candidate_manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    candidate_manifest["simulation_only_linux_override"] = {
        "base_manifest_sha256": file_record(base / "manifest.json")["sha256"],
        "base_seal_sha256": file_record(base / "SHA256SUMS")["sha256"],
        "bundle_manifest_sha256": file_record(manifest_path)["sha256"],
        "sim_ram_mib": bundle_manifest["sim_ram_mib"],
        "quiet_opensbi": quiet_opensbi,
        "old_artifacts": old,
        "new_artifacts": new,
        "rtl_unchanged": True,
    }
    (package / "manifest.json").write_text(
        json.dumps(candidate_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seal(package)
    check_seal(package)
    final_rtl = {name: row["sha256"] for name, row in
                 tree_records(package, exclude_build=False).items() if name.startswith("rtl/")}
    if final_rtl != initial_rtl:
        raise ValueError("derived package changed RTL")
    report = {"status": "PREPARED_NOT_RUN", "package": str(package),
              "sim_ram_mib": bundle_manifest["sim_ram_mib"],
              "manifest_sha256": file_record(package / "manifest.json")["sha256"],
              "seal_sha256": file_record(package / "SHA256SUMS")["sha256"],
              "rtl_unchanged": True}
    (output / "derivation.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-package", type=Path, required=True)
    parser.add_argument("--linux-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(derive(args.base_package, args.linux_bundle, args.output), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
