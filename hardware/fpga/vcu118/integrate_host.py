#!/usr/bin/env python3
"""Apply only optional host/DDR board additions to an existing exported snapshot.

Unlike a full export this preserves the snapshot's CPU/Ara fixes and all
unrelated working-tree changes. SHA256SUMS for unrelated files are untouched.
"""
import argparse
import hashlib
import json
from pathlib import Path

from host_debug_fpga import patch_soc_debug
from ddr2_fpga import patch_ddr2


def apply(package, refresh_checksums=False):
    here = Path(__file__).resolve().parent
    updated = set()

    def write(name, data):
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
        updated.add(name)

    manifest = json.loads((package / "manifest.json").read_text())
    for path in sorted((here / "rtl").glob("*.sv")):
        name = "rtl/board/" + path.name
        write(name, path.read_bytes())
        if name not in manifest["files"]:
            manifest["files"].append(name)
    name = "rtl/cheshire/hw/cheshire_soc.sv"
    write(name, patch_soc_debug((package / name).read_text()).encode())
    name = "rtl/board/dram_wrapper_xilinx.sv"
    text = (package / name).read_text()
    if "parameter int unsigned Channel = 0" not in text:
        text = patch_ddr2(text)
    write(name, text.encode())
    write("manifest.json", (json.dumps(manifest, indent=2) + "\n").encode())
    # Regenerate the manifest-derived source list, including existing fields.
    def tcl_list(values):
        if any(any(c in str(v) for c in "{}\\\n") for v in values):
            raise ValueError("Unsafe source path/define")
        separator = " " + chr(92) + "\n    "
        return "[list " + separator.join("{" + str(v) + "}" for v in values) + "]"
    lines = ["# Generated from manifest.json. All paths are package-relative.",
             "set rtl_files " + tcl_list(manifest["files"]),
             "set rtl_include_dirs " + tcl_list(manifest["include_dirs"]),
             "set rtl_defines " + tcl_list([k if v is None else f"{k}={v}"
                 for k, v in manifest["defines"].items()])]
    write("scripts/sources.tcl", ("\n".join(lines) + "\n").encode())
    scripts = (
        "config.tcl", "common.tcl", "constraint_checks.tcl", "create_project.tcl",
        "create_ip.tcl", "run_support.tcl", "run.ps1", "create_profile.ps1",
        "prepare_profile.tcl", "write_profile_bit.ps1", "write_profile_bit.tcl",
    )
    for name in scripts:
        write("scripts/" + name, (here / "scripts" / name).read_bytes())
    for path in sorted((here / "software").glob("host_*")):
        if path.is_file():
            write("software/" + path.name, path.read_bytes())
    for name in ("constraints/cdc.xdc", "software/fpga_debug.h", "docs/HOST_WORKFLOW.md"):
        write(name, (here / name).read_bytes())
    sums = {}
    for line in (package / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    # Explicit opt-in seals the current package contents, including preserved
    # pre-existing work. It does not overwrite those files or assert test PASS.
    for name in set(sums) | updated if refresh_checksums else updated:
        sums[name] = hashlib.sha256((package / name).read_bytes()).hexdigest()
    write("SHA256SUMS", "".join(f"{sums[n]}  {n}\n" for n in sorted(sums)).encode())
    suffix = "all existing checksums refreshed" if refresh_checksums else "unrelated checksums preserved"
    print(f"Updated {len(updated)-1} feature files; {suffix}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--refresh-checksums", action="store_true",
                        help="Seal current contents of all existing checksum-listed files")
    args = parser.parse_args()
    apply(args.package.resolve(), args.refresh_checksums)
