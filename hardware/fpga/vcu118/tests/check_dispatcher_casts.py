#!/usr/bin/env python3
"""Compare the original and exported VL expressions in a bounded VCS test."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export import patch_dispatcher_vlen_casts
from prepare import ROOT


def expression_module(source, name):
    avl = re.findall(r"csr_vl_d = \(\(\|acc_req_i\.rs1\[.*?;", source, re.S)
    slide = re.findall(r"if \(\|ara_req\.stride\[.*?;", source, re.S)
    if len(avl) != 1 or len(slide) != 2:
        raise RuntimeError("Unexpected dispatcher comparison sites")
    return f"""
module {name} #(parameter int unsigned VLEN = 1024,
  localparam type vlen_t = logic[$clog2(VLEN+1)-1:0]) (
  input logic [63:0] avl, stride,
  input logic [4:0] imm,
  input int unsigned vlmax,
  input vlen_t csr_vl_q,
  output vlen_t csr_vl_d,
  output logic null_vx, null_vi
);
  timeunit 1ns;
  timeprecision 1ps;
  typedef logic [63:0] elen_t;
  struct packed {{ logic [63:0] rs1; }} acc_req_i;
  struct packed {{ elen_t stride; }} ara_req;
  logic null_vslideup;
  always_comb begin
    acc_req_i.rs1 = avl;
    {avl[0]}
    ara_req.stride = stride;
    null_vslideup = 1'b0;
    {slide[0]}
    null_vx = null_vslideup;
    ara_req.stride = elen_t'(imm);
    null_vslideup = 1'b0;
    {slide[1]}
    null_vi = null_vslideup;
  end
endmodule
"""


TESTBENCH = r"""
module tb;
  timeunit 1ns;
  timeprecision 1ps;
  logic [10:0] done = '0;
  for (genvar p = 0; p < 11; p++) begin : gen_vlen
    localparam int VLEN = 64 << p;
    localparam int W = $clog2(VLEN+1);
    logic [63:0] avl, stride;
    logic [4:0] imm;
    int unsigned vlmax;
    logic [W-1:0] vl, old_vl, new_vl;
    logic old_vx, old_vi, new_vx, new_vi;
    int checks = 0;
    dispatcher_original #(.VLEN(VLEN)) original (
      .avl, .stride, .imm, .vlmax, .csr_vl_q(vl), .csr_vl_d(old_vl),
      .null_vx(old_vx), .null_vi(old_vi));
    dispatcher_patched #(.VLEN(VLEN)) patched (
      .avl, .stride, .imm, .vlmax, .csr_vl_q(vl), .csr_vl_d(new_vl),
      .null_vx(new_vx), .null_vi(new_vi));
    task automatic check;
      #1;
      if ({old_vl, old_vx, old_vi} !== {new_vl, new_vx, new_vi})
        $fatal(1, "VLEN=%0d avl=%h stride=%h vl=%0d old/new differ", VLEN, avl, stride, vl);
      if (!$isunknown({avl, stride, imm, vl})) begin
        if (new_vl !== ((avl > vlmax) ? vlmax : avl) ||
            new_vx !== (stride >= vl) || new_vi !== ({59'b0, imm} >= vl))
          $fatal(1, "VLEN=%0d unsigned full-width reference mismatch", VLEN);
      end
      checks++;
    endtask
    task automatic check_value(input logic [63:0] value);
      avl = value;
      stride = value;
      imm = value[4:0];
      check();
    endtask
    initial begin
      for (int sew = 8; sew <= 64; sew *= 2) begin
        for (int lmul = -3; lmul <= 3; lmul++) begin
          vlmax = lmul >= 0 ? (VLEN / sew) << lmul : (VLEN / sew) >> (-lmul);
          if (vlmax == 0) continue;
          for (int v = 0; v < 5; v++) begin
            case (v)
              0: vl = 0;
              1: vl = 1;
              2: vl = vlmax / 2;
              3: vl = vlmax - 1;
              4: vl = vlmax;
            endcase
            check_value(0);
            check_value(vlmax - 1);
            check_value(vlmax);
            check_value(64'(vlmax) + 1);
            check_value(vl);
            check_value((64'b1 << W) - 1);
            check_value(64'b1 << W);
            check_value((64'b1 << W) + 1);
            for (int bitno = W; bitno < 64; bitno++) check_value(64'b1 << bitno);
            check_value('1);
            for (int offset = 0; offset < 32; offset++) check_value(offset);
            repeat (64) check_value({$urandom, $urandom});
            check_value('x);
            check_value('z);
            check_value({{(64-W){1'b0}}, {W{1'bx}}});
          end
        end
      end
      $display("PASS VLEN=%0d comparisons=%0d", VLEN, checks);
      done[p] = 1'b1;
    end
  end
  initial begin
    wait (&done);
    $display("PASS: all 11 VLEN configurations, original/patched and unsigned reference");
    $finish;
  end
  initial begin
    #1000000;
    $fatal(1, "Expression test watchdog");
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New independent test directory")
    parser.add_argument("--vcs", default="vcs")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = (ROOT / "hardware/src/ara_dispatcher.sv").read_text()
    test = (expression_module(source, "dispatcher_original") +
            expression_module(patch_dispatcher_vlen_casts(source), "dispatcher_patched") +
            TESTBENCH)
    (output / "tb.sv").write_text(test)
    with (output / "compile.log").open("w") as log:
        subprocess.run([args.vcs, "-full64", "-sverilog", "-top", "tb", "tb.sv", "-o", "simv"],
                       cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv"), "+ntb_random_seed=1"], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: all 11 VLEN configurations" not in result:
        raise RuntimeError("Missing expression-test completion marker")


if __name__ == "__main__":
    main()
