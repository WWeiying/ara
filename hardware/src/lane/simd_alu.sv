// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Ara's SIMD ALU, operating on elements 64-bit wide, and generating 64 bits per cycle.

module simd_alu import ara_pkg::*; import rvv_pkg::*; #(
    // Support for fixed-point data types
    parameter  fixpt_support_e FixPtSupport = FixedPointEnable,
    // Dependant parameters. DO NOT CHANGE!
    localparam int    unsigned DataWidth    = $bits(elen_t),
    localparam int    unsigned StrbWidth    = DataWidth/8,
    localparam type            strb_t       = logic [StrbWidth-1:0]
  ) (
    input  elen_t      operand_a_i,
    input  elen_t      operand_b_i,
    input  logic       valid_i,
    input  logic       vm_i,
    input  strb_t      mask_i,
    input  logic       narrowing_select_i,
    input  ara_op_e    op_i,
    input  vew_e       vew_i,
    output vxsat_t     vxsat_o,
    input  strb_t      rm,
    input  vxrm_t      vxrm_i,
    output elen_t      result_o
  );

  ///////////////////
  //  Definitions  //
  ///////////////////

  typedef union packed {
    logic [0:0][63:0] w64;
    logic [1:0][31:0] w32;
    logic [3:0][15:0] w16;
    logic [7:0][ 7:0] w8;
  } alu_operand_t;

  alu_operand_t opa, opb, res;
  assign opa      = operand_a_i;
  assign opb      = operand_b_i;
  assign result_o = res;


  vxsat_t vxsat;
  vxrm_t vxrm;
  assign vxrm = vxrm_i;
  assign vxsat_o = vxsat;

  logic arith_sub, arith_average, arith_average_signed, arith_reverse;
  logic arith_mask_carry, compare_signed;
  logic [63:0] arith_x, arith_y, add_y, correction;
  logic [63:0] carry_save_sum, carry_save_majority, carry_save_carry, arith_sum;
  logic [7:0] element_start, byte_extension;
  logic [7:0] carry_p [4], carry_g [4];
  logic [63:0] arithmetic_result [4];
  logic [7:0] arithmetic_sat [4], compare_less [4], compare_equal [4];
  logic [7:0] less, equal;

  assign arith_sub = op_i inside {VSUB, VSBC, VMSBC, VRSUB, VSSUB, VSSUBU,
      VASUB, VASUBU, VMIN, VMINU, VMAX, VMAXU, VREDMIN, VREDMINU,
      VREDMAX, VREDMAXU, VMSEQ, VMSNE, VMSLT, VMSLTU, VMSLE, VMSLEU,
      VMSGT, VMSGTU};
  assign arith_average = FixPtSupport == FixedPointEnable &&
      (op_i inside {VAADD, VAADDU, VASUB, VASUBU});
  assign arith_average_signed = op_i inside {VAADD, VASUB};
  assign arith_reverse = op_i == VRSUB;
  assign arith_mask_carry = !vm_i && (op_i inside {VADC, VMADC, VSBC, VMSBC});
  assign compare_signed = op_i inside {VMAX, VREDMAX, VMIN, VREDMIN,
      VMSLT, VMSLE, VMSGT};
  assign arith_x = arith_reverse ? operand_a_i : operand_b_i;
  assign arith_y = arith_reverse ? operand_b_i : operand_a_i;
  assign add_y = arith_y ^ {64{arith_sub}};

  // Inject carry/borrow at bit zero and averaging round-up at bit one.
  // A sparse third operand avoids a second full-width rounding adder.
  for (genvar b = 0; b < 8; b++) begin : gen_correction
    wire low_carry = arith_sub
        ? (~arith_x[8*b] & arith_y[8*b])
        : ( arith_x[8*b] & arith_y[8*b]);
    wire retained_lsb = arith_x[8*b+1] ^ arith_y[8*b+1] ^ low_carry;
    wire discarded_lsb = arith_x[8*b] ^ arith_y[8*b];
    logic round_up;
    always_comb begin
      case (vxrm_i)
        2'b00: round_up = discarded_lsb;
        2'b01: round_up = discarded_lsb & retained_lsb;
        2'b10: round_up = 1'b0;
        2'b11: round_up = discarded_lsb & ~retained_lsb;
      endcase
    end
    assign element_start[b] = (b == 0) ||
        ((b & ((1 << vew_i) - 1)) == 0);
    assign correction[8*b+:8] = {6'b0,
        element_start[b] & arith_average & round_up,
        element_start[b] & (arith_sub ^ (arith_mask_carry & mask_i[b]))};
  end

  assign carry_save_sum = arith_x ^ add_y ^ correction;
  assign carry_save_majority = (arith_x & add_y) |
      ((arith_x ^ add_y) & correction);

  // Byte-local carry-save plus a three-level prefix. Neither carry path
  // crosses a SIMD element boundary. Keep the dropped top carry for SEW+1.
  for (genvar b = 0; b < 8; b++) begin : gen_arith_byte
    wire carry_from_previous;
    if (b == 0) assign carry_from_previous = 1'b0;
    else assign carry_from_previous = carry_save_majority[8*b-1] & ~element_start[b];
    assign carry_save_carry[8*b+:8] =
        {carry_save_majority[8*b+:7], carry_from_previous};
    wire [8:0] base_sum = {1'b0, carry_save_sum[8*b+:8]} +
                         {1'b0, carry_save_carry[8*b+:8]};
    assign carry_p[0][b] = (&base_sum[7:0]) & ~element_start[b];
    assign carry_g[0][b] = base_sum[8];
    wire cin;
    if (b == 0) assign cin = 1'b0;
    else assign cin = carry_g[3][b-1] & ~element_start[b];
    assign arith_sum[8*b+:8] = base_sum[7:0] + cin;
    assign byte_extension[b] =
        arith_sub ^ carry_save_majority[8*b+7] ^ carry_g[3][b];
  end
  for (genvar level = 0; level < 3; level++) begin : gen_arith_prefix
    for (genvar b = 0; b < 8; b++) begin : gen_byte
      if (b >= (1 << level)) begin
        assign carry_p[level+1][b] = carry_p[level][b] & carry_p[level][b-(1 << level)];
        assign carry_g[level+1][b] = carry_g[level][b] |
            (carry_p[level][b] & carry_g[level][b-(1 << level)]);
      end else begin
        assign carry_p[level+1][b] = carry_p[level][b];
        assign carry_g[level+1][b] = carry_g[level][b];
      end
    end
  end

  // Only result formatting is replicated by SEW; the arithmetic is shared.
  for (genvar fmt = 0; fmt < 4; fmt++) begin : gen_arith_format
    localparam int W = 8 << fmt;
    for (genvar e = 0; e < 64/W; e++) begin : gen_element
      wire [W-1:0] sum = arith_sum[e*W+:W];
      wire xs = arith_x[e*W+W-1];
      wire ys = arith_y[e*W+W-1];
      wire ext = byte_extension[e*(W/8)+W/8-1];
      wire signed_overflow = (xs ^ sum[W-1]) & ~((xs ^ ys) ^ arith_sub);
      wire signed_sat = op_i inside {VSADD, VSSUB};
      wire unsigned_sat = op_i inside {VSADDU, VSSUBU};
      wire saturate = FixPtSupport == FixedPointEnable &&
          ((signed_sat & signed_overflow) | (unsigned_sat & ext));
      wire [W-1:0] limit = signed_sat
          ? {xs, {(W-1){~xs}}} : {W{~arith_sub}};
      wire average_ext = ext ^ (arith_average_signed & (xs ^ ys));
      assign arithmetic_result[fmt][e*W+:W] =
          (op_i inside {VMADC, VMSBC}) ? {{(W-2){1'b0}}, 1'b1, ext} :
          arith_average ? {average_ext, sum[W-1:1]} :
          saturate ? limit : sum;
      // Preserve the existing VSSUB byte-enable-facing saturation encoding.
      assign arithmetic_sat[fmt][e*(W/8)+:W/8] = op_i == VSSUB
          ? {{(W/8-1){1'b0}}, saturate} : {(W/8){saturate}};
      assign compare_less[fmt][e*(W/8)+:W/8] =
          {{(W/8-1){1'b0}}, (compare_signed && (xs != ys)) ? xs : ext};
      assign compare_equal[fmt][e*(W/8)+:W/8] =
          {{(W/8-1){1'b0}}, operand_a_i[e*W+:W] == operand_b_i[e*W+:W]};
    end
  end
  assign less = valid_i && vew_i <= EW64 ? compare_less[vew_i[1:0]] : '0;
  assign equal = valid_i && vew_i <= EW64 ? compare_equal[vew_i[1:0]] : '0;

  always_comb begin: p_alu
    // Default assignment
    res       = '0;
    vxsat.w64 = '0;

    if (valid_i)
      unique case (op_i)
        // Logical operations
        VAND, VREDAND: res = operand_a_i & operand_b_i;
        VOR, VREDOR  : res = operand_a_i | operand_b_i;
        VXOR, VREDXOR: res = operand_a_i ^ operand_b_i;

        // Mask logical operations
        VMAND   : res = operand_a_i & operand_b_i;
        VMANDNOT: res = ~operand_a_i & operand_b_i;
        VMNAND  : res = ~(operand_a_i & operand_b_i);
        VMOR    : res = operand_a_i | operand_b_i;
        VMNOR   : res = ~(operand_a_i | operand_b_i);
        VMORNOT : res = ~operand_a_i | operand_b_i;
        VMXOR   : res = operand_a_i ^ operand_b_i;
        VMXNOR  : res = ~(operand_a_i ^ operand_b_i);

        // Mask operands pass-through
        VCPOP, VFIRST, VMSBF, VMSOF, VMSIF, VIOTA: res = operand_b_i;

        // Mask operands pass-through
        VRGATHER, VRGATHEREI16, VCOMPRESS: res = operand_a_i;

        // Arithmetic instructions share the same partitioned datapath.
        VADD, VADC, VMADC, VSUB, VSBC, VMSBC, VRSUB,
        VREDSUM, VWREDSUMU, VWREDSUM:
          if (vew_i <= EW64) res = arithmetic_result[vew_i[1:0]];
        VSADD, VSADDU, VSSUB, VSSUBU, VAADD, VAADDU, VASUB, VASUBU:
          if (FixPtSupport == FixedPointEnable && vew_i <= EW64) begin
            res = arithmetic_result[vew_i[1:0]];
            vxsat = arithmetic_sat[vew_i[1:0]];
          end

        // Shift instructions
        VSLL: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b] = opb.w8 [b] << opa.w8 [b][2:0];
            EW16: for (int b = 0; b < 4; b++) res.w16[b] = opb.w16[b] << opa.w16[b][3:0];
            EW32: for (int b = 0; b < 2; b++) res.w32[b] = opb.w32[b] << opa.w32[b][4:0];
            EW64: for (int b = 0; b < 1; b++) res.w64[b] = opb.w64[b] << opa.w64[b][5:0];
          endcase
        VSRL: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b] = opb.w8 [b] >> opa.w8 [b][2:0];
            EW16: for (int b = 0; b < 4; b++) res.w16[b] = opb.w16[b] >> opa.w16[b][3:0];
            EW32: for (int b = 0; b < 2; b++) res.w32[b] = opb.w32[b] >> opa.w32[b][4:0];
            EW64: for (int b = 0; b < 1; b++) res.w64[b] = opb.w64[b] >> opa.w64[b][5:0];
          endcase
        VSRA: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b] = $signed(opb.w8 [b]) >>> opa.w8 [b][2:0];
            EW16: for (int b = 0; b < 4; b++) res.w16[b] = $signed(opb.w16[b]) >>> opa.w16[b][3:0];
            EW32: for (int b = 0; b < 2; b++) res.w32[b] = $signed(opb.w32[b]) >>> opa.w32[b][4:0];
            EW64: for (int b = 0; b < 1; b++) res.w64[b] = $signed(opb.w64[b]) >>> opa.w64[b][5:0];
          endcase
        VNSRL: unique case (vew_i)
            EW8 : for (int b = 0; b < 4; b++) res.w8 [2*b + narrowing_select_i] = opb.w16[b] >>
                opa.w16[b][3:0];
            EW16: for (int b = 0; b < 2; b++) res.w16[2*b + narrowing_select_i] = opb.w32[b] >>
                opa.w32[b][4:0];
            EW32: for (int b = 0; b < 1; b++) res.w32[2*b + narrowing_select_i] = opb.w64[b] >>
                opa.w64[b][5:0];
          endcase
        VNSRA: unique case (vew_i)
            EW8 : for (int b = 0; b < 4; b++) res.w8 [2*b + narrowing_select_i] =
                $signed(opb.w16[b]) >>> opa.w16[b][3:0];
            EW16: for (int b = 0; b < 2; b++) res.w16[2*b + narrowing_select_i] =
                $signed(opb.w32[b]) >>> opa.w32[b][4:0];
            EW32: for (int b = 0; b < 1; b++) res.w32[2*b + narrowing_select_i] =
                $signed(opb.w64[b]) >>> opa.w64[b][5:0];
          endcase

        // Fixed point shift instructions
        VSSRA: if (FixPtSupport == FixedPointEnable) unique case (vew_i)
            EW8: for (int b = 0; b < 8; b++) begin
                automatic logic [7:0] sra = $signed(opb.w8 [b]) >>> opa.w8 [b][2:0];
                res.w8[b] = prefix_add65(sra, 65'd0, rm[b]);
              end
            EW16: for (int b = 0; b < 4; b++) begin
                automatic logic [15:0] sra = $signed(opb.w16[b]) >>> opa.w16[b][3:0];
                res.w16[b] = prefix_add65(sra, 65'd0, rm[b]);
              end
            EW32: for (int b = 0; b < 2; b++) begin
                automatic logic [31:0] sra = $signed(opb.w32[b]) >>> opa.w32[b][4:0];
                res.w32[b] = prefix_add65(sra, 65'd0, rm[b]);
              end
            EW64: for (int b = 0; b < 1; b++) begin
                automatic logic [63:0] sra = $signed(opb.w64[b]) >>> opa.w64[b][5:0];
                res.w64[b] = prefix_add65(sra, 65'd0, rm[b]);
              end
          endcase
        VSSRL: if (FixPtSupport == FixedPointEnable) unique case (vew_i)
            EW8: for (int b = 0; b < 8; b++) begin
                automatic logic [8:0] srl = opb.w8 [b] >> opa.w8 [b][2:0];
                res.w8[b] = prefix_add65(srl, 65'd0, rm[b]);
              end
            EW16: for (int b = 0; b < 4; b++) begin
                automatic logic [16:0] srl = opb.w16[b] >> opa.w16[b][3:0];
                res.w16[b] = prefix_add65(srl, 65'd0, rm[b]);
              end
            EW32: for (int b = 0; b < 2; b++) begin
                automatic logic [32:0] srl = opb.w32[b] >> opa.w32[b][4:0];
                res.w32[b] = prefix_add65(srl, 65'd0, rm[b]);
              end
            EW64: for (int b = 0; b < 1; b++) begin
                automatic logic [64:0] srl = opb.w64[b] >> opa.w64[b][5:0];
                res.w64[b] = prefix_add65(srl, 65'd0, rm[b]);
              end
          endcase

        // Fixed point clip instructions
        VNCLIP: if (FixPtSupport == FixedPointEnable) unique case (vew_i)
            EW8 : for (int b = 0; b < 4; b++) begin
                automatic logic signed [15:0] shifted =
                    $signed(opb.w16[b]) >>> opa.w16[b][3:0];
                automatic logic [8:0] low_sum =
                    prefix_add65({1'b0, shifted[7:0]}, 65'd0, rm[b]);
                automatic logic negative = shifted[15];
                automatic logic sat = negative
                    ? ((shifted[15:8] != 8'hff) ||
                       (!low_sum[8] && !low_sum[7]))
                    : ((shifted[15:8] != 8'h00) ||
                       low_sum[8] || low_sum[7]);
                vxsat.w8[2*b + narrowing_select_i] = sat;
                res.w8[2*b + narrowing_select_i] = sat
                    ? (negative ? 8'h80 : 8'h7f) : low_sum[7:0];
              end
            EW16: for (int b = 0; b < 2; b++) begin
                automatic logic signed [31:0] shifted =
                    $signed(opb.w32[b]) >>> opa.w32[b][4:0];
                automatic logic [16:0] low_sum =
                    prefix_add65({1'b0, shifted[15:0]}, 65'd0, rm[b]);
                automatic logic negative = shifted[31];
                automatic logic sat = negative
                    ? ((shifted[31:16] != 16'hffff) ||
                       (!low_sum[16] && !low_sum[15]))
                    : ((shifted[31:16] != 16'h0000) ||
                       low_sum[16] || low_sum[15]);
                vxsat.w16[2*b + narrowing_select_i] = {2{sat}};
                res.w16[2*b + narrowing_select_i] = sat
                    ? (negative ? 16'h8000 : 16'h7fff) : low_sum[15:0];
              end
            EW32: for (int b = 0; b < 1; b++) begin
                automatic logic signed [63:0] shifted =
                    $signed(opb.w64[b]) >>> opa.w64[b][5:0];
                automatic logic [32:0] low_sum =
                    prefix_add65({1'b0, shifted[31:0]}, 65'd0, rm[b]);
                automatic logic negative = shifted[63];
                automatic logic sat = negative
                    ? ((shifted[63:32] != 32'hffff_ffff) ||
                       (!low_sum[32] && !low_sum[31]))
                    : ((shifted[63:32] != 32'h0000_0000) ||
                       low_sum[32] || low_sum[31]);
                vxsat.w32[narrowing_select_i] = {4{sat}};
                res.w32[narrowing_select_i] = sat
                    ? (negative ? 32'h8000_0000 : 32'h7fff_ffff)
                    : low_sum[31:0];
              end
          endcase
        VNCLIPU: if (FixPtSupport == FixedPointEnable) unique case (vew_i)
            EW8 : for (int b = 0; b < 4; b++) begin
                automatic logic [15:0] shifted =
                    opb.w16[b] >> opa.w16[b][3:0];
                automatic logic [8:0] low_sum =
                    prefix_add65({1'b0, shifted[7:0]}, 65'd0, rm[b]);
                automatic logic sat = |shifted[15:8] || low_sum[8];
                vxsat.w8[2*b + narrowing_select_i] = sat;
                res.w8[2*b + narrowing_select_i] = sat
                    ? 8'hff : low_sum[7:0];
              end
            EW16: for (int b = 0; b < 2; b++) begin
                automatic logic [31:0] shifted =
                    opb.w32[b] >> opa.w32[b][4:0];
                automatic logic [16:0] low_sum =
                    prefix_add65({1'b0, shifted[15:0]}, 65'd0, rm[b]);
                automatic logic sat = |shifted[31:16] || low_sum[16];
                vxsat.w16[2*b + narrowing_select_i] = {2{sat}};
                res.w16[2*b + narrowing_select_i] = sat
                    ? 16'hffff : low_sum[15:0];
              end
            EW32: for (int b = 0; b < 1; b++) begin
                automatic logic [63:0] shifted =
                    opb.w64[b] >> opa.w64[b][5:0];
                automatic logic [32:0] low_sum =
                    prefix_add65({1'b0, shifted[31:0]}, 65'd0, rm[b]);
                automatic logic sat = |shifted[63:32] || low_sum[32];
                vxsat.w32[narrowing_select_i] = {4{sat}};
                res.w32[narrowing_select_i] = sat
                    ? 32'hffff_ffff : low_sum[31:0];
              end
          endcase

        // Merge instructions
        VMERGE: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b] = mask_i[1*b] ? opa.w8 [b] : opb.w8 [b];
            EW16: for (int b = 0; b < 4; b++) res.w16[b] = mask_i[2*b] ? opa.w16[b] : opb.w16[b];
            EW32: for (int b = 0; b < 2; b++) res.w32[b] = mask_i[4*b] ? opa.w32[b] : opb.w32[b];
            EW64: for (int b = 0; b < 1; b++) res.w64[b] = mask_i[8*b] ? opa.w64[b] : opb.w64[b];
          endcase

        // Scalar move
        VMVSX, VFMVSF: res = opa;

        // Comparison instructions
        VMIN, VMINU, VMAX, VMAXU,
        VREDMINU, VREDMIN, VREDMAXU, VREDMAX: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b] =
                (less[1*b] ^ (op_i == VMAX || op_i == VMAXU || op_i == VREDMAXU || op_i == VREDMAX)) ? opb.w8 [b] : opa.w8 [b];
            EW16: for (int b = 0; b < 4; b++) res.w16[b] =
                (less[2*b] ^ (op_i == VMAX || op_i == VMAXU || op_i == VREDMAXU || op_i == VREDMAX)) ? opb.w16[b] : opa.w16[b];
            EW32: for (int b = 0; b < 2; b++) res.w32[b] =
                (less[4*b] ^ (op_i == VMAX || op_i == VMAXU || op_i == VREDMAXU || op_i == VREDMAX)) ? opb.w32[b] : opa.w32[b];
            EW64: for (int b = 0; b < 1; b++) res.w64[b] =
                (less[8*b] ^ (op_i == VMAX || op_i == VMAXU || op_i == VREDMAXU || op_i == VREDMAX)) ? opb.w64[b] : opa.w64[b];
          endcase
        VMSEQ, VMSNE: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b][1:0] =
                {mask_i[1*b], equal[1*b] ^ (op_i == VMSNE)};
            EW16: for (int b = 0; b < 4; b++) res.w16[b][1:0] =
                {mask_i[2*b], equal[2*b] ^ (op_i == VMSNE)};
            EW32: for (int b = 0; b < 2; b++) res.w32[b][1:0] =
                {mask_i[4*b], equal[4*b] ^ (op_i == VMSNE)};
            EW64: for (int b = 0; b < 1; b++) res.w64[b][1:0] =
                {mask_i[8*b], equal[8*b] ^ (op_i == VMSNE)};
          endcase
        VMSLT, VMSLTU: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b][1:0] = {mask_i[1*b], less[1*b]};
            EW16: for (int b = 0; b < 4; b++) res.w16[b][1:0] = {mask_i[2*b], less[2*b]};
            EW32: for (int b = 0; b < 2; b++) res.w32[b][1:0] = {mask_i[4*b], less[4*b]};
            EW64: for (int b = 0; b < 1; b++) res.w64[b][1:0] = {mask_i[8*b], less[8*b]};
          endcase
        VMSLE, VMSLEU, VMSGT, VMSGTU: unique case (vew_i)
            EW8 : for (int b = 0; b < 8; b++) res.w8 [b][1:0] =
                {mask_i[1*b], (less[1*b] || equal[1*b]) ^ (op_i inside {VMSGT, VMSGTU})};
            EW16: for (int b = 0; b < 4; b++) res.w16[b][1:0] =
                {mask_i[2*b], (less[2*b] || equal[2*b]) ^ (op_i inside {VMSGT, VMSGTU})};
            EW32: for (int b = 0; b < 2; b++) res.w32[b][1:0] =
                {mask_i[4*b], (less[4*b] || equal[4*b]) ^ (op_i inside {VMSGT, VMSGTU})};
            EW64: for (int b = 0; b < 1; b++) res.w64[b][1:0] =
                {mask_i[8*b], (less[8*b] || equal[8*b]) ^ (op_i inside {VMSGT, VMSGTU})};
          endcase

        default:;
      endcase
  end : p_alu

  //////////////////
  //  Assertions  //
  //////////////////

  if (DataWidth != $bits(alu_operand_t))
    $error("[simd_valu] The SIMD vector ALU only works for a datapath 64-bit wide.");

endmodule : simd_alu
