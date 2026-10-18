// SPDX-License-Identifier: SHL-0.51
// Focused registered exact-completion boundary test. Fixed-point lane inputs
// encode 1.0 + 2.0 independently (bits 149 and 150), plus a header seed.
module rce_exact_handoff_tb;
  import ara_pkg::*;
  import ara_rce_pkg::*;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  rce_exact_command_t command;
  logic command_valid=0, command_ready;
  elen_t [3:0] operand='0;
  logic [3:0] operand_valid='0, operand_ready;
  rce_exact_result_t result, held;
  logic result_valid, result_ready=0;
  int simultaneous=0, accepted=0, popped=0, handoffs=0, triple=0;
  logic [3:0] lane_consumed;
  int folded_paths=0, fallback_paths=0;
  logic was_stalled=0;
  rce_exact_result_t stalled_result;
  reduction_completion_engine #(.EnableExact(1'b1)) dut (
    .clk_i(clk),.rst_ni(rst_n),
    .cmd_i('0),.cmd_valid_i(1'b0),.cmd_ready_o(),
    .partial_i('0),.partial_valid_i('0),.partial_ready_o(),
    .seed_i('0),.seed_valid_i(1'b0),.seed_ready_o(),
    .seed_lifetime_i('0),.external_seed_i('0),.external_seed_valid_i('0),
    .ordinary_seed_i('0),.ordinary_seed_valid_i('0),
    .result_o(),.result_valid_o(),.result_ready_i(1'b0),.occupancy_o(),
    .shared_add_ready_i(1'b0),.shared_add_response_i('0),.shared_add_response_valid_i(1'b0),
    .exact_cmd_i(command),.exact_cmd_valid_i(command_valid),.exact_cmd_ready_o(command_ready),
    .exact_operand_i(operand),.exact_operand_valid_i(operand_valid),.exact_operand_ready_o(operand_ready),
    .exact_seed_ready_i(1'b0),.exact_seed_data_i('0),.exact_local_complete_o(),
    .exact_lane_consumed_o(lane_consumed),.exact_result_o(result),.exact_result_valid_o(result_valid),
    .exact_result_ready_i(result_ready),.exact_events_o()
  );
  always @(posedge clk) begin
    if (!rst_n) was_stalled=0;
    else begin
      if (was_stalled && (!result_valid || result !== stalled_result))
        $fatal(1,"FAIL: result changed across a stalled cycle");
      was_stalled=result_valid && !result_ready;
      stalled_result=result;
    end
  end
  always @(posedge clk) if (rst_n) begin
    if (command_valid && command_ready) accepted++;
    if (result_valid && result_ready) popped++;
    if (dut.gen_exact.completed_push && result_valid && result_ready) simultaneous++;
    if (dut.gen_exact.completed_push && command_valid && command_ready) begin
      handoffs++;
      if (result_valid && result_ready) triple++;
    end
  end
  task automatic tick;
    @(posedge clk); #1;
  endtask
  task automatic issue(input int id, input bit at_root_boundary=0);
    // Folded frames return at the negedge following their root capture;
    // use that low phase so command valid precedes the completion edge.
    if(!at_root_boundary || clk) @(negedge clk);
    command='{id:vid_t'(id),vd:5'(id+4),version:vreg_version_t'(id+2),late_seed:1'b0};
    command_valid=1;
    #1; if (!command_ready) $fatal(1,"FAIL: command not accepted");
    tick();
    @(negedge clk); command_valid=0;
  endtask
  task automatic beat(input elen_t [3:0] words);
    @(negedge clk); operand=words; operand_valid='1;
    @(posedge clk);
    if (operand_ready !== 4'hf) $fatal(1,"FAIL: legal frame not accepted");
    #1;
    @(negedge clk); operand_valid='0;
  endtask
  task automatic frame(input int id,input logic [31:0] seed);
    elen_t [3:0] words;
    for (int lane=0;lane<4;lane++) begin
      words[lane]='0;
      words[lane][31:28]=4'he;
      words[lane][27:26]=2'(lane);
      words[lane][21:20]=lane<2 ? 2'b11 : 2'b00;
      words[lane][13:11]=3'd3;
      words[lane][7:0]=8'(id);
    end
    words[0][17]=1'b1; words[0][63:32]=seed;
    beat(words); beat('0); beat('0);
    words='0;
    words[0]=64'h200000; // 2^149 / 2^128
    words[1]=64'h400000; // 2^150 / 2^128
    beat(words);
  endtask
  // Folding can bypass SEED_ADD, but both paths stop at a registered root
  // before the completed output capture. Never wait an arbitrary extra edge.
  task automatic finish_stages(input bit old_result_buffered);
    if (result_valid !== old_result_buffered)
      $fatal(1,"FAIL: output changed before root capture");
    if (dut.gen_exact.state_q.name()=="EXACT_SEED_ADD") begin
      fallback_paths++;
      if(dut.gen_exact.exact_seed_folded_q) $fatal(1,"FAIL: folded seed entered fallback");
      tick();
    end else if(dut.gen_exact.state_q.name()!="EXACT_RESULT" || !dut.gen_exact.exact_seed_folded_q)
      $fatal(1,"FAIL: frame did not reach registered root");
    if(dut.gen_exact.exact_seed_folded_q) folded_paths++;
    if(dut.gen_exact.state_q.name()!="EXACT_RESULT" || result_valid!==old_result_buffered)
      $fatal(1,"FAIL: transparent result before completion capture");
  endtask
  task automatic check_result(input int id,input logic [31:0] value);
    rce_exact_result_t expected;
    expected='{id:vid_t'(id),vd:5'(id+4),version:vreg_version_t'(id+2),
               be:8'h0f,data:value,fflags:5'b0};
    if (!result_valid || result !== expected)
      $fatal(1,"FAIL: result id=%0d expected=%h actual=%h valid=%b",id,expected,result,result_valid);
  endtask
  task automatic check_owner(input int id);
    if(dut.gen_exact.state_q.name()!="EXACT_RECEIVE" ||
       dut.gen_exact.owner_q !== command || dut.gen_exact.owner_q.id!=vid_t'(id) ||
       dut.gen_exact.exact_root_q!==288'b0 || dut.gen_exact.exact_packet_beat_q!==3'b0 ||
       dut.gen_exact.exact_seed_valid_q || lane_consumed!==4'b0)
      $fatal(1,"FAIL: old/new context isolation failed id=%0d",id);
  endtask
  initial begin
    if (!RceExactDecoupleEnable) $fatal(1,"FAIL: exact decoupling disabled");
    repeat(2) tick(); @(negedge clk); rst_n=1;
    issue(0);frame(0,32'h3f800000);finish_stages(0);
    if(lane_consumed!==4'hf) $fatal(1,"FAIL: finishing owner lanes not consumed");
    // Capture raw owner-zero result while accepting owner one on this edge.
    issue(1,1);check_result(0,32'h40800000);check_owner(1);
    if(handoffs!=1) $fatal(1,"FAIL: first capture and command were not simultaneous");
    frame(1,32'h40000000);finish_stages(1);
    repeat(4) begin
      tick();check_result(0,32'h40800000);
      if(command_ready || dut.gen_exact.completed_push || lane_consumed!==4'hf ||
         dut.gen_exact.owner_q.id!=vid_t'(1))
        $fatal(1,"FAIL: full completion buffer did not retain new raw owner");
    end
    // Pop zero, capture one's raw result, and accept owner two on one edge.
    @(negedge clk);result_ready=1;
    command='{id:vid_t'(2),vd:5'd6,version:vreg_version_t'(4),late_seed:1'b0};
    command_valid=1;
    #1;if(!command_ready || !dut.gen_exact.completed_push)
      $fatal(1,"FAIL: triple transfer not ready");
    check_result(0,32'h40800000);
    tick();check_result(1,32'h40a00000);check_owner(2);
    @(negedge clk);result_ready=0;command_valid=0;
    if(handoffs!=2 || triple!=1 || simultaneous!=1 || popped!=1)
      $fatal(1,"FAIL: triple transfer counters mismatch");
    frame(2,32'h7f7fffff);finish_stages(1);
    repeat(2) begin tick();check_result(1,32'h40a00000);end
    // Reset discards both an old buffered result and the waiting raw owner.
    @(negedge clk);rst_n=0;
    tick();if(result_valid || !command_ready || lane_consumed!==4'b0)
      $fatal(1,"FAIL: reset retained a completion/owner");
    @(negedge clk);rst_n=1;
    repeat(2) begin tick();if(result_valid) $fatal(1,"FAIL: reset completion reappeared");end
    issue(3);check_owner(3);frame(3,32'h3f800000);finish_stages(0);
    tick();check_result(3,32'h40800000);
    @(negedge clk);result_ready=1;
    tick();tick();
    if(accepted!=4 || popped!=2 || handoffs!=2 || triple!=1 || result_valid || folded_paths!=3 || fallback_paths!=1)
      $fatal(1,"FAIL: final transfer accounting mismatch");
    $display("RCE_EXACT_HANDOFF_PASS commands=4 handoffs=2 triple=1 popped=2 reset_discard=2 folded=3 fallback=1");
    $finish;
  end
  initial begin #20000;$fatal(1,"FAIL: handoff timeout");end
endmodule
