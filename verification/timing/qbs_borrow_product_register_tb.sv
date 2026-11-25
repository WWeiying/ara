module qbs_borrow_product_register_tb;
  import ara_pkg::*;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n, lease, native_idle, valid;
  logic [15:0] weights;
  logic [63:0] activations;
  logic [1:0] owned, ready, result_valid;
  logic signed [16:0] result_pair [2][4];
  int input_count, result_count;

  for (genvar i = 0; i < 2; i++) begin : gen_pair
    logic mul_valid_in, mul_ready_in, mul_valid_out, mul_ready_out;
    logic [63:0] a, b;
    logic [127:0] product;
    qbs_lane_mul_borrow #(.RegisteredMul(i == 1)) i_borrow (
      .clk_i(clk), .rst_ni(rst_n), .lease_i(lease), .native_quiescent_i(native_idle),
      .owned_o(owned[i]), .valid_i(valid), .ready_o(ready[i]),
      .weight_i(weights), .activation_i(activations),
      .mul_valid_o(mul_valid_in), .mul_a_o(a), .mul_b_o(b), .mul_ready_i(mul_ready_in),
      .mul_valid_i(mul_valid_out), .mul_product_i(product), .mul_ready_o(mul_ready_out),
      .result_valid_o(result_valid[i]), .result_pair_o(result_pair[i])
    );
    simd_mul_shared #(.Bypass8(i == 0)) i_mul (
      .clk_i(clk), .rst_ni(rst_n), .operand_a_i(a), .operand_b_i(b), .operand_c_i('0),
      .mask_i('1), .op_i(VMULH), .sew_i(2'b00), .vxrm_i('0),
      .valid_i(mul_valid_in), .ready_o(mul_ready_in), .ready_i(mul_ready_out),
      .valid_o(mul_valid_out), .product_o(product), .result_o(), .mask_o(), .vxsat_o(), .sew_o()
    );
  end

  always @(posedge clk) if (rst_n) begin
    if (owned[0] !== owned[1] || ready[0] !== ready[1] || result_valid[0] !== result_valid[1])
      $fatal(1, "borrow ownership or cadence mismatch");
    if (valid && ready[0]) input_count++;
    if (result_valid[0]) begin
      for (int i = 0; i < 4; i++)
        if ($isunknown(result_pair[0][i]) || result_pair[0][i] !== result_pair[1][i])
          $fatal(1, "borrow pair %0d mismatch result=%0d", i, result_count);
      result_count++;
    end
  end

  initial begin
    rst_n = 0; lease = 0; valid = 0; native_idle = 0;
    weights = 0; activations = 0;
    repeat (3) @(negedge clk);
    rst_n = 1;
    for (int episode = 0; episode < 64; episode++) begin
      lease = 1;
      native_idle = 0;
      repeat (2) @(negedge clk);
      if (owned != 0) $fatal(1, "borrow acquired during native use");
      native_idle = 1;
      @(negedge clk);
      if (ready != 2'b11) $fatal(1, "borrow could not acquire");
      for (int i = 0; i < 130; i++) begin
        valid = i < 96 || ($urandom_range(0, 3) != 0);
        weights = 16'($urandom);
        activations = {$urandom, $urandom};
        @(negedge clk);
      end
      valid = 0;
      lease = 0;
      repeat (6) @(negedge clk);
      if (owned != 0 || result_count != input_count) $fatal(1, "borrow did not drain");
    end
    $display("QBS_BORROW_PRODUCT_REGISTER_PASS transfers=%0d", result_count);
    $finish;
  end
endmodule
