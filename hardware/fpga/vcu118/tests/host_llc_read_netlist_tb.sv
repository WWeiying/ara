`timescale 1ps/1ps
module tb;
  reg clk = 0;
  always #5000 clk = ~clk;
  reg rst_n = 0, valid = 0;
  reg [47:0] address = 0;
  reg [7:0] length = 0;
  reg [2:0] size = 3;
  reg [1:0] burst = 1;
  wire ready, way_valid, r_valid, r_last;
  wire [7:0] line_addr;
  wire [2:0] block_offset;
  wire [3:0] r_id;
  wire [1:0] r_resp;
  integer cycle = 0, requests = 0, responses = 0, total = 0, cases = 0;
  integer offset, beats, sz, fixed_burst, wait_cycles, min_size = 3;
  reg active = 0;
  reg [47:0] expected;
  wire way_ready = (cycle % 4 != 0);
  wire r_ready = (cycle % 5 != 0);

  axi_llc_read_unit dut (
    .clk_i(clk), .rst_ni(rst_n), .test_i(1'b0),
    .\desc_i[a_x_id] (4'h9), .\desc_i[a_x_addr] (address),
    .\desc_i[a_x_len] (length), .\desc_i[a_x_size] (size),
    .\desc_i[a_x_burst] (burst), .\desc_i[a_x_lock] (1'b0),
    .\desc_i[a_x_cache] (4'b0), .\desc_i[a_x_prot] (3'b0),
    .\desc_i[x_resp] (2'b0), .\desc_i[x_last] (1'b1),
    .\desc_i[spm] (1'b1), .\desc_i[rw] (1'b0),
    .\desc_i[way_ind] (8'h01), .\desc_i[evict] (1'b0),
    .\desc_i[evict_tag] (34'b0), .\desc_i[refill] (1'b0), .\desc_i[flush] (1'b0),
    .desc_valid_i(valid), .desc_ready_o(ready),
    // The extracted cell retains address bits [13:6] on the unlock alias;
    // the duplicate way_inp line_addr port has no driver in this export.
    .\r_unlock_o[index] (line_addr), .\way_inp_o[blk_offset] (block_offset),
    .way_inp_valid_o(way_valid), .way_inp_ready_i(way_ready),
    // Return one dummy SRAM token whenever the metadata FIFO can accept it.
    // Data storage is outside this test; addresses/beat counts/last/ID are checked.
    .\way_out_i[cache_unit] (2'b0), .\way_out_i[data] (64'h0123456789abcdef),
    .way_out_valid_i(1'b1), .r_chan_valid_o(r_valid), .r_chan_ready_i(r_ready),
    .\r_chan_slv_o[last] (r_last), .\r_chan_slv_o[id] (r_id),
    .\r_chan_slv_o[resp] (r_resp), .r_unlock_gnt_i(1'b1)
  );

  always @(posedge clk) begin
    cycle <= cycle + 1;
    if (rst_n && active) begin
      if (way_valid && way_ready) begin
        expected = address + (burst == 0 ? 0 : (requests << size));
        if ({line_addr, block_offset} !== expected[13:3])
          $fatal(1, "READ_ADDR start=%h size=%0d beat=%0d got_word=%h expected_word=%h",
                 address, size, requests, {line_addr, block_offset}, expected[13:3]);
        requests = requests + 1;
        total = total + 1;
        if (requests > length + 1) $fatal(1, "Extra SRAM request");
      end
      if (r_valid && r_ready) begin
        // RRESP[0] is an optimized-away constant in the extracted submodule.
        if (r_id !== 4'h9 || r_resp[1] !== 0 || r_last !== (responses == length))
          $fatal(1, "READ_RESP beat=%0d id=%h resp=%h last=%b", responses, r_id, r_resp, r_last);
        responses = responses + 1;
      end
    end
  end

  initial begin
    if ($value$plusargs("min_size=%d", min_size)) begin end
    if (min_size < 0 || min_size > 3) $fatal(1, "Invalid min_size");
    #200000;
    for (sz = min_size; sz <= 3; sz = sz + 1)
      for (offset = 0; offset < 64; offset = offset + (1 << sz))
        for (beats = 1; beats <= ((64-offset) >> sz); beats = beats + 1)
          for (fixed_burst = 0; fixed_burst < 2; fixed_burst = fixed_burst + 1) begin
            @(negedge clk);
            active = 0; valid = 0; rst_n = 0;
            repeat (2) @(negedge clk);
            address = 48'h1001ff00 + offset;
            length = beats - 1; size = sz; burst = fixed_burst ? 0 : 1;
            requests = 0; responses = 0; active = 1; rst_n = 1;
            @(negedge clk);
            valid = 1;
            @(posedge clk);
            while (!ready) @(posedge clk);
            @(negedge clk);
            valid = 0;
            wait_cycles = 0;
            while (responses < beats && wait_cycles < 1000) begin
              @(negedge clk);
              wait_cycles = wait_cycles + 1;
            end
            if (responses != beats || requests != beats) $fatal(1, "Read unit timeout");
            cases = cases + 1;
          end
    $display("PASS read_unit cases=%0d requests=%0d", cases, total);
    $finish;
  end
  initial begin #10000000000; $fatal(1, "Global timeout"); end
endmodule
