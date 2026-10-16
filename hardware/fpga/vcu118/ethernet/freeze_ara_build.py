#!/usr/bin/env python3
"""Freeze combined build inputs, never launch tools or modify the source package."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import xml.etree.ElementTree as ET

from ara_init import validate_firmware
from check_ara_xsa import check as check_xsa


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_relative(root, name):
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
        raise ValueError(f"Unsafe package path: {name}")
    path = root / relative
    if path.is_symlink() or not path.is_file() or root.resolve() not in path.resolve().parents:
        raise ValueError(f"Missing or external package input: {name}")
    return path


def freeze(package, bd, xsa, elf, metadata, output):
    inputs = json.loads(metadata.read_text(encoding="utf-8-sig"))
    recorded = {row["Path"].replace("\\", "/").split("/")[-1]: row["Hash"].lower() for row in inputs}
    for path, name in ((xsa, "loader_no_bitstream.xsa"), (elf, "fast_probe.elf")):
        if digest(path) != recorded.get(name):
            raise ValueError(f"Firmware build metadata mismatch: {name}")
    validate_firmware(elf.read_bytes(), recorded["fast_probe.elf"])
    with zipfile.ZipFile(xsa) as archive:
        check_xsa(ET.fromstring(archive.read("loader_bd.hwh")))
    design = json.loads(bd.read_text())["design"]
    if design["design_info"]["name"] != "loader_bd" or design["design_info"]["tool_version"] != "2020.1":
        raise ValueError("Unexpected loader BD")
    # The final BD was validated/import-tested without its private controller.
    if "xilinx.com:ip:ddr4:" in bd.read_text():
        raise ValueError("Loader BD contains a private MIG")
    selected = {}
    for row in (package / "SHA256SUMS").read_text().splitlines():
        _, name = row.split("  ", 1)
        selected[name] = checked_relative(package, name)
    # This previously measured sender is maintained in the exported software tree.
    for name in ("eth_fast_load.py", "eth_load.py"):
        selected["software/" + name] = checked_relative(package, "software/" + name)
    here = Path(__file__).resolve().parent
    for path in here.iterdir():
        if path.is_file() and path.suffix in (".py", ".tcl", ".ps1", ".md"):
            selected["ethernet/" + path.name] = path
    for path in (here / "firmware").iterdir():
        if path.is_file() and path.suffix in (".c", ".h"):
            selected["ethernet/firmware/" + path.name] = path
            if path.name in recorded and digest(path) != recorded[path.name]:
                raise ValueError(f"Firmware source changed since ELF build: {path.name}")
    selected.update({"ethernet/loader_bd/loader_bd.bd": bd,
                     "ethernet/artifacts/loader_no_bitstream.xsa": xsa,
                     "ethernet/artifacts/fast_probe.elf": elf,
                     "ethernet/artifacts/firmware_inputs.json": metadata})
    if len({name.casefold() for name in selected}) != len(selected):
        raise ValueError("Case-insensitive input collision")
    hashes = {name: digest(path) for name, path in selected.items()}
    output.mkdir(parents=True, exist_ok=False)
    target = output / "package"
    for name, path in selected.items():
        dest = target / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
        if digest(dest) != hashes[name] or digest(path) != hashes[name]:
            raise RuntimeError(f"Input changed while freezing: {name}; incomplete snapshot not runnable")
    # Verify all sources again to reject changes to an already-copied input.
    if any(digest(path) != hashes[name] for name, path in selected.items()):
        raise RuntimeError("Source inputs changed during freezing")
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    for tool in ("ara_load.py", "ara_init.py"):
        subprocess.run([sys.executable, str((target / "ethernet" / tool).resolve()), "--help"],
                       cwd=output, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       check=True, timeout=30)
    rows = "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes))
    (target / "SHA256SUMS").write_text(rows)
    report = {"profile": "host_ethernet", "files": len(hashes),
              "inventory_sha256": digest(target / "SHA256SUMS"),
              "firmware_sha256": recorded["fast_probe.elf"],
              "source_is_dirty_snapshot": True, "board_validated": False}
    (output / "snapshot.json").write_text(json.dumps(report, indent=2) + "\n")
    shutil.copyfile(here / "run_combined.ps1", output / "run_combined.ps1")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "bd", "xsa", "elf", "metadata", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(freeze(args.package, args.bd, args.xsa, args.elf, args.metadata, args.out), indent=2))
