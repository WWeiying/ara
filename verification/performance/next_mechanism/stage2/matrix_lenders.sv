`timescale 1ns/1ps

// Engine-level lane resource model, not a SoC or VMFPU ownership acceptance.
// The four real EW8 multipliers below are the existing lane resources in this
// fixture. There is no substitute behavioral dot-product array.
module stage2_matrix_lenders import ara_pkg::*; import rvv_pkg::*; #(
  parameter bit CooperativeWaves = 1'b0
) (
  input logic clk_i, rst_ni,
  input logic lease_i, command_fire_i, success_i, fault_i,
  input logic [3:0] command_m_i, profile_i,
  input logic [5:0] command_n_i,
  input logic [31:0] engine_pairs_i, engine_dot_cycles_i,
  input logic native_valid_i,
  input logic [15:0] native_stream_valid_i,
  input logic [3:0] native_k_per_i,
  input logic loan_valid_i,
  output logic [3:0] loan_ready_o,
  input logic [15:0] loan_weight_i [4],
  input logic [63:0] loan_activation_i,
  output logic [3:0] loan_result_valid_o,
  output logic signed [16:0] loan_result_pair_o [4][4]
);
  logic [3:0] owned, mul_request, mul_ready, mul_result_valid, mul_result_ready;
  logic [63:0] mul_a [4], mul_b [4];
  logic [127:0] product [4];
  for (genvar lane = 0; lane < 4; lane++) begin : gen_lane
    qbs_lane_mul_borrow borrower (
      .clk_i, .rst_ni, .lease_i, .native_quiescent_i(1'b1), .owned_o(owned[lane]),
      .valid_i(loan_valid_i), .ready_o(loan_ready_o[lane]),
      .weight_i(loan_weight_i[lane]), .activation_i(loan_activation_i),
      .mul_valid_o(mul_request[lane]), .mul_a_o(mul_a[lane]), .mul_b_o(mul_b[lane]),
      .mul_ready_i(mul_ready[lane]), .mul_valid_i(mul_result_valid[lane]),
      .mul_product_i(product[lane]), .mul_ready_o(mul_result_ready[lane]),
      .result_valid_o(loan_result_valid_o[lane]), .result_pair_o(loan_result_pair_o[lane])
    );
    simd_mul #(.ElementWidth(EW8), .NumPipeRegs(0), .ExternalProduct(1'b0)) multiplier (
      .clk_i, .rst_ni, .operand_a_i(mul_a[lane]), .operand_b_i(mul_b[lane]),
      .operand_c_i('0), .product_i('0), .op_i(VMULH), .mask_i('1),
      .vxrm_i(vxrm_t'(0)), .valid_i(mul_request[lane]), .ready_o(mul_ready[lane]),
      .ready_i(mul_result_ready[lane]), .valid_o(mul_result_valid[lane]),
      .result_o(), .product_o(product[lane]), .mask_o(), .vxsat_o()
    );
  end

  logic [2:0] return_due;
  logic terminal_seen, command_active = 0;
  longint unsigned sequence_id = 0, commands = 0;
  longint unsigned native_issues = 0, native_useful = 0;
  longint unsigned loan_issues = 0, loan_useful = 0, loan_returns = 0;
  longint unsigned total_native = 0, total_loan = 0, total_returns = 0;
  longint unsigned reset_commands = 0, reset_flushed = 0;
  wire eligible = CooperativeWaves && command_m_i == 8 && profile_i == 1;
  wire loan_fire = loan_valid_i && (&loan_ready_o);

  always @(posedge clk_i) begin
    if (!rst_ni) begin
      if (command_active) begin
        $display("STAGE2_MATRIX_RESET seq=%0d native_issues=%0d loan_issues=%0d loan_returns=%0d",
          sequence_id, native_issues, loan_issues, loan_returns);
        reset_commands++;
        reset_flushed += loan_issues - loan_returns;
        command_active = 0;
      end
      return_due <= '0;
      terminal_seen = 0;
      native_issues = 0; native_useful = 0;
      loan_issues = 0; loan_useful = 0; loan_returns = 0;
    end else begin
      assert (loan_result_valid_o === {4{return_due[2]}})
        else $fatal(1, "STAGE2_MATRIX fixed-three-cycle loan response");
      return_due <= {return_due[1:0], loan_fire};
      assert (!loan_valid_i || (eligible && (&owned) && (&loan_ready_o) && native_valid_i))
        else $fatal(1, "STAGE2_MATRIX non-atomic or ineligible loan");
      assert (!eligible || native_valid_i === loan_valid_i)
        else $fatal(1, "STAGE2_MATRIX native/loan issue split");
      assert (mul_result_valid === mul_request)
        else $fatal(1, "STAGE2_MATRIX real EW8 multiplier did not execute");
      if (command_fire_i) begin
        assert (return_due == 0 && loan_result_valid_o == 0)
          else $fatal(1, "STAGE2_MATRIX previous command did not drain");
        sequence_id++;
        command_active = 1;
        terminal_seen = 0;
        native_issues = 0; native_useful = 0;
        loan_issues = 0; loan_useful = 0; loan_returns = 0;
      end
      if (native_valid_i) begin
        native_issues++;
        native_useful += $countones(native_stream_valid_i) * native_k_per_i;
        total_native++;
      end
      if (loan_fire) begin
        loan_issues++;
        loan_useful += $countones(native_stream_valid_i) * 2;
        total_loan++;
      end
      if (&loan_result_valid_o) begin
        loan_returns++;
        total_returns++;
      end
      if ((success_i || fault_i) && !terminal_seen) begin
        assert (return_due == 0 && loan_result_valid_o == 0 && loan_issues == loan_returns)
          else $fatal(1, "STAGE2_MATRIX terminal before real lender drain");
        if (success_i) begin
          assert (native_useful + loan_useful == engine_pairs_i &&
                  native_issues == engine_dot_cycles_i)
            else $fatal(1, "STAGE2_MATRIX native/loan useful-work accounting");
          assert (eligible ? (loan_issues == native_issues && loan_useful == native_useful)
                           : (loan_issues == 0))
            else $fatal(1, "STAGE2_MATRIX fallback or paired work accounting");
        end
        commands++;
        command_active = 0;
        terminal_seen = 1;
        $display("STAGE2_MATRIX_COMMAND seq=%0d cooperative=%0d m=%0d n=%0d profile=%0d success=%0d fault=%0d native_issues=%0d native_useful=%0d native_products=%0d loan_issues=%0d loan_useful=%0d loan_products=%0d loan_returns=%0d latency=3",
          sequence_id, CooperativeWaves, command_m_i, command_n_i, profile_i,
          success_i, fault_i, native_issues, native_useful, native_issues*32,
          loan_issues, loan_useful, loan_issues*32, loan_returns);
      end
    end
  end
  final begin
    $display("STAGE2_MATRIX_LENDERS_DONE commands=%0d native_issues=%0d loan_issues=%0d loan_returns=%0d reset_commands=%0d reset_flushed=%0d latency=3 instances=4 scope=engine_not_soc",
      commands, total_native, total_loan, total_returns, reset_commands, reset_flushed);
  end
endmodule
