`timescale 1ps/1ps
module tb;
  reg [47:0] address;
  reg [7:0] length;
  reg [2:0] size;
  reg [1:0] burst;
  wire [7:0] desc_length, next_length;
  wire [47:0] next_address;
  wire last;
  integer region, offset, sz, beats, fixed_burst, available, expected_len;
  integer cases = 0;

`ifdef WRITE_CUTTER
  axi_llc_burst_cutter dut (
`else
  axi_llc_burst_cutter__parameterized0 dut (
`endif
    .clk_i(1'b0), .rst_ni(1'b1),
    .\curr_chan_i[addr] (address), .\curr_chan_i[len] (length),
    .\curr_chan_i[size] (size), .\curr_chan_i[burst] (burst),
    .\desc_o[a_x_len] (desc_length), .\desc_o[x_last] (last),
    .\next_chan_o[addr] (next_address), .\next_chan_o[len] (next_length)
  );

  initial begin
    // This extracted block has optimized-away rule inputs. Check only its
    // surviving length/last/next-line outputs, not unconnected exported ports.
    for (region = 0; region < 2; region = region + 1)
      for (sz = 0; sz <= 3; sz = sz + 1)
        for (offset = 0; offset < 64; offset = offset + (1 << sz))
          for (beats = 1; beats <= 256; beats = beats + 1)
            for (fixed_burst = 0; fixed_burst < 2; fixed_burst = fixed_burst + 1) begin
              address = (region == 0 ? 48'hffff0000 : 48'h1001ff00) + offset;
              length = beats - 1;
              size = sz;
              burst = fixed_burst ? 0 : 1;
              available = (64 - offset) >> sz;
              expected_len = (fixed_burst || beats <= available) ? beats - 1 : available - 1;
              #1000;
              if (desc_length !== expected_len[7:0] ||
                  last !== (fixed_burst || beats <= available))
                $fatal(1, "CUTTER addr=%h size=%0d beats=%0d burst=%0d len=%0d last=%b expected_len=%0d",
                       address, size, beats, burst, desc_length, last, expected_len);
              if (!last && (next_address[47:6] !== (address[47:6] + 42'd1) ||
                            next_length !== (length - available[7:0])))
                $fatal(1, "NEXT addr=%h size=%0d len=%0d next=%h next_len=%0d",
                       address, size, length, next_address, next_length);
              cases = cases + 1;
            end
    $display("PASS cutter cases=%0d", cases);
    $finish;
  end
endmodule
