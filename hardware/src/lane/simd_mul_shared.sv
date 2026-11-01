// SPDX-License-Identifier: SHL-0.51
module simd_mul_shared import ara_pkg::*; import rvv_pkg::*; #(
  parameter fixpt_support_e FixPtSupport = FixedPointEnable,
  parameter int unsigned NumPipeRegs = 1,
  parameter bit Bypass8 = 1'b1
) (
  input logic clk_i, rst_ni,
  input elen_t operand_a_i, operand_b_i, operand_c_i,
  input logic [7:0] mask_i,
  input ara_op_e op_i,
  input logic [1:0] sew_i,
  input vxrm_t vxrm_i,
  input logic valid_i,
  output logic ready_o,
  input logic ready_i,
  output logic valid_o,
  output elen_t result_o,
  output logic [7:0] mask_o,
  output vxsat_t vxsat_o,
  output logic [1:0] sew_o
);
  typedef struct packed {
    logic [127:0] product;
    logic [63:0] c;
    logic [7:0] mask, sat;
    ara_op_e op;
    logic [1:0] sew;
  } payload_t;
  payload_t in_data, out_data;
  logic [7:0] sat_mode [4];
  simd_mul_shared_product core (
    .a_i(operand_a_i), .b_i(operand_b_i), .sew_i,
    .signed_a_i(op_i inside {VMULH, VSMUL}),
    .signed_b_i(op_i inside {VMULH, VMULHSU, VSMUL}), .product_o(in_data.product)
  );
  assign in_data.c = operand_c_i;
  assign in_data.mask = mask_i;
  assign in_data.op = op_i;
  assign in_data.sew = sew_i;
  assign in_data.sat = sat_mode[sew_i];
  for (genvar s=0; s<4; s++) begin : gen_sat
    localparam int N=8<<s;
    for (genvar e=0; e<64/N; e++) begin : gen_element
      localparam logic [N-1:0] Min = {1'b1, {(N-1){1'b0}}};
      assign sat_mode[s][e*(N/8)+:N/8] = {(N/8){
        FixPtSupport == FixedPointEnable && op_i == VSMUL &&
        operand_a_i[e*N+:N] == Min && operand_b_i[e*N+:N] == Min}};
    end
  end
  if (NumPipeRegs == 0) begin : gen_comb
    assign ready_o = ready_i;
    assign valid_o = valid_i;
    assign out_data = in_data;
  end else begin : gen_pipe
    payload_t data_q [NumPipeRegs];
    logic [NumPipeRegs-1:0] valid_q;
    logic [NumPipeRegs:0] ready;
    wire bypass = Bypass8 && sew_i == 0;
    wire empty = !(|valid_q);
    assign ready[NumPipeRegs] = ready_i;
    assign ready_o = bypass && valid_i ? empty && ready_i : ready[0];
    assign valid_o = valid_q[NumPipeRegs-1] || (empty && bypass && valid_i);
    assign out_data = valid_q[NumPipeRegs-1] ? data_q[NumPipeRegs-1] : in_data;
    for (genvar p=0; p<NumPipeRegs; p++) begin : gen_stage
      assign ready[p] = !valid_q[p] || ready[p+1];
      wire input_valid;
      payload_t input_data;
      if (p == 0) begin
        assign input_valid = valid_i && !bypass;
        assign input_data = in_data;
      end else begin
        assign input_valid = valid_q[p-1];
        assign input_data = data_q[p-1];
      end
      always_ff @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin valid_q[p] <= 0; data_q[p] <= '0; end
        else if (ready[p]) begin
          valid_q[p] <= input_valid;
          if (input_valid) data_q[p] <= input_data;
        end
      end
    end
  end
  assign mask_o = out_data.mask;
  assign vxsat_o = out_data.sat;
  assign sew_o = out_data.sew;
  logic [63:0] lo [4], hi [4], fractional [4], sat_value [4];
  logic [7:0] round_inc [4];
  for (genvar s=0; s<4; s++) begin : gen_route
    localparam int N=8<<s;
    for (genvar e=0; e<64/N; e++) begin : gen_element
      wire [2*N-1:0] prod = out_data.product[e*2*N+:2*N];
      assign lo[s][e*N+:N] = prod[N-1:0];
      assign hi[s][e*N+:N] = prod[2*N-1:N];
      assign fractional[s][e*N+:N] = prod[2*N-2:N-1];
      assign sat_value[s][e*N+:N] = {1'b0, {(N-1){1'b1}}};
      logic inc;
      always_comb case (vxrm_i)
        0: inc = prod[N-2];
        1: inc = prod[N-2] && (prod[N-1] || |prod[N-3:0]);
        2: inc = 0;
        3: inc = !prod[N-1] && |prod[N-2:0];
      endcase
      assign round_inc[s][e*(N/8)+:N/8] = {{(N/8-1){1'b0}},inc};
    end
  end
  logic [63:0] add_a, add_b, sum;
  logic [7:0] cin;
  always_comb begin
    add_a = lo[out_data.sew]; add_b = '0; cin = '0;
    case (out_data.op)
      VMULH, VMULHU, VMULHSU: add_a = hi[out_data.sew];
      VMACC, VMADD: add_b = out_data.c;
      VNMSAC, VNMSUB: begin add_a = ~lo[out_data.sew]; add_b = out_data.c; cin = '1; end
      VSMUL: begin add_a = fractional[out_data.sew]; cin = round_inc[out_data.sew]; end
      default: ;
    endcase
  end
  simd_mul_partition_add post_add (.a_i(add_a), .b_i(add_b), .sew_i(out_data.sew), .carry_i(cin), .sum_o(sum));
  always_comb begin
    result_o = sum;
    if (out_data.op == VSMUL) begin
      if (FixPtSupport == FixedPointEnable) begin
        for (int b=0; b<8; b++)
          if (out_data.sat[b]) result_o[b*8+:8] = sat_value[out_data.sew][b*8+:8];
      end else result_o = '0;
    end else if (!(out_data.op inside {VMUL,VMULH,VMULHU,VMULHSU,VMACC,VMADD,VNMSAC,VNMSUB})) result_o = '0;
  end
endmodule
