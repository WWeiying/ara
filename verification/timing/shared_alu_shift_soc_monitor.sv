// SPDX-License-Identifier: SHL-0.51
// Read-only, whole-VALU probe. Counts are beats/cycles, not instructions.
module shared_alu_shift_soc_monitor import ara_pkg::*; import rvv_pkg::*; #(
  parameter fixpt_support_e FixPtSupport = FixedPointEnable
) (
  input logic clk_i, rst_ni, valid_i, vm_i, narrowing_select_i,
  input elen_t operand_a_i, operand_b_i, actual_result,
  input vxsat_t actual_sat,
  input logic [7:0] mask_i, rm,
  input ara_op_e op_i,
  input vew_e vew_i,
  input vxrm_t vxrm_i,
  input logic [7:0] observed_be_i, raw_write_be_i,
  input logic issue_pending, queue_full, wb_req, wb_gnt, mask_fire
);
  elen_t expected_result;
  vxsat_t expected_sat;
  longint unsigned cycle, evaluated[4], writebacks, wb_blocked;
  longint unsigned pending_not_evaluated, pending_queue_full, mask_outputs;
  simd_alu_reference #(.FixPtSupport(FixPtSupport)) i_reference (
    .result_o(expected_result), .vxsat_o(expected_sat), .*);
  logic observation_ok;
  logic [7:0] inactive_x_bytes;
  longint unsigned inactive_x_events;
  shared_alu_observation i_observation (.check_ok(observation_ok), .*);
  initial $display("ALU_SOC_MONITOR %m");
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      cycle = 0; inactive_x_events = 0; writebacks = 0; wb_blocked = 0;
      pending_not_evaluated = 0; pending_queue_full = 0; mask_outputs = 0;
      foreach (evaluated[s]) evaluated[s] = 0;
    end else begin
      cycle++;
      if (valid_i) begin
        assert (observation_ok)
          else $fatal(1, "ALU_SOC_MISMATCH %m cycle=%0d op=%0d sew=%0d a=%h b=%h mask=%h vxrm=%0d got=%h/%h expected=%h/%h observed_be=%h raw_be=%h",
              cycle, op_i, vew_i, operand_a_i, operand_b_i, mask_i, vxrm_i,
              actual_result, actual_sat, expected_result, expected_sat, observed_be_i, raw_write_be_i);
        if (|inactive_x_bytes) begin
          if (inactive_x_events < 8)
            $display("ALU_INACTIVE_X %m cycle=%0d op=%0d sew=%0d select=%b a=%h b=%h observed_be=%h raw_be=%h inactive_x=%h got=%h/%h ref=%h/%h",
                cycle, op_i, vew_i, narrowing_select_i, operand_a_i, operand_b_i,
                observed_be_i, raw_write_be_i, inactive_x_bytes,
                actual_result, actual_sat, expected_result, expected_sat);
          inactive_x_events++;
        end
        if (vew_i <= EW64) evaluated[vew_i[1:0]]++;
      end
      if (wb_req && wb_gnt) writebacks++;
      if (wb_req && !wb_gnt) wb_blocked++;
      if (issue_pending && !valid_i) pending_not_evaluated++;
      if (issue_pending && queue_full) pending_queue_full++;
      if (mask_fire) mask_outputs++;
    end
  end
  final $display("ALU_OBSERVATION_SUMMARY %m inactive_x_events=%0d", inactive_x_events);
  final $display("ALU_SOC_ACTIVITY %m eval=%0d,%0d,%0d,%0d wb=%0d wb_blocked=%0d pending=%0d queue_full=%0d mask=%0d",
      evaluated[0],evaluated[1],evaluated[2],evaluated[3],writebacks,wb_blocked,
      pending_not_evaluated,pending_queue_full,mask_outputs);
endmodule

bind valu shared_alu_shift_soc_monitor #(.FixPtSupport(FixPtSupport)) i_alu_soc_monitor (
  .clk_i(clk_i), .rst_ni(rst_ni), .valid_i(valu_valid),
  .vm_i(vinsn_issue_q.vm), .narrowing_select_i(narrowing_select_q),
  .operand_a_i(alu_operand_a), .operand_b_i(alu_operand_b),
  .actual_result(valu_result), .actual_sat(alu_vxsat),
  .mask_i((mask_valid_i && !vinsn_issue_q.vm) ? mask_i : {StrbWidth{1'b1}}),
  .raw_write_be_i(result_write.be),
  .observed_be_i(result_write.be &
      (narrowing(vinsn_issue_q.op) ? masked_narrow_preserve_be : {StrbWidth{1'b1}}) &
      (vinsn_issue_q.preserve_narrow_vd
       ? (active_from_vstart(vinsn_issue_q.vl - issue_cnt_q,
                            vinsn_issue_q.vstart, vinsn_issue_q.vtype.vsew) &
          (vinsn_issue_q.vm ? {StrbWidth{1'b1}} : mask_i))
       : {StrbWidth{1'b1}})),
  .rm(r), .op_i(vinsn_issue_q.op), .vew_i(vinsn_issue_q.vtype.vsew),
  .vxrm_i(alu_vxrm_i), .issue_pending(vinsn_issue_valid),
  .queue_full(result_queue_full), .wb_req(alu_result_req_o),
  .wb_gnt(alu_result_gnt_i), .mask_fire(mask_operand_gnt)
);
