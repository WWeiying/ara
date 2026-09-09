#!/usr/bin/env python3
"""Bounded VCS equivalence test for the exported AKV byte-count expressions."""
import argparse
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export import patch_akv_byte_counts
from prepare import ROOT


def module(source, name, patched=False):
    replay = re.findall(r"  always_comb begin\n    replay_word_bytes = '0;.*?\n  end", source, re.S)
    assert len(replay) == 1
    extra = ""
    if patched:
        declaration = re.findall(r"  logic \[\$clog2\(AxiDataWidth/8\+1\).*?;", source)
        read = re.findall(r"  always_comb begin\n    fpga_read_data_byte_count = '0;.*?\n  end", source, re.S)
        assert len(declaration) == len(read) == 1
        extra = declaration[0] + "\n" + read[0]
    count = re.findall(r"q_external_bytes_o <= q_external_bytes_o \+\s*(.*?);", source)
    assert len(count) == 1
    return f"""
module {name} #(parameter int AxiDataWidth = 128, NrLanes = 4) (
  input logic [AxiDataWidth/8-1:0] read_data_strb,
  input logic [7:0] ldu_result_be_o [NrLanes],
  output logic [6:0] replay_word_bytes,
  output logic [31:0] read_bytes
);
  timeunit 1ns; timeprecision 1ps;
  {replay[0]}
  {extra}
  assign read_bytes = {count[0]};
endmodule
"""


TB = r"""
module tb;
  timeunit 1ns; timeprecision 1ps;
  logic [15:0] read_data_strb;
  logic [7:0] ldu_result_be_o [4];
  logic [6:0] old_replay, new_replay;
  logic [31:0] old_read, new_read;
  int checks = 0;
  original dut_old (.read_data_strb, .ldu_result_be_o,
    .replay_word_bytes(old_replay), .read_bytes(old_read));
  patched dut_new (.read_data_strb, .ldu_result_be_o,
    .replay_word_bytes(new_replay), .read_bytes(new_read));
  task automatic check;
    #1;
    if ({old_replay, old_read} !== {new_replay, new_read})
      $fatal(1, "Mismatch read=%h replay=%p old=%d/%d new=%d/%d",
             read_data_strb, ldu_result_be_o, old_replay, old_read, new_replay, new_read);
    checks++;
  endtask
  initial begin
    read_data_strb = '0;
    foreach (ldu_result_be_o[lane]) ldu_result_be_o[lane] = '0;
    // Exhaust all 16-bit read strobes, and all byte masks on every lane.
    for (int pattern = 0; pattern < 65536; pattern++) begin
      read_data_strb = 16'(pattern);
      foreach (ldu_result_be_o[lane]) ldu_result_be_o[lane] = 8'(pattern >> (2*lane));
      check();
    end
    // Exhaust the four-state combinations of a byte enable, on each lane.
    for (int lane = 0; lane < 4; lane++) begin
      for (int pattern = 0; pattern < 65536; pattern++) begin
        for (int b = 0; b < 8; b++) begin
          case ((pattern >> (2*b)) & 3)
            0: ldu_result_be_o[lane][b] = 1'b0;
            1: ldu_result_be_o[lane][b] = 1'b1;
            2: ldu_result_be_o[lane][b] = 1'bx;
            3: ldu_result_be_o[lane][b] = 1'bz;
          endcase
        end
        read_data_strb = {ldu_result_be_o[lane], ldu_result_be_o[lane]};
        check();
      end
    end
    repeat (10000) begin
      read_data_strb = $urandom;
      foreach (ldu_result_be_o[lane]) ldu_result_be_o[lane] = $urandom;
      check();
    end
    read_data_strb = '1;
    foreach (ldu_result_be_o[lane]) ldu_result_be_o[lane] = '1;
    check();
    if (new_read != 16 || new_replay != 32) $fatal(1, "Counter width overflow");
    $display("PASS: AKV byte-count equivalence, %0d cases, including X/Z", checks);
    $finish;
  end
  initial begin
    #1000000;
    $fatal(1, "Byte-count test watchdog");
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New independent test directory")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = (ROOT / "hardware/src/vlsu/akv/akv_engine.sv").read_text()
    test = module(source, "original") + module(patch_akv_byte_counts(source), "patched", True) + TB
    (output / "tb.sv").write_text(test)
    with (output / "compile.log").open("w") as log:
        subprocess.run(["vcs", "-full64", "-sverilog", "-top", "tb", "tb.sv", "-o", "simv"],
                       cwd=output, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    with (output / "run.log").open("w") as log:
        subprocess.run([str(output / "simv"), "+ntb_random_seed=1"], cwd=output,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=60)
    result = (output / "run.log").read_text()
    print(result)
    if "PASS: AKV byte-count equivalence" not in result:
        raise RuntimeError("Missing completion marker")


if __name__ == "__main__":
    main()
