`timescale 1ps/1ps
module tb;
  reg clk = 0;
  always #5000 clk = ~clk;
  reg rst_n = 0, valid = 0, w_valid = 0, w_last = 0;
  reg [47:0] address = 0;
  reg [7:0] length = 0;
  reg [1:0] burst = 1;
  reg [63:0] w_data = 0;
  reg [7:0] w_strb = 0;
  wire ready, w_ready, way_valid, b_valid;
  wire [7:0] line_addr, way_strb;
  wire [2:0] block_offset;
  wire [63:0] way_data;
  wire [3:0] b_id;
  wire [1:0] b_resp;
  integer cycle = 0, requests = 0, responses = 0, total = 0, cases = 0;
  integer offset, beats, fixed_burst, wait_cycles, i;
  reg active = 0;
  reg [47:0] expected;
  wire way_ready = (cycle % 4 != 0);
  wire b_ready = (cycle % 5 != 0);

  function [63:0] pattern(input integer beat);
    pattern = 64'hefcdab8967452301 ^ (64'h1032547698badcfe * beat);
  endfunction
  function [7:0] strobe(input integer beat);
    strobe = 8'hff ^ (1 << (beat % 8));
  endfunction

  axi_llc_write_unit dut (
    .clk_i(clk), .rst_ni(rst_n), .test_i(1'b0),
    .\desc_i[a_x_id] (4'h9), .\desc_i[a_x_addr] (address),
    .\desc_i[a_x_len] (length), .\desc_i[a_x_size] (3'd3),
    .\desc_i[a_x_burst] (burst), .\desc_i[a_x_lock] (1'b0),
    .\desc_i[a_x_cache] (4'b0), .\desc_i[a_x_prot] (3'b0),
    .\desc_i[x_resp] (2'b0), .\desc_i[x_last] (1'b1),
    .\desc_i[spm] (1'b1), .\desc_i[rw] (1'b1),
    .\desc_i[way_ind] (8'h01), .\desc_i[evict] (1'b0),
    .\desc_i[evict_tag] (34'b0), .\desc_i[refill] (1'b0), .\desc_i[flush] (1'b0),
    .desc_valid_i(valid), .desc_ready_o(ready),
    .\w_chan_slv_i[data] (w_data), .\w_chan_slv_i[strb] (w_strb),
    .\w_chan_slv_i[last] (w_last), .\w_chan_slv_i[user] (2'b0),
    .w_chan_valid_i(w_valid), .w_chan_ready_o(w_ready),
    // Unlike the read-unit export, this export retains the way address alias.
    .\way_inp_o[line_addr] (line_addr), .\way_inp_o[blk_offset] (block_offset),
    .\way_inp_o[data] (way_data), .\way_inp_o[strb] (way_strb),
    .way_inp_valid_o(way_valid), .way_inp_ready_i(way_ready),
    .b_chan_valid_o(b_valid), .b_chan_ready_i(b_ready),
    .\b_chan_slv_o[id] (b_id), .\b_chan_slv_o[resp] (b_resp), .w_unlock_gnt_i(1'b1)
  );

  always @(posedge clk) begin
    cycle <= cycle + 1;
    if (rst_n && active) begin
      if (way_valid && way_ready) begin
        expected = address + (burst == 0 ? 0 : requests * 8);
        if ({line_addr, block_offset} !== expected[13:3] ||
            way_data !== pattern(requests) || way_strb !== strobe(requests))
          $fatal(1, "WRITE start=%h beat=%0d word=%h expected=%h data=%h strb=%h",
                 address, requests, {line_addr, block_offset}, expected[13:3], way_data, way_strb);
        requests = requests + 1;
        total = total + 1;
        if (requests > length + 1) $fatal(1, "Extra SRAM write");
      end
      if (b_valid && b_ready) begin
        // BRESP[0] and constant WE are unconnected aliases in this cell export.
        if (b_id !== 4'h9 || b_resp[1] !== 0 || requests != length + 1)
          $fatal(1, "WRITE_RESP id=%h resp=%h requests=%0d", b_id, b_resp, requests);
        responses = responses + 1;
        if (responses > 1) $fatal(1, "Extra B response");
      end
    end
  end

  initial begin
    #200000;
    for (offset = 0; offset < 64; offset = offset + 8)
      for (beats = 1; beats <= ((64-offset) >> 3); beats = beats + 1)
        for (fixed_burst = 0; fixed_burst < 2; fixed_burst = fixed_burst + 1) begin
          @(negedge clk);
          active = 0; valid = 0; w_valid = 0; rst_n = 0;
          repeat (2) @(negedge clk);
          address = 48'h1001ff00 + offset;
          length = beats - 1; burst = fixed_burst ? 0 : 1;
          requests = 0; responses = 0; active = 1; rst_n = 1;
          @(negedge clk);
          valid = 1;
          @(posedge clk);
          while (!ready) @(posedge clk);
          @(negedge clk);
          valid = 0;
          for (i = 0; i < beats; i = i + 1) begin
            w_data = pattern(i); w_strb = strobe(i); w_last = (i == beats-1); w_valid = 1;
            @(posedge clk);
            while (!w_ready) @(posedge clk);
            @(negedge clk);
            w_valid = 0;
            if (i % 3 == 0) @(negedge clk);
          end
          wait_cycles = 0;
          while (responses < 1 && wait_cycles < 1000) begin
            @(negedge clk);
            wait_cycles = wait_cycles + 1;
          end
          repeat (3) @(negedge clk);
          if (responses != 1 || requests != beats) $fatal(1, "Write unit timeout");
          cases = cases + 1;
        end
    if (cases != 72 || total != 240) $fatal(1, "Coverage mismatch");
    $display("PASS write_unit cases=%0d requests=%0d", cases, total);
    $finish;
  end
  initial begin #10000000000; $fatal(1, "Global timeout"); end
endmodule
