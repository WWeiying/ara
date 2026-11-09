// Passive verification probes. No DUT signals are driven or forced.
module resident_lane_monitor #(
  parameter int LaneIdWidth = 2
) (
  input logic clk_i, rst_ni,
  input logic [LaneIdWidth-1:0] lane_id_i,
  input logic issue_valid_i, processing_valid_i,
  input logic [31:0] issue_op_i, issue_id_i, issue_remaining_i, state_i,
  input logic [31:0] sew_i, resize_i,
  input logic [2:0] operand_valid_i, operand_ready_i, operand_required_i,
  input logic operands_valid_i, mask_valid_i, vm_i, latency_stall_i,
  input logic fp_valid_i, fp_ready_i, fp_out_valid_i, fp_out_ready_i,
  input logic result_full_i, result_req_i, result_gnt_i,
  input logic [7:0] issue_be_i
);
  string prefix, path;
  integer fd;
  bit enabled;
  longint unsigned cycle, first_cycle, end_cycle, rows;
  initial begin
    enabled = $value$plusargs("RESIDENT_TRACE=%s", prefix);
    first_cycle = 125000;
    end_cycle = 162000;
    if ($value$plusargs("RESIDENT_FIRST=%d", first_cycle)) begin end
    if ($value$plusargs("RESIDENT_END=%d", end_cycle)) begin end
    if (enabled && (end_cycle <= first_cycle || end_cycle-first_cycle > 200000))
      $fatal(1, "Invalid resident trace interval");
    fd = 0;
  end
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= 0;
      rows <= 0;
    end else begin
      cycle <= cycle + 1;
      if (enabled && !fd) begin
        path = $sformatf("%s.lane%0d.csv", prefix, lane_id_i);
        fd = $fopen(path, "w");
        if (!fd) $fatal(1, "Cannot open resident lane trace");
        $fdisplay(fd, "cycle,issue_valid,processing_valid,issue_op,issue_id,issue_remaining,state,sew,resize,operand_valid,operand_ready,operand_required,operands_valid,mask_valid,vm,latency_stall,fp_valid,fp_ready,fp_out_valid,fp_out_ready,result_full,result_req,result_gnt,issue_be");
      end
      if (enabled && cycle >= first_cycle && cycle < end_cycle) begin
        $fdisplay(fd, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
          cycle, issue_valid_i, processing_valid_i, issue_op_i, issue_id_i,
          issue_remaining_i, state_i, sew_i, resize_i, operand_valid_i,
          operand_ready_i, operand_required_i, operands_valid_i, mask_valid_i,
          vm_i, latency_stall_i, fp_valid_i, fp_ready_i, fp_out_valid_i,
          fp_out_ready_i, result_full_i, result_req_i, result_gnt_i, issue_be_i);
        rows <= rows + 1;
      end
    end
  end
  final begin
    if (enabled) begin
      $display("[RESIDENT_LANE] lane=%0d first=%0d end=%0d rows=%0d", lane_id_i, first_cycle, end_cycle, rows);
      if (fd) $fclose(fd);
    end
  end
endmodule

bind vmfpu resident_lane_monitor #(.LaneIdWidth($bits(lane_id_i))) i_resident_lane_monitor (
  .clk_i(clk_i), .rst_ni(rst_ni), .lane_id_i(lane_id_i),
  .issue_valid_i(vinsn_issue_q_valid), .processing_valid_i(vinsn_processing_q_valid),
  .issue_op_i(32'(vinsn_issue_q.op)), .issue_id_i(32'(vinsn_issue_q.id)),
  .issue_remaining_i(32'(issue_cnt_q)), .state_i(32'(mfpu_state_q)),
  .sew_i(32'(vinsn_issue_q.vtype.vsew)), .resize_i(32'(vinsn_issue_q.cvt_resize)),
  .operand_valid_i(mfpu_operand_valid_i), .operand_ready_i(mfpu_operand_ready_o),
  .operand_required_i(operands_ready), .operands_valid_i(operands_valid),
  .mask_valid_i(mask_valid_i), .vm_i(vinsn_issue_q.vm), .latency_stall_i(latency_stall),
  .fp_valid_i(vfpu_in_valid), .fp_ready_i(vfpu_in_ready),
  .fp_out_valid_i(vfpu_out_valid), .fp_out_ready_i(vfpu_out_ready),
  .result_full_i(result_queue_full), .result_req_i(mfpu_result_req_o),
  .result_gnt_i(mfpu_result_gnt_i), .issue_be_i(issue_be)
);

