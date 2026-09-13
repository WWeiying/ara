// SPDX-License-Identifier: SHL-0.51
module datapath_equivalence_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  logic clk_i = 0, rst_ni = 0;
  always #5 clk_i = ~clk_i;
  elen_t operand_a_i, operand_b_i, result_o, ref_result;
  logic valid_i, vm_i, narrowing_select_i;
  logic [7:0] mask_i, rm;
  ara_op_e op_i;
  vew_e vew_i;
  vxrm_t vxrm_i;
  vxsat_t vxsat_o, ref_sat;
  longint unsigned checks = 0, dot_checks = 0;
  int seed = 32'h12345678;
  ara_op_e operations [24] = '{VADD, VADC, VMADC, VSUB, VSBC, VMSBC, VRSUB,
      VSADD, VSADDU, VSSUB, VSSUBU, VAADD, VAADDU, VASUB, VASUBU,
      VSSRA, VSSRL, VNCLIP, VNCLIPU, VREDSUM, VWREDSUM, VWREDSUMU, VMIN, VMAX};
  fixed_p_rounding i_rounding (.r_o(rm), .*);
  simd_alu i_dut (.*);
  simd_alu_reference i_reference (.result_o(ref_result), .vxsat_o(ref_sat), .*);

  logic dot_input_valid, dot_valid, ref_dot_valid;
  logic [2:0] m_i, row_count_i;
  logic [15:0] stream_valid_i, stream_valid_o, ref_stream_valid;
  logic signed [7:0] weight_quant_i [4][8], activation_quant_i [4][8];
  logic signed [18:0] stream_sum_o [16], ref_stream_sum [16];
  typedef struct packed {
    logic [15:0] mask;
    logic [15:0][18:0] sums;
  } dot_result_t;
  dot_result_t expected_dot [$];
  qbs_dot_array i_dot (.valid_i(dot_input_valid), .valid_o(dot_valid), .*);
  qbs_dot_array_reference i_dot_reference (
      .valid_i(dot_input_valid), .valid_o(ref_dot_valid),
      .stream_valid_o(ref_stream_valid), .stream_sum_o(ref_stream_sum), .*);

  task automatic check_dot;
    dot_result_t value;
    if (!rst_ni) begin
      expected_dot.delete();
      assert (!dot_valid && !ref_dot_valid)
        else $fatal(1, "dot reset did not clear valid");
    end else begin
      if (ref_dot_valid) begin
        value.mask = ref_stream_valid;
        for (int stream = 0; stream < 16; stream++) value.sums[stream] = ref_stream_sum[stream];
        expected_dot.push_back(value);
      end
      if (dot_valid) begin
        assert (expected_dot.size() != 0) else $fatal(1, "dot output without input");
        value = expected_dot.pop_front();
        assert (stream_valid_o === value.mask) else $fatal(1, "dot stream mask mismatch");
        for (int stream = 0; stream < 16; stream++) begin
          assert (stream_sum_o[stream] === value.sums[stream])
            else $fatal(1, "dot stream=%0d got=%0d expected=%0d",
                stream, stream_sum_o[stream], $signed(value.sums[stream]));
          dot_checks++;
        end
      end
    end
  endtask

  task automatic check_alu;
    #1;
    checks++;
    assert ({result_o, vxsat_o} === {ref_result, ref_sat})
      else $fatal(1, "ALU op=%0d sew=%0d a=%h b=%h mode=%0d mask=%h got=%h/%h ref=%h/%h",
          op_i, vew_i, operand_a_i, operand_b_i, vxrm_i, mask_i,
          result_o, vxsat_o, ref_result, ref_sat);
  endtask

  task automatic check_prefix(input logic [64:0] a, b, c, input logic cin);
    assert (prefix_add65(a, b, cin) === 65'(a + b + cin))
      else $fatal(1, "prefix add a=%h b=%h carry=%b", a, b, cin);
    assert (prefix_sub65(a, b, cin) === 65'(a - b - cin))
      else $fatal(1, "prefix sub a=%h b=%h borrow=%b", a, b, cin);
    assert (prefix_add3_65(a, b, c, cin) === 65'(a + b + c + cin))
      else $fatal(1, "prefix add3 a=%h b=%h c=%h carry=%b", a, b, c, cin);
    checks += 3;
  endtask

  initial begin
    seed = $urandom(seed);
    dot_input_valid = 0;
    m_i = 1;
    row_count_i = 4;
    stream_valid_i = 0;
    weight_quant_i = '{default:'{default:0}};
    activation_quant_i = '{default:'{default:0}};
    valid_i = 0;
    #20;
    rst_ni = 1;
    for (int bit_index = 0; bit_index < 65; bit_index++) begin
      for (int cin = 0; cin < 2; cin++) begin
        check_prefix((65'd1 << bit_index)-1'b1, 65'd1, '0, 1'(cin));
        check_prefix('1, 65'd1 << bit_index, '1, 1'(cin));
        check_prefix('0, (65'd1 << bit_index)-1'b1, '0, 1'(cin));
      end
    end
    for (int trial = 0; trial < 10000; trial++)
      check_prefix({1'($urandom), $urandom, $urandom},
                   {1'($urandom), $urandom, $urandom},
                   {1'($urandom), $urandom, $urandom}, 1'($urandom));
    for (int sew = 0; sew < 4; sew++) begin
      vew_i = vew_e'(sew);
      for (int operation = 0; operation < 24; operation++) begin
        op_i = operations[operation];
        if (sew == 3 && op_i inside {VNCLIP, VNCLIPU}) continue;
        for (int trial = 0; trial < 1200; trial++) begin
          operand_a_i = {$urandom, $urandom};
          operand_b_i = {$urandom, $urandom};
          if (trial < 128) begin
            operand_a_i = (64'd1 << (trial / 2)) - 1'b1;
            operand_b_i = trial[0] ? '1 : 64'd1;
          end
          vxrm_i = vxrm_t'(trial % 4);
          narrowing_select_i = 1'(trial);
          valid_i = trial % 19 != 0;
          vm_i = 1'($urandom);
          mask_i = 8'($urandom);
          check_alu();
        end
      end
    end
    valid_i = 0;
    for (int trial = 0; trial < 12000; trial++) begin
      @(negedge clk_i);
      rst_ni = trial % 997 != 0;
      dot_input_valid = trial % 7 != 0;
      m_i = 3'(trial % 6);
      row_count_i = 3'((trial / 6) % 5);
      stream_valid_i = 16'($urandom);
      for (int row = 0; row < 4; row++)
        for (int lane = 0; lane < 8; lane++) begin
          weight_quant_i[row][lane] = trial < 600 ? -8'sd128 : 8'($urandom);
          activation_quant_i[row][lane] = trial < 600 ? -8'sd128 : 8'($urandom);
        end
      @(posedge clk_i);
      #1;
      check_dot();
    end
    @(negedge clk_i);
    rst_ni = 1;
    dot_input_valid = 0;
    repeat (5) begin
      @(posedge clk_i);
      #1;
      check_dot();
    end
    assert (expected_dot.size() == 0) else $fatal(1, "dot outputs lost during drain");
    $display("Timing datapath equivalence PASS arithmetic_checks=%0d dot_checks=%0d",
             checks, dot_checks);
    $finish;
  end
endmodule
