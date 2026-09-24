#!/usr/bin/env python3
"""Bounded protocol test of exported xbar/atomics/LLC, not a board acceptance test."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verilator", default="verilator")
    args = parser.parse_args()
    tool = shutil.which(args.verilator)
    if not tool:
        parser.error("Verilator not found; supply --verilator")
    tests = Path(__file__).resolve().parent
    hardware = tests.parents[2]
    package = hardware / "fpga/ara_dsa_vcu118"
    manifest = json.loads((package / "manifest.json").read_text())
    groups = ("rtl/common_cells/", "rtl/axi/", "rtl/axi_llc/", "rtl/axi_riscv_atomics/")
    files = [package / name for name in manifest["files"]
             if name.startswith(groups) or "/prim_subreg" in name]
    files += [hardware / "deps/tech_cells_generic/src/rtl/tc_sram.sv",
              package / "rtl/board/dram_wrapper_xilinx.sv",
              tests / "host_mig_boundary_model.sv",
              tests / "host_burst_path_tb.sv"]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Exported tag-store reset uses default:'0 for an enum-bearing struct.
    command = [tool, "--binary", "--timing", "--assert", "-Wno-fatal", "-Wno-ENUMVALUE", "-j", "4",
               "--top-module", "host_burst_path_tb", "--Mdir", str(out / "obj"),
               "--timescale", "1ns/1ps", "+define+TARGET_VCU118"]
    command += ["-I" + str(package / inc) for inc in manifest["include_dirs"]]
    command += list(map(str, files))
    headers = sorted({p for inc in manifest["include_dirs"]
                      for p in (package / inc).rglob("*.svh")})
    provenance = files + headers + [Path(__file__).resolve(), package / "manifest.json",
                                    package / "software/reference/cheshire_bootrom.S"]
    record = {"scope": "host input -> xbar -> atomics -> cut -> LLC/SPM -> actual DDR wrapper -> modeled MIG AXI",
              "not_tested": ["vendor JTAG IP/host Tcl", "XPM/URAM", "MIG internals/DDR PHY", "physical timing/metastability",
                             "other active masters", "full CPU execution"],
              "command": command,
              "verilator_version": subprocess.check_output([tool, "--version"], text=True).strip(),
              "verilator_root": os.environ.get("VERILATOR_ROOT"),
              "inputs": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in provenance},
              "passed": False}
    try:
        with (out / "compile.log").open("w") as log:
            subprocess.run(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                           check=True, timeout=300)
        with (out / "run.log").open("w") as log:
            subprocess.run([str(out / "obj/Vhost_burst_path_tb")], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
        result = (out / "run.log").read_text()
        marker = next((line for line in result.splitlines()
                       if line.startswith("PASS: host burst path ")), None)
        if marker is None:
            raise RuntimeError("Missing completion marker")
        record["passed"] = True
        record["result"] = marker
        print(marker)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
        record["error"] = str(exc)
        raise SystemExit(f"FAILED: inspect {out}/compile.log and run.log") from None
    finally:
        (out / "result.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"Evidence: {out}")


if __name__ == "__main__":
    main()
