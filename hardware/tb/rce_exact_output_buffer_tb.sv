// SPDX-License-Identifier: SHL-0.51
// Focused registered exact-completion boundary test. Fixed-point lane inputs
// encode 1.0 + 2.0 independently (bits 149 and 150), plus a header seed.
module rce_exact_output_buffer_tb;
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
  int simultaneous=0, accepted=0, popped=0;
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
    .exact_lane_consumed_o(),.exact_result_o(result),.exact_result_valid_o(result_valid),
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
  end
  task automatic tick;
    @(posedge clk); #1;
  endtask
  task automatic issue(input int id);
    @(negedge clk);
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
  // A frame ends immediately before seed capture. Exactly two edges remain:
  // seed/root capture, then rounded result capture in the completion buffer.
  task automatic finish_stages(input bit old_result_buffered);
    if (dut.gen_exact.state_q.name() != "EXACT_SEED_ADD")
      $fatal(1,"FAIL: last limb did not enter seed stage");
    if (result_valid !== old_result_buffered)
      $fatal(1,"FAIL: output changed before seed capture");
    tick();
    if (dut.gen_exact.state_q.name() != "EXACT_RESULT")
      $fatal(1,"FAIL: seed stage did not advance on exactly one edge");
    if (result_valid !== old_result_buffered)
      $fatal(1,"FAIL: transparent finalizer output before result capture");
  endtask
  task automatic check_result(input int id,input logic [31:0] value);
    rce_exact_result_t expected;
    expected='{id:vid_t'(id),vd:5'(id+4),version:vreg_version_t'(id+2),
               be:8'h0f,data:value,fflags:5'b0};
    if (!result_valid || result !== expected)
      $fatal(1,"FAIL: result id=%0d expected=%h actual=%h valid=%b",id,expected,result,result_valid);
  endtask
  initial begin
    if (!RceExactDecoupleEnable) $fatal(1,"FAIL: exact decoupling disabled");
    repeat(2) tick(); @(negedge clk); rst_n=1;
    issue(0); frame(0,32'h3f800000); // 1+2+1 = 4
    finish_stages(0);
    tick(); check_result(0,32'h40800000);
    if (!command_ready) $fatal(1,"FAIL: next command blocked by buffered result");
    held=result;
    repeat(4) begin tick(); if (!result_valid || result!==held) $fatal(1,"FAIL: stalled result changed"); end
    issue(1); frame(1,32'h40000000); // 1+2+2 = 5
    finish_stages(1);
    repeat(3) begin tick(); check_result(0,32'h40800000); end
    @(negedge clk); result_ready=1;
    #1; if (!dut.gen_exact.completed_push) $fatal(1,"FAIL: replacement not ready");
    tick(); check_result(1,32'h40a00000);
    @(negedge clk); result_ready=0;
    if (simultaneous!=1 || popped!=1) $fatal(1,"FAIL: pop/push was not simultaneous");
    repeat(3) begin tick(); check_result(1,32'h40a00000); end
    @(negedge clk); result_ready=1;
    tick(); if (result_valid) $fatal(1,"FAIL: consumed slot stayed valid");
    @(negedge clk); result_ready=0;
    issue(2); frame(2,32'h40400000); finish_stages(0); tick(); check_result(2,32'h40c00000);
    @(negedge clk); rst_n=0;
    tick(); if (result_valid || !command_ready) $fatal(1,"FAIL: reset did not clear buffer/owner");
    @(negedge clk); rst_n=1;
    repeat(3) begin tick(); if (result_valid) $fatal(1,"FAIL: reset result reappeared"); end
    issue(3); frame(3,32'h3f800000); finish_stages(0); tick(); check_result(3,32'h40800000);
    @(negedge clk); result_ready=1;
    tick(); tick();
    if (accepted!=4 || popped!=3 || simultaneous!=1 || result_valid)
      $fatal(1,"FAIL: accounting accepted=%0d popped=%0d simultaneous=%0d",accepted,popped,simultaneous);
    $display("RCE_EXACT_OUTPUT_BUFFER_PASS commands=4 popped=3 reset_discard=1 simultaneous=1");
    $finish;
  end
  initial begin #20000; $fatal(1,"FAIL: timeout"); end
endmodule
