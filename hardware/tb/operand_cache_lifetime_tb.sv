// SPDX-License-Identifier: SHL-0.51
// Exercise real requester forwarding at the epoch-wrap lifetime boundary.
module operand_cache_lifetime_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam int VLEN=1024;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [9:0] vaddr_t;
  typedef struct packed {
    vid_t id; // ID of the vector instruction

    logic [4:0] vs; // Vector register operand

    logic scale_vl; // Rescale vl taking into account the new and old EEW

    resize_e cvt_resize;    // Resizing of FP conversions

    logic is_reduct; // Is this a reduction?
    logic is_slide; // Is this a slide?

    rvv_pkg::vew_e eew;        // Effective element width
    opqueue_conversion_e conv; // Type conversion

    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)

    // Vector machine metadata
    rvv_pkg::vtype_t vtype;
    vlen_t vl;
    vlen_t vstart;

    // Hazards
    logic [NrVInsn-1:0] hazard;
    // Architectural register epoch expected by this operand.
    vreg_version_t source_version;
    // Epoch zero is a valid value after wraparound, not an invalid sentinel.
    logic source_version_valid;
  } operand_request_cmd_t;

  typedef struct packed {
    rvv_pkg::vew_e eew;        // Effective element width
    vlen_t elem_count;         // Vector body length
    opqueue_conversion_e conv; // Type conversion
    logic [1:0] ntr_red;       // Neutral type for reductions
    logic is_reduct;           // Is this a reduction?
    target_fu_e target_fu;     // Target FU of the opqueue (if it is not clear)
  } operand_queue_cmd_t;


  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic [NrVInsn-1:0][NrVInsn-1:0] hazards='0;
  operand_request_cmd_t [NrOperandQueues-1:0] requests='0;
  logic [NrOperandQueues-1:0] request_valid='0, request_ready, issued, forward_valid;
  elen_t [NrOperandQueues-1:0] forward_data;
  logic [7:0] vrf_req, vrf_wen;
  logic alu_req=0, alu_reduction=0, alu_grant;
  vid_t alu_id=0;
  vreg_version_t alu_version=0;
  elen_t alu_data=32;
  vaddr_t addr;
  assign addr=vaddr(2,4,VLEN);
  operand_requester #(.NrLanes(4), .VLEN(VLEN), .NrBanks(8),
    .vaddr_t(vaddr_t), .operand_request_cmd_t(operand_request_cmd_t),
    .operand_queue_cmd_t(operand_queue_cmd_t)) dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .lane_id_i('0),
    .global_hazard_table_i(hazards),
    .operand_request_i(requests),
    .operand_request_valid_i(request_valid),
    .operand_request_ready_o(request_ready),
    .forwarded_operand_o(forward_data),
    .forwarded_operand_valid_o(forward_valid),
    .lsu_ex_flush_i('0),
    .lsu_ex_flush_o(),
    .vrf_req_o(vrf_req),
    .vrf_addr_o(),
    .vrf_wen_o(vrf_wen),
    .vrf_wdata_o(),
    .vrf_be_o(),
    .vrf_tgt_opqueue_o(),
    .operand_queue_ready_i('1),
    .operand_issued_o(issued),
    .operand_queue_cmd_o(),
    .operand_queue_cmd_valid_o(),
    .alu_result_req_i(alu_req),
    .alu_result_id_i(alu_id),
    .alu_result_version_i(alu_version),
    .alu_result_is_reduction_i(alu_reduction),
    .alu_result_addr_i(addr),
    .alu_result_wdata_i(alu_data),
    .alu_result_be_i(8'h0f),
    .alu_result_gnt_o(alu_grant),
    .mfpu_result_req_i('0),
    .mfpu_result_id_i('0),
    .mfpu_result_version_i('0),
    .mfpu_result_is_reduction_i('0),
    .mfpu_result_addr_i('0),
    .mfpu_result_wdata_i('0),
    .mfpu_result_be_i('0),
    .mfpu_result_gnt_o(),
    .masku_result_req_i('0),
    .masku_result_id_i('0),
    .masku_result_addr_i('0),
    .masku_result_wdata_i('0),
    .masku_result_be_i('0),
    .masku_result_gnt_o(),
    .masku_result_final_gnt_o(),
    .sldu_result_req_i('0),
    .sldu_result_id_i('0),
    .sldu_result_addr_i('0),
    .sldu_result_wdata_i('0),
    .sldu_result_be_i('0),
    .sldu_result_gnt_o(),
    .sldu_result_final_gnt_o(),
    .ldu_result_req_i('0),
    .ldu_result_id_i('0),
    .ldu_result_addr_i('0),
    .ldu_result_wdata_i('0),
    .ldu_result_be_i('0),
    .ldu_result_gnt_o(),
    .ldu_result_final_gnt_o()
  );

  task automatic reset_dut;
    @(negedge clk); rst_n=0; alu_req=0; request_valid='0; hazards='0;
    requests='0;
    repeat(3) @(negedge clk);
    rst_n=1;
  endtask
  task automatic fill_cache;
    @(negedge clk); alu_req=1; alu_reduction=1; alu_id=0; alu_version=0; alu_data=32;
    @(posedge clk);
    if(!alu_grant) $fatal(1,"FAIL: initial cache fill not granted");
    @(negedge clk); alu_req=0; alu_reduction=0;
  endtask
  task automatic request_seed(input logic pending);
    requests[AluA]='0;
    requests[AluA].id=7;
    requests[AluA].vs=2;
    requests[AluA].source_version_valid=1;
    requests[AluA].source_version=0;
    requests[AluA].eew=EW32;
    requests[AluA].vtype.vsew=EW32;
    requests[AluA].vl=1;
    requests[AluA].is_reduct=1;
    requests[AluA].target_fu=ALU_SLDU;
    requests[AluA].hazard[6]=pending;
    hazards[7][6]=pending;
    request_valid[AluA]=1;
    @(posedge clk);
    if(!request_ready[AluA]) $fatal(1,"FAIL: requester did not accept seed");
    @(negedge clk); request_valid='0;
  endtask
  task automatic check_age(input int delay_cycles, input logic expect_forward);
    logic read_seen;
    reset_dut();
    fill_cache();
    repeat(delay_cycles) @(negedge clk);
    request_seed(0);
    read_seen=|(vrf_req & ~vrf_wen);
    @(posedge clk); #1;
    if(forward_valid[AluA] != expect_forward || read_seen == expect_forward)
      $fatal(1,"FAIL: age boundary delay=%0d forward=%0b read=%0b",delay_cycles,forward_valid[AluA],read_seen);
    if(expect_forward && forward_data[AluA]!=32)
      $fatal(1,"FAIL: age boundary payload corrupted");
    $display("PASS: cache age delay=%0d forward=%0b",delay_cycles,expect_forward);
  endtask
  initial begin
    #100000;
    $fatal(1,"FAIL: cache lifetime watchdog");
  end
  initial begin
    reset_dut();
    fill_cache();
    request_seed(0);
    @(posedge clk); #1;
    if(!forward_valid[AluA] || forward_data[AluA]!=32)
      $fatal(1,"FAIL: fresh cache forwarding was disabled");
    $display("PASS: fresh epoch-zero cached seed");
    reset_dut();
    fill_cache();
    // At producer grant, seven younger writes may already have epochs.
    // Retire one normal write/cycle, with seven newer writes in flight.
    // After 249 more issues the issue epoch may wrap to zero, while the last
    // issued write still owns a RAW hazard. Grant tags advance only to 249.
    // This tests the interface's one-issue/cycle bound, not CVA6 throughput.
    for(int i=1;i<=249;i++) begin
      alu_req=1; alu_reduction=0; alu_version=vreg_version_t'(i);
      alu_id=vid_t'(i%7); alu_data=7;
      @(posedge clk);
      if(!alu_grant) $fatal(1,"FAIL: normal write was not granted");
      @(negedge clk);
    end
    alu_req=0;
    repeat(2) @(negedge clk);
    request_seed(1);
    @(posedge clk); #1;
    if(forward_valid[AluA])
      $fatal(1,"FAIL: wrapped epoch forwarded old payload %0d while new producer pending",forward_data[AluA]);
    if(issued[AluA]) $fatal(1,"FAIL: pending new producer did not block read");
    @(negedge clk); alu_req=1; alu_version=0; alu_id=6; alu_data=7;
    @(posedge clk); if(!alu_grant) $fatal(1,"FAIL: final writer not granted");
    @(negedge clk); alu_req=0; hazards='0;
    @(posedge clk);
    if(!issued[AluA] || !(|(vrf_req & ~vrf_wen)))
      $fatal(1,"FAIL: expired cache did not fall back to VRF");
    $display("PASS: pending wrapped epoch waits and reads VRF");
    check_age(0,1);
    check_age(1,1);
    check_age(244,1);
    check_age(245,1);
    check_age(246,0);
    check_age(247,0);
    check_age(254,0);
    $display("PASS: operand cache lifetime");
    $finish;
  end
endmodule
