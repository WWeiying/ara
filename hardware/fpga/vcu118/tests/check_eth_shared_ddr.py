#!/usr/bin/env python3
"""Bounded protocol test of the actual shared DDR integration, without vendor PHY."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--vcs", default="vcs")
    parser.add_argument("--static-ids", action="store_true")
    parser.add_argument("--single-loader-id", action="store_true",
                        help="Compare fixed-ID specialization cycle-by-cycle with generic protection")
    parser.add_argument("--id-order-check", action="store_true")
    parser.add_argument("--counter-check", action="store_true")
    parser.add_argument("--range-check", action="store_true",
                        help="Exhaustive address-protection equivalence instead of protocol test")
    args = parser.parse_args()
    if args.range_check and (args.static_ids or args.id_order_check):
        parser.error("Range equivalence and protocol modes must be run separately")
    if args.single_loader_id and (not args.static_ids or args.id_order_check or args.range_check):
        parser.error("--single-loader-id requires --static-ids protocol mode")
    if args.counter_check and any((args.static_ids, args.single_loader_id, args.id_order_check, args.range_check)):
        parser.error("Counter equivalence must run separately")
    here = Path(__file__).resolve().parents[1]
    package = here.parent / "ara_dsa_vcu118"
    manifest = json.loads((package / "manifest.json").read_text())
    files = [package / p for p in manifest["files"]
             if p.startswith(("rtl/common_cells/", "rtl/axi/"))]
    files += [here / "rtl/ara_eth_shared_ddr.sv"]
    if args.counter_check:
        files += [here / "tests/eth_loader_counter_tb.sv"]
    elif args.id_order_check:
        files += [here / "tests/eth_shared_id_order_tb.sv"]
    elif args.range_check:
        files += [here / "tests/eth_shared_timing_top.sv", here / "tests/eth_shared_range_tb.sv"]
    else:
        files += [here / "tests/eth_shared_ddr_tb.sv"]
    includes = ["+incdir+" + str(package / p) for p in manifest["include_dirs"]]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    command = [args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
               *(["+define+TEST_STATIC_IDS"] if args.static_ids else []),
               *(["+define+TEST_LOADER_SINGLE_ID"] if args.single_loader_id else []),
               "+define+SYNTHESIS+VCS", *includes, "-top", "tb", *map(str, files), "-o", "simv"]
    with (output / "compile.log").open("w") as log:
        subprocess.run(command, cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=180)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv")], cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120 if args.range_check else 30)
    result = (output / "run.log").read_text()
    print(result)
    marker = "PASS: shared DDR range equivalence" if args.range_check else "PASS: shared DDR"
    if marker not in result:
        raise RuntimeError("Missing completion marker")
    (output / "result.json").write_text(json.dumps({
        "scope": ("Shared DDR address-protection equivalence" if args.range_check else
                  "Shared DDR protocol") + "; not PHY, timing, firmware or board acceptance",
        "static_ids": args.static_ids or args.id_order_check,
        "id_order_check": args.id_order_check,
        "single_loader_id": args.single_loader_id,
        "counter_check": args.counter_check,
        "sources": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "run_sha256": hashlib.sha256(result.encode()).hexdigest(),
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
