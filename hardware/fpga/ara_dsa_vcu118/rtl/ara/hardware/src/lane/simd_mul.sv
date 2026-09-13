// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Authors: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
//          Matteo Perotti <mperotti@iis.ee.ethz.ch>
// Description:
// Ara's SIMD Multiplier, operating on elements 64-bit wide.
// The parametric number of pipeline register determines the intrinsic latency of the unit.
// Once the pipeline is full, the unit can generate 64 bits per cycle.

module simd_mul import ara_pkg::*; import rvv_pkg::*; #(
    // Support for fixed-point data types
    parameter  fixpt_support_e FixPtSupport = FixedPointEnable,
    // SIMD-multiplier parameters
    parameter  int    unsigned NumPipeRegs  = 0,
    parameter  vew_e           ElementWidth = EW64,
    // Dependant parameters. DO NOT CHANGE!
    localparam int    unsigned DataWidth    = $bits(elen_t),
    localparam int    unsigned StrbWidth    = DataWidth/8,
    localparam type            strb_t       = logic [DataWidth/8-1:0]
  ) (
    input  logic       clk_i,
    input  logic       rst_ni,
    input  elen_t      operand_a_i,
    input  elen_t      operand_b_i,
    input  elen_t      operand_c_i,
    input  strb_t      mask_i,
    input  ara_op_e    op_i,
    output elen_t      result_o,
    output strb_t      mask_o,
    output vxsat_t     vxsat_o,
    input  vxrm_t      vxrm_i,
    input  logic       valid_i,
    output logic       ready_o,
    input  logic       ready_i,
    output logic       valid_o
  );