module resident_akv_monitor #(
  parameter int NrLanes = 4
) (
  input logic clk_i, rst_ni,
  input logic front_valid_i, front_ready_i,
  input logic [31:0] insn_i,
  input logic command_fire_i, terminal_i, busy_i, ara_idle_i,
  input logic [31:0] state_i, command_i, word_i, column_i,
  input logic [NrLanes-1:0] replay_req_i, replay_gnt_i, replay_final_i,
  input logic [NrLanes-1:0] accepted_i, final_seen_i,
  input logic column_busy_i, column_valid_i, column_bank_i, bank_conflict_i,
  input logic ar_valid_i, ar_ready_i, r_valid_i, r_ready_i
);
  string prefix;
  integer fd;
  bit enabled;
  longint unsigned cycle, first_cycle, end_cycle, rows;
  initial begin
    enabled = $value$plusargs("RESIDENT_TRACE=%s", prefix);
    first_cycle = 125000;
    end_cycle = 162000;
    if ($value$plusargs("RESIDENT_FIRST=%d", first_cycle)) begin end
    if ($value$plusargs("RESIDENT_END=%d", end_cycle)) begin end
    if (enabled && (end_cycle <= first_cycle || end_cycle-first_cycle > 200000))
      $fatal(1, "Invalid resident trace interval");
    fd = 0;
    if (enabled) begin
      fd = $fopen({prefix, ".akv.csv"}, "w");
      if (!fd) $fatal(1, "Cannot open resident AKV trace");
      $fdisplay(fd, "cycle,front_valid,front_ready,insn,command_fire,terminal,busy,ara_idle,state,command,word,column,replay_req,replay_gnt,replay_final,accepted,final_seen,column_busy,column_valid,column_bank,bank_conflict,ar_valid,ar_ready,r_valid,r_ready");
    end
  end
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= 0;
      rows <= 0;
    end else begin
      cycle <= cycle + 1;
      if (enabled && cycle >= first_cycle && cycle < end_cycle) begin
        $fdisplay(fd, "%0d,%0d,%0d,%08h,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d",
          cycle, front_valid_i, front_ready_i, insn_i, command_fire_i, terminal_i,
          busy_i, ara_idle_i, state_i, command_i, word_i, column_i,
          replay_req_i, replay_gnt_i, replay_final_i, accepted_i, final_seen_i,
          column_busy_i, column_valid_i, column_bank_i, bank_conflict_i,
          ar_valid_i, ar_ready_i, r_valid_i, r_ready_i);
        rows <= rows + 1;
      end
    end
  end
  final begin
    if (enabled) begin
      $display("[RESIDENT_AKV] first=%0d end=%0d rows=%0d", first_cycle, end_cycle, rows);
      if (fd) $fclose(fd);
    end
  end
endmodule

`define RES_AKV i_ara.i_vlsu.i_akv_engine
bind ara_system resident_akv_monitor #(.NrLanes($bits(i_ara.i_vlsu.akv_ldu_result_req))) i_resident_akv_monitor (
  .clk_i(clk_i), .rst_ni(rst_ni),
  .front_valid_i(acc_req.acc_req.req_valid), .front_ready_i(acc_resp.acc_resp.req_ready),
  .insn_i(acc_req.acc_req.insn), .command_fire_i(i_ara.i_vlsu.akv_command_fire),
  .terminal_i(i_ara.i_vlsu.akv_terminal), .busy_i(i_ara.i_vlsu.akv_busy),
  .ara_idle_i(i_ara.ara_idle), .state_i(32'(`RES_AKV.state_q)),
  .command_i(32'(`RES_AKV.active_command_q)), .word_i(32'(`RES_AKV.replay_word_q)),
  .column_i(32'(`RES_AKV.replay_column_index_q)),
  .replay_req_i(i_ara.i_vlsu.akv_ldu_result_req),
  .replay_gnt_i(i_ara.i_vlsu.akv_ldu_result_gnt),
  .replay_final_i(i_ara.i_vlsu.akv_ldu_result_final_gnt),
  .accepted_i(`RES_AKV.replay_accepted_q), .final_seen_i(`RES_AKV.replay_final_seen_q),
  .column_busy_i(`RES_AKV.v2_column_busy), .column_valid_i(`RES_AKV.v2_column_valid),
  .column_bank_i(`RES_AKV.v2_column_bank_cycle), .bank_conflict_i(`RES_AKV.v2_context_conflict),
  .ar_valid_i(i_ara.i_vlsu.akv_axi_ar_valid), .ar_ready_i(i_ara.i_vlsu.akv_axi_ar_ready),
  .r_valid_i(i_ara.i_vlsu.akv_axi_r_valid), .r_ready_i(i_ara.i_vlsu.akv_axi_r_ready)
);
`undef RES_AKV
