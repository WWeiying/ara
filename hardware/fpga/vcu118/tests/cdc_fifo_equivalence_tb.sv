module fifo_check #(
  parameter int Width = 582,
  parameter int LogDepth = 5,
  parameter time SrcHalf = 10ns,
  parameter time DstHalf = 1667ps,
  parameter int Id = 0
) (output logic done = 0);
  timeunit 1ns; timeprecision 1ps;
  typedef struct packed { logic [Width-2:0] data; logic last; } payload_t;
  logic src_clk = 0, dst_clk = 0, clocks_run = 1;
  always #(SrcHalf) if (clocks_run) src_clk = ~src_clk;
  initial begin
    #317ps;
    forever #(DstHalf) if (clocks_run) dst_clk = ~dst_clk;
  end
  logic arst_n = 0, src_rst_n, dst_rst_n;
  rstgen wr_reset(src_clk, arst_n, 1'b0, src_rst_n, );
  rstgen rd_reset(dst_clk, arst_n, 1'b0, dst_rst_n, );
  payload_t src_data = '0, dst_data, ref_data;
  logic src_valid = 0, src_ready, ref_ready, dst_valid, ref_valid, dst_ready = 0;
  cdc_fifo_gray #(.T(payload_t), .LOG_DEPTH(LogDepth)) dut (
    .src_clk_i(src_clk), .src_rst_ni(src_rst_n), .src_data_i(src_data),
    .src_valid_i(src_valid), .src_ready_o(src_ready),
    .dst_clk_i(dst_clk), .dst_rst_ni(dst_rst_n), .dst_data_o(dst_data),
    .dst_valid_o(dst_valid), .dst_ready_i(dst_ready)
  );
  reference_cdc_fifo_gray #(.T(payload_t), .LOG_DEPTH(LogDepth)) reference (
    .src_clk_i(src_clk), .src_rst_ni(src_rst_n), .src_data_i(src_data),
    .src_valid_i(src_valid), .src_ready_o(ref_ready),
    .dst_clk_i(dst_clk), .dst_rst_ni(dst_rst_n), .dst_data_o(ref_data),
    .dst_valid_o(ref_valid), .dst_ready_i(dst_ready)
  );
  payload_t queue[$];
  int mode = 0, sent = 0, received = 0, stalled = 0, full_hits = 0, checks = 0;
  int sequence_number = 0;
  bit accepted = 0;
  logic [31:0] wr_random = 32'hcafed00d ^ Id, rd_random = 32'h31415926 ^ Id;
  function automatic logic [31:0] step(input logic [31:0] x);
    return {x[30:0], x[31] ^ x[21] ^ x[1] ^ x[0]};
  endfunction
  function automatic payload_t payload(input int n);
    logic [Width-1:0] bits;
    for (int b = 0; b < Width; b++) bits[b] = ((n*17 + b*13) >> (b%19)) & 1;
    return payload_t'(bits);
  endfunction
  always @(negedge arst_n) queue.delete();
  always @(negedge src_clk) begin
    wr_random = step(wr_random);
    if (!src_rst_n) begin src_valid = 0; src_data = '0; end
    else if (!src_valid || accepted) begin
      src_valid = mode == 1 || (mode == 2 && wr_random[2:0] != 0);
      src_data = payload(sequence_number);
    end
  end
  always @(negedge dst_clk) begin
    rd_random = step(rd_random);
    dst_ready = dst_rst_n && (mode == 3 || (mode == 2 && rd_random[1:0] != 0));
  end
  always @(posedge src_clk) begin
    accepted = src_rst_n && src_valid && src_ready;
    if (accepted) begin queue.push_back(src_data); sent++; sequence_number++; end
    if (src_rst_n && src_valid && !src_ready) full_hits++;
    #1ps;
    if (src_rst_n) begin
      if (src_ready !== ref_ready || dut.async_wptr !== reference.async_wptr ||
          dut.async_data !== reference.async_data)
        $fatal(1, "FIFO %0d write state/handshake mismatch", Id);
      checks++;
    end
  end
  always @(posedge dst_clk) begin : read_check
    payload_t expected;
    if (dst_rst_n && dst_valid && dst_ready) begin
      if (!queue.size()) $fatal(1, "FIFO %0d unexpected output", Id);
      expected = queue.pop_front();
      if (dst_data !== expected) $fatal(1, "FIFO %0d data order mismatch", Id);
      received++;
    end
    if (dst_rst_n && dst_valid && !dst_ready) stalled++;
    #1ps;
    if (dst_rst_n) begin
      if (dst_valid !== ref_valid || dst_data !== ref_data ||
          dut.async_rptr !== reference.async_rptr)
        $fatal(1, "FIFO %0d read state/latency mismatch", Id);
      checks++;
    end
  end
  if (LogDepth == 5 && Width >= 128) begin : selector_checks
    for (genvar s = 0; s < (Width+63)/64; s++) begin : gen_slice
      always @(negedge src_clk) if (src_rst_n)
        if (dut.i_src.gen_fpga_write.gen_slice[s].select_q !==
            (32'b1 << dut.i_src.wptr_bin[4:0])) $fatal(1, "write selector drift");
      always @(negedge dst_clk) if (dst_rst_n)
        if (dut.i_dst.gen_fpga_read.gen_slice[s].select_q !==
            (32'b1 << dut.i_dst.rptr_bin[4:0])) $fatal(1, "read selector drift");
    end
  end
  initial begin
    #113ns; arst_n = 1;
    for (int epoch = 0; epoch < 4; epoch++) begin
      // Fill to capacity, random sustained traffic, then completely drain.
      mode = 1; repeat (160) @(negedge src_clk);
      mode = 2; repeat (3000) @(negedge src_clk);
      mode = 3; repeat (200) @(negedge src_clk);
      repeat (200) @(negedge dst_clk);
      #1ns;
      if (queue.size() || dst_valid) $fatal(1, "FIFO %0d failed to drain", Id);
      // Reset while full, including both clocks stopped. Common assertion,
      // independently synchronized release is the original FIFO contract.
      mode = 1; repeat (160) @(negedge src_clk);
      #713ps; clocks_run = 0; arst_n = 0;
      #20ns;
      if (dst_valid || ref_valid) $fatal(1, "FIFO output survived reset");
      arst_n = 1; #20ns;
      if (src_rst_n || dst_rst_n) $fatal(1, "reset released without a clock");
      clocks_run = 1;
    end
    if (received < 128 || full_hits < 4 || stalled < 4)
      $fatal(1, "FIFO %0d insufficient traffic/full/stall coverage", Id);
    $display("PASS FIFO %0d width=%0d depth=%0d sent=%0d received=%0d checks=%0d full=%0d stalled=%0d",
             Id, Width, 2**LogDepth, sent, received, checks, full_hits, stalled);
    done = 1;
  end
endmodule

module tb;
  timeunit 1ns; timeprecision 1ps;
  wire [6:0] done;
  fifo_check #(.Id(0)) w_forward(done[0]);
  fifo_check #(.Width(521), .SrcHalf(1667ps), .DstHalf(10ns), .Id(1)) r_reverse(done[1]);
  fifo_check #(.Width(128), .SrcHalf(3ns), .DstHalf(5ns), .Id(2)) boundary(done[2]);
  fifo_check #(.Width(129), .SrcHalf(5ns), .DstHalf(3ns), .Id(3)) partial_slice(done[3]);
  fifo_check #(.Width(40), .Id(4)) narrow_unchanged(done[4]);
  fifo_check #(.Width(256), .LogDepth(3), .Id(5)) other_depth(done[5]);
  fifo_check #(.Width(8), .LogDepth(1), .Id(6)) min_depth(done[6]);
  initial begin wait (&done); $display("PASS: all FIFO comparisons"); $finish; end
  initial begin #2ms; $fatal(1, "bounded FIFO test timed out"); end
endmodule
