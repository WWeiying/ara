// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module shared_mul_bank_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  logic clk = 0, rst = 0;
  always #5 clk = ~clk;
  logic [63:0] a, b, c;
  logic [7:0] mask;
  ara_op_e op;
  vxrm_t rm;
  logic [1:0] sew;
  logic [3:0] valid, ready, ref_ready, out_valid, ref_valid, consume;
  logic [63:0] result [4], ref_result [4];
  logic [7:0] masks [4], ref_masks [4], sat [4], ref_sat [4];
  logic [127:0] product;
  logic input_fired;
  int accepted [4], retired [4];
  int unsigned rng = 32'h612ac732;
  ara_op_e ops [9] = '{VMUL, VMULH, VMULHU, VMULHSU, VMACC, VMADD,
                       VNMSAC, VNMSUB, VSMUL};
  function automatic int unsigned randword();
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return rng;
  endfunction
`ifdef TEST_VMFPU_BANK
  logic [3:0][63:0] bank_result;
  logic [3:0][7:0] bank_mask, bank_sat;
  extracted_shared_mul_bank dut_bank (
    .clk_i_gated(clk), .rst_ni(rst), .vmul_simd_op_a_q(a),
    .vmul_simd_op_b_q(b), .vmul_simd_op_c_q(c), .vmul_simd_mask_q(mask),
    .vmul_simd_op_q(op), .mfpu_vxrm_i(rm), .vmul_simd_in_valid_q(valid),
    .vmul_simd_out_ready(consume), .vmul_simd_in_ready(ready),
    .vmul_simd_out_valid(out_valid), .vmul_simd_result(bank_result),
    .vmul_simd_mask(bank_mask), .mfpu_vxsat(bank_sat)
  );
`else
  simd_mul_shared_product core (
    .a_i(a), .b_i(b), .sew_i(sew),
    .signed_a_i(op inside {VMULH, VSMUL}),
    .signed_b_i(op inside {VMULH, VMULHSU, VSMUL}), .product_o(product)
  );
`endif
  for (genvar s = 0; s < 4; s++) begin : gen_bank
`ifdef TEST_VMFPU_BANK
    assign result[s] = bank_result[s];
    assign masks[s] = bank_mask[s];
    assign sat[s] = bank_sat[s];
`else
    simd_mul #(.ElementWidth(vew_e'(s)), .NumPipeRegs(s == 0 ? 0 : 1),
               .ExternalProduct(1)) dut (
      .clk_i(clk), .rst_ni(rst), .operand_a_i(a), .operand_b_i(b),
      .operand_c_i(c), .product_i(product), .mask_i(mask), .op_i(op), .vxrm_i(rm),
      .valid_i(valid[s]), .ready_o(ready[s]), .ready_i(consume[s]),
      .valid_o(out_valid[s]), .result_o(result[s]), .mask_o(masks[s]), .vxsat_o(sat[s])
    );
`endif
    simd_mul_reference #(.ElementWidth(vew_e'(s)), .NumPipeRegs(s == 0 ? 0 : 1)) ref_dut (
      .clk_i(clk), .rst_ni(rst), .operand_a_i(a), .operand_b_i(b),
      .operand_c_i(c), .mask_i(mask), .op_i(op), .vxrm_i(rm),
      .valid_i(valid[s]), .ready_o(ref_ready[s]), .ready_i(consume[s]),
      .valid_o(ref_valid[s]), .result_o(ref_result[s]), .mask_o(ref_masks[s]), .vxsat_o(ref_sat[s])
    );
  end
  always @(posedge clk) if (rst) begin
    input_fired = |(valid & ready);
    assert (ready === ref_ready && out_valid === ref_valid)
      else $fatal(1, "shared bank handshake mismatch");
    for (int s = 0; s < 4; s++) begin
      if (valid[s] && ready[s]) accepted[s]++;
      if (out_valid[s]) begin
        assert ({result[s], masks[s], sat[s]} === {ref_result[s], ref_masks[s], ref_sat[s]})
          else $fatal(1, "shared bank result mismatch sew=%0d", s);
        if (consume[s]) retired[s]++;
      end
    end
  end
  initial begin
    a = 0; b = 0; c = 0; mask = 0; op = VMUL; rm = 0; sew = 0;
    valid = 0; consume = 0;
    repeat (3) @(negedge clk);
    rst = 1;
    for (int n = 0; n < 20000; n++) begin
      @(negedge clk);
      // Keep the producer transaction stable until accepted; consumers stall independently.
      if (valid == 0 || input_fired) begin
        sew = 2'(randword());
        valid = randword() % 5 ? 4'b0001 << sew : 4'b0000;
        a = {randword(), randword()}; b = {randword(), randword()};
        c = {randword(), randword()}; mask = 8'(randword());
        op = ops[randword() % 9];
      end
      rm = vxrm_t'(randword());
      consume = n < 2000 ? 4'b1111 : 4'(randword());
    end
    @(negedge clk);
    // Finish the current producer transaction before removing valid.
    consume = '1;
    @(negedge clk);
    valid = 0;
    repeat (3) @(negedge clk);
    for (int s = 0; s < 4; s++) begin
      assert (accepted[s] == retired[s] && accepted[s] > 100)
        else $fatal(1, "shared bank accounting mismatch sew=%0d accepted=%0d retired=%0d", s, accepted[s], retired[s]);
      $display("shared bank sew=%0d transactions=%0d", 8 << s, retired[s]);
    end
    $display("Shared MUL bank PASS");
    $finish;
  end
  initial begin #300000; $fatal(1, "shared bank watchdog"); end
endmodule
