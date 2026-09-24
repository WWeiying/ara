`timescale 1ps/1ps
module tb;
  reg clk = 0;
  always #5000 clk = ~clk;
  reg rst_n = 0, valid = 0;
  reg [47:0] address = 0;
  reg [7:0] length = 0;
  reg [2:0] size = 3;
  reg [1:0] burst = 1;
  wire ready, desc_valid, desc_last;
  wire [47:0] desc_address;
  wire [7:0] desc_length;
  wire [2:0] desc_size;
  wire [1:0] desc_burst;
  integer cycle = 0, remaining = 0, count = 0, cases = 0;
  integer offset, beats, stall, limit, available;
  reg active = 0;
  reg [47:0] expected;
  wire desc_ready = !stall || cycle % 4 == 0;

`ifdef WRITE_CUTTER
  axi_llc_chan_splitter dut (
`else
  axi_llc_chan_splitter__parameterized0 dut (
`endif
    .clk_i(clk), .rst_ni(rst_n),
    .\ax_chan_slv_i[id] (4'b0), .\ax_chan_slv_i[addr] (address),
    .\ax_chan_slv_i[len] (length), .\ax_chan_slv_i[size] (size),
    .\ax_chan_slv_i[burst] (burst), .\ax_chan_slv_i[lock] (1'b0),
    .\ax_chan_slv_i[cache] (4'b0), .\ax_chan_slv_i[prot] (3'b0),
    .\ax_chan_slv_i[qos] (4'b0), .\ax_chan_slv_i[region] (4'b0),
    .\ax_chan_slv_i[user] (2'b0), .ax_chan_valid_i(valid), .ax_chan_ready_o(ready),
    .\desc_o[a_x_addr] (desc_address), .\desc_o[a_x_len] (desc_length),
    .\desc_o[a_x_size] (desc_size), .\desc_o[a_x_burst] (desc_burst),
    .\desc_o[x_last] (desc_last), .desc_valid_o(desc_valid), .desc_ready_i(desc_ready)
  );

  always @(posedge clk) begin
    cycle <= cycle + 1;
    if (rst_n && active && desc_valid && desc_ready) begin
      available = (64 - (expected & 63)) >> size;
      if (available > remaining) available = remaining;
      if (remaining == 0 || desc_address !== expected || desc_length !== (available - 1) ||
          desc_size !== size || desc_burst !== burst || desc_last !== (available == remaining))
        $fatal(1, "SPLITTER got=%h len=%0d size=%0d last=%b expected=%h beats=%0d remaining=%0d",
               desc_address, desc_length, desc_size, desc_last, expected, available, remaining);
      expected = expected + 8 * available;
      remaining = remaining - available;
      count = count + 1;
    end
  end

  initial begin
    #200000;
    for (offset = 0; offset < 128; offset = offset + 8)
      for (beats = 1; beats <= 17; beats = beats + 1)
        for (stall = 0; stall < 2; stall = stall + 1) begin
          @(negedge clk);
          active = 0; valid = 0; rst_n = 0;
          repeat (2) @(negedge clk);
          rst_n = 1; address = 48'h1001ff00 + offset; length = beats - 1;
          expected = address; remaining = beats; active = 1;
          @(negedge clk);
          valid = 1;
          @(posedge clk);
          while (!ready) @(posedge clk);
          @(negedge clk);
          valid = 0; limit = 0;
          while (remaining != 0 && limit < 200) begin
            @(negedge clk);
            limit = limit + 1;
          end
          if (remaining != 0) $fatal(1, "Splitter timeout");
          repeat (3) @(negedge clk);
          cases = cases + 1;
        end
    $display("PASS splitter cases=%0d descriptors=%0d", cases, count);
    $finish;
  end
  initial begin #1000000000; $fatal(1, "Global timeout"); end
endmodule
