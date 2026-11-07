`timescale 1ns/1ps

// Independent functional contract, not a foundry timing/power SRAM model.
module TS1N28HPCPSVTB8192X128M4SWBASO (
  input logic SLP, SD, CLK, CEB, WEB, CEBM, WEBM, AWT,
  input logic [12:0] A, AM,
  input logic [127:0] D, BWEB, DM, BWEBM,
  input logic BIST,
  output logic [127:0] Q
);
  logic [127:0] mem [8192];
  initial for (int word = 0; word < 8192; word++)
    mem[word] = 128'h5ac3_96e1_5ac3_96e1_5ac3_96e1_5ac3_96e1;
  always @(posedge CLK) begin
    if ($isunknown({SLP, SD, CEB, WEB, CEBM, WEBM, AWT, BIST}) ||
        SLP || SD || !CEBM || !WEBM || AWT || BIST || AM !== '0 || DM !== '0 || BWEBM !== '1)
      $fatal(1, "MC_MACRO_CONTROL_FAIL");
    if (!CEB) begin
      if ($isunknown(A)) $fatal(1, "MC_MACRO_ADDRESS_FAIL");
      if (!WEB) begin
        if ($isunknown({D, BWEB})) $fatal(1, "MC_MACRO_WRITE_FAIL");
        for (int bit_index = 0; bit_index < 128; bit_index++)
          if (!BWEB[bit_index]) mem[A][bit_index] <= D[bit_index];
      end else Q <= mem[A];
    end
  end
endmodule

module sram_mc_case #(
  parameter int Id = 0,
  parameter int Width = 128,
  parameter int Words = 8192,
  parameter bit DefaultDepth = 0
) (input logic clk, output logic done);
  localparam int Bytes = Width/8;
  localparam int Depth = DefaultDepth ? 1048576/Bytes : Words;
  localparam int Banks = Depth/8192;
  localparam int Pool = 4*Banks;
  logic rst_n, req, we, rvalid;
  logic [63:0] addr;
  logic [Width-1:0] wdata, rdata;
  logic [Bytes-1:0] be;
  logic [Width-1:0] reference_mem [Depth];
  logic [Width-1:0] held;
  logic expected_valid;
  logic [Bytes-1:0] phase_seen;
  int unsigned steps, reads, writes, idle, masked, zero_mask, holds, switches;
  int previous_bank;
  bit have_read;

  if (DefaultDepth) begin : gen_default
    ara_soc_sram_mc_slice #(.AxiDataWidth(Width)) dut (
      .clk_i(clk), .rst_ni(rst_n), .l2_req(req), .l2_we(we), .l2_addr(addr),
      .l2_wdata(wdata), .l2_be(be), .l2_rdata(rdata), .l2_rvalid(rvalid));
    initial begin
      if (dut.L2NumWords != Depth || dut.L2NumWords*Bytes != 1048576)
        $fatal(1, "MC_DEFAULT_CAPACITY_FAIL id=%0d", Id);
      if ($bits(dut.gen_dram[0].i_dram.Q) != 128)
        $fatal(1, "MC_LEGACY_HIERARCHY_FAIL id=%0d", Id);
    end
  end else begin : gen_override
    ara_soc_sram_mc_slice #(.AxiDataWidth(Width), .L2NumWords(Words)) dut (
      .clk_i(clk), .rst_ni(rst_n), .l2_req(req), .l2_we(we), .l2_addr(addr),
      .l2_wdata(wdata), .l2_be(be), .l2_rdata(rdata), .l2_rvalid(rvalid));
    initial if ($bits(dut.gen_dram[0].i_dram.Q) != 128)
      $fatal(1, "MC_LEGACY_HIERARCHY_FAIL id=%0d", Id);
  end

  function automatic int pool_word(int index);
    case (index % 4)
      0: return (index/4)*8192;
      1: return (index/4)*8192 + 1;
      2: return (index/4)*8192 + 8190;
      3: return (index/4)*8192 + 8191;
    endcase
  endfunction

  function automatic logic [Width-1:0] pattern(int unsigned word, int unsigned salt);
    logic [Width-1:0] value;
    for (int byte_index = 0; byte_index < Bytes; byte_index++)
      value[8*byte_index +: 8] = 8'(word*17 + salt*13 + byte_index*29 + Width);
    return value;
  endfunction

  task automatic reset_control;
    @(negedge clk);
    req = 0; we = 0; rst_n = 0;
    held = '0; expected_valid = 0; have_read = 0; previous_bank = -1;
    #1;
    if (rvalid !== 0 || rdata !== '0) $fatal(1, "MC_ASYNC_RESET_FAIL id=%0d", Id);
    repeat (2) @(posedge clk);
    @(negedge clk); rst_n = 1;
    #1;
    if (rvalid !== 0 || rdata !== '0) $fatal(1, "MC_RESET_RELEASE_FAIL id=%0d", Id);
  endtask

  task automatic cycle(input bit request, input bit writing, input int word,
                        input logic [Bytes-1:0] mask, input logic [Width-1:0] value,
                        input int phase = 0);
    @(negedge clk);
    req = request; we = writing;
    addr = 64'h80000000 + 64'(word)*Bytes + phase;
    be = mask; wdata = value;
    #1;
    if ($isunknown({rvalid, rdata}) || rvalid !== expected_valid || rdata !== held)
      $fatal(1, "MC_EARLY_OR_HOLD_FAIL id=%0d step=%0d", Id, steps);
    @(posedge clk);
    if (request && writing) begin
      for (int byte_index = 0; byte_index < Bytes; byte_index++)
        if (mask[byte_index]) reference_mem[word][8*byte_index +: 8] = value[8*byte_index +: 8];
      writes++;
      if (mask != '1) masked++;
      if (mask == '0) zero_mask++;
    end
    if (request && !writing) begin
      held = reference_mem[word]; reads++;
      if (have_read && previous_bank != word/8192) switches++;
      previous_bank = word/8192; have_read = 1;
    end else holds++;
    if (!request) idle++;
    if (request) phase_seen[phase] = 1;
    expected_valid = request; steps++;
    #1;
    if ($isunknown({rvalid, rdata}) || rvalid !== expected_valid || rdata !== held)
      $fatal(1, "MC_READBACK_OR_LATENCY_FAIL id=%0d step=%0d word=%0d got=%h expected=%h",
             Id, steps, word, rdata, held);
  endtask

  initial begin : traffic
    logic [Bytes-1:0] mask;
    int word;
    int unsigned random_state;
    done = 0; rst_n = 0; req = 0; we = 0; addr = '0; wdata = '0; be = '0;
    held = '0; expected_valid = 0; phase_seen = '0;
    steps = 0; reads = 0; writes = 0; idle = 0; masked = 0; zero_mask = 0;
    holds = 0; switches = 0; have_read = 0; previous_bank = -1;
    reset_control();
    for (int i = 0; i < Pool; i++)
      cycle(1, 1, pool_word(i), '1, pattern(pool_word(i), 1));
    for (int i = 0; i < Pool; i++)
      cycle(1, 0, pool_word(i), '1, '0);
    for (int byte_index = 0; byte_index < Bytes; byte_index++) begin
      word = (byte_index % Banks)*8192 + ((byte_index % 2) ? 8191 : 0);
      mask = '0; mask[byte_index] = 1;
      cycle(1, 1, word, mask, pattern(word, 100 + byte_index), byte_index);
      cycle(1, 0, word, '1, '0, byte_index);
      cycle(0, 1, pool_word((byte_index + 4) % Pool), '1, '1, byte_index);
      cycle(1, 0, word, '1, '0, byte_index);
    end
    cycle(1, 1, pool_word(0), '0, '1);
    cycle(1, 0, pool_word(0), '1, '0);
    cycle(1, 0, pool_word(Pool-1), '1, '0);
    cycle(1, 1, pool_word(0), '1, pattern(pool_word(0), 912));
    repeat (3) cycle(0, 1, pool_word(0), '1, '0);
    cycle(1, 0, pool_word(0), '1, '0);
    random_state = 32'h31415926 + Id;
    for (int i = 0; i < 128; i++) begin
      random_state = random_state*32'd1664525 + 32'd1013904223;
      word = pool_word((random_state >> 2) % Pool);
      for (int b = 0; b < Bytes; b++) mask[b] = random_state[b % 32];
      case (random_state[1:0])
        0: cycle(0, 1, word, mask, pattern(word, random_state), (random_state >> 10) % Bytes);
        1: cycle(1, 0, word, mask, pattern(word, random_state), (random_state >> 10) % Bytes);
        2: cycle(1, 1, word, '1, pattern(word, random_state), (random_state >> 10) % Bytes);
        3: cycle(1, 1, word, mask, pattern(word, random_state), (random_state >> 10) % Bytes);
      endcase
    end
    reset_control();
    cycle(1, 0, pool_word(0), '1, '0);
    cycle(1, 0, pool_word(Pool-1), '1, '0);
    cycle(0, 1, pool_word(0), '1, '1);
    cycle(0, 0, pool_word(Pool-1), '0, '0);
    if (phase_seen !== '1 || zero_mask == 0 || masked == 0 || (Banks > 1 && switches == 0))
      $fatal(1, "MC_COVERAGE_FAIL id=%0d", Id);
    $display("MC_CASE_PASS id=%0d width=%0d words=%0d banks=%0d columns=%0d default_depth=%0d steps=%0d reads=%0d writes=%0d idle=%0d masked=%0d zero_mask=%0d holds=%0d switches=%0d phases=%0d checked_read_bytes=%0d resets=2",
        Id, Width, Depth, Banks, (Width+127)/128, DefaultDepth, steps, reads, writes, idle,
        masked, zero_mask, holds, switches, $countones(phase_seen), reads*Bytes);
    done = 1;
  end
endmodule

module ara_soc_sram_mc_tb;
  logic clk = 0;
  always #5 clk = !clk;
  wire [9:0] done;
  sram_mc_case #(.Id(0), .Width(8),   .Words(8192)) a0(clk, done[0]);
  sram_mc_case #(.Id(1), .Width(32),  .Words(8192)) a1(clk, done[1]);
  sram_mc_case #(.Id(2), .Width(64),  .Words(16384)) a2(clk, done[2]);
  sram_mc_case #(.Id(3), .Width(128), .Words(8192)) a3(clk, done[3]);
  sram_mc_case #(.Id(4), .Width(128), .DefaultDepth(1)) a4(clk, done[4]);
  sram_mc_case #(.Id(5), .Width(256), .Words(8192)) a5(clk, done[5]);
  sram_mc_case #(.Id(6), .Width(256), .Words(16384)) a6(clk, done[6]);
  sram_mc_case #(.Id(7), .Width(256), .DefaultDepth(1)) a7(clk, done[7]);
  sram_mc_case #(.Id(8), .Width(512), .Words(8192)) a8(clk, done[8]);
  sram_mc_case #(.Id(9), .Width(512), .DefaultDepth(1)) a9(clk, done[9]);
  initial begin
    wait (&done);
    #1; $display("MC_COMPONENT_PASS cases=10"); $finish;
  end
  initial begin
    #200000; $fatal(1, "MC_WATCHDOG_FAIL");
  end
endmodule
