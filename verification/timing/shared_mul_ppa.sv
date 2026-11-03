// SPDX-License-Identifier: SHL-0.51
// Identical registered boundaries around the extracted VMFPU integer bank.
// This measures a local subsystem, not the full VMFPU issue/result queues.
module shared_mul_ppa import ara_pkg::*; import rvv_pkg::*; (
  input logic clk_i, rst_ni,
  input elen_t a_i,b_i,c_i,
  input logic [7:0] mask_i,
  input ara_op_e op_i,
  input vxrm_t rm_i,
  input logic [1:0] sew_i,
  input logic valid_i, ready_i,
  output logic ready_o, valid_o,
  output elen_t result_o,
  output logic [7:0] mask_o, sat_o
);
  elen_t a,b,c;
  logic [7:0] mask;
  ara_op_e op;
  vxrm_t rm;
  logic [3:0] valid,ready,ov;
  elen_t [3:0] result;
  logic [3:0][7:0] masks,sats;
  elen_t selected_result;
  logic [7:0] selected_mask,selected_sat;
  logic selected_valid;
  // The register owns the preceding tag, not the next producer's SEW.
  assign ready_o = !(|valid) || |(valid & ready);
  extracted_shared_mul_bank bank (
    .clk_i_gated(clk_i),.rst_ni,
    .vmul_simd_op_a_q(a),.vmul_simd_op_b_q(b),.vmul_simd_op_c_q(c),
    .vmul_simd_mask_q(mask),.vmul_simd_op_q(op),.mfpu_vxrm_i(rm),
    .vmul_simd_in_valid_q(valid),.vmul_simd_out_ready({4{ready_i}}),
    .vmul_simd_in_ready(ready),.vmul_simd_out_valid(ov),
    .vmul_simd_result(result),.vmul_simd_mask(masks),.mfpu_vxsat(sats)
  );
  always_comb begin
    selected_result='0;selected_mask='0;selected_sat='0;selected_valid=|ov;
    for(int s=0;s<4;s++) if(ov[s]) begin
      selected_result=result[s];selected_mask=masks[s];selected_sat=sats[s];
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if(!rst_ni) begin
      a<='0;b<='0;c<='0;mask<='0;op<=VMUL;rm<='0;valid<='0;
      result_o<='0;mask_o<='0;sat_o<='0;valid_o<=0;
    end else begin
      rm<=rm_i;
      if(ready_o) begin
        a<=a_i;b<=b_i;c<=c_i;mask<=mask_i;op<=op_i;
        valid<=valid_i ? 4'b1<<sew_i : 4'b0;
      end
      if(ready_i) begin
        valid_o<=selected_valid;
        if(selected_valid) begin
          result_o<=selected_result;mask_o<=selected_mask;sat_o<=selected_sat;
        end
      end
    end
  end
endmodule
