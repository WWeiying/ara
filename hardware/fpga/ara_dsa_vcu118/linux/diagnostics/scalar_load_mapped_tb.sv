`timescale 1ns/1ps
// Boundary tests of the load cell exported from the frozen whole-design DCP.
module scalar_load_mapped_tb;
  reg clk=0, rst=0, valid=0, hit=1, conflict=0, grant=0, exception=0;
  reg [43:0] ppn=44'h80000;
  reg [2:0] commit_id=0;
  wire pop, translate, data_req, kill_req, completed, ex_valid;
  wire [2:0] result_id;
  wire request_id;
  reg cache_pending=0, response_id=0;
  always #5 clk=~clk;
  // WT D-cache acknowledges killed requests with rvalid to release the LSU slot.
  always @(posedge clk) begin
    if (!rst) begin cache_pending<=0; response_id<=0; end
    else if (kill_req && cache_pending) cache_pending<=0;
    else if (data_req && grant) begin
      cache_pending<=1;
      response_id<=request_id;
    end
  end
  load_unit dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(1'b0), .valid_i(valid),
    .\lsu_ctrl_i[valid] (valid),
    .\lsu_ctrl_i[vaddr] (64'hffffffd602e10b80),
    .\lsu_ctrl_i[tinst] (32'b0), .\lsu_ctrl_i[hs_ld_st_inst] (1'b0),
    .\lsu_ctrl_i[hlvx_inst] (1'b0), .\lsu_ctrl_i[overflow] (1'b0),
    .\lsu_ctrl_i[g_overflow] (1'b0), .\lsu_ctrl_i[data] (64'b0),
    .\lsu_ctrl_i[be] (8'hff), .\lsu_ctrl_i[fu] (4'd1),
    .\lsu_ctrl_i[operation] (8'd38), .\lsu_ctrl_i[trans_id] (3'd3),
    .pop_ld_o(pop), .valid_o(completed), .trans_id_o(result_id),
    .\ex_o[valid] (ex_valid), .translation_req_o(translate),
    .paddr_i({ppn,12'hb80}), .dtlb_ppn_i(ppn), .dtlb_hit_i(hit),
    .\ex_i[cause] (64'd13), .\ex_i[tval] (64'hffffffd602e10b80),
    .\ex_i[tval2] (41'b0), .\ex_i[tinst] (32'b0),
    .\ex_i[gva] (1'b0), .\ex_i[valid] (exception),
    .page_offset_matches_i(conflict), .store_buffer_empty_i(1'b1),
    .commit_tran_id_i(commit_id), .dcache_wbuffer_not_ni_i(1'b1),
    .\req_port_i[data_gnt] (grant), .\req_port_i[data_rvalid] (kill_req && cache_pending),
    .\req_port_i[data_rid] (response_id), .\req_port_i[data_rdata] (64'b0),
    .\req_port_i[data_ruser] (2'b0), .\req_port_o[data_req] (data_req),
    .\req_port_o[kill_req] (kill_req), .\req_port_o[data_id] (request_id)
  );
  task automatic reset_case;
    @(negedge clk); rst=0; valid=0; hit=1; conflict=0; grant=0;
    exception=0; ppn=44'h80000; commit_id=0;
    repeat(3) @(negedge clk);
    rst=1;
    @(negedge clk);
  endtask
  task automatic expect_exception;
    exception=1; #1;
    if (pop !== 1 || completed !== 1 || ex_valid !== 1 || result_id !== 3)
      $fatal(1,"exception blocked pop=%b complete=%b ex=%b id=%h",pop,completed,ex_valid,result_id);
  endtask
  initial begin
    #201;
    reset_case(); valid=1; grant=1; #1;
    if (pop !== 1 || translate !== 1 || data_req !== 1)
      $fatal(1,"DDR load incorrectly waits for commit");
    $display("PASS DDR load accepts with commit mismatch");

    reset_case(); valid=1;
    repeat(4) begin @(negedge clk); #1;
      if (pop !== 0 || translate !== 1 || data_req !== 1)
        $fatal(1,"cache grant wait protocol");
    end
    expect_exception();
    $display("PASS exception escapes cache grant wait");

    reset_case(); valid=1; conflict=1;
    @(negedge clk); expect_exception();
    $display("PASS exception escapes store conflict wait");

    reset_case(); valid=1; hit=0; grant=1;
    @(negedge clk); grant=0; #1;
    if (kill_req !== 1 || pop !== 0) $fatal(1,"TLB miss did not kill request");
    @(negedge clk); #1;
    if (translate !== 1 || pop !== 0) $fatal(1,"translation wait protocol");
    hit=1;
    @(negedge clk); grant=1; #1;
    if (pop !== 1) $fatal(1,"TLB hit failed to unblock DDR load");
    $display("PASS TLB miss then hit resumes DDR load");

    // Frozen Cheshire peripherals occupy [0, 0x10000000), exclusive upper bound.
    reset_case(); valid=1; ppn=44'h02000; grant=1;
    #1; if (pop !== 0) $fatal(1,"non-idempotent load accepted before commit");
    // Model cache grants only on requests; aborted requests return above.
    repeat(8) begin
      @(negedge clk); grant=0; #1; grant=data_req; #1;
      if (pop !== 0) $fatal(1,"non-idempotent load escaped commit gate");
    end
    commit_id=3;
    begin : release_ni
      bit seen;
      seen=0;
      repeat(8) begin
        @(negedge clk); grant=0; #1; grant=data_req; #1;
        if (pop === 1) begin seen=1; break; end
      end
      if (!seen) $fatal(1,"non-idempotent load did not release at commit");
    end
    $display("PASS non-idempotent commit gate blocks and releases");
    $display("SCALAR_LOAD_MAPPED_PASS cases=5");
    $finish;
  end
  initial begin #100000; $fatal(1,"timeout"); end
endmodule
