// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module stage2_vmfpu_fp_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  localparam int VLEN = 1024;
  localparam config_pkg::cva6_cfg_t Config =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [9:0] vaddr_t;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef struct packed {
    vid_t id;
    ara_op_e op;
    logic vm, use_vs1, use_vs2, use_vd_op, preserve_narrow_vd;
    elen_t scalar_op;
    logic use_scalar_op, skip_sldu_operand;
    vfu_e vfu;
    logic [4:0] vd;
    logic use_vd, swap_vs2_vd_op;
    roundmode_e fp_rm;
    logic wide_fp_imm;
    resize_e cvt_resize;
    vlen_t vl, vstart;
    vtype_t vtype;
  } operation_t;
  logic clk = 0, rst = 0;
  always #5 clk = ~clk;
  operation_t operation;
  logic operation_valid = 0, native_ready;
  logic [2:0][63:0] operands = '0;
  logic [2:0] operand_valid = 0, operand_ready;
  logic [NrVInsn-1:0] native_done;
  logic native_result_valid, native_grant = 0, saturated;
  logic [63:0] native_result;
  vid_t native_id;
  logic [7:0] native_be;
  logic [4:0] flags;
  logic flags_valid, red_valid, red_ready = 0, red_complete;
  logic slide_valid = 0, slide_ready;
  logic [63:0] slide_data = 0;
  logic lease = 0, borrow_valid = 0, owned, borrow_ready, borrow_result_valid;
  logic [15:0] weight = 0;
  logic [63:0] activation = 0;
  logic signed [16:0] pair_result [4];
  logic pv_acquire = 0, pv_acquire_ready, pv_owned;
  logic pv_release = 0, pv_release_ready, pv_valid = 0, pv_ready;
  logic [2:0][63:0] pv_operands = 0;
  logic [3:0] pv_tag = 0, pv_result_tag;
  logic pv_result_valid, pv_result_ready = 0;
  logic [63:0] pv_result;
  logic [4:0] pv_flags;
  logic [63:0] native_expected, pv_expected;
  logic [7:0] expected_be;
  logic [4:0] expected_flags, pv_expected_flags;
  int cycles = 0, native_cases = 0, native_accepts = 0, writes = 0, dones = 0;
  int flag_events = 0, nv_events = 0, grant_stalls = 0, native_held = 0;
  int pv_acquires = 0, pv_releases = 0, pv_returns = 0, pv_held = 0;
  int borrowed = 0, returned = 0, red_tokens = 0, red_completes = 0;
  logic [2:0] expected_valid = 0;
  logic signed [16:0] expected_pair [3][4];

  vmfpu #(.NrLanes(4), .VLEN(VLEN), .CVA6Cfg(Config), .SharedFma(1'b0),
      .FPUSupport(FPUSupportHalfSingleDouble), .FPExtSupport(FPExtSupportEnable),
      .EnableQbsLaneMul(1'b1), .EnableResidentPv(1'b1),
      .vaddr_t(vaddr_t), .vfu_operation_t(operation_t)) dut (
    .clk_i(clk), .rst_ni(rst), .lane_id_i(2'b00),
    .mfpu_vxsat_o(saturated), .mfpu_vxrm_i('0),
    .fflags_ex_o(flags), .fflags_ex_valid_o(flags_valid),
    .vfu_operation_i(operation), .vfu_operation_valid_i(operation_valid),
    .mfpu_ready_o(native_ready), .mfpu_vinsn_done_o(native_done),
    .fpu_red_complete_o(red_complete), .reduction_any_active_o(),
    .reduction_global_any_active_i(1'b1),
    .mfpu_operand_i(operands), .mfpu_operand_valid_i(operand_valid),
    .mfpu_operand_ready_o(operand_ready),
    .mfpu_result_req_o(native_result_valid), .mfpu_result_id_o(native_id),
    .mfpu_result_addr_o(), .mfpu_result_wdata_o(native_result),
    .mfpu_result_be_o(native_be), .mfpu_result_gnt_i(native_grant),
    .mfpu_red_valid_o(red_valid), .mfpu_red_ready_i(red_ready),
    .sldu_operand_i(slide_data), .sldu_mfpu_valid_i(slide_valid),
    .sldu_mfpu_ready_o(slide_ready),
    .mask_operand_o(), .mask_operand_valid_o(), .mask_operand_ready_i(1'b1),
    .mask_i(8'hff), .mask_valid_i(1'b0), .mask_ready_o(),
    .resident_acquire_i(pv_acquire), .resident_acquire_ready_o(pv_acquire_ready),
    .resident_owned_o(pv_owned), .resident_release_i(pv_release),
    .resident_release_ready_o(pv_release_ready),
    .resident_valid_i(pv_valid), .resident_ready_o(pv_ready),
    .resident_operands_i(pv_operands), .resident_tag_i(pv_tag),
    .resident_mask_i(4'hf), .resident_rm_i(3'd0),
    .resident_result_valid_o(pv_result_valid), .resident_result_ready_i(pv_result_ready),
    .resident_result_o(pv_result), .resident_result_tag_o(pv_result_tag),
    .resident_result_flags_o(pv_flags),
    .qbs_mul_lease_i(lease), .qbs_mul_valid_i(borrow_valid),
    .qbs_mul_weight_i(weight), .qbs_mul_activation_i(activation),
    .qbs_mul_owned_o(owned), .qbs_mul_ready_o(borrow_ready),
    .qbs_mul_result_valid_o(borrow_result_valid), .qbs_mul_result_pair_o(pair_result)
  );

  always @(posedge clk) begin
    if (rst) begin
      if (owned && pv_owned) $fatal(1, "Double ownership");
      if (owned && (native_ready || native_result_valid || |operand_ready ||
          |native_done || flags_valid || red_complete || red_valid || pv_result_valid))
        $fatal(1, "Native/PV tail overlapped QBS ownership");
      if (pv_owned && (owned || native_ready || native_result_valid ||
          |operand_ready || |native_done || flags_valid))
        $fatal(1, "Native/QBS overlapped PV ownership");
      if (operation_valid && native_ready) native_accepts++;
      if (operation_valid && !native_ready) native_held++;
      if (pv_acquire && !pv_acquire_ready) pv_held++;
      if (pv_acquire && pv_acquire_ready) pv_acquires++;
      if (pv_release && pv_release_ready) pv_releases++;
      if (native_result_valid && !native_grant) grant_stalls++;
      if (native_result_valid && native_grant) begin
        if ((native_result & (expected_be == 8'h0f ? 64'hffffffff : '1)) !== native_expected ||
            native_be !== expected_be || native_id !== operation.id)
          $fatal(1, "Native bits/id/mask: got=%h expected=%h be=%h", native_result, native_expected, native_be);
        writes++;
      end
      if (|native_done) begin
        if (native_done !== (NrVInsn'(1) << operation.id)) $fatal(1, "Native done identity");
        dones++;
      end
      if (flags_valid) begin
        if (flags !== expected_flags) $fatal(1, "Native flags got=%h expected=%h", flags, expected_flags);
        flag_events++;
        if (flags[4]) nv_events++;
      end
      if (saturated) $fatal(1, "Unexpected saturation");
      if (red_valid && red_ready) red_tokens++;
      if (red_complete) red_completes++;
      if (pv_result_valid && pv_result_ready) begin
        if (pv_result !== pv_expected || pv_flags !== pv_expected_flags || pv_result_tag !== pv_tag)
          $fatal(1, "PV bits/tag/flags got=%h/%h/%h", pv_result, pv_result_tag, pv_flags);
        pv_returns++;
      end
      expected_valid <= {expected_valid[1:0], borrow_valid && borrow_ready};
      for (int s = 1; s < 3; s++)
        for (int c = 0; c < 4; c++) expected_pair[s][c] <= expected_pair[s-1][c];
      if (borrow_valid && borrow_ready) begin
        borrowed++;
        for (int c = 0; c < 4; c++)
          expected_pair[0][c] <=
              int'($signed(weight[7:0])) * int'($signed(activation[16*c +: 8])) +
              int'($signed(weight[15:8])) * int'($signed(activation[16*c+8 +: 8]));
      end
    end else expected_valid <= 0;
    #1;
    if (rst && borrow_result_valid !== expected_valid[2]) $fatal(1, "Borrowed latency/valid");
    if (rst && borrow_result_valid) begin
      for (int c = 0; c < 4; c++)
        if (pair_result[c] !== expected_pair[2][c]) $fatal(1, "Borrowed pair bits");
      returned++;
    end
    cycles++;
    if (cycles > 4000) $fatal(1, "Bounded full-FP arbitration timeout");
  end

  // kind: FMA, sNaN maximum, FP division, ordered reduction, post-borrow multiply.
  task automatic native_case(input int kind, input bit withdraw_lease = 0,
                             input bit request_pv = 0, input bit request_lease = 0);
    logic [2:0] pending;
    int age, held_result, slide_delay, before_writes, before_done, before_flags;
    bit accepted, finished, slide_sent;
    @(negedge clk);
    operation = '0;
    operation.id = vid_t'(native_cases);
    operation.op = VFMACC;
    operation.vm = 1;
    operation.use_vs1 = 1;
    operation.use_vs2 = 1;
    operation.use_vd_op = 1;
    operation.use_vd = 1;
    operation.vd = 4;
    operation.vfu = VFU_MFpu;
    operation.fp_rm = RNE;
    operation.cvt_resize = CVT_SAME;
    operation.vl = 2;
    operation.vtype = '{vill:0, vma:1, vta:1, vsew:EW32, vlmul:LMUL_1};
    operands[0] = {2{32'h3f800000}};
    operands[1] = {2{32'h40000000}};
    operands[2] = {2{32'h40400000}};
    native_expected = {2{32'h40a00000}};
    expected_flags = 0;
    expected_be = 8'hff;
    pending = 3'b111;
    case (kind)
      1: begin
        operation.op = VFMAX;
        operation.use_vd_op = 0;
        operands[1] = {2{32'h7f800001}};
        native_expected = {2{32'h3f800000}};
        expected_flags = 5'b10000;
        pending = 3'b011;
      end
      2: begin
        operation.op = VFDIV;
        operation.use_vd_op = 0;
        operands[0] = {2{32'h40000000}};
        operands[1] = {2{32'h40c00000}};
        native_expected = {2{32'h40400000}};
        pending = 3'b011;
      end
      3: begin
        operation.op = VFREDOSUM;
        operation.use_vd_op = 0;
        operation.swap_vs2_vd_op = 1;
        operation.vl = 1;
        operands[0] = 64'h3f800000;
        operands[2] = 64'h40000000;
        native_expected = 64'h40400000;
        expected_be = 8'h0f;
        pending = 3'b101;
      end
      4: begin
        operation.op = VFMUL;
        operation.use_vd_op = 0;
        operands[0] = {2{32'hbf800000}};
        native_expected = {2{32'hc0000000}};
        pending = 3'b011;
      end
      default: ;
    endcase
    before_writes = writes; before_done = dones; before_flags = flag_events;
    if (request_pv) begin lease = 1; pv_acquire = 1; end
    if (request_lease) lease = 1;
    operation_valid = 1;
    operand_valid = 0;
    native_grant = 0;
    age = 0; accepted = 0; finished = 0; held_result = 0;
    slide_delay = -1; slide_sent = 0;
    while (!finished && age < 500) begin
      @(posedge clk);
      if (operation_valid && native_ready) accepted = 1;
      pending &= ~(operand_ready & operand_valid);
      if (native_result_valid && !native_grant) held_result++;
      if (red_valid && red_ready) begin
        if (slide_delay >= 0 || slide_sent) $fatal(1, "Duplicate reduction token");
        slide_data = native_result;
        slide_delay = 12;
      end
      if (slide_valid && slide_ready) slide_sent = 1;
      finished = |native_done;
      age++;
      @(negedge clk);
      if (accepted) begin operation_valid = 0; operand_valid = pending; end
      if (withdraw_lease && age == 3) lease = 0;
      native_grant = native_result_valid && held_result >= 8;
      red_ready = kind == 3 && age >= 12 && slide_delay < 0;
      if (slide_delay > 0) slide_delay--;
      slide_valid = slide_delay == 0 && !slide_sent;
    end
    operation_valid = 0; operand_valid = 0; native_grant = 0;
    red_ready = 0; slide_valid = 0;
    repeat (8) @(negedge clk);
    if (!accepted || !finished || pending != 0 || writes != before_writes+1 ||
        dones != before_done+1 || flag_events != before_flags+1 || held_result < 8)
      $fatal(1, "Native accounting kind=%0d age=%0d accepted=%0d done=%0d pending=%h writes=%0d flags=%0d",
          kind, age, accepted, finished, pending, writes-before_writes, flag_events-before_flags);
    if (kind == 3 && (!slide_sent || red_tokens != 1 || red_completes != 1))
      $fatal(1, "Ordered reduction/SLDU completion missing");
    native_cases++;
  endtask

  task automatic private_case(input bit nan_case);
    int age;
    logic [72:0] held;
    // acquire remains asserted until the real handshake, including native drain.
    age = 0;
    if (!pv_owned) begin
      do begin @(posedge clk); age++; end while (!pv_acquire_ready && age < 100);
      if (!pv_acquire_ready || owned) $fatal(1, "Held PV acquisition made no progress");
    end
    @(negedge clk); pv_acquire = 0;
    if (!pv_owned) $fatal(1, "Missing PV ownership");
    pv_tag++;
    pv_operands[0] = nan_case ? {4{16'h7c01}} : {4{16'h3c00}};
    pv_operands[1] = {4{16'h4000}};
    pv_operands[2] = {4{16'h4200}};
    pv_expected = nan_case ? {4{16'h7e00}} : {4{16'h4500}};
    pv_expected_flags = nan_case ? 5'b10000 : 0;
    pv_valid = 1;
    age = 0;
    do begin @(posedge clk); age++; end while (!pv_ready && age < 100);
    if (!pv_ready) $fatal(1, "PV FMA not accepted");
    @(negedge clk); pv_valid = 0; pv_release = 1;
    age = 0;
    do begin @(negedge clk); age++; end while (!pv_result_valid && age < 100);
    if (!pv_result_valid) $fatal(1, "PV FMA did not return");
    held = {pv_result, pv_result_tag, pv_flags};
    repeat (10) begin
      @(negedge clk);
      if (!pv_owned || owned || pv_release_ready || !pv_result_valid ||
          {pv_result, pv_result_tag, pv_flags} !== held)
        $fatal(1, "PV release before held result drain");
    end
    pv_result_ready = 1;
    @(posedge clk);
    @(negedge clk); pv_result_ready = 0;
    age = 0;
    do begin @(posedge clk); age++; end while (!pv_release_ready && age < 100);
    if (!pv_release_ready) $fatal(1, "PV release did not drain");
    @(negedge clk); pv_release = 0;
    if (pv_owned) $fatal(1, "PV release handshake lost");
  endtask

  task automatic borrow_batch;
    int age;
    age = 0;
    do begin @(negedge clk); age++; end while (!borrow_ready && age < 100);
    if (!borrow_ready || pv_owned) $fatal(1, "Pending QBS lease made no progress");
    for (int i = 0; i < 8; i++) begin
      weight = i[0] ? 16'h7f80 : 16'h8080;
      activation = i[1] ? 64'hff7f008001fe807f : 64'h8080808080808080;
      borrow_valid = 1;
      @(negedge clk);
    end
    borrow_valid = 0;
  endtask

  initial begin
    operation = '0;
    repeat (4) @(negedge clk);
    rst = 1;
    // All three requests are held: native first, then PV, then QBS.
    native_case(0, 0, 1);
    private_case(0);
    borrow_batch();
    // A native request stays valid across QBS pipeline drain; PV also waits.
    pv_acquire = 1;
    native_case(1, 1);
    private_case(1);
    native_case(2, 0, 0, 1);
    borrow_batch();
    native_case(3, 1);
    @(negedge clk); lease = 1;
    borrow_batch();
    native_case(4, 1);
    repeat (12) @(negedge clk);
    if (native_cases != 5 || native_accepts != 5 || writes != 5 || dones != 5 ||
        flag_events != 5 || nv_events != 1 || grant_stalls < 40 ||
        native_held < 3 || pv_held < 8 || pv_acquires != 2 || pv_releases != 2 ||
        pv_returns != 2 || borrowed != 24 || returned != 24 || red_tokens != 1 ||
        red_completes != 1 || owned || pv_owned)
      $fatal(1, "Incomplete full-FP/PV/borrow coverage");
    $display("STAGE2_VMFPU_FP_PASS native=%0d writes=%0d flags=%0d nv=%0d grant_stalls=%0d native_held=%0d pv_held=%0d pv_acquires=%0d pv_releases=%0d pv_returns=%0d borrowed=%0d returned=%0d red_tokens=%0d red_completes=%0d",
        native_cases, writes, flag_events, nv_events, grant_stalls, native_held, pv_held,
        pv_acquires, pv_releases, pv_returns, borrowed, returned, red_tokens, red_completes);
    $finish;
  end
endmodule
