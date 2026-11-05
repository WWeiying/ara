// Valid-qualified miter plus an independent byte-write SRAM scoreboard.
module vrf_return_case import ara_pkg::*; #(parameter int Banks = 8)(output bit done);
  localparam int Words = 32;
  typedef logic [$clog2(Words)-1:0] addr_t;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic [Banks-1:0] req, wen;
  addr_t [Banks-1:0] addr;
  opqueue_e [Banks-1:0] target;
  elen_t [Banks-1:0] wdata;
  logic [Banks-1:0][7:0] be;
  elen_t [NrOperandQueues-1:0] actual, original, expected;
  logic [NrOperandQueues-1:0] valid, old_valid, expected_valid;
  logic [63:0] memory [Banks][Words];
  int hits [Banks][NrOperandQueues];
  int cycles = 0, reads = 0, writes = 0;
  int random_state = 32'h1234abcd + Banks;
  int negative = 0;

  vector_regfile #(.NrBanks(Banks), .VRFSize(Banks*Words*64), .vaddr_t(addr_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .req_i(req), .addr_i(addr), .tgt_opqueue_i(target),
    .wen_i(wen), .wdata_i(wdata), .be_i(be), .operand_o(actual), .operand_valid_o(valid));
  vector_regfile_reference #(.NrBanks(Banks), .VRFSize(Banks*Words*64), .vaddr_t(addr_t)) ref_dut (
    .clk_i(clk), .rst_ni(rst_n), .req_i(req), .addr_i(addr), .tgt_opqueue_i(target),
    .wen_i(wen), .wdata_i(wdata), .be_i(be), .operand_o(original), .operand_valid_o(old_valid));

  function automatic int unsigned rng();
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return unsigned'(random_state);
  endfunction

  task automatic idle();
    req = '0; wen = 'x; addr = 'x; target = 'x; wdata = 'x; be = 'x;
  endtask

  task automatic tick();
    @(posedge clk);
    expected_valid = '0;
    expected = 'x;
    if (rst_n) for (int b = 0; b < Banks; b++) if (req[b]) begin
      if (wen[b]) begin
        for (int byte_idx = 0; byte_idx < 8; byte_idx++)
          if (be[b][byte_idx]) memory[b][addr[b]][byte_idx*8+:8] = wdata[b][byte_idx*8+:8];
        writes++;
      end else if (unsigned'(target[b]) < NrOperandQueues) begin
        expected_valid[target[b]] = 1;
        expected[target[b]] = memory[b][addr[b]];
        hits[b][target[b]]++;
        reads++;
      end
    end
    #1;
    if (valid !== expected_valid || valid !== old_valid)
      $fatal(1, "VRF_VALID_MISMATCH banks=%0d cycle=%0d got=%h expected=%h old=%h",
        Banks, cycles, valid, expected_valid, old_valid);
    for (int q = 0; q < NrOperandQueues; q++) if (valid[q]) begin
      if (actual[q] !== expected[q] || actual[q] !== original[q])
        $fatal(1, "VRF_DATA_MISMATCH banks=%0d cycle=%0d queue=%0d got=%h expected=%h old=%h",
          Banks, cycles, q, actual[q], expected[q], original[q]);
    end
    cycles++;
    @(negedge clk);
  endtask

  initial begin
    done = 0;
    void'($value$plusargs("NEGATIVE=%d", negative));
    foreach (memory[b,w]) memory[b][w] = 'x;
    foreach (hits[b,q]) hits[b][q] = 0;
    idle(); tick(); tick(); rst_n = 1;
    if (Banks == 8 && negative != 0) begin
      // Exercise the production invariant checks without relying on the miter.
      idle(); req[0] = 1; wen[0] = 0; addr[0] = 0; target[0] = AluA;
      case (negative)
        1: begin req[1] = 1; wen[1] = 0; addr[1] = 0; target[1] = AluA; end
        2: target[0] = opqueue_e'(15);
        3: target[0] = opqueue_e'('x);
        4: req[0] = 1'bx;
      endcase
      repeat (3) @(posedge clk);
      #1; $fatal(1, "VRF_NEGATIVE_NOT_REJECTED");
    end
    // Read unwritten words: valid X data is preserved, idle X tags are ignored.
    for (int b = 0; b < Banks; b++) for (int q = 0; q < NrOperandQueues; q++) begin
      idle(); req[b] = 1; wen[b] = 0; addr[b] = 0; target[b] = opqueue_e'(q); tick();
    end
    // Initialize every word using actual gated SRAM write ports.
    for (int w = 0; w < Words; w++) begin
      idle();
      for (int b = 0; b < Banks; b++) begin
        req[b] = 1; wen[b] = 1; addr[b] = addr_t'(w); target[b] = AluA;
        be[b] = '1; wdata[b] = {32'(b*Words+w), ~(32'(b*Words+w))};
      end
      tick();
    end
    // All bank/target mappings with maximal simultaneous distinct returns.
    for (int w = 0; w < Words; w++) for (int shift = 0; shift < NrOperandQueues; shift++) begin
      idle();
      for (int b = 0; b < Banks; b++) begin
        req[b] = 1; wen[b] = 0; addr[b] = addr_t'(w);
        target[b] = opqueue_e'((b+shift)%NrOperandQueues);
      end
      tick();
    end
    // Mixed read/write bursts, byte enables, target changes, clock wakeups and resets.
    for (int n = 0; n < 30000; n++) begin
      int shift;
      shift = rng()%NrOperandQueues;
      idle();
      for (int b = 0; b < Banks; b++) if ((rng()%4) != 0) begin
        req[b] = 1; wen[b] = (rng()%3) == 0; addr[b] = addr_t'(rng()%Words);
        target[b] = wen[b] ? AluA : opqueue_e'((b+shift)%NrOperandQueues);
        be[b] = 8'(rng()); wdata[b] = {rng(), rng()};
        if (wen[b] && n%31 == 0) wdata[b][7:0] = 'x;
      end
      tick();
      if (n%997 == 0) begin
        rst_n = 0; idle(); tick(); tick(); rst_n = 1;
      end
    end
    idle(); tick(); tick();
    foreach (hits[b,q]) if (hits[b][q] == 0) $fatal(1, "VRF_MAPPING_NOT_COVERED");
    $display("VRF_RETURN_CASE_PASS banks=%0d cycles=%0d reads=%0d writes=%0d mappings=%0d",
      Banks, cycles, reads, writes, Banks*NrOperandQueues);
    done = 1;
  end
endmodule

module vrf_return_tb;
  wire [2:0] done;
  vrf_return_case #(.Banks(1)) single_bank(done[0]);
  vrf_return_case #(.Banks(2)) two_bank(done[1]);
  vrf_return_case #(.Banks(8)) lane_banks(done[2]);
  initial begin
    wait (&done); $display("VRF_RETURN_PASS"); $finish;
  end
  initial begin #1000000; $fatal(1, "VRF_RETURN_WATCHDOG"); end
endmodule
