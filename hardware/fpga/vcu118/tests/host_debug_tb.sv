// SPDX-License-Identifier: SHL-0.51
module host_debug_tb;
  timeunit 1ns; timeprecision 1ps;
  typedef struct packed {logic [31:0] addr, wdata; logic [3:0] wstrb;
    logic write, valid;} reg_req_t;
  typedef struct packed {logic [31:0] rdata; logic error, ready;} reg_rsp_t;
  typedef struct packed {logic [47:0] addr; logic [2:0] id;} addr_t;
  typedef struct packed {logic [63:0] data; logic [7:0] strb; logic last;} w_t;
  typedef struct packed {logic [2:0] id; logic [1:0] resp;} b_t;
  typedef struct packed {logic [63:0] data; logic [2:0] id; logic [1:0] resp; logic last;} r_t;
  typedef struct packed {addr_t aw, ar; w_t w;
    logic aw_valid, ar_valid, w_valid, b_ready, r_ready;} req_t;
  typedef struct packed {r_t r; b_t b;
    logic aw_ready, ar_ready, w_ready, b_valid, r_valid;} rsp_t;
  logic clk = 0, rst = 0, soc_rst = 0;
  always #5 clk = ~clk;
  reg_req_t host = '0, cpu = '0;
  reg_rsp_t hr, cr;
  req_t req = '0;
  rsp_t rsp = '0;
  logic [1:0][14:0][63:0] metrics;
  logic enable_count, clear_count;
  logic [7:0] retired = 0;
  logic [63:0] pc = 64'h80001234, head_pc = 64'h80001238;
  logic trap = 0;
  int checks = 0;
  assign metrics[1] = '0;
  ara_axi_observer #(.req_t(req_t), .rsp_t(rsp_t)) observer (
    .clk_i(clk), .rst_ni(rst), .soc_rst_ni(soc_rst),
    .enable_i(enable_count), .clear_i(clear_count),
    .req_i(req), .rsp_i(rsp), .counters_o(metrics[0])
  );
  ara_fpga_debug #(.DualDdr(1), .reg_req_t(reg_req_t), .reg_rsp_t(reg_rsp_t)) dut (
    .clk_i(clk), .rst_ni(rst), .soc_rst_ni(soc_rst), .status_i(4'h7),
    .host_req_i(host), .cpu_req_i(cpu), .host_rsp_o(hr), .cpu_rsp_o(cr),
    .retire_count_i(retired), .retire_pc_i(pc), .head_pc_i(head_pc),
    .trap_i(trap), .trap_pc_i(head_pc), .trap_cause_i(64'd4),
    .trap_tval_i(64'h80000003), .ddr_metrics_i(metrics),
    .count_enable_o(enable_count), .count_clear_o(clear_count)
  );
  task automatic tick;
    @(posedge clk); #1; @(negedge clk);
  endtask
  task automatic wr(input logic [31:0] addr, value);
    host = '{addr: addr, wdata: value, wstrb: 4'hf, write: 1'b1, valid: 1'b1};
    tick(); host = '0;
  endtask
  task automatic expect_word(input logic [31:0] addr, value);
    host = '{addr: addr, default: '0}; host.valid = 1;
    #1;
    if (!hr.ready || hr.error || hr.rdata !== value)
      $fatal(1, "addr=%h expected=%h got=%h ready=%b err=%b", addr,value,hr.rdata,hr.ready,hr.error);
    checks++; host = '0;
  endtask
  initial begin
    #12; rst = 1; soc_rst = 1; @(negedge clk);
    expect_word('h0, 'h41524442);
    expect_word('h4, 1);
    expect_word('h8, 3);
    expect_word('hc, 50000000);
    host = '{addr: 32'h300, default: '0}; host.valid = 1;
    #1; if (!hr.error) $fatal(1,"unmapped access accepted"); checks++; host = '0;
    wr('h1c, 'h12345678);
    host = '{addr:32'h1c, wdata:32'haabbccdd, wstrb:4'b0101, write:1'b1,valid:1'b1};
    tick(); host = '0;
    expect_word('h1c, 'h12bb56dd);
    // Backpressure applies only to the conflicting CPU write, not reads.
    cpu = '{addr:32'h24, wdata:32'h44, wstrb:4'hf, write:1'b1, valid:1'b1};
    host = '{addr:32'h24, wdata:32'h55, wstrb:4'hf, write:1'b1, valid:1'b1};
    #1; if (cr.ready) $fatal(1,"CPU write lost during arbitration"); checks++;
    tick(); host = '0; tick(); cpu = '0; expect_word('h24, 'h44);
    wr('h10, 1);
    retired = 2;
    req.ar_valid = 1; req.ar.addr = 'h80001000; rsp.ar_ready = 1;
    req.aw_valid = 1; req.aw.addr = 48'h100001000; rsp.aw_ready = 1;
    tick();
    req.ar_valid = 0; req.aw_valid = 0;
    rsp.r_valid = 1; rsp.r.last = 1; rsp.r.resp = 2; rsp.r.id = 3; req.r_ready = 1;
    req.w_valid = 1; req.w.strb = 'h35; rsp.w_ready = 1;
    rsp.b_valid = 1; rsp.b.resp = 3; rsp.b.id = 5; req.b_ready = 1;
    trap = 1; tick();
    req = '0; rsp = '0; retired = 0; trap = 0;
    wr('h10, 4); wr('h10, 2);
    expect_word('h108, 4);
    expect_word('h110, 'h80001234);
    expect_word('h118, 'h80001238);
    expect_word('h120, 'h80001238);
    expect_word('h128, 4);
    expect_word('h130, 'h80000003);
    expect_word('h138, 1);
    expect_word('h180, 1); expect_word('h188, 1);
    expect_word('h190, 8); expect_word('h198, 4);
    expect_word('h1c0, 0); expect_word('h1c8, 0);
    expect_word('h1d0, 'h80001000); expect_word('h1d8, 'h1000);
    expect_word('h1dc, 1); expect_word('h1e0, 2);
    expect_word('h1e8, 0); expect_word('h1f0, 'h507);
    // Snapshot is stable across live updates and reset, not a torn 64b read.
    wr('h10, 8); retired = 1; tick(); tick(); retired = 0;
    expect_word('h108, 4);
    soc_rst = 0; tick(); tick();
    expect_word('h108, 6); expect_word('h190, 8);
    soc_rst = 1; tick();
    // A permanently stalled main request cannot block local debug reads.
    wr('h10, 1); wr('h28, 4);
    req.aw_valid = 1; rsp.aw_ready = 0;
    repeat (8) tick();
    expect_word('h2c, 1); expect_word('h10, 1);
    expect_word('h0, 'h41524442);
    wr('h10, 1); wr('h28, 0); req = '0;
    expect_word('h2c, 0); expect_word('h30, 0);
    wr('h30, 1); expect_word('h30, 1);
    $display("PASS: host debug %0d checks",checks); $finish;
  end
  initial begin #100000; $fatal(1, "test timeout"); end
endmodule
