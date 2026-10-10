module gather_stall_probe #(
    parameter int unsigned NrLanes = 4
) (
    input logic clk_i,
    input logic rst_ni,
    input logic issue_valid,
    input logic [7:0] issue_op,
    input ara_pkg::vid_t issue_id,
    input logic [15:0] issue_vl,
    input logic [15:0] issue_count,
    input logic [15:0] processing_count,
    input logic [15:0] gather_count,
    input logic [15:0] input_count,
    input logic [NrLanes-1:0] alu_valid,
    input logic [NrLanes-1:0] alu_ready,
    input logic [NrLanes-1:0] mask_valid,
    input logic [NrLanes-1:0] mask_ready,
    input logic [NrLanes-1:0] data_valid,
    input logic [NrLanes-1:0] data_ready,
    input logic index_empty,
    input logic index_full,
    input logic index_push,
    input logic index_pop,
    input logic request_empty,
    input logic request_full,
    input logic request_push,
    input logic request_pop,
    input logic index_out_of_range,
    input logic result_full,
    input logic result_valid
);
  longint unsigned cycle;
  int unsigned start_cycle = 86000;
  int unsigned stop_cycle = 86800;

  initial begin
    void'($value$plusargs("GATHER_PROBE_START=%d", start_cycle));
    void'($value$plusargs("GATHER_PROBE_STOP=%d", stop_cycle));
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= '0;
    end else begin
      cycle <= cycle + 1;
      if ($test$plusargs("GATHER_STALL_PROBE") &&
          cycle >= start_cycle && cycle <= stop_cycle) begin
        $display("[GATHER_STALL] cyc=%0d issue=%b op=%0d id=%0d vl=%0d left=%0d processing=%0d scan=%0d input=%0d alu=%b/%b mask=%b/%b data=%b/%b idx=%b/%b/%b/%b req=%b/%b/%b/%b oor=%b result=%b/%b",
                 cycle, issue_valid, issue_op, issue_id, issue_vl,
                 issue_count, processing_count, gather_count, input_count,
                 alu_valid, alu_ready, mask_valid, mask_ready,
                 data_valid, data_ready, index_empty, index_full,
                 index_push, index_pop, request_empty, request_full,
                 request_push, request_pop, index_out_of_range,
                 result_full, result_valid);
      end
      if ($test$plusargs("GATHER_STALL_PROBE") && cycle == stop_cycle)
        $finish;
    end
  end
endmodule

bind masku gather_stall_probe #(.NrLanes(NrLanes)) i_gather_stall_probe (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .issue_valid(vinsn_issue_valid),
    .issue_op(vinsn_issue.op),
    .issue_id(vinsn_issue.id),
    .issue_vl(vinsn_issue.vl),
    .issue_count(issue_cnt_q),
    .processing_count(processing_cnt_q),
    .gather_count(vrgat_cnt_q),
    .input_count(in_ready_cnt_q),
    .alu_valid(masku_operand_alu_valid),
    .alu_ready(masku_operand_alu_ready),
    .mask_valid(masku_operand_m_valid),
    .mask_ready(masku_operand_m_ready),
    .data_valid(masku_operand_vd_valid),
    .data_ready(masku_operand_vd_ready),
    .index_empty(vrgat_idx_fifo_empty),
    .index_full(vrgat_idx_fifo_full),
    .index_push(vrgat_idx_fifo_push),
    .index_pop(vrgat_idx_fifo_pop),
    .request_empty(vrgat_req_fifo_empty),
    .request_full(vrgat_req_fifo_full),
    .request_push(vrgat_req_fifo_push),
    .request_pop(vrgat_req_fifo_pop),
    .index_out_of_range(vrgat_idx_oor_q),
    .result_full(result_queue_full),
    .result_valid(out_vrf_word_valid)
);
