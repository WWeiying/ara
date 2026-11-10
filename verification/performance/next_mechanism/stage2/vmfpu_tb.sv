// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module stage2_vmfpu_tb;
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
  logic native_result_valid, native_grant = 0;
  logic [63:0] native_result;
  vid_t native_id;
  logic [7:0] native_be;
  logic [4:0] flags;
  logic flags_valid, saturated;
  logic lease = 0, borrow_valid = 0, owned, borrow_ready, borrow_result_valid;
  logic [15:0] weight = 0;
  logic [63:0] activation = 0;
  logic signed [16:0] pair_result [4];
  logic [63:0] native_expected;
  int native_written = 0, native_cases = 0;
  int borrowed = 0, returned = 0, cancelled = 0, collisions = 0;
  int acquisitions = 0, releases = 0;
  logic [2:0] expected_valid = 0;
  logic signed [16:0] expected_pair [3][4];
  int cycles = 0;

  vmfpu #(.NrLanes(4), .VLEN(VLEN), .CVA6Cfg(Config),
      .FPUSupport(FPUSupportNone), .FPExtSupport(FPExtSupportDisable),
      .EnableQbsLaneMul(1'b1), .EnableResidentPv(1'b0),
      .vaddr_t(vaddr_t), .vfu_operation_t(operation_t)) dut (
    .clk_i(clk), .rst_ni(rst), .lane_id_i(2'b00),
    .mfpu_vxsat_o(saturated), .mfpu_vxrm_i('0),
    .fflags_ex_o(flags), .fflags_ex_valid_o(flags_valid),
    .vfu_operation_i(operation), .vfu_operation_valid_i(operation_valid),
    .mfpu_ready_o(native_ready), .mfpu_vinsn_done_o(native_done),
    .fpu_red_complete_o(), .reduction_any_active_o(), .reduction_global_any_active_i(1'b0),
    .mfpu_operand_i(operands), .mfpu_operand_valid_i(operand_valid),
    .mfpu_operand_ready_o(operand_ready),
    .mfpu_result_req_o(native_result_valid), .mfpu_result_id_o(native_id),
    .mfpu_result_addr_o(), .mfpu_result_wdata_o(native_result),
    .mfpu_result_be_o(native_be), .mfpu_result_gnt_i(native_grant),
    .mfpu_red_valid_o(), .mfpu_red_ready_i(1'b0), .sldu_operand_i('0),
    .sldu_mfpu_valid_i(1'b0), .sldu_mfpu_ready_o(),
    .mask_operand_o(), .mask_operand_valid_o(), .mask_operand_ready_i(1'b1),
    .mask_i(8'hff), .mask_valid_i(1'b0), .mask_ready_o(),
    .resident_acquire_i(1'b0), .resident_acquire_ready_o(), .resident_owned_o(),
    .resident_release_i(1'b0), .resident_release_ready_o(),
    .resident_valid_i(1'b0), .resident_ready_o(), .resident_operands_i('0),
    .resident_tag_i('0), .resident_mask_i('0), .resident_rm_i('0),
    .resident_result_valid_o(), .resident_result_ready_i(1'b0),
    .resident_result_o(), .resident_result_tag_o(), .resident_result_flags_o(),
    .qbs_mul_lease_i(lease), .qbs_mul_valid_i(borrow_valid),
    .qbs_mul_weight_i(weight), .qbs_mul_activation_i(activation),
    .qbs_mul_owned_o(owned), .qbs_mul_ready_o(borrow_ready),
    .qbs_mul_result_valid_o(borrow_result_valid), .qbs_mul_result_pair_o(pair_result)
  );

  function automatic logic [63:0] expected_native(
      input logic [63:0] a, b, input int sew, input bit high_half);
    logic [63:0] value, element_mask;
    logic signed [127:0] av, bv, product;
    int width;
    width = 8 << sew;
    element_mask = 64'hffffffffffffffff >> (64-width);
    value = '0;
    for (int e = 0; e < 64/width; e++) begin
      av = 128'((a >> (e*width)) & element_mask);
      bv = 128'((b >> (e*width)) & element_mask);
      if (high_half && av[width-1]) av -= 128'sd1 << width;
      if (high_half && bv[width-1]) bv -= 128'sd1 << width;
      product = av * bv;
      value |= (64'(high_half ? product >>> width : product) & element_mask) << (e*width);
    end
    return value;
  endfunction

  always @(posedge clk) begin
    if (!rst) begin
      for (int s = 0; s < 3; s++) begin
        if (s < 2 && expected_valid[s]) cancelled++;
        for (int c = 0; c < 4; c++) expected_pair[s][c] <= '0;
      end
      expected_valid <= '0;
    end else begin
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
      if (native_result_valid && native_grant) begin
        if (native_result !== native_expected || native_be !== 8'hff || native_id !== operation.id)
          $fatal(1, "Native result mismatch sew=%0d got=%h expected=%h be=%h",
              operation.vtype.vsew, native_result, native_expected, native_be);
        native_written++;
      end
      if (owned && (native_ready || native_result_valid || |operand_ready || |native_done))
        $fatal(1, "Native interface active during QBS ownership");
      if (flags_valid || saturated)
        $fatal(1, "Integer borrowing leaked architectural exception flags");
    end
    #1;
    if (borrow_result_valid !== expected_valid[2])
      $fatal(1, "Borrowed product latency/valid mismatch cycle=%0d", cycles);
    if (borrow_result_valid) begin
      for (int c = 0; c < 4; c++)
        if (pair_result[c] !== expected_pair[2][c])
          $fatal(1, "Borrowed pair mismatch cycle=%0d context=%0d got=%0d expected=%0d",
              cycles, c, pair_result[c], expected_pair[2][c]);
      returned++;
    end
    cycles++;
    if (cycles > 12000) $fatal(1, "Bounded VMFPU test timed out");
  end

  task automatic native_case(input int sew, input bit high_half);
    logic [2:0] pending;
    int initial_writes, age;
    bit done;
    @(negedge clk);
    operation = '0;
    operation.id = vid_t'(native_cases % NrVInsn);
    operation.op = high_half ? VMULH : VMUL;
    operation.vm = 1;
    operation.use_vs1 = 1;
    operation.use_vs2 = 1;
    operation.use_vd = 1;
    operation.vd = 4;
    operation.vfu = VFU_MFpu;
    operation.cvt_resize = CVT_SAME;
    operation.vl = vlen_t'(8 >> sew);
    operation.vtype = '{vill:0, vma:1, vta:1, vsew:vew_e'(sew), vlmul:LMUL_1};
    operands[0] = 64'h807fff010203fe80;
    operands[1] = 64'hff807f02ff0180ff;
    native_expected = expected_native(operands[0], operands[1], sew, high_half);
    operation_valid = 1;
    native_grant = 0;
    pending = 3'b011;
    operand_valid = pending;
    initial_writes = native_written;
    age = 0;
    done = 0;
    do begin @(posedge clk); age++; end while (!native_ready && age < 40);
    if (!native_ready) $fatal(1, "Native request was not accepted");
    @(negedge clk); operation_valid = 0;
    while (!done && age < 400) begin
      @(posedge clk);
      pending &= ~operand_ready;
      done = |native_done;
      age++;
      @(negedge clk);
      operand_valid = pending;
      native_grant = age > 12;
    end
    if (!done || native_written != initial_writes + 1 || pending != 0)
      $fatal(1, "Native request did not complete once sew=%0d age=%0d", sew, age);
    native_cases++;
    operand_valid = 0;
    native_grant = 0;
  endtask

  task automatic borrow_case(input int count, input bit cancel_with_reset);
    int age;
    @(negedge clk);
    lease = 1;
    operation_valid = 1;
    repeat (3) begin
      @(posedge clk); #1;
      if (owned || native_ready || borrow_ready) $fatal(1, "Native offer/acquire collision");
      collisions++;
    end
    @(negedge clk); operation_valid = 0;
    age = 0;
    do begin @(negedge clk); age++; end while (!borrow_ready && age < 12);
    if (!borrow_ready) $fatal(1, "Multiplier lease not acquired");
    acquisitions++;
    for (int i = 0; i < count; i++) begin
      weight = i % 4 == 0 ? 16'h8080 : 16'($urandom());
      activation = i % 4 == 0 ? 64'h8080808080808080 : {$urandom(), $urandom()};
      borrow_valid = i % 5 != 0;
      @(negedge clk);
    end
    if (cancel_with_reset) begin
      rst = 0;
      lease = 0;
      borrow_valid = 0;
      repeat (3) @(negedge clk);
      rst = 1;
    end else begin
      lease = 0;
      borrow_valid = 0;
      age = 0;
      do begin @(negedge clk); age++; end while (owned && age < 12);
      if (owned || borrow_result_valid) $fatal(1, "Multiplier release did not drain");
      releases++;
    end
  endtask

  initial begin
    operation = '0;
    repeat (4) @(negedge clk);
    rst = 1;
    for (int sew = 0; sew < 4; sew++) native_case(sew, 0);
    borrow_case(257, 0);
    for (int sew = 0; sew < 4; sew++) native_case(sew, 1);
    borrow_case(17, 1);
    native_case(0, 0);
    borrow_case(65, 0);
    native_case(3, 1);
    repeat (8) @(negedge clk);
    if (native_cases != 10 || acquisitions != 3 || releases != 2 ||
        borrowed != returned + cancelled || returned < 250 || collisions != 9)
      $fatal(1, "Incomplete VMFPU borrowing coverage or response accounting");
    $display("STAGE2_VMFPU_PASS native=%0d borrowed=%0d returned=%0d cancelled=%0d acquires=%0d releases=%0d collisions=%0d",
        native_cases, borrowed, returned, cancelled, acquisitions, releases, collisions);
    $finish;
  end
endmodule
