// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Muhammad Ijaz
// Description:
// Ara's fixed point rounding module, operating on elements 64-bit wide, and generating rounding r for each stream of elements.

module fixed_p_rounding import ara_pkg::*; import rvv_pkg::*; #(
    // Dependant parameters. DO NOT CHANGE!
    localparam int  unsigned DataWidth = $bits(elen_t),
    localparam int  unsigned StrbWidth = DataWidth/8,
    localparam type          strb_t    = logic [StrbWidth-1:0]
  ) (
    input  elen_t   operand_a_i,
    input  elen_t   operand_b_i,
    input  logic    valid_i,
    input  ara_op_e op_i,
    input  vew_e    vew_i,
    input  vxrm_t   vxrm_i,
    output strb_t   r_o
  );

  /////////////////
  // Definitions //
  /////////////////

  typedef union packed {
    logic [0:0][63:0] w64;
    logic [1:0][31:0] w32;
    logic [3:0][15:0] w16;
    logic [7:0][ 7:0] w8;
  } rounding_args_t;

  rounding_args_t opa, opb;
  assign opa = operand_a_i;
  assign opb = operand_b_i;

  vxrm_t vxrm;
  assign vxrm = vxrm_i;

  function automatic logic rounding_increment(
    input logic [63:0] value,
    input logic  [5:0] shift,
    input vxrm_t       mode
  );
    logic retained_lsb, rounding_bit, sticky;
    logic [63:0] lower_mask;

    rounding_increment = 1'b0;
    retained_lsb = 1'b0;
    rounding_bit = 1'b0;
    sticky       = 1'b0;
    lower_mask   = '0;

    if (shift != 0) begin
      retained_lsb = value[shift];
      rounding_bit = value[shift-1'b1];
      lower_mask   = (64'h1 << (shift-1'b1)) - 1'b1;
      sticky       = |(value & lower_mask);

      unique case (mode)
        2'b00: rounding_increment = rounding_bit;
        2'b01: rounding_increment = rounding_bit & (sticky | retained_lsb);
        2'b10: rounding_increment = 1'b0;
        2'b11: rounding_increment = !retained_lsb & (rounding_bit | sticky);
      endcase
    end
  endfunction : rounding_increment

  always_comb begin
    r_o = '0;

    if (valid_i) begin
      unique case (op_i)
        VSSRA, VSSRL: begin
          unique case (vew_i)
            EW8 : for (int i = 0; i < 8; i++)
              r_o[i] = rounding_increment({56'b0, opb.w8[i]}, {3'b0, opa.w8[i][2:0]}, vxrm);
            EW16: for (int i = 0; i < 4; i++)
              r_o[i] = rounding_increment({48'b0, opb.w16[i]}, {2'b0, opa.w16[i][3:0]}, vxrm);
            EW32: for (int i = 0; i < 2; i++)
              r_o[i] = rounding_increment({32'b0, opb.w32[i]}, {1'b0, opa.w32[i][4:0]}, vxrm);
            EW64: r_o[0] = rounding_increment(opb.w64[0], opa.w64[0][5:0], vxrm);
          endcase
        end
        VNCLIP, VNCLIPU: begin
          unique case (vew_i)
            EW8 : for (int i = 0; i < 4; i++)
              r_o[i] = rounding_increment({48'b0, opb.w16[i]}, {2'b0, opa.w16[i][3:0]}, vxrm);
            EW16: for (int i = 0; i < 2; i++)
              r_o[i] = rounding_increment({32'b0, opb.w32[i]}, {1'b0, opa.w32[i][4:0]}, vxrm);
            EW32: r_o[0] = rounding_increment(opb.w64[0], opa.w64[0][5:0], vxrm);
            default:;
          endcase
        end
        default: r_o = '0;
      endcase
    end
  end

endmodule : fixed_p_rounding
