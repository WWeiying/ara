`timescale 1ns/1ps
// Whole-design store-buffer netlist versus an independent FIFO payload oracle.
// Addresses stay in DDR; constant-specialized unused ports are tied low.
module scalar_store_mapped_tb;
  reg clk=0, rst=0, flush=0, push=0, commit=0, grant=0;
  reg [55:0] address=0;
  reg [63:0] data=0;
  reg [11:0] offset=0;
  wire ready, commit_ready, no_pending, empty, conflict, request;
  wire [10:0] index;
  wire [44:0] tag;
  wire [63:0] output_data;
  wire [7:0] be;
  wire [1:0] size;
  reg [55:0] expected_address[4];
  reg [63:0] expected_data[4];
  int checks=0, transactions=0;
  always #5 clk=~clk;
  store_buffer dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(flush), .stall_st_pending_i(1'b0),
    .no_st_pending_o(no_pending), .store_buffer_empty_o(empty),
    .page_offset_i(offset), .page_offset_matches_o(conflict),
    .commit_i(commit), .commit_ready_o(commit_ready), .ready_o(ready),
    .valid_i(push), .valid_without_flush_i(push), .paddr_i(address),
    .data_i(data), .be_i(8'hff), .data_size_i(2'b11),
    .\req_port_i[data_gnt] (grant), .\req_port_i[data_rvalid] (1'b0),
    .\req_port_i[data_rid] (1'b0), .\req_port_i[data_rdata] (64'b0),
    .\req_port_i[data_ruser] (2'b0), .\req_port_o[data_req] (request),
    .\req_port_o[address_index] (index), .\req_port_o[address_tag] (tag),
    .\req_port_o[data_wdata] (output_data), .\req_port_o[data_be] (be),
    .\req_port_o[data_size] (size)
  );
  task automatic tick;
    @(posedge clk); #1; @(negedge clk);
  endtask
  task automatic check(input logic condition, input string message);
    checks++;
    if (condition !== 1'b1) $fatal(1,"STORE_MAPPED_FAIL tx=%0d %s",transactions,message);
  endtask
  initial begin
    #201;
    repeat(3) tick(); rst=1; tick();
    check(empty && no_pending && !request,"reset");
    for(int batch=0; batch<128; batch++) begin
      for(int slot=0; slot<4; slot++) begin
        check(ready,"spec queue readiness");
        expected_address[slot]=56'h80000000 + 56'(batch*4096+slot*8);
        expected_data[slot]=64'h0123456789abcdef ^ (64'(batch*4+slot)*64'h0102040810204081);
        address=expected_address[slot]; data=expected_data[slot]; push=1;
        tick(); push=0; #1;
        transactions++;
      end
      check(!ready && no_pending && !empty && !request,"full speculative queue");
      for(int slot=0; slot<4; slot++) begin
        offset=expected_address[slot][11:0]; #1;
        check(conflict,"speculative address lost");
      end
      offset=12'hff8; #1; check(!conflict,"false address conflict");
      for(int slot=0; slot<4; slot++) begin
        check(commit_ready,"commit readiness");
        commit=1; tick(); commit=0; #1;
      end
      check(!commit_ready && !no_pending && !empty,"full commit queue");
      for(int slot=0; slot<4; slot++) begin
        check(request && {tag,index} === expected_address[slot],"committed address order");
        // WT store path uses byte enables; whole-design synthesis removes size.
        check(output_data === expected_data[slot] && be === 8'hff,
              $sformatf("committed payload order got=%h expected=%h be=%h size_unused=%b",
                        output_data,expected_data[slot],be,size));
        offset=expected_address[slot][11:0]; #1;
        check(conflict,"committed address lost");
        grant=1; tick(); grant=0; #1;
        check(!conflict,"stale conflict after grant");
      end
      check(empty && no_pending && !request && ready,"queues did not drain");
      // Check that flushing a partial queue removes its address conflict.
      address=56'h81234560; offset=12'h560; push=1; tick(); push=0; #1;
      check(no_pending && !empty && conflict,"pre-flush speculative state");
      flush=1; tick(); flush=0; #1;
      check(no_pending && empty && !conflict,"flush left stale conflict");
      transactions++;
    end
    $display("SCALAR_STORE_MAPPED_PASS transactions=%0d checks=%0d",transactions,checks);
    $finish;
  end
  initial begin #100000; $fatal(1,"STORE_MAPPED_FAIL watchdog"); end
endmodule
