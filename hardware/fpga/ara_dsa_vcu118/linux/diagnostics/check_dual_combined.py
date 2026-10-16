"""Check actual staged wrappers with two vendor PHY stubs and one loader stub."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TESTS = Path(__file__).resolve().parents[3] / "vcu118/tests"
sys.path.insert(0, str(TESTS))
from check_ddr2 import WRAPPER_TB, vendor_stub

LOADER = """
package loader_count;
  int instances = 0;
endpackage
module ara_eth_loader #(parameter type req_t=logic, rsp_t=logic)(
 input logic sys_clk_i, sys_rst_i, ui_clk_i, ui_resetn_i,
 output req_t req_o, input rsp_t rsp_i, input logic [255:0] status_i,
 output logic lock_o,
 input logic eth_ref_p, eth_ref_n, eth_rxp, eth_rxn,
 output logic eth_txp, eth_txn, eth_mdc, eth_phy_reset_n,
 inout wire eth_mdio
);
 initial loader_count::instances++;
 assign req_o='0;
 assign lock_o=0;
 assign {eth_txp,eth_txn,eth_mdc,eth_phy_reset_n}='0;
 assign eth_mdio=1'bz;
endmodule
"""


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    pkg, out = a.package.resolve(), a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((pkg / "manifest.json").read_text())
    files = [pkg / f for f in manifest["files"] if f.startswith(("rtl/common_cells/", "rtl/axi/"))]
    files += [pkg / "rtl/board/dram_wrapper_xilinx.sv", pkg / "rtl/board/ara_eth_shared_ddr.sv"]
    incs = ["+incdir+" + str(pkg / d) for d in manifest["include_dirs"]]
    incs.append("+incdir+" + str(pkg / "rtl/board"))
    stubs = out / "vendor_stubs.sv"
    stubs.write_text(vendor_stub("ddr4") + vendor_stub("ddr4_c2") + LOADER)
    tb = out / "combined_tb.sv"
    tb.write_text(WRAPPER_TB.replace('    $display("PASS: DDR',
        '    if (loader_count::instances != 1) $fatal(1, "Expected exactly one Ethernet loader");\n'
        '    $display("PASS: DDR'))
    cmd = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps",
           "+define+SYNTHESIS+VCS+TARGET_VCU118+ARA_FPGA_DDR2+ARA_FPGA_ETHERNET",
           *incs, "-top", "wrapper_tb", *map(str, files), str(stubs), str(tb), "-o", "simv"]
    with (out / "compile.log").open("w") as log:
        subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv")], cwd=out, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=30)
    result = (out / "run.log").read_text()
    if "PASS: DDR" not in result:
        raise RuntimeError("Missing success marker")
    report = {"passed": True, "scope": "Real staged wrappers, one loader, coupled reset; vendor PHY and loader stubbed",
              "sources": {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files + [stubs, tb]}}
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(result)


if __name__ == "__main__":
    main()
