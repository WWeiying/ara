// Compare against the mapped design's FIFO protocol, including backpressure
// before acceptance. An invalid payload is deliberately not a transaction.
module request_bypass_equivalence_tb;
  bit clk;
  always #5 clk = !clk;
  logic rst_n, clear, valid_in, ready_in;
  logic [171:0] data_in, ref_data, data_out;
  logic ready_out, valid_out, ref_empty, ref_full;
  int unsigned seed = 32'h13a20cb5;
  int bypasses, holds, fulls, buffered, clears;

  fall_through_register_v1 #(.T(logic [171:0]), .DEPTH(2)) candidate (
    .clk_i(clk), .rst_ni(rst_n), .clr_i(clear), .testmode_i(1'b0),
    .valid_i(valid_in), .ready_o(ready_out), .data_i(data_in),
    .valid_o(valid_out), .ready_i(ready_in), .data_o(data_out));
  fifo_v3 #(.dtype(logic [171:0]), .DEPTH(2), .FALL_THROUGH(1'b1)) reference_fifo (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(clear), .testmode_i(1'b0),
    .data_i(data_in), .data_o(ref_data), .full_o(ref_full), .empty_o(ref_empty),
    .usage_o(), .push_i(valid_in && !ref_full), .pop_i(ready_in && !ref_empty));

  initial begin
    rst_n = 0; clear = 0; valid_in = 0; ready_in = 0; data_in = '0;
    repeat (2) @(negedge clk);
    for (int i=0; i<20000; i++) begin
      seed = seed ^ (seed << 13); seed = seed ^ (seed >> 17); seed = seed ^ (seed << 5);
      rst_n = (i % 601 != 0); clear = seed[15:11] == 0;
      valid_in = seed[2]; ready_in = seed[5];
      data_in = {data_in[139:0], seed};
      #1;
      if ({ready_out,valid_out} !== {!ref_full,!ref_empty} ||
          (valid_out && data_out !== ref_data))
        $fatal(1, "FIFO mismatch at cycle %0d", i);
      if (rst_n && !clear) begin
        if (valid_out && ready_in && reference_fifo.status_cnt_q == 0) bypasses++;
        if (valid_out && !ready_in) holds++;
        if (ref_full) fulls++;
        if (valid_in && ready_out && valid_out && ready_in &&
            reference_fifo.status_cnt_q != 0) buffered++;
      end
      if (clear && !ref_empty) clears++;
      @(negedge clk);
    end
    if (!(bypasses && holds && fulls && buffered && clears)) $fatal(1, "missing coverage");
    $display("REQUEST_BYPASS_PASS cycles=20000 bypass=%0d stall=%0d full=%0d replace=%0d clear=%0d",
             bypasses, holds, fulls, buffered, clears);
    $finish;
  end
endmodule
