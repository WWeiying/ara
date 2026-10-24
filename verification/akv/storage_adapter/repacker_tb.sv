module repacker_tb;
  bit clk = 0;
  always #5 clk = !clk;
  bit rst = 0, abort_write = 0, valid = 0;
  logic [15:0] tag, strb, out_tag;
  logic [8:0] offset, row_bytes, out_offset;
  logic [127:0] data, out_data;
  logic out_valid, last, busy;
  int expected_tag, expected_offset, expected_bytes;
  int writes = 0, checked_bytes = 0, rows = 0, aborts = 0;
  bit checking = 0;
  bit chain_pending = 0;
  int chain_tag, cycle = 0, final_input_cycle[int], latency_checks = 0;
  akv_legacy_repacker dut (
    .clk_i(clk), .rst_ni(rst), .abort_i(abort_write), .fragment_valid_i(valid),
    .fragment_tag_i(tag), .fragment_offset_i(offset), .row_bytes_i(row_bytes),
    .fragment_data_i(data), .fragment_strb_i(strb), .write_valid_o(out_valid),
    .write_tag_o(out_tag), .write_offset_o(out_offset), .write_data_o(out_data),
    .write_last_o(last), .busy_o(busy)
  );
  function automatic byte payload(int t, int p);
    return byte'((t * 29) ^ (p * 13) ^ (p >> 3));
  endfunction
  always @(posedge clk) begin
    cycle++;
    if (rst && !abort_write && valid && unsigned'(offset) + $countones(strb) == row_bytes)
      final_input_cycle[int'(tag)] = cycle;
    if (rst && out_valid) begin
    assert (checking && out_tag == expected_tag && out_offset == expected_offset)
      else $fatal(1, "REPACK_OUTPUT_IDENTITY");
    for (int i=0; i<16; i++) begin
      assert (out_data[i*8 +: 8] === payload(expected_tag, expected_offset+i))
        else $fatal(1, "REPACK_OUTPUT_BYTE");
      checked_bytes++;
    end
    assert (last == (expected_offset + 16 == expected_bytes))
      else $fatal(1, "REPACK_OUTPUT_LAST");
    expected_offset += 16;
    writes++;
    if(last) begin
      assert(final_input_cycle.exists(int'(out_tag)) &&
             cycle-final_input_cycle[int'(out_tag)] == 2)
        else $fatal(1,"REPACK_FINAL_WRITE_LATENCY");
      latency_checks++;
      if(chain_pending) begin
        expected_tag=chain_tag; expected_offset=0; chain_pending=0;
      end
    end
    end
  end
  task automatic fragment(int t, int p, int count, int bytes);
    @(negedge clk);
    valid = 1; tag = 16'(t); offset = 9'(p); row_bytes = 9'(bytes);
    strb = 16'((32'd1 << count)-1);
    // Poison invalid bytes: the adapter must not leak these into pending data.
    data = '1;
    for (int i=0; i<count; i++) data[i*8 +: 8] = payload(t,p+i);
  endtask
  task automatic drain();
    @(negedge clk); valid = 0;
    repeat(4) @(negedge clk);
    assert (!busy) else $fatal(1, "REPACK_DRAIN");
  endtask
  task automatic full_row(int t, int bytes, int alignment);
    int p, count;
    expected_tag=t; expected_offset=0; expected_bytes=bytes; checking=1;
    p=0;
    while(p < bytes) begin
      // Mirrors compact fragments split by physical 16-byte beat boundaries.
      count=16-((alignment+p)%16);
      if(count>bytes-p) count=bytes-p;
      fragment(t,p,count,bytes); p+=count;
      if((p/16)%3==1) begin
        @(negedge clk); valid=0;
      end
    end
    drain();
    assert(expected_offset==bytes) else $fatal(1,"REPACK_ROW_INCOMPLETE");
    rows++; checking=0;
  endtask
  initial begin
    repeat(3) @(negedge clk); rst=1;
    for(int n=128;n<=256;n+=64)
      for(int a=0;a<16;a+=2) full_row(16'h8000+n+a,n,a);
    // Abort every nonzero even partial occupancy, then readmit a new identity.
    for(int p=2;p<16;p+=2) begin
      checking=0;
      fragment(16'hdead,0,p,256);
      @(negedge clk); valid=0;
      @(negedge clk); abort_write=1;
      @(negedge clk); abort_write=0;
      drain(); aborts++;
      full_row(16'h9100+p,256,16-p);
    end
    // Abort with a registered whole-word emission and a younger fragment.
    fragment(16'hdead,0,16,128);
    fragment(16'hdead,16,16,128);
    @(negedge clk); valid=0; abort_write=1;
    @(negedge clk); abort_write=0;
    drain(); aborts++;
    full_row(16'hbeef,128,0);
    // Change identity with no idle cycle while the older final write is pending.
    checking=1; expected_tag=16'hcafe; expected_offset=0; expected_bytes=128;
    chain_pending=1; chain_tag=16'hface;
    for(int p=0;p<128;p+=16) fragment(16'hcafe,p,16,128);
    for(int p=0;p<128;p+=16) fragment(16'hface,p,16,128);
    drain();
    assert(expected_offset==128 && !chain_pending) else $fatal(1,"REPACK_CHAIN");
    rows+=2;
    $display("REPACK_UNIT_PASS rows=%0d aborts=%0d writes=%0d bytes=%0d latency_checks=%0d", rows,aborts,writes,checked_bytes,latency_checks);
    $finish;
  end
  initial begin #200000; $fatal(1,"REPACK_TIMEOUT"); end
endmodule
