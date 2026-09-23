`include "axi/typedef.svh"
package ddr2_test_pkg;
  `AXI_TYPEDEF_ALL(axi, logic [47:0], logic [4:0], logic [63:0], logic [7:0], logic [1:0])
endpackage

// Protocol-only bank model: sparse storage deliberately truncates to MIG local addresses.
module ddr2_test_bank import ddr2_test_pkg::*; #(
  parameter int Bank = 0
) (
  input logic clk_i, rst_ni, allow_r_i, allow_b_i,
  input axi_req_t req_i,
  output axi_resp_t rsp_o,
  output int reads_o, writes_o
);
  logic [63:0] memory [longint unsigned];
  logic writing, reading, b_valid;
  logic [47:0] w_addr, r_addr;
  logic [4:0] w_id, r_id;
  logic [7:0] r_left, w_left;
  int cycle;
  always_comb begin
    rsp_o = '0;
    rsp_o.aw_ready = !writing && !b_valid && cycle % 3 != 0;
    rsp_o.w_ready = writing && cycle % 4 != 0;
    rsp_o.ar_ready = !reading && cycle % 5 != 0;
    rsp_o.b_valid = b_valid && allow_b_i;
    rsp_o.b.id = w_id;
    rsp_o.b.resp = axi_pkg::RESP_OKAY;
    rsp_o.r_valid = reading && allow_r_i;
    rsp_o.r.id = r_id;
    rsp_o.r.data = memory.exists(longint'(r_addr[30:3])) ? memory[longint'(r_addr[30:3])] : '0;
    rsp_o.r.last = r_left == 0;
    rsp_o.r.resp = axi_pkg::RESP_OKAY;
  end
  task automatic check_bank(input logic [47:0] address);
    if (Bank == 0 && !(address >= 48'h8000_0000 && address < 48'h1_0000_0000))
      $fatal(1, "C1 misroute %h", address);
    if (Bank == 1 && !(address >= 48'h1_0000_0000 && address < 48'h1_8000_0000))
      $fatal(1, "C2 misroute %h", address);
  endtask
  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      writing <= 0; reading <= 0; b_valid <= 0; cycle <= 0;
      reads_o <= 0; writes_o <= 0;
      w_addr <= '0; r_addr <= '0; w_id <= '0; r_id <= '0;
      r_left <= '0; w_left <= '0;
    end else begin
      cycle <= cycle + 1;
      if (req_i.aw_valid && rsp_o.aw_ready) begin
        check_bank(req_i.aw.addr);
        writing <= 1; w_addr <= req_i.aw.addr; w_id <= req_i.aw.id;
        w_left <= req_i.aw.len; writes_o <= writes_o + 1;
      end
      if (req_i.w_valid && rsp_o.w_ready) begin
        for (int byte_idx = 0; byte_idx < 8; byte_idx++)
          if (req_i.w.strb[byte_idx]) memory[longint'(w_addr[30:3])][8*byte_idx+:8] = req_i.w.data[8*byte_idx+:8];
        if (req_i.w.last !== (w_left == 0)) $fatal(1, "W ownership/length mismatch");
        w_addr <= w_addr + 8; w_left <= w_left - 1;
        if (req_i.w.last) begin writing <= 0; b_valid <= 1; end
      end
      if (rsp_o.b_valid && req_i.b_ready) b_valid <= 0;
      if (req_i.ar_valid && rsp_o.ar_ready) begin
        check_bank(req_i.ar.addr);
        reading <= 1; r_addr <= req_i.ar.addr; r_id <= req_i.ar.id;
        r_left <= req_i.ar.len; reads_o <= reads_o + 1;
      end
      if (rsp_o.r_valid && req_i.r_ready) begin
        r_addr <= r_addr + 8; r_left <= r_left - 1;
        if (r_left == 0) reading <= 0;
      end
    end
  end
endmodule

module tb;
  timeunit 1ns; timeprecision 1ps;
  import ddr2_test_pkg::*;
  logic clk = 0, rst_n = 0;
  always #10 clk = ~clk;
  axi_req_t req = '0;
  axi_resp_t rsp;
  axi_req_t [1:0] bank_req;
  axi_resp_t [1:0] bank_rsp;
  logic [1:0] allow_r = '1, allow_b = '1;
  int reads[2], writes[2], checks = 0;
  ara_ddr_router #(
    .req_t(axi_req_t), .rsp_t(axi_resp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .req_i(req), .rsp_o(rsp), .req_o(bank_req), .rsp_i(bank_rsp)
  );
  for (genvar bank = 0; bank < 2; bank++) begin : gen_banks
    ddr2_test_bank #(.Bank(bank)) i_bank (
      .clk_i(clk), .rst_ni(rst_n), .allow_r_i(allow_r[bank]), .allow_b_i(allow_b[bank]),
      .req_i(bank_req[bank]), .rsp_o(bank_rsp[bank]), .reads_o(reads[bank]), .writes_o(writes[bank])
    );
  end
  task automatic aw(input logic [47:0] address, input logic [4:0] id, input int beats);
    @(negedge clk);
    req.aw = '0; req.aw.addr = address; req.aw.id = id;
    req.aw.len = 8'(beats-1); req.aw.size = 3; req.aw.burst = axi_pkg::BURST_INCR;
    req.aw_valid = 1;
    do @(posedge clk); while (!rsp.aw_ready);
    @(negedge clk); req.aw_valid = 0;
  endtask
  task automatic w(input logic [63:0] base, input int beats);
    for (int beat = 0; beat < beats; beat++) begin
      @(negedge clk);
      req.w = '0; req.w.data = base + 64'(beat); req.w.strb = '1;
      req.w.last = beat == beats-1; req.w_valid = 1;
      do @(posedge clk); while (!rsp.w_ready);
      @(negedge clk); req.w_valid = 0;
    end
  endtask
  task automatic b(input logic [4:0] id, input axi_pkg::resp_t response = axi_pkg::RESP_OKAY);
    repeat (3) @(negedge clk);
    req.b_ready = 1;
    do @(posedge clk); while (!rsp.b_valid);
    if (rsp.b.id !== id || rsp.b.resp !== response) $fatal(1, "B mismatch id=%h", rsp.b.id);
    checks++;
    @(negedge clk); req.b_ready = 0;
  endtask
  task automatic ar(input logic [47:0] address, input logic [4:0] id, input int beats);
    @(negedge clk);
    req.ar = '0; req.ar.addr = address; req.ar.id = id;
    req.ar.len = 8'(beats-1); req.ar.size = 3; req.ar.burst = axi_pkg::BURST_INCR;
    req.ar_valid = 1;
    do @(posedge clk); while (!rsp.ar_ready);
    @(negedge clk); req.ar_valid = 0;
  endtask
  task automatic r(input logic [4:0] id, input logic [63:0] base, input int beats,
                   input axi_pkg::resp_t response = axi_pkg::RESP_OKAY);
    for (int beat = 0; beat < beats; beat++) begin
      repeat (3) @(negedge clk);
      req.r_ready = 1;
      do @(posedge clk); while (!rsp.r_valid);
      if (rsp.r.id !== id || rsp.r.resp !== response || rsp.r.last !== (beat == beats-1))
        $fatal(1, "R identity/ordering mismatch id=%h expected=%h", rsp.r.id, id);
      if (response == axi_pkg::RESP_OKAY && rsp.r.data !== base + 64'(beat))
        $fatal(1, "R data mismatch got=%h expected=%h", rsp.r.data, base + 64'(beat));
      checks++;
      @(negedge clk); req.r_ready = 0;
    end
  endtask
  task automatic write_read(input logic [47:0] address, input logic [63:0] data, input int beats);
    // W may arrive before AW; the existing xbar must retain ownership.
    fork aw(address, 5'h12, beats); w(data, beats); b(5'h12); join
    fork ar(address, 5'h13, beats); r(5'h13, data, beats); join
  endtask
  initial begin
    int before_reads, before_writes;
    repeat (4) @(negedge clk); rst_n = 1;
    write_read(48'h8000_0000, 64'h1234, 8);
    write_read(48'h1_0000_0000, 64'habcd, 8);
    fork ar(48'h8000_0000, 1, 8); r(1, 64'h1234, 8); join
    write_read(48'hffff_ffc0, 64'hc1ff, 8);
    write_read(48'h1_7fff_ffc0, 64'hc2ff, 8);
    write_read(48'h8000_0800, 64'h256b, 256);
    before_reads = reads[0] + reads[1]; before_writes = writes[0] + writes[1];
    for (int index = 0; index < 4; index++) begin
      logic [47:0] address;
      case (index)
        0: address = 48'h7fff_fff8;
        1: address = 48'h1_8000_0000;
        2: address = 48'h2_8000_0000;
        3: address = 48'h8000_8000_0000;
      endcase
      fork aw(address, 3, 4); w(64'hbad, 4); b(3, axi_pkg::RESP_DECERR); join
      fork ar(address, 4, 4); r(4, 0, 4, axi_pkg::RESP_DECERR); join
    end
    if (reads[0]+reads[1] != before_reads || writes[0]+writes[1] != before_writes)
      $fatal(1, "Unmapped transaction reached a MIG");

    // Same ID targeting C2 must wait until C1's RLAST is accepted.
    allow_r[0] = 0; before_reads = reads[1];
    ar(48'h8000_0000, 7, 1);
    fork
      ar(48'h1_0000_0000, 7, 1);
      begin
        repeat (20) @(negedge clk);
        if (reads[1] != before_reads) $fatal(1, "Same-ID read bypassed C1");
        allow_r[0] = 1;
        r(7, 64'h1234, 1); r(7, 64'habcd, 1);
      end
    join
    // Different full IDs, including identical low three bits, may reorder.
    allow_r[0] = 0;
    ar(48'h8000_0000, 1, 1);
    ar(48'h1_0000_0000, 9, 1);
    r(9, 64'habcd, 1);
    allow_r[0] = 1; r(1, 64'h1234, 1);

    // Same-ID writes to a new bank must wait for the previous B response.
    allow_b[0] = 0; before_writes = writes[1];
    fork aw(48'h8000_0040, 6, 2); w(64'hc100, 2); join
    fork
      aw(48'h1_0000_0040, 6, 2);
      w(64'hc200, 2);
      begin
        repeat (20) @(negedge clk);
        if (writes[1] != before_writes) $fatal(1, "Same-ID write bypassed C1");
        allow_b[0] = 1; b(6); b(6);
      end
    join
    fork ar(48'h8000_0040, 0, 2); r(0, 64'hc100, 2); join
    fork ar(48'h1_0000_0040, 0, 2); r(0, 64'hc200, 2); join

    // Full fabric reset aborts in-flight work; no response may leak afterward.
    allow_r = 0; allow_b = 0;
    ar(48'h8000_0000, 2, 8);
    fork aw(48'h1_0000_0080, 3, 2); w(64'hdead, 2); join
    repeat (8) @(negedge clk);
    rst_n = 0; req = '0;
    repeat (4) @(negedge clk);
    rst_n = 1; allow_r = '1; allow_b = '1;
    repeat (10) begin
      @(negedge clk);
      if (rsp.b_valid || rsp.r_valid) $fatal(1, "Stale response survived reset");
    end
    write_read(48'h1_0000_0080, 64'hbeef, 2);
    $display("PASS: DDR router %0d response checks, boundaries/alias/DECERR/order/reset", checks);
    $finish;
  end
  initial begin #500000; $fatal(1, "DDR router watchdog"); end
endmodule
