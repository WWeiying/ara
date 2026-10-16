`timescale 1ns/1ps
// Probe-semantics test, not a CPU reachability or board-deadlock proof.
module scalar_store_probe_tb;
  import ariane_pkg::*;
  localparam config_pkg::cva6_cfg_t CVA6Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  `include "load_contract_types.svh"
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic flush = 0, commit = 0, valid = 0;
  logic no_pending, empty, conflict, ready, commit_ready;
  logic [11:0] offset = 12'h100;
  dcache_req_i_t req;
  dcache_req_o_t rsp = '0;
  int checks = 0;
  store_buffer #(.CVA6Cfg(CVA6Cfg), .dcache_req_i_t(dcache_req_i_t),
      .dcache_req_o_t(dcache_req_o_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(flush), .stall_st_pending_i(1'b0),
    .no_st_pending_o(no_pending), .store_buffer_empty_o(empty),
    .page_offset_i(offset), .page_offset_matches_o(conflict),
    .commit_i(commit), .commit_ready_o(commit_ready), .ready_o(ready),
    .valid_i(valid), .valid_without_flush_i(valid),
    .paddr_i(CVA6Cfg.PLEN'(64'h8000_0100)), .rvfi_mem_paddr_o(),
    .data_i(64'h1122334455667788), .be_i(8'hff), .data_size_i(2'b11),
    .req_port_i(rsp), .req_port_o(req)
  );
  task automatic tick;
    @(posedge clk); #1; @(negedge clk);
  endtask
  task automatic check(logic condition, string message);
    checks++;
    if (condition !== 1'b1) $fatal(1, "STORE_PROBE_FAIL %s", message);
  endtask
  initial begin
    repeat (3) tick();
    rst_n = 1; tick();
    check(no_pending && empty && !conflict, "reset state");
    check(ready, "enqueue readiness");
    valid = 1; tick(); valid = 0; #1;
    repeat (8) begin
      check(no_pending && !empty && conflict && !req.data_req,
            "speculative conflict must coexist with no_st_pending");
      tick();
    end
    $display("STORE_PROBE_SPEC no_st_pending=%b empty=%b conflict=%b spec=%0d commit=%0d",
             no_pending, empty, conflict, dut.speculative_status_cnt_q, dut.commit_status_cnt_q);
    offset = 12'h108; #1;
    check(!conflict, "different eight-byte offset must not alias");
    offset = 12'h107; #1;
    check(conflict, "same eight-byte offset must alias");
    offset = 12'h100;
    check(commit_ready, "commit readiness");
    commit = 1; tick(); commit = 0; #1;
    check(!no_pending && !empty && conflict && req.data_req,
          "committed store waits for cache grant");
    rsp.data_gnt = 1; tick(); rsp = '0; #1;
    check(no_pending && empty && !conflict && !req.data_req, "grant drains conflict");
    valid = 1; tick(); valid = 0;
    flush = 1; tick(); flush = 0; #1;
    check(no_pending && empty && !conflict, "flush removes speculative conflict");
    $display("STORE_PROBE_PASS checks=%0d", checks);
    $finish;
  end
  initial begin
    #2000;
    $fatal(1, "STORE_PROBE_FAIL watchdog");
  end
endmodule
