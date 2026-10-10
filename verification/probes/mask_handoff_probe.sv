module mask_handoff_probe #(
    parameter int unsigned NrLanes = 4
) (
    input logic clk_i,
    input logic rst_ni,
    input ara_pkg::vid_t source_owner,
    input logic [NrLanes-1:0] source_valid,
    input logic source_ready,
    input logic [NrLanes-1:0] sink_ready,
    input logic [NrLanes-1:0] sink_input_valid,
    input logic [NrLanes-1:0] sink_stored_valid,
    input ara_pkg::vid_t sink_owner,
    input logic sink_issue_valid,
    input ara_pkg::vid_t sink_issue_owner
);
  longint unsigned cycle;
  int unsigned start_cycle = 1118;
  int unsigned stop_cycle = 1140;

  initial begin
    void'($value$plusargs("MASK_HANDOFF_START=%d", start_cycle));
    void'($value$plusargs("MASK_HANDOFF_STOP=%d", stop_cycle));
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) cycle <= '0;
    else begin
      cycle <= cycle + 1;
      if ($test$plusargs("MASK_HANDOFF_PROBE") &&
          cycle >= start_cycle && cycle <= stop_cycle) begin
        $display("[MASK_HANDOFF] cycle=%0d src=%0d:%b ready=%b sink_ready=%b sink_in=%b sink_q=%0d:%b issue=%b:%0d",
                 cycle, source_owner, source_valid, source_ready,
                 sink_ready, sink_input_valid, sink_owner,
                 sink_stored_valid, sink_issue_valid, sink_issue_owner);
      end
      if ($test$plusargs("MASK_HANDOFF_PROBE") && cycle == stop_cycle) $finish;
    end
  end
endmodule

bind ara mask_handoff_probe #(.NrLanes(NrLanes)) i_mask_handoff_probe (
    .clk_i(clk_i),
    .rst_ni(rst_ni),
    .source_owner(i_masku.mask_owner_id_o),
    .source_valid(mask_valid),
    .source_ready(vldu_mask_ready),
    .sink_ready(i_vlsu.i_vldu.mask_ready_q),
    .sink_input_valid(i_vlsu.i_vldu.mask_valid_d),
    .sink_stored_valid(i_vlsu.i_vldu.mask_valid_q),
    .sink_owner(i_vlsu.i_vldu.mask_word_q[0].owner),
    .sink_issue_valid(i_vlsu.i_vldu.vinsn_issue_valid),
    .sink_issue_owner(i_vlsu.i_vldu.vinsn_issue_q.id)
);
