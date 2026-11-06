// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Experimental wide-weight ingress building block, not yet instantiated by
// qbs_engine. One instance owns one private payload bank between clears.
// Inputs are ordered, compacted, nonempty byte prefixes of at most 32 bytes.
// Preserve a partial word across beats instead of issuing two conflicting
// writes when a beat crosses a 32-byte SRAM word boundary.
module qbs_weight_line_assembler #(
  parameter int unsigned ByteAddrWidth = 8,
  localparam int unsigned WordAddrWidth = ByteAddrWidth - 5
) (
  input logic clk_i,
  input logic rst_ni,
  input logic clear_i,
  input logic valid_i,
  output logic ready_o,
  input logic [ByteAddrWidth-1:0] offset_i,
  input logic [255:0] data_i,
  input logic [31:0] strb_i,
  input logic last_i,
  output logic write_valid_o,
  input logic write_ready_i,
  output logic [WordAddrWidth-1:0] write_addr_o,
  output logic [255:0] write_data_o,
  output logic [31:0] write_strb_o,
  output logic pending_o
);
  logic carry_valid_q, carry_last_q, closed_q;
  logic [WordAddrWidth-1:0] carry_addr_q;
  logic [255:0] carry_data_q;
  logic [31:0] carry_strb_q;
  logic output_valid_q;
  logic [WordAddrWidth-1:0] output_addr_q;
  logic [255:0] output_data_q;
  logic [31:0] output_strb_q;
  logic [511:0] shifted_data;
  logic [63:0] shifted_strb;
  logic [255:0] merged_data;
  logic [31:0] merged_strb;
  logic output_space, input_fire, first_word_closes;

  assign output_space = !output_valid_q || write_ready_i;
  assign ready_o = rst_ni && !clear_i && !closed_q &&
                   !carry_last_q && output_space;
  assign input_fire = valid_i && ready_o;
  assign write_valid_o = output_valid_q && rst_ni && !clear_i;
  assign write_addr_o = output_addr_q;
  assign write_data_o = output_data_q;
  assign write_strb_o = output_strb_q;
  assign pending_o = carry_valid_q || output_valid_q;

  // A bounded byte rotation/split, not a dynamically indexed register file.
  assign shifted_data = {256'b0, data_i} << {offset_i[4:0], 3'b000};
  assign shifted_strb = {32'b0, strb_i} << offset_i[4:0];
  assign merged_strb = shifted_strb[31:0] |
                       (carry_valid_q ? carry_strb_q : 32'b0);
  for (genvar b = 0; b < 32; b++) begin : gen_merge
    assign merged_data[8*b +: 8] = shifted_strb[b]
        ? shifted_data[8*b +: 8]
        : carry_valid_q && carry_strb_q[b] ? carry_data_q[8*b +: 8] : 8'b0;
  end
  assign first_word_closes = (|shifted_strb[63:32]) || merged_strb[31] || last_i;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      carry_valid_q <= 1'b0;
      carry_last_q <= 1'b0;
      carry_strb_q <= '0;
      output_valid_q <= 1'b0;
      closed_q <= 1'b0;
    end else if (clear_i) begin
      carry_valid_q <= 1'b0;
      carry_last_q <= 1'b0;
      carry_strb_q <= '0;
      output_valid_q <= 1'b0;
      closed_q <= 1'b0;
    end else begin
      if (output_space) output_valid_q <= 1'b0;

      // A last input may close a full word plus a partial second word. The
      // latter flushes through the same write port, after any older output.
      if (carry_valid_q && carry_last_q && output_space) begin
        output_valid_q <= 1'b1;
        output_addr_q <= carry_addr_q;
        output_data_q <= carry_data_q;
        output_strb_q <= carry_strb_q;
        carry_valid_q <= 1'b0;
        carry_last_q <= 1'b0;
        carry_strb_q <= '0;
      end

      if (input_fire) begin
        closed_q <= last_i;
        if (first_word_closes) begin
          output_valid_q <= 1'b1;
          output_addr_q <= offset_i[ByteAddrWidth-1:5];
          output_data_q <= merged_data;
          output_strb_q <= merged_strb;
          carry_valid_q <= |shifted_strb[63:32];
          carry_last_q <= last_i && (|shifted_strb[63:32]);
          carry_addr_q <= offset_i[ByteAddrWidth-1:5] + WordAddrWidth'(1);
          carry_data_q <= shifted_data[511:256];
          carry_strb_q <= shifted_strb[63:32];
        end else begin
          carry_valid_q <= 1'b1;
          carry_last_q <= 1'b0;
          carry_addr_q <= offset_i[ByteAddrWidth-1:5];
          carry_data_q <= merged_data;
          carry_strb_q <= merged_strb;
        end
      end
    end
  end

`ifndef SYNTHESIS
  logic stream_started_q;
  logic [ByteAddrWidth:0] next_offset_q;
  initial assert (ByteAddrWidth >= 6 && ByteAddrWidth <= 16);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      stream_started_q <= 1'b0;
      next_offset_q <= '0;
    end else if (clear_i) begin
      stream_started_q <= 1'b0;
      next_offset_q <= '0;
    end else if (input_fire) begin
      assert (strb_i != 0 && (strb_i & (strb_i + 32'd1)) == 0)
        else $fatal(1, "QBS weight line input must be a nonempty compacted prefix");
      assert (!stream_started_q || {1'b0, offset_i} == next_offset_q)
        else $fatal(1, "QBS weight line input is not sequential");
      assert (unsigned'(offset_i) + $countones(strb_i) <= (1 << ByteAddrWidth))
        else $fatal(1, "QBS weight line input exceeds its private bank");
      assert (!carry_valid_q || carry_addr_q == offset_i[ByteAddrWidth-1:5])
        else $fatal(1, "QBS weight line carry belongs to another word");
      assert (!carry_valid_q || !(|(carry_strb_q & shifted_strb[31:0])))
        else $fatal(1, "QBS weight line input rewrites a buffered byte");
      stream_started_q <= 1'b1;
      next_offset_q <= {1'b0, offset_i} + (ByteAddrWidth+1)'($countones(strb_i));
    end
  end
  assert property (@(posedge clk_i) disable iff (!rst_ni || clear_i)
      write_valid_o && !write_ready_i |=>
      clear_i || (write_valid_o && $stable({write_addr_o, write_data_o, write_strb_o})))
    else $fatal(1, "QBS weight line output changed under backpressure");
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      write_valid_o |-> write_strb_o != 0)
    else $fatal(1, "QBS weight line emitted an empty write");
`endif
endmodule
