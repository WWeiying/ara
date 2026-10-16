#!/usr/bin/env python3
"""Create an offline image plan and source snapshot for future Ara integration."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
FPGA = HERE.parents[1]
SOFTWARE = FPGA / "ara_dsa_vcu118/software"
sys.path.insert(0, str(SOFTWARE))
from host_image import CAP_HOST, prepare_image
from eth_load import parse_load

DDR_START = 0x80000000
DIAGNOSTIC_START = 0xFEFF0000
LOADER_START = 0xFF000000
DDR_END = 0x100000000


def validate_image(image):
    # This proposed integration map is stricter than the standalone loader map.
    for segment in image.segments:
        if not DDR_START <= segment.address < segment.address + segment.size <= DIAGNOSTIC_START:
            raise ValueError("Image overlaps planned diagnostic/loader reservation or leaves DDR1: "
                             f"0x{segment.address:x}+0x{segment.size:x}")


def source_files():
    files = {path for path in HERE.rglob("*") if path.is_file() and
             path.suffix in {".c", ".h", ".sv", ".tcl", ".xdc", ".py", ".md"}}
    files.update(SOFTWARE / name for name in (
        "eth_fast_load.py", "eth_load.py", "host_image.py", "host_load.py",
        "host_transport.py", "host_vivado.tcl", "host_smoke.elf",
        "host_start.S", "host_smoke.ld", "fpga_debug.h"))
    package = FPGA / "ara_dsa_vcu118"
    files.update(package / name for name in (
        "rtl/board/ara_dsa_vcu118.sv", "rtl/board/dram_wrapper_xilinx.sv",
        "rtl/board/ara_host_bridge.sv", "rtl/board/ara_fpga_debug.sv",
        "constraints/board.xdc", "scripts/create_ip.tcl", "scripts/config.tcl",
        "software/reference/cheshire_bootrom.c", "software/reference/cheshire_bootrom.S"))
    return sorted(files)


def prepare(elf, loads, output):
    image = prepare_image(elf, loads, caps=CAP_HOST)
    validate_image(image)
    inputs = source_files()
    for path in inputs:
        if not path.is_file():
            raise ValueError(f"Missing preparation input: {path}")
    output.mkdir(parents=True, exist_ok=False)
    inventory = []
    with zipfile.ZipFile(output / "sources.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for path in inputs:
            data = path.read_bytes()
            name = path.relative_to(FPGA).as_posix()
            archive.writestr(name, data)
            inventory.append({"path": name, "bytes": len(data),
                              "sha256": hashlib.sha256(data).hexdigest()})
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=FPGA,
                            capture_output=True, text=True)
    report = {
        "state": "offline_preparation_complete_integration_not_validated",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head": result.stdout.strip() if result.returncode == 0 else None,
        "provenance": "Source hashes include uncommitted files; git HEAD alone is insufficient.",
        "hardware_validated": False, "launch_allowed": False,
        "image": image.manifest(),
        "payload_bytes_including_bss": sum(s.size for s in image.segments),
        "proposed_regions_half_open": {
            "application": [DDR_START, DIAGNOSTIC_START],
            "diagnostic": [DIAGNOSTIC_START, LOADER_START],
            "loader_private": [LOADER_START, DDR_END]},
        "legacy_jtag_preflight_conflicts": {"address": 0xFFFF0000,
                                            "region": "loader_private"},
        "sources": inventory,
        "sources_zip_sha256": hashlib.sha256((output / "sources.zip").read_bytes()).hexdigest(),
        "remaining_gates": [
            "Single shared C1 MIG and checked global-to-bank address translation",
            "DDR arbitration, ID conversion, CDC and common reset validation",
            "Hardware write admission, network/DMA drain and no-write launch lock",
            "Cold passive boot and CPU/LLC cache visibility validation",
            "Matching integrated bitstream/firmware identity and reserved-region enforcement",
            "Relocated JTAG preflight and verified network-load/JTAG-launch orchestration",
            "Route timing, DRC, CDC and integrated board acceptance"],
    }
    (output / "plan.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--elf", type=Path, default=SOFTWARE / "host_smoke.elf")
    parser.add_argument("--load", action="append", type=parse_load, default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = prepare(args.elf, args.load, args.out)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"PREPARATION_FAILED: {exc}", file=sys.stderr)
        return 1
    print(report["state"])
    print(f"PAYLOAD_BYTES {report['payload_bytes_including_bss']}")
    print(f"SOURCE_FILES {len(report['sources'])}")
    print(f"EVIDENCE {args.out.resolve()}")
    print("No Vivado, board access, reset, transfer or launch was performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
