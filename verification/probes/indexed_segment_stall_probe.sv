module indexed_segment_stall_probe #(
    parameter int unsigned NrLanes = 4,
    parameter int unsigned VLEN = 1024
) (
    input logic clk_i,
    input logic rst_ni,
    input ara_pkg::vid_t idx_id,
    input logic [$clog2(VLEN+1)-1:0] idx_vstart,
    input logic [$clog2(VLEN+1)-1:0] idx_vl,
    input logic [$clog2(VLEN+1)-1:0] idx_remaining,
    input logic idx_valid,
    input logic idx_ready,
    input logic predicate_valid,
    input logic predicate_active,
    input ara_pkg::vid_t mask_owner,
    input logic [$clog2(VLEN+1)-1:0] mask_first,
    input logic [NrLanes-1:0] mask_word_valid,
    input logic queue_empty,
    input logic queue_full,
    input logic descriptor_push,
    input logic descriptor_skip,
    input logic ar_valid,
    input logic ar_ready,
    input logic addrgen_req_valid,
    input logic addrgen_req_ready,
    input logic vldu_issue_valid,
    input ara_pkg::vid_t vldu_issue_id,
    input logic [NrLanes-1:0] vldu_mask_valid,
    input ara_pkg::vid_t vldu_mask_owner,
    input logic [$clog2(VLEN+1)-1:0] vldu_mask_first,
    input logic vldu_descriptor_valid,
    input logic vldu_descriptor_ready,
    input logic r_valid,
    input logic r_ready,
    input logic [NrLanes-1:0] result_grant,
    input logic [15:0] result_queue_count,
    input logic [15:0] issue_bytes,
    input logic [15:0] commit_bytes,
    input logic vinsn_done
);
  longint unsigned cycle;
  int unsigned start_cycle = 8100;
  int unsigned stop_cycle = 8300;

  initial begin
    void'($value$plusargs("IDX_PROBE_START=%d", start_cycle));
    void'($value$plusargs("IDX_PROBE_STOP=%d", stop_cycle));
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      cycle <= '0;
    end else begin
      cycle <= cycle + 1;
      if ($test$plusargs("INDEXED_SEG_STALL_PROBE") &&
          cycle >= start_cycle && cycle <= stop_cycle) begin
        $display("[IDX_SEG_STALL] cyc=%0d ag=%0d:%0d/%0d left=%0d idx=%b/%b pred=%b/%b mask=%0d:%0d:%b q=%b/%b push=%b skip=%b ar=%b/%b req=%b/%b ld=%b:%0d lmask=%b:%0d:%0d desc=%b/%b r=%b/%b grant=%b resq=%0d issueB=%0d commitB=%0d done=%b",
                 cycle, idx_id, idx_vstart, idx_vl, idx_remaining,
                 idx_valid, idx_ready, predicate_valid, predicate_active,
                 mask_owner, mask_first, mask_word_valid, queue_empty, queue_full,
                 descriptor_push, descriptor_skip, ar_valid, ar_ready,
                 addrgen_req_valid, addrgen_req_ready, vldu_issue_valid,
                 vldu_issue_id, vldu_mask_valid, vldu_mask_owner,
                 vldu_mask_first, vldu_descriptor_valid, vldu_descriptor_ready,
                 r_valid, r_ready, result_grant, result_queue_count,
                 issue_bytes, commit_bytes, vinsn_done);
      end
      if ($test$plusargs("INDEXED_SEG_STALL_PROBE") && cycle == stop_cycle) begin
        $finish;
      end
    end
  end
endmodule

bind vlsu indexed_segment_stall_probe #(.NrLanes(NrLanes), .VLEN(VLEN)) i_indexed_segment_stall_probe (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .idx_id(i_addrgen.pe_req_q.id),
    .idx_vstart(i_addrgen.pe_req_q.vstart),
    .idx_vl(i_addrgen.pe_req_q.vl),
    .idx_remaining(i_addrgen.idx_op_cnt_q),
    .idx_valid(i_addrgen.idx_vaddr_valid_q),
    .idx_ready(i_addrgen.idx_vaddr_ready_d),
    .predicate_valid(i_addrgen.idx_predicate_valid),
    .predicate_active(i_addrgen.idx_predicate_active),
    .mask_owner(i_addrgen.ldu_mask_owner_id_i),
    .mask_first(i_addrgen.ldu_mask_first_element_i),
    .mask_word_valid(i_addrgen.ldu_mask_word_valid_i),
    .queue_empty(i_addrgen.axi_addrgen_queue_empty),
    .queue_full(i_addrgen.axi_addrgen_queue_full),
    .descriptor_push(i_addrgen.axi_addrgen_queue_push),
    .descriptor_skip(i_addrgen.axi_addrgen_queue.is_skip),
    .ar_valid(i_addrgen.axi_ar_valid_o),
    .ar_ready(i_addrgen.axi_ar_ready_i),
    .addrgen_req_valid(i_addrgen.addrgen_req_valid),
    .addrgen_req_ready(i_addrgen.addrgen_req_ready),
    .vldu_issue_valid(i_vldu.vinsn_issue_valid),
    .vldu_issue_id(i_vldu.vinsn_issue_q.id),
    .vldu_mask_valid(i_vldu.mask_valid_q),
    .vldu_mask_owner(i_vldu.mask_word_q[0].owner),
    .vldu_mask_first(i_vldu.mask_word_q[0].first_element),
    .vldu_descriptor_valid(i_vldu.axi_addrgen_req_valid_i),
    .vldu_descriptor_ready(i_vldu.axi_addrgen_req_ready_o),
    .r_valid(i_vldu.axi_r_valid_i),
    .r_ready(i_vldu.axi_r_ready_o),
    .result_grant(i_vldu.ldu_result_gnt_i),
    .result_queue_count(i_vldu.result_queue_cnt_q),
    .issue_bytes(i_vldu.issue_cnt_bytes_q),
    .commit_bytes(i_vldu.commit_cnt_bytes_q),
    .vinsn_done(i_vldu.pe_resp_o.vinsn_done)
);
