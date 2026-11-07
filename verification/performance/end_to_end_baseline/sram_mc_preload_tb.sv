`timescale 1ns/1ps

module sram_mc_preload_case #(parameter int Width = 128)
  (input logic clk, output logic done);
  localparam int Capacity = 1048576;
  localparam int Bytes = Width/8;
  localparam int Words = Capacity/Bytes;
  localparam int Banks = Words/8192;
  logic rst_n = 0;
  logic req = 0, we = 0, rvalid;
  logic [63:0] addr = 0;
  logic [Width-1:0] wdata = 0, rdata, held;
  logic [Bytes-1:0] be = 0;
  logic [7:0] oracle [Capacity];
  int reads, checked_bytes, holds, boundaries;
  logic expected_valid;

  ara_soc_sram_mc_slice #(.AxiDataWidth(Width)) dut (
    .clk_i(clk), .rst_ni(rst_n), .l2_req(req), .l2_we(we), .l2_addr(addr),
    .l2_wdata(wdata), .l2_be(be), .l2_rdata(rdata), .l2_rvalid(rvalid));

`define SRAM_MC_PRELOAD_SOC dut
`define SRAM_MC_PRELOAD_WIDTH Width
`define SRAM_MC_PRELOAD_CAPACITY Capacity
`define SRAM_MC_PRELOAD_RESET_N rst_n
`include "sram_mc_preload.svh"
`undef SRAM_MC_PRELOAD_SOC
`undef SRAM_MC_PRELOAD_WIDTH
`undef SRAM_MC_PRELOAD_CAPACITY
`undef SRAM_MC_PRELOAD_RESET_N

  task automatic read_word(input int word);
    @(negedge clk);
    req = 1;
    addr = 64'h80000000 + 64'(word)*Bytes;
    #1;
    if ($isunknown({rvalid, rdata}) || rvalid !== expected_valid || rdata !== held)
      $fatal(1, "MC_PRELOAD_EARLY_READ_FAIL width=%0d word=%0d", Width, word);
    @(posedge clk);
    #1;
    if (rvalid !== 1 || $isunknown(rdata))
      $fatal(1, "MC_PRELOAD_READ_VALID_FAIL width=%0d word=%0d", Width, word);
    for (int b = 0; b < Bytes; b++) begin
      if ($isunknown(oracle[word*Bytes+b]) || rdata[b*8 +: 8] !== oracle[word*Bytes+b])
        $fatal(1, "MC_PRELOAD_BYTE_FAIL width=%0d offset=%0d got=%h expected=%h",
               Width, word*Bytes+b, rdata[b*8 +: 8], oracle[word*Bytes+b]);
      checked_bytes++;
    end
    held = rdata;
    expected_valid = 1;
    reads++;
  endtask

  task automatic idle_hold(input int next_word);
    @(negedge clk);
    req = 0;
    addr = 64'h80000000 + 64'(next_word)*Bytes;
    #1;
    if (rdata !== held) $fatal(1, "MC_PRELOAD_EARLY_HOLD_FAIL");
    @(posedge clk);
    #1;
    if (rvalid !== 0 || rdata !== held || $isunknown({rvalid, rdata}))
      $fatal(1, "MC_PRELOAD_IDLE_HOLD_FAIL width=%0d", Width);
    expected_valid = 0;
    holds++;
  endtask

  initial begin : traffic
    string oracle_path;
    int fd, value;
    done = 0;
    reads = 0; checked_bytes = 0; holds = 0; boundaries = 0;
    held = '0; expected_valid = 0;
    if (!$value$plusargs("MC_ORACLE=%s", oracle_path)) $fatal(1, "MC_PRELOAD_ORACLE_REQUIRED");
    fd = $fopen(oracle_path, "rb");
    if (!fd) $fatal(1, "MC_PRELOAD_ORACLE_OPEN_FAIL");
    for (int i = 0; i < Capacity; i++) begin
      value = $fgetc(fd);
      if (value == -1) $fatal(1, "MC_PRELOAD_ORACLE_SHORT_FAIL");
      oracle[i] = 8'(value);
    end
    if ($fgetc(fd) != -1) $fatal(1, "MC_PRELOAD_ORACLE_EXTRA_FAIL");
    $fclose(fd);
    wait (sram_mc_preload_done === 1);
    repeat (2) @(posedge clk);
    @(negedge clk);
    #1;
    if (rdata !== '0 || rvalid !== 0) $fatal(1, "MC_PRELOAD_INITIAL_RESET_FAIL");
    rst_n = 1;
    for (int word = 0; word < Words; word++) begin
      read_word(word);
      if (word % 8192 == 8191) begin
        idle_hold((word+1) % Words);
        if (word+1 < Words) boundaries++;
      end
    end
    @(negedge clk); rst_n = 0; req = 0;
    #1;
    if (rvalid !== 0 || rdata !== '0) $fatal(1, "MC_PRELOAD_SELECTOR_RESET_FAIL");
    held = '0; expected_valid = 0;
    repeat (2) @(posedge clk);
    @(negedge clk); rst_n = 1;
    read_word(0);
    idle_hold(Words-1);
    if (reads != Words+1 || checked_bytes != Capacity+Bytes || holds != Banks+1 || boundaries != Banks-1)
      $fatal(1, "MC_PRELOAD_COVERAGE_FAIL");
    $display("MC_PRELOAD_CASE_PASS width=%0d banks=%0d columns=%0d words=%0d reads=%0d checked_bytes=%0d holds=%0d boundaries=%0d resets=2",
             Width, Banks, Width/128, Words, reads, checked_bytes, holds, boundaries);
    done = 1;
  end
endmodule

module sram_mc_preload_tb;
  logic clk = 0;
  wire [1:0] done;
  always #10 clk = ~clk;
  sram_mc_preload_case #(.Width(128)) i_128 (.clk(clk), .done(done[0]));
  sram_mc_preload_case #(.Width(256)) i_256 (.clk(clk), .done(done[1]));
  initial begin
    wait (done === 2'b11);
    $display("MC_PRELOAD_COMPONENT_PASS cases=2");
    $finish;
  end
  initial begin
    #5000000;
    $fatal(1, "MC_PRELOAD_TIMEOUT_FAIL");
  end
endmodule
