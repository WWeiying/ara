#!/usr/bin/env python3
"""Extract the changed combinational cones from exact pre/post-edit RTL."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def between(text, start, stop):
    return text[text.index(start):text.index(stop, text.index(start))]


def correction_module(text):
    declarations = between(text, "  logic [FlatEntries-1:0] correction_pending_flat;",
                           "  always_comb begin\n    start_context")
    body = between(text, "  always_comb begin\n    correction_first_upper_mask",
                   "  always_comb begin\n    correction_consume")
    return """module qbs_correction_select_comb (
  input logic [31:0] pending_i, input logic [4:0] rr_i,
  output logic [1:0] valid_o, output logic [4:0] first_o, second_o
);
  localparam int FlatEntries = 32;
  wire [4:0] correction_rr_q = rr_i;
""" + declarations + """
  assign correction_pending_flat = pending_i;
""" + body + """
  assign valid_o = {correction_second_found, correction_first_found};
  assign first_o = correction_first_found ? correction_first_index : '0;
  assign second_o = correction_second_found ? correction_second_index : '0;
endmodule
module qbs_correction_select_timing (
  input logic clk_i, rst_ni,
  input logic [31:0] pending_i, input logic [4:0] rr_i,
  output logic [1:0] valid_o, output logic [4:0] first_o, second_o
);
  logic [31:0] pending_q;
  logic [4:0] rr_q, first_d, second_d;
  logic [1:0] valid_d;
  qbs_correction_select_comb i_select (.pending_i(pending_q), .rr_i(rr_q),
      .valid_o(valid_d), .first_o(first_d), .second_o(second_d));
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      pending_q <= '0; rr_q <= '0;
      valid_o <= '0; first_o <= '0; second_o <= '0;
    end else begin
      pending_q <= pending_i; rr_q <= rr_i;
      valid_o <= valid_d; first_o <= first_d; second_o <= second_d;
    end
  end
endmodule
"""


def address_module(text, optimized):
    function = between(text, "  function automatic logic [31:0] block_byte_offset(",
                       "  always_comb begin : form_read_range") if optimized else ""
    compute = """
    offset = 64'(block_byte_offset(logical_row, k_q, row_bytes_q, bytes_q, r4_q));
""" if optimized else """
    block_index = r4_q ? (((64'(logical_row) >> 2) * blocks_q + k_q) << 2)
                       : (64'(logical_row) * blocks_q + k_q);
    offset = block_index * bytes_q;
"""
    return """module qbs_address_timing (
  input logic clk_i, rst_ni,
  input logic [5:0] row_i, input logic [2:0] index_i,
  input logic [7:0] k_i, input logic [8:0] blocks_i,
  input logic [15:0] bytes_i, input logic [63:0] base_i,
  input logic r4_i, output logic [63:0] address_o
);
  logic [5:0] row_q;
  logic [2:0] index_q;
  logic [7:0] k_q;
  logic [8:0] blocks_q;
  logic [15:0] bytes_q;
  logic [24:0] row_bytes_q;
  logic [63:0] base_q, address_d, offset, block_index;
  logic [6:0] logical_row;
  logic r4_q;
""" + function + """
  always_comb begin
    logical_row = 7'(row_q) + 7'(index_q);
    block_index = '0;
""" + compute + """
    address_d = base_q + offset;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      row_q <= '0; index_q <= '0; k_q <= '0; blocks_q <= '0;
      bytes_q <= '0; row_bytes_q <= '0; base_q <= '0; r4_q <= '0; address_o <= '0;
    end else begin
      row_q <= row_i; index_q <= index_i; k_q <= k_i; blocks_q <= blocks_i;
      bytes_q <= bytes_i; row_bytes_q <= blocks_i * bytes_i;
      base_q <= base_i; r4_q <= r4_i; address_o <= address_d;
    end
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    for name, directory in (("before", args.before),
                            ("after", ROOT / "hardware/src/vlsu/qbs")):
        out = args.output / name
        out.mkdir(parents=True, exist_ok=True)
        profile = (directory / "qbs_profile_engine_int.sv").read_text()
        engine = (directory / "qbs_engine.sv").read_text()
        (out / "qbs_correction_select_timing.sv").write_text(correction_module(profile))
        (out / "qbs_address_timing.sv").write_text(address_module(engine, name == "after"))
    for top in ("qbs_correction_select_timing", "qbs_address_timing"):
        old = (args.output / "before" / (top + ".sv")).read_text()
        old = re.sub(r"\b(qbs_correction_select_comb|qbs_correction_select_timing|qbs_address_timing)\b",
                     lambda match: match[0] + "_reference", old)
        (args.output / (top + "_reference.sv")).write_text(old)
    for module in ("qbs_profile_engine_int", "qbs_fp_accumulator"):
        source = args.before / (module + ".sv")
        if not source.exists():
            source = ROOT / "hardware/src/vlsu/qbs" / (module + ".sv")
        text = re.sub(r"\b" + module + r"\b", module + "_reference", source.read_text())
        (args.output / (module + "_reference.sv")).write_text(text)


if __name__ == "__main__":
    main()
