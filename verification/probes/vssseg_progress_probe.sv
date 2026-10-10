// Focused, simulation-only visibility for a stalled segmented vector store.
module vssseg_progress_probe (
  input logic        clk_i,
  input logic        rst_ni,
  input logic        backend_alloc_i,
  input logic [31:0] arch_insn_i,
  input logic [1:0]  seg_state_i,
  input logic [31:0] seg_count_i,
  input logic        seg_req_valid_i,
  input logic        seg_req_ready_i,
  input logic        seg_resp_valid_i,
  input logic        seg_idle_i,
  input logic [31:0] addr_state_i,
  input logic        addr_req_valid_i,
  input logic        addr_req_ready_i,
  input logic [63:0] addr_req_addr_i,
  input logic        aw_valid_i,
  input logic        aw_ready_i,
  input logic [63:0] aw_addr_i,
  input logic [31:0] store_issue_i,
  input logic [31:0] store_commit_i,
  input logic [31:0] store_bytes_i,
  input logic [31:0] operand_valid_i,
  input logic        w_valid_i,
  input logic        w_ready_i,
  input logic        w_last_i,
  input logic        b_valid_i,
  input logic        b_ready_i
);
  bit enabled;
  bit capture;
  int unsigned samples;
  integer log_fd;

  initial enabled = $test$plusargs("VSSSEG_PROBE");

  always @(posedge clk_i) begin
    if (enabled && rst_ni) begin
      if (!capture && backend_alloc_i && arch_insn_i == 32'h2aa480a7) begin
        log_fd = $fopen("vssseg_progress.log", "w");
        if (log_fd == 0) $fatal(1, "cannot open vssseg_progress.log");
        capture = 1'b1;
        samples = 0;
      end
      if (capture) begin
        $fdisplay(log_fd,
          "t=%0t n=%0d seg=%0d/%0d req=%0b/%0b resp=%0b idle=%0b ag=%0d aq=%0b/%0b a=%h aw=%0b/%0b awa=%h st=%0d/%0d bytes=%0d op=%h w=%0b/%0b/%0b b=%0b/%0b",
          $time, samples, seg_state_i, seg_count_i, seg_req_valid_i,
          seg_req_ready_i, seg_resp_valid_i, seg_idle_i, addr_state_i,
          addr_req_valid_i, addr_req_ready_i, addr_req_addr_i, aw_valid_i,
          aw_ready_i, aw_addr_i, store_issue_i, store_commit_i, store_bytes_i,
          operand_valid_i, w_valid_i, w_ready_i, w_last_i, b_valid_i, b_ready_i);
        $fflush(log_fd);
        samples++;
        if (samples == 512) begin
          $fclose(log_fd);
          $display("[VSSSEG_PROBE_DONE] captured 512 cycles");
          $finish;
        end
      end
    end
  end
endmodule

bind ara_system vssseg_progress_probe i_vssseg_progress_probe (
  .clk_i(clk_i),
  .rst_ni(rst_ni),
  .backend_alloc_i(i_ara.i_sequencer.verify_vinsn_alloc),
  .arch_insn_i(i_ara.ara_req.verify_arch_insn),
  .seg_state_i(i_ara.i_dispatcher.i_segment_sequencer.gen_segment_support.state_q),
  .seg_count_i(32'(i_ara.i_dispatcher.i_segment_sequencer.gen_segment_support.segment_cnt_q)),
  .seg_req_valid_i(i_ara.i_dispatcher.i_segment_sequencer.ara_req_valid_o),
  .seg_req_ready_i(i_ara.i_dispatcher.i_segment_sequencer.ara_req_ready_i),
  .seg_resp_valid_i(i_ara.i_dispatcher.i_segment_sequencer.ara_resp_valid_i),
  .seg_idle_i(i_ara.i_dispatcher.i_segment_sequencer.ara_idle_i),
  .addr_state_i(32'(i_ara.i_vlsu.i_addrgen.state_q)),
  .addr_req_valid_i(i_ara.i_vlsu.axi_addrgen_req_valid),
  .addr_req_ready_i(i_ara.i_vlsu.stu_axi_addrgen_req_ready),
  .addr_req_addr_i(i_ara.i_vlsu.axi_addrgen_req.addr),
  .aw_valid_i(i_ara.i_vlsu.i_addrgen.axi_aw_valid_o),
  .aw_ready_i(i_ara.i_vlsu.i_addrgen.axi_aw_ready_i),
  .aw_addr_i(i_ara.i_vlsu.i_addrgen.axi_aw_o.addr),
  .store_issue_i(32'(i_ara.i_vlsu.i_vstu.vinsn_queue_q.issue_cnt)),
  .store_commit_i(32'(i_ara.i_vlsu.i_vstu.vinsn_queue_q.commit_cnt)),
  .store_bytes_i(32'(i_ara.i_vlsu.i_vstu.issue_cnt_bytes_q)),
  .operand_valid_i(32'(i_ara.i_vlsu.i_vstu.stu_operand_valid_i)),
  .w_valid_i(i_ara.i_vlsu.i_vstu.axi_w_valid_o),
  .w_ready_i(i_ara.i_vlsu.i_vstu.axi_w_ready_i),
  .w_last_i(i_ara.i_vlsu.i_vstu.axi_w_o.last),
  .b_valid_i(i_ara.i_vlsu.i_vstu.axi_b_valid_i),
  .b_ready_i(i_ara.i_vlsu.i_vstu.axi_b_ready_o)
);
