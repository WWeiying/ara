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

  logic shift_left, shift_signed, shift_narrow, shift_clip;
  logic [2:0] shift_sew;
  logic [5:0] shift_amount [8];
  logic [7:0] shift_fill;
  logic [63:0] shift_stage [7];
  logic [63:0] shifted, rounded;
  logic [7:0] round_start, round_boundary, round_cin, round_cout;
  logic [7:0] round_p [4], round_g [4];
  logic [63:0] narrow_result [3];
  logic [7:0] narrow_sat [3];
  logic [63:0] selected_operand;
  logic select_a [8];

  assign shift_left = op_i == VSLL;
  assign shift_signed = op_i inside {VSRA, VNSRA, VSSRA, VNCLIP};
  assign shift_narrow = op_i inside {VNSRL, VNSRA, VNCLIP, VNCLIPU};
  assign shift_clip = FixPtSupport == FixedPointEnable &&
      (op_i inside {VNCLIP, VNCLIPU});
  assign shift_sew = {1'b0, vew_i[1:0]} + {2'b0, shift_narrow};

  // Global bit reversal turns left shifts into right shifts. Reverse the
  // element controls too; no variable per-element reversal network is needed.
  for (genvar bitpos = 0; bitpos < 64; bitpos++) begin : gen_shift_reverse
    assign shift_stage[0][bitpos] = shift_left ? operand_b_i[63-bitpos] : operand_b_i[bitpos];
    assign shifted[bitpos] = shift_left ? shift_stage[6][63-bitpos] : shift_stage[6][bitpos];
  end
  for (genvar b = 0; b < 8; b++) begin : gen_shift_control
    logic [5:0] right_amount, left_amount;
    logic sign_bit;
    always_comb begin
      right_amount = '0;
      left_amount = '0;
      sign_bit = 1'b0;
      case (shift_sew)
        EW8: begin
          right_amount = {3'b0, operand_a_i[8*b+:3]};
          left_amount = {3'b0, operand_a_i[8*(7-b)+:3]};
          sign_bit = operand_b_i[8*b+7];
        end
        EW16: begin
          right_amount = {2'b0, operand_a_i[16*(b/2)+:4]};
          left_amount = {2'b0, operand_a_i[16*((7-b)/2)+:4]};
          sign_bit = operand_b_i[16*(b/2)+15];
        end
        EW32: begin
          right_amount = {1'b0, operand_a_i[32*(b/4)+:5]};
          left_amount = {1'b0, operand_a_i[32*((7-b)/4)+:5]};
          sign_bit = operand_b_i[32*(b/4)+31];
        end
        EW64: begin
          right_amount = operand_a_i[5:0];
          left_amount = operand_a_i[5:0];
          sign_bit = operand_b_i[63];
        end
        default:;
      endcase
    end
    assign shift_amount[b] = shift_left ? left_amount : right_amount;
    assign shift_fill[b] = shift_signed & sign_bit;
  end
  // Six constant-distance stages shared by every SEW and shift operation.
  // Cross-element inputs are replaced by zero or the element's original sign.
  for (genvar stage = 0; stage < 6; stage++) begin : gen_shift_stage
    for (genvar bitpos = 0; bitpos < 64; bitpos++) begin : gen_bit
      localparam int From = bitpos + (1 << stage);
      wire source_bit;
      if (From >= 64) begin
        assign source_bit = shift_fill[bitpos/8];
      end else begin
        localparam int MinSew = (bitpos/8 == From/8) ? 0 :
            (bitpos/16 == From/16) ? 1 : (bitpos/32 == From/32) ? 2 : 3;
        assign source_bit = shift_sew >= MinSew
            ? shift_stage[stage][From] : shift_fill[bitpos/8];
      end
      assign shift_stage[stage+1][bitpos] = shift_amount[bitpos/8][stage]
          ? source_bit : shift_stage[stage][bitpos];
    end
  end

  // A shared incrementer rounds the shifted low destination-width field.
  // In narrowing mode the upper half must neither receive nor propagate carry.
  for (genvar b = 0; b < 8; b++) begin : gen_shift_round
    always_comb begin
      round_start[b] = 1'b0;
      round_boundary[b] = 1'b1;
      case (vew_i)
        EW8: begin
          round_start[b] = shift_narrow ? ((b%2 == 0) & rm[b/2]) : rm[b];
          round_boundary[b] = 1'b1;
        end
        EW16: begin
          round_start[b] = shift_narrow ? ((b%4 == 0) & rm[b/4]) : ((b%2 == 0) & rm[b/2]);
          round_boundary[b] = b%2 == 0;
        end
        EW32: begin
          round_start[b] = shift_narrow ? ((b == 0) & rm[0]) : ((b%4 == 0) & rm[b/4]);
          round_boundary[b] = b%4 == 0;
        end
        EW64: begin
          round_start[b] = (b == 0) & rm[0];
          round_boundary[b] = b == 0;
        end
        default:;
      endcase
    end
    wire byte_all_ones = &shifted[8*b+:8];
    assign round_p[0][b] = byte_all_ones & ~round_boundary[b];
    assign round_g[0][b] = byte_all_ones & round_start[b];
    if (b == 0) assign round_cin[b] = round_start[b];
    else assign round_cin[b] = round_start[b] |
        (round_g[3][b-1] & ~round_boundary[b]);
    assign rounded[8*b+:8] = shifted[8*b+:8] + round_cin[b];
    assign round_cout[b] = byte_all_ones & round_cin[b];
  end
  for (genvar stage = 0; stage < 3; stage++) begin : gen_round_prefix
    for (genvar b = 0; b < 8; b++) begin : gen_byte
      if (b >= (1 << stage)) begin
        assign round_p[stage+1][b] = round_p[stage][b] & round_p[stage][b-(1 << stage)];
        assign round_g[stage+1][b] = round_g[stage][b] |
            (round_p[stage][b] & round_g[stage][b-(1 << stage)]);
      end else begin
        assign round_p[stage+1][b] = round_p[stage][b];
        assign round_g[stage+1][b] = round_g[stage][b];
      end
    end
  end
  for (genvar fmt = 0; fmt < 3; fmt++) begin : gen_narrow_format
    localparam int W = 8 << fmt;
    for (genvar e = 0; e < 64/(2*W); e++) begin : gen_element
      wire [W-1:0] high_bits = shifted[2*W*e+W+:W];
      wire [W-1:0] low_bits = rounded[2*W*e+:W];
      wire negative = shifted[2*W*e+2*W-1];
      wire carry = round_cout[(2*W*e+W)/8-1];
      wire signed_sat = negative
          ? ((!(&high_bits)) | (!carry & !low_bits[W-1]))
          : ((|high_bits) | carry | low_bits[W-1]);
      wire sat = shift_clip & ((op_i == VNCLIP) ? signed_sat : ((|high_bits) | carry));
      wire [W-1:0] limit = op_i == VNCLIP
          ? {negative, {(W-1){~negative}}} : {W{1'b1}};
      wire [W-1:0] value = shift_clip ? (sat ? limit : low_bits) : shifted[2*W*e+:W];
      assign narrow_result[fmt][2*W*e+:2*W] = narrowing_select_i
          ? {value, {W{1'b0}}} : {{W{1'b0}}, value};
      assign narrow_sat[fmt][2*W*e/8+:2*W/8] = narrowing_select_i
          ? {{(W/8){sat}}, {(W/8){1'b0}}} : {{(W/8){1'b0}}, {(W/8){sat}}};
    end
  end

  // Merge and min/max differ only in the per-element source selection.
  for (genvar b = 0; b < 8; b++) begin : gen_operand_select
    wire choose_max = op_i inside {VMAX, VMAXU, VREDMAX, VREDMAXU};
    logic [7:0] selectors;
    assign selectors = op_i == VMERGE ? mask_i : ~(less ^ {8{choose_max}});
    always_comb begin
      case (vew_i)
        EW8: select_a[b] = selectors[b];
        EW16: select_a[b] = selectors[2*(b/2)];
        EW32: select_a[b] = selectors[4*(b/4)];
        default: select_a[b] = selectors[0];
      endcase
    end
    assign selected_operand[8*b+:8] = select_a[b] ? operand_a_i[8*b+:8] : operand_b_i[8*b+:8];
  end

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

        // Shared shift, rounding and narrowing datapaths.
        VSLL, VSRL, VSRA:
          if (vew_i <= EW64) res = shifted;
        VNSRL, VNSRA:
          if (vew_i <= EW32) res = narrow_result[vew_i[1:0]];
        VSSRL, VSSRA:
          if (FixPtSupport == FixedPointEnable && vew_i <= EW64)
            res = rounded;
        VNCLIP, VNCLIPU:
          if (FixPtSupport == FixedPointEnable && vew_i <= EW32) begin
            res = narrow_result[vew_i[1:0]];
            vxsat = narrow_sat[vew_i[1:0]];
          end

        VMERGE:
          if (vew_i <= EW64) res = selected_operand;

        // Scalar move
        VMVSX, VFMVSF: res = opa;

        // Comparison instructions
        VMIN, VMINU, VMAX, VMAXU,
        VREDMINU, VREDMIN, VREDMAXU, VREDMAX:
          if (vew_i <= EW64) res = selected_operand;
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
