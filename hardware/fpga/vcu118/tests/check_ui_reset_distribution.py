"""Cycle-level reset test extracted from the real wrapper, with real rstgen RTL."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from ui_reset_fpga import patch_ui_reset_distribution

TB = r'''
module tb;
  timeunit 1ns; timeprecision 1ps;
  logic c0=0, c1=0, run0=1, run1=1, sys=0, allow=0, cal0=1, cal1=1;
  always #3 if (run0) c0=~c0;
  always #4 if (run1) c1=~c1;
  wire r0, r1, u0, u1;
  wire coupled = allow & r0 & r1;
  reset_dut d0(c0,sys,1'b0,cal0,coupled,r0,u0);
  reset_dut d1(c1,sys,1'b0,cal1,coupled,r1,u1);
  int n0=0, n1=0, checks=0;
  // Count from the actual synchronizer input, not from system reset latency.
  always @(posedge c0 or negedge coupled) begin
    if (!coupled) n0<=0; else if (n0<5) n0<=n0+1;
  end
  always @(posedge c1 or negedge coupled) begin
    if (!coupled) n1<=0; else if (n1<5) n1<=n1+1;
  end
  // Sampling delay must not block the counter's asynchronous reset event.
  always @(posedge c0 or negedge coupled) begin
    #0.001;
    if (u0 !== (n0==5)) $fatal(1,"C1 release must take exactly five UI edges");
    checks++;
  end
  always @(posedge c1 or negedge coupled) begin
    #0.001;
    if (u1 !== (n1==5)) $fatal(1,"C2 release must take exactly five UI edges");
    checks++;
  end
  task automatic released;
    #160;
    if (!u0 || !u1) $fatal(1,"Reset release deadlock");
  endtask
  initial begin
    #1; sys=1; #2; sys=0; allow=1; released();
    for (int phase=1; phase<=100; phase++) begin
      // Fractional phase avoids an undefined testbench/DUT active-edge race.
      @(negedge c0); #(phase%13+0.25); allow=0; #0.01;
      if (u0 || u1) $fatal(1,"Reset assertion waited for a clock");
      #1; allow=1; released();
    end
    @(negedge c0); run0=0;
    @(negedge c1); run1=0;
    #1; allow=0; #0.01;
    if (u0 || u1) $fatal(1,"Reset assertion failed with clocks stopped");
    allow=1; #100;
    if (u0 || u1) $fatal(1,"Reset released without clock");
    run0=1; #100;
    if (!u0 || u1) $fatal(1,"Cross-domain release coupled to wrong clock");
    run1=1; released();
    cal1=0; #12;
    if (u0 || u1 || !r0) $fatal(1,"Calibration failure did not reset both interfaces");
    cal1=1; released();
    @(negedge c0); run0=0;
    @(negedge c1); run1=0;
    sys=1; #0.01;
    if (u0 || u1 || r0 || r1) $fatal(1,"Stopped-clock system reset failed");
    sys=0; #80;
    if (u0 || u1) $fatal(1,"POR released without clock");
    run0=1; run1=1; released();
    $display("PASS UI_RESET_DISTRIBUTION checks=%0d phases=100",checks);
    $finish;
  end
  initial begin #50000; $fatal(1,"Watchdog"); end
endmodule
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    p.add_argument("--candidate", action="store_true")
    p.add_argument("--package", type=Path, help="Test a sealed staged package instead of the worktree")
    a = p.parse_args()
    pkg = a.package.resolve() if a.package else HERE.parents[1] / "ara_dsa_vcu118"
    wrapper = pkg / "rtl/board/dram_wrapper_xilinx.sv"
    text = wrapper.read_text()
    if a.candidate:
        text = patch_ui_reset_distribution(text)
    start, end = "  logic ui_resetn;", "  // Signals before resizing"
    if text.count(start)!=1 or text.count(end)!=1:
        raise ValueError("Ambiguous reset block")
    block = start + text.split(start)[1].split(end)[0]
    dut = '''module reset_dut(input logic dram_axi_clk, sys_rst_i, dram_rst_o,
      calib_complete, fabric_reset_ni, output logic fabric_ready_o, output wire reset_out);
    ''' + block + "\n assign reset_out=ui_resetn;\nendmodule\n"
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = []
    for name in ("rstgen.sv", "rstgen_bypass.sv"):
        src = pkg / "rtl/common_cells/src" / name
        dest = out / name
        dest.write_bytes(src.read_bytes())
        sources.append(dest)
    (out / "dut.sv").write_text(dut)
    (out / "tb.sv").write_text(TB)
    sources += [out / "dut.sv", out / "tb.sv"]
    cmd = ["vcs", "-full64", "-sverilog", "-timescale=1ns/1ps", "+define+SYNTHESIS+ARA_FPGA_DDR2",
           "-top", "tb", *map(str,sources), "-o", "simv"]
    with (out / "compile.log").open("w") as log:
        subprocess.run(cmd,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=180)
    with (out / "run.log").open("w") as log:
        subprocess.run([str(out / "simv")],cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30)
    log = (out / "run.log").read_text()
    if "PASS UI_RESET_DISTRIBUTION" not in log:
        raise RuntimeError("Missing pass marker")
    report = {"passed":True,"candidate":a.candidate,
              "scope":"Digital reset sequencing only; not physical timing or analog metastability signoff",
              "wrapper_sha256":hashlib.sha256(wrapper.read_bytes()).hexdigest(),
              "sources":{s.name:hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}}
    (out / "result.json").write_text(json.dumps(report,indent=2)+"\n")
    print(log)


if __name__ == "__main__":
    main()