`include "common_cells/registers.svh"

  ///////////////////
  //  Definitions  //
  ///////////////////

  typedef union packed {
    logic [0:0][63:0] w64;
    logic [1:0][31:0] w32;
    logic [3:0][15:0] w16;
    logic [7:0][ 7:0] w8;
  } mul_operand_t;

  typedef union packed {
    logic [0:0][127:0] w128;
    logic [1:0][63:0] w64;
    logic [3:0][31:0] w32;
    logic [7:0][15:0] w16;
  } mul_result_t;
  localparam int unsigned ElementBits = 8 << int'(ElementWidth);
  typedef logic [DataWidth/ElementBits-1:0] element_sat_t;
  mul_operand_t opc;
  mul_result_t input_product, mul_res;
  element_sat_t input_sat;
  element_sat_t [NumPipeRegs:0] sat_d;
  vxsat_t vxsat;
  ara_op_e      op;

  // Retain the existing handshake latency, but put its registers between
  // multiplication and accumulation/rounding instead of before both cones.
  wire signed_a = op_i inside {VMULH, VSMUL};
  wire signed_b = op_i inside {VMULH, VMULHSU, VSMUL};
  for (genvar l = 0; l < DataWidth/ElementBits; l++) begin : gen_input_product
    wire [ElementBits-1:0] a = operand_a_i[l*ElementBits +: ElementBits];
    wire [ElementBits-1:0] b = operand_b_i[l*ElementBits +: ElementBits];
    localparam logic [ElementBits-1:0] MinSigned = {1'b1, {(ElementBits-1){1'b0}}};
    assign input_product[l*2*ElementBits +: 2*ElementBits] =
        $signed({a[ElementBits-1] & signed_a, a}) *
        $signed({b[ElementBits-1] & signed_b, b});
    assign input_sat[l] = FixPtSupport == FixedPointEnable && op_i == VSMUL &&
                         a == MinSigned && b == MinSigned;
    assign vxsat[l*(ElementBits/8) +: ElementBits/8] =
        {(ElementBits/8){sat_d[NumPipeRegs][l]}};
  end

  ///////////////////////
  //  Pipeline stages  //
  ///////////////////////

  // Input signals for the next stage (= output signals of the previous stage)
  mul_operand_t [NumPipeRegs:0] opc_d;
  mul_result_t  [NumPipeRegs:0] product_d;
  ara_op_e      [NumPipeRegs:0] op_d;
  strb_t        [NumPipeRegs:0] mask_d;
  logic         [NumPipeRegs:0] valid_d;
  // Ready signal is combinatorial for all stages
  logic         [NumPipeRegs:0] stage_ready;

  // Input stage: First element of pipeline is taken from inputs
  assign product_d[0] = input_product;
  assign sat_d[0] = input_sat;
  assign opc_d[0]   = operand_c_i;
  assign op_d[0]    = op_i;
  assign mask_d[0]  = mask_i;
  assign valid_d[0] = valid_i;

  // Generate the pipeline stages in case they are needed
  if (NumPipeRegs > 0) begin : gen_pipeline
    // Pipelined versions of signals for later stages
    mul_operand_t [NumPipeRegs-1:0] opc_q;
    mul_result_t [NumPipeRegs-1:0] product_q;
    element_sat_t [NumPipeRegs-1:0] sat_q;
    strb_t [NumPipeRegs-1:0] mask_q;
    ara_op_e [NumPipeRegs-1:0] op_q;
    logic [NumPipeRegs-1:0] valid_q;

    for (genvar i = 0; i < NumPipeRegs; i++) begin : gen_pipeline_stages
      // Next state from previous register to form a shift register
      assign product_d[i+1] = product_q[i];
      assign sat_d[i+1] = sat_q[i];
      assign opc_d[i+1]   = opc_q[i];
      assign op_d[i+1]    = op_q[i];
      assign mask_d[i+1]  = mask_q[i];
      assign valid_d[i+1] = valid_q[i];

      // Determine the ready signal of the current stage - advance the pipeline:
      // 1. if the next stage is ready for our data
      // 2. if the next stage register only holds a bubble (not valid) -> we can pop it
      assign stage_ready[i] = stage_ready[i+1] | ~valid_q[i];

      // Enable register if pipeline ready
      logic reg_ena;
      assign reg_ena = stage_ready[i];

      // Generate the pipeline
      `FFL(valid_q[i], valid_d[i], reg_ena, '0)
      `FFL(product_q[i], product_d[i], reg_ena, '0)
      `FFL(sat_q[i], sat_d[i], reg_ena, '0)
      `FFL(opc_q[i], opc_d[i], reg_ena, '0)
      `FFL(op_q[i], op_d[i], reg_ena, ara_op_e'('0))
      `FFL(mask_q[i], mask_d[i], reg_ena, '0)
    end : gen_pipeline_stages
  end

  // Input stage: Propagate ready signal from pipeline
  assign ready_o = stage_ready[0];

  // Output stage: bind last stage outputs to the pipeline output. Directly connects to input if no
  // regs.
  assign mul_res = product_d[NumPipeRegs];
  assign opc     = opc_d[NumPipeRegs];
  assign op      = op_d[NumPipeRegs];
  assign mask_o  = mask_d[NumPipeRegs];
  assign valid_o = valid_d[NumPipeRegs];

  // Output stage: Ready travels backwards from output side
  assign stage_ready[NumPipeRegs] = ready_i;

  //////////////////
  //  Multiplier  //
  //////////////////

  // saturation and rounding mode
  vxrm_t  vxrm;
  strb_t  r;

  assign vxrm    = vxrm_i;
  assign vxsat_o = vxsat;


  if (ElementWidth == EW64) begin: gen_p_mul_ew64
    always_comb begin : p_mul
      // Default assignment
      result_o = '0;

      unique case (op)
        // Single-Width integer multiply instructions
        VMUL: for (int l = 0; l < 1; l++) result_o[64*l +: 64] = mul_res.w128[l][63:0];
        VSMUL: if (FixPtSupport == FixedPointEnable) begin
          unique case (vxrm)
            2'b00: for (int b=0; b<1; b++) r[b] = mul_res.w128[b][62];
            2'b01: for (int b=0; b<1; b++)
              r[b] = mul_res.w128[b][62] & ((mul_res.w128[b][61:0] != '0) | mul_res.w128[b][63]);
            2'b10: r ='0;
            2'b11: for (int b=0; b<1; b++) r[b] = !mul_res.w128[b][63] & (mul_res.w128[b][62:0] != '0);
          endcase
          for (int l = 0; l < 1; l++) begin
            if (|vxsat.w64[l])
              result_o[64*l +: 64] = 64'h7fff_ffff_ffff_ffff;
            else
              result_o[64*l +: 64] = prefix_add65(64'(mul_res.w128[l] >> 63), 65'd0, r[l]);
          end
        end
        VMULH,
        VMULHU,
        VMULHSU: for (int l = 0; l < 1; l++) result_o[64*l +: 64] = mul_res.w128[l][127:64];
        // Single-Width integer multiply-add instructions
        VMACC,
        VMADD: begin
          for (int l = 0; l < 1; l++) result_o[64*l +: 64] = prefix_add65(mul_res.w128[l][63:0], opc.w64[l], 1'b0);
        end
        VNMSAC,
        VNMSUB: begin
          for (int l = 0; l < 1; l++) result_o[64*l +: 64] = prefix_sub65(opc.w64[l], mul_res.w128[l][63:0], 1'b0);
        end
        default: result_o = '0;
      endcase
    end
  end : gen_p_mul_ew64 else if (ElementWidth == EW32) begin: gen_p_mul_ew32
    always_comb begin : p_mul
      unique case (op)
        // Single-Width integer multiply instructions
        VMUL: for (int l = 0; l < 2; l++) result_o[32*l +: 32] = mul_res.w64[l][31:0];
        VSMUL: if (FixPtSupport == FixedPointEnable) begin
          unique case (vxrm)
            2'b00: for (int b=0; b<2; b++) r[b] = mul_res.w64[b][30];
            2'b01: for (int b=0; b<2; b++) r[b] =
              mul_res.w64[b][30] & ((mul_res.w64[b][29:0] != '0) | mul_res.w64[b][31]);
            2'b10: r ='0;
            2'b11: for (int b=0; b<2; b++) r[b] = !mul_res.w64[b][31] & (mul_res.w64[b][30:0] != '0);
          endcase
          for (int l = 0; l < 2; l++) begin
            if (|vxsat.w32[l])
              result_o[32*l +: 32] = 32'h7fff_ffff;
            else
              result_o[32*l +: 32] = prefix_add65(32'(mul_res.w64[l] >> 31), 65'd0, r[l]);
          end
        end
        VMULH,
        VMULHU,
        VMULHSU: for (int l = 0; l < 2; l++) result_o[32*l +: 32] = mul_res.w64[l][63:32];
        // Single-Width integer multiply-add instructions
        VMACC,
        VMADD: for (int l = 0; l < 2; l++) result_o[32*l +: 32] = prefix_add65(mul_res.w64[l][31:0], opc.w32[l], 1'b0);
        VNMSAC,
        VNMSUB: for (int l = 0; l < 2; l++) begin
            result_o[32*l +: 32] = prefix_sub65(opc.w32[l], mul_res.w64[l][31:0], 1'b0);
          end
        default: result_o = '0;
      endcase
    end
  end : gen_p_mul_ew32 else if (ElementWidth == EW16) begin: gen_p_mul_ew16
    always_comb begin : p_mul
      unique case (op)
        // Single-Width integer multiply instructions
        VMUL: for (int l = 0; l < 4; l++) result_o[16*l +: 16] = mul_res.w32[l][15:0];
        VSMUL: if (FixPtSupport == FixedPointEnable) begin
          unique case (vxrm)
            2'b00: for (int b=0; b<4; b++) r[b] = mul_res.w32[b][14];
            2'b01: for (int b=0; b<4; b++) r[b] =
              mul_res.w32[b][14] & ((mul_res.w32[b][13:0] != '0) | mul_res.w32[b][15]);
            2'b10: r ='0;
            2'b11: for (int b=0; b<4; b++) r[b] = !mul_res.w32[b][15] & (mul_res.w32[b][14:0] != '0);
          endcase
          for (int l = 0; l < 4; l++) begin
            if (|vxsat.w16[l])
              result_o[16*l +: 16] = 16'h7fff;
            else
              result_o[16*l +: 16] = prefix_add65(16'(mul_res.w32[l] >> 15), 65'd0, r[l]);
          end
        end
        VMULH,
        VMULHU,
        VMULHSU: for (int l = 0; l < 4; l++) result_o[16*l +: 16] = mul_res.w32[l][31:16];
        // Single-Width integer multiply-add instructions
        VMACC,
        VMADD: for (int l = 0; l < 4; l++) result_o[16*l +: 16] = prefix_add65(mul_res.w32[l][15:0], opc.w16[l], 1'b0);
        VNMSAC,
        VNMSUB: for (int l = 0; l < 4; l++) begin
            result_o[16*l +: 16] = prefix_sub65(opc.w16[l], mul_res.w32[l][15:0], 1'b0);
          end
        default: result_o = '0;
      endcase
    end
  end : gen_p_mul_ew16 else if (ElementWidth == EW8) begin: gen_p_mul_ew8
    always_comb begin : p_mul
      unique case (op)
        // Single-Width integer multiply instructions
        VMUL: for (int l = 0; l < 8; l++) result_o[8*l +: 8] = mul_res.w16[l][7:0];
        VSMUL: if (FixPtSupport == FixedPointEnable) begin
          unique case (vxrm)
            2'b00: for (int b=0; b<8; b++) r[b] = mul_res.w16[b][6];
            2'b01: for (int b=0; b<8; b++) r[b] =
              mul_res.w16[b][6] & ((mul_res.w16[b][5:0] != '0) | mul_res.w16[b][7]);
            2'b10: r ='0;
            2'b11: for (int b=0; b<8; b++) r[b] = !mul_res.w16[b][7] & (mul_res.w16[b][6:0] != '0);
          endcase
          for (int l = 0; l < 8; l++) begin
            if (vxsat.w8[l])
              result_o[8*l +: 8] = 8'h7f;
            else
              result_o[8*l +: 8] = prefix_add65(8'(mul_res.w16[l] >> 7), 65'd0, r[l]);
          end
        end
        VMULH,
        VMULHU,
        VMULHSU: for (int l = 0; l < 8; l++) result_o[8*l +: 8] = mul_res.w16[l][15:8];
        // Single-Width integer multiply-add instructions
        VMACC,
        VMADD: for (int l = 0; l < 8; l++) result_o[8*l +: 8] = prefix_add65(mul_res.w16[l][7:0], opc.w8[l], 1'b0);
        VNMSAC,
        VNMSUB: for (int l = 0; l < 8; l++) result_o[8*l +: 8] = prefix_sub65(opc.w8[l], mul_res.w16[l][7:0], 1'b0);
        default: result_o = '0;
      endcase
    end
  end : gen_p_mul_ew8 else begin: gen_p_mul_error
    $error("[simd_vmul] Invalid ElementWidth.");
  end : gen_p_mul_error

endmodule : simd_mul
