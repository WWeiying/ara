`timescale 1ns/1ps
// Two outstanding requests, overlapping return/allocation, and flushed returns.
// Cache/MMU are boundary stimuli, not a whole-cache or board liveness proof.
module scalar_load_slots_mapped_tb;
  reg clk=0, rst=0, valid=0, flush=0, grant=0, rvalid=0, rid=0;
  reg [2:0] id=0;
  reg [63:0] rdata=0;
  wire pop, completed, ex_valid, request, request_id, kill_req;
  wire [2:0] result_id;
  wire [63:0] result;
  reg slot_a, slot_b, slot_c;
  int checks=0;
  always #5 clk=~clk;
  load_unit dut (
    .clk_i(clk), .rst_ni(rst), .flush_i(flush), .valid_i(valid),
    .\lsu_ctrl_i[valid] (valid), .\lsu_ctrl_i[vaddr] (64'hffffffd602e10b80),
    .\lsu_ctrl_i[tinst] (32'b0), .\lsu_ctrl_i[hs_ld_st_inst] (1'b0),
    .\lsu_ctrl_i[hlvx_inst] (1'b0), .\lsu_ctrl_i[overflow] (1'b0),
    .\lsu_ctrl_i[g_overflow] (1'b0), .\lsu_ctrl_i[data] (64'b0),
    .\lsu_ctrl_i[be] (8'hff), .\lsu_ctrl_i[fu] (4'd1),
    .\lsu_ctrl_i[operation] (8'd38), .\lsu_ctrl_i[trans_id] (id),
    .pop_ld_o(pop), .valid_o(completed), .trans_id_o(result_id), .result_o(result),
    .\ex_o[valid] (ex_valid),
    .paddr_i(56'h80000b80), .dtlb_ppn_i(44'h80000), .dtlb_hit_i(1'b1),
    .\ex_i[cause] (64'b0), .\ex_i[tval] (64'b0), .\ex_i[tval2] (41'b0),
    .\ex_i[tinst] (32'b0), .\ex_i[gva] (1'b0), .\ex_i[valid] (1'b0),
    .page_offset_matches_i(1'b0), .store_buffer_empty_i(1'b1),
    .commit_tran_id_i(3'd7), .dcache_wbuffer_not_ni_i(1'b1),
    .\req_port_i[data_gnt] (grant), .\req_port_i[data_rvalid] (rvalid),
    .\req_port_i[data_rid] (rid), .\req_port_i[data_rdata] (rdata),
    .\req_port_i[data_ruser] (2'b0), .\req_port_o[data_req] (request),
    .\req_port_o[kill_req] (kill_req), .\req_port_o[data_id] (request_id)
  );
  task automatic tick;
    @(posedge clk); #1; @(negedge clk);
  endtask
  task automatic check(input logic condition, input string message);
    checks++;
    if(condition !== 1'b1) $fatal(1,"LOAD_SLOTS_FAIL %s",message);
  endtask
  task automatic accept(input logic[2:0] new_id, output logic slot);
    valid=1; grant=1; id=new_id; #1;
    check(pop && request && !kill_req,"new request must be accepted");
    slot=request_id;
    tick(); valid=0; grant=0;
  endtask
  task automatic response(input logic slot, input logic[2:0] expected_id,
                          input logic[63:0] value, input logic canceled);
    rvalid=1; rid=slot; rdata=value; #1;
    check(completed === !canceled,"response validity");
    if(!canceled) begin
      check(result_id === expected_id && result === value && !ex_valid,
            $sformatf("response id=%d expected=%d data=%h expected=%h",
                      result_id,expected_id,result,value));
    end
  endtask
  initial begin
    #201; repeat(3) tick(); rst=1; tick();
    for(int n=0;n<128;n++) begin
      accept(3'(n),slot_a);
      accept(3'(n+1),slot_b);
      check(slot_a != slot_b,"two accepted loads must own different slots");
      tick();
      // Both slots are occupied. A third request must remain unaccepted.
      valid=1; id=3'(n+2); grant=0; #1;
      check(!pop && !request,"full buffer accepted a third load");
      valid=0;
      response(slot_a,3'(n),64'h0123456789abcdef ^ 64'(n),0);
      tick(); rvalid=0;
      // Reuse A while the old B response arrives on the same edge.
      response(slot_b,3'(n+1),64'hfedcba9876543210 ^ 64'(n),0);
      accept(3'(n+2),slot_c); rvalid=0;
      check(slot_c == slot_a,"freed slot was not reused");
      tick();
      response(slot_c,3'(n+2),64'hf00dcafea55a1234 ^ 64'(n),0);
      tick(); rvalid=0; tick();
      accept(3'(n+3),slot_a);
      accept(3'(n+4),slot_b);
      flush=1; tick(); flush=0;
      response(slot_a,3'(n+3),64'h55,1); tick(); rvalid=0;
      response(slot_b,3'(n+4),64'haa,1); tick(); rvalid=0; tick();
    end
    $display("SCALAR_LOAD_SLOTS_MAPPED_PASS requests=640 checks=%0d",checks);
    $finish;
  end
  initial begin #100000; $fatal(1,"LOAD_SLOTS_FAIL watchdog"); end
endmodule
