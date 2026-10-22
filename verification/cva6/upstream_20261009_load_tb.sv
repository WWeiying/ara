`timescale 1ns/1ps
module upstream_20261009_load_tb;
  `include "upstream_20261009_common.svh"
  logic flush = 0, valid = 0, pop, result_valid;
  lsu_ctrl_t ctrl;
  exception_t ex, ex_out;
  dcache_req_i_t req;
  dcache_req_o_t resp;
  logic [CVA6Cfg.TRANS_ID_BITS-1:0] trans_id;
  logic [63:0] result_data;
  logic [CVA6Cfg.PLEN-1:0] pa = 56'h80001000;
  load_unit #(.CVA6Cfg(CVA6Cfg), .exception_t(exception_t), .lsu_ctrl_t(lsu_ctrl_t),
    .dcache_req_i_t(dcache_req_i_t), .dcache_req_o_t(dcache_req_o_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .valid_i(valid), .lsu_ctrl_i(ctrl),
    .pop_ld_o(pop), .valid_o(result_valid), .trans_id_o(trans_id),
    .result_o(result_data), .ex_o(ex_out), .translation_req_o(), .vaddr_o(),
    .tinst_o(), .hs_ld_st_inst_o(), .hlvx_inst_o(), .paddr_i(pa), .ex_i(ex),
    .dtlb_hit_i(1'b1), .dtlb_ppn_i(44'h80001), .page_offset_o(),
    .page_offset_matches_i(1'b0), .store_buffer_empty_i(1'b1),
    .commit_tran_id_i(ctrl.trans_id), .req_port_i(resp), .req_port_o(req),
    .dcache_wbuffer_not_ni_i(1'b1));

  initial begin
    int rc, cancel, wait_grant, delay_cycles, tid, slot;
    open_files(); ctrl = '0; resp = '0; ex = '0;
    while (!$feof(input_file)) begin
      rc = $fscanf(input_file, "%d %d %d %d %d\n", id, cancel, wait_grant, delay_cycles, tid);
      if (rc != 5 || id != completed) $fatal(1, "Bad load case");
      flush = 0; valid = 0; resp = '0; ex = '0;
      reset_dut();
      ctrl = '0; ctrl.vaddr = 64'h80001000; ctrl.operation = LD;
      ctrl.be = '1; ctrl.trans_id = CVA6Cfg.TRANS_ID_BITS'(tid);
      valid = 1;
      if (wait_grant) begin
        @(posedge clk); #1;
        @(negedge clk);
      end
      resp.data_gnt = 1; flush = cancel;
      #1; slot = int'(req.data_id);
      observe("allocation_fire", req.data_req && resp.data_gnt);
      @(posedge clk); #1;
      observe("flushed_slot", dut.ldbuf_flushed_q[slot]);
      @(negedge clk); valid = 0; flush = 0; resp = '0;
      // The canceled request is already accepted. Model a delayed response;
      // this is not a claim that every cache controller returns killed work.
      repeat (delay_cycles) begin @(posedge clk); @(negedge clk); end
      resp.data_rvalid = 1; resp.data_rid = slot;
      resp.data_rdata = 64'h1234567887654321;
      #1;
      observe("old_reply_valid", result_valid);
      observe("old_reply_id", trans_id);
      observe("old_reply_data", result_data);
      observe("old_reply_exception", ex_out.valid);
      @(posedge clk); #1;
      @(negedge clk); resp = '0;
      // Reuse the same architectural transaction ID after draining old work.
      valid = 1; resp.data_gnt = 1;
      #1; slot = int'(req.data_id);
      observe("reuse_fire", req.data_req && resp.data_gnt);
      @(posedge clk); #1;
      @(negedge clk); valid = 0; resp = '0;
      repeat (3) begin @(posedge clk); @(negedge clk); end
      resp.data_rvalid = 1; resp.data_rid = slot;
      resp.data_rdata = 64'hfedcba9876543210;
      #1;
      observe("reuse_reply_valid", result_valid);
      observe("reuse_reply_id", trans_id);
      observe("reuse_reply_data", result_data);
      observe("reuse_reply_exception", ex_out.valid);
      @(posedge clk); #1;
      @(negedge clk); resp = '0;
      observe("drained", dut.ldbuf_valid_q == '0);
      completed++;
    end
    finish_test();
  end
endmodule
