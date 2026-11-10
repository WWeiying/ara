// SPDX-License-Identifier: Apache-2.0
`timescale 1ns/1ps
module resident_qk_fpu_tb;
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
  int cycle = 0;
  always @(posedge clk) cycle <= cycle + 1;
  int cid, mode, elements, heads, iterations, rm, action;
  int ns, np, nf, nw, expected_flags;
  logic cmd_valid = 0, cmd_ready, abort_command = 0;
  logic seed_valid = 0, seed_ready, stream_valid = 0, stream_ready, stream_kind = 0;
  logic [63:0] seed_data = 0, stream_data = 0;
  logic fvalid, fready, freturn_valid, freturn_ready;
  logic [2:0][63:0] operands;
  logic [3:0] tag, mask, returned_tag;
  logic [2:0] frm;
  logic ctrl_fp32;
  logic [63:0] returned_data;
  logic [4:0] returned_flags;
  logic result_valid, result_ready, done_valid, done_ready = 0, done_error, busy;
  logic [63:0] result_data;
  logic [3:0] result_slot;
  logic [7:0] result_be;
  logic [4:0] done_flags;
  logic acquire = 0, acquire_ready, owned, release_owner = 0, release_ready, format32 = 0;
  logic private_ready, private_valid, private_return_valid, private_return_ready;
  logic issue_allow, return_allow, write_enable = 0;
  logic native_ready, native_result, native_flags_valid;
  logic [NrVInsn-1:0] native_done;
  logic [4:0] native_flags;
  logic [2:0] native_operand_ready;
  logic qbs_lease = 0, qbs_valid = 0, qbs_owned, qbs_ready, qbs_return_valid;
  logic signed [16:0] qbs_pair [4];
  logic [63:0] seed_words [16], packet_data [1024];
  int seed_slots [16], packet_kind [1024];
  typedef struct packed {
    logic [3:0] slot, mask;
    logic [63:0] a, b, c, value;
    logic [4:0] flags;
  } expected_fma_t;
  expected_fma_t expected_fma [4096], pending_fma [16];
  logic [63:0] expected_write [16];
  int write_slots [16], write_be [16];
  logic [15:0] pending = 0;
  bit checking = 0;
  int issued = 0, returned = 0, written = 0, accepted_flags = 0;
  int stalled_returns = 0, prestart_cycles = 0, qbs_issued = 0, qbs_returned = 0;
  int qbs_before, qbs_return_before, cancelled, cancelled_total = 0;
  int cases_done = 0, inactive_done = 0, aborts_done = 0, resets_done = 0;
  logic [63:0] held_return_data;
  logic [8:0] held_return_meta;
  bit held_return = 0;

  assign issue_allow = cycle % 7 != 1;
  assign return_allow = cycle % 11 >= 3;
  assign private_valid = fvalid && issue_allow;
  assign fready = private_ready && issue_allow;
  assign freturn_valid = private_return_valid && return_allow;
  assign private_return_ready = freturn_ready && return_allow;
  assign result_ready = write_enable && cycle % 5 != 2;

  akv_resident_pv_lane controller (
    .clk_i(clk), .rst_ni(rst), .abort_i(abort_command),
    .cmd_valid_i(cmd_valid), .cmd_ready_o(cmd_ready), .cmd_elements_i(6'(elements)),
    .cmd_two_heads_i(heads == 2), .cmd_tokens_i(7'(iterations)), .cmd_rm_i(3'(rm)),
    .cmd_qk_i(mode == 1), .cmd_dimensions_i(8'(iterations)), .fpu_fp32_o(ctrl_fp32),
    .seed_valid_i(seed_valid), .seed_ready_o(seed_ready), .seed_data_i(seed_data),
    .stream_valid_i(stream_valid), .stream_ready_o(stream_ready),
    .stream_is_value_i(stream_kind), .stream_data_i(stream_data),
    .fpu_valid_o(fvalid), .fpu_ready_i(fready), .fpu_operands_o(operands),
    .fpu_tag_o(tag), .fpu_mask_o(mask), .fpu_rm_o(frm),
    .fpu_result_valid_i(freturn_valid), .fpu_result_ready_o(freturn_ready),
    .fpu_result_i(returned_data), .fpu_result_tag_i(returned_tag), .fpu_result_flags_i(returned_flags),
    .result_valid_o(result_valid), .result_ready_i(result_ready), .result_data_o(result_data),
    .result_slot_o(result_slot), .result_be_o(result_be),
    .done_valid_o(done_valid), .done_ready_i(done_ready), .done_error_o(done_error),
    .done_flags_o(done_flags), .busy_o(busy)
  );

  vmfpu #(.NrLanes(4), .VLEN(VLEN), .CVA6Cfg(Config), .SharedFma(1'b0),
      .FPUSupport(FPUSupportHalfSingleDouble), .FPExtSupport(FPExtSupportEnable),
      .EnableResidentPv(1'b1), .EnableQbsLaneMul(1'b1),
      .vaddr_t(vaddr_t), .vfu_operation_t(operation_t)) dut (
    .clk_i(clk), .rst_ni(rst), .lane_id_i(2'b00), .mfpu_vxsat_o(), .mfpu_vxrm_i('0),
    .fflags_ex_o(native_flags), .fflags_ex_valid_o(native_flags_valid),
    .vfu_operation_i(operation_t'('0)), .vfu_operation_valid_i(1'b0),
    .mfpu_ready_o(native_ready), .mfpu_vinsn_done_o(native_done),
    .fpu_red_complete_o(), .reduction_any_active_o(), .reduction_global_any_active_i(1'b0),
    .mfpu_operand_i('0), .mfpu_operand_valid_i('0), .mfpu_operand_ready_o(native_operand_ready),
    .mfpu_result_req_o(native_result), .mfpu_result_id_o(), .mfpu_result_addr_o(),
    .mfpu_result_wdata_o(), .mfpu_result_be_o(), .mfpu_result_gnt_i(1'b0),
    .mfpu_red_valid_o(), .mfpu_red_ready_i(1'b0), .sldu_operand_i('0),
    .sldu_mfpu_valid_i(1'b0), .sldu_mfpu_ready_o(), .mask_operand_o(), .mask_operand_valid_o(),
    .mask_operand_ready_i(1'b1), .mask_i('1), .mask_valid_i(1'b0), .mask_ready_o(),
    .resident_acquire_i(acquire), .resident_acquire_ready_o(acquire_ready), .resident_owned_o(owned),
    .resident_release_i(release_owner), .resident_release_ready_o(release_ready),
    .resident_valid_i(private_valid), .resident_ready_o(private_ready),
    .resident_operands_i(operands), .resident_tag_i(tag), .resident_mask_i(mask), .resident_rm_i(frm),
    .resident_fp32_i(format32), .resident_result_valid_o(private_return_valid),
    .resident_result_ready_i(private_return_ready), .resident_result_o(returned_data),
    .resident_result_tag_o(returned_tag), .resident_result_flags_o(returned_flags),
    .qbs_mul_lease_i(qbs_lease), .qbs_mul_valid_i(qbs_valid),
    .qbs_mul_weight_i(16'h807f), .qbs_mul_activation_i(64'h04030201fffe807f),
    .qbs_mul_owned_o(qbs_owned), .qbs_mul_ready_o(qbs_ready),
    .qbs_mul_result_valid_o(qbs_return_valid), .qbs_mul_result_pair_o(qbs_pair)
  );

  function automatic logic [63:0] element_bits(input logic [3:0] m, input bit fp32);
    logic [63:0] bits_value;
    bits_value = '0;
    if (fp32) begin
      for (int e = 0; e < 2; e++) if (m[e]) bits_value[32*e+:32] = '1;
    end else begin
      for (int e = 0; e < 4; e++) if (m[e]) bits_value[16*e+:16] = '1;
    end
    return bits_value;
  endfunction

  always @(posedge clk) begin
    if (cycle > 250000) $fatal(1, "QKFPU bounded watchdog");
    if (rst) begin
      if (owned && (qbs_owned || native_ready || native_result || native_flags_valid ||
                    |native_done || |native_operand_ready))
        $fatal(1, "QKFPU native/QBS interface overlapped resident ownership");
      if (held_return && ({returned_flags, returned_tag} !== held_return_meta ||
                          returned_data !== held_return_data || !private_return_valid))
        $fatal(1, "QKFPU stalled private result changed");
      held_return = private_return_valid && !private_return_ready;
      held_return_meta = {returned_flags, returned_tag};
      held_return_data = returned_data;
      if (held_return) stalled_returns++;
      if (checking) begin
        if (private_valid && private_ready) begin
          if (issued >= nf || pending[tag] || ctrl_fp32 !== format32 ||
              {tag, mask, operands[0], operands[1], operands[2]} !==
              {expected_fma[issued].slot, expected_fma[issued].mask,
               expected_fma[issued].a, expected_fma[issued].b, expected_fma[issued].c})
            $fatal(1, "QKFPU input/order mismatch case=%0d seq=%0d tag=%0d mask=%h", cid, issued, tag, mask);
          pending_fma[tag] = expected_fma[issued];
          pending[tag] = 1;
          issued++;
        end
        if (private_return_valid && private_return_ready) begin
          if (!pending[returned_tag] || returned_flags !== pending_fma[returned_tag].flags ||
              ((returned_data ^ pending_fma[returned_tag].value) &
               element_bits(pending_fma[returned_tag].mask, format32)) !== 0)
            $fatal(1, "QKFPU SoftFloat result/flags mismatch case=%0d tag=%0d got=%h flags=%h expected=%h/%h",
                   cid, returned_tag, returned_data, returned_flags,
                   pending_fma[returned_tag].value, pending_fma[returned_tag].flags);
          pending[returned_tag] = 0;
          accepted_flags |= int'(returned_flags);
          returned++;
        end
        if (result_valid && result_ready) begin
          logic [63:0] keep;
          keep = '0;
          for (int b = 0; b < 8; b++) if (result_be[b]) keep[8*b+:8] = '1;
          if (written >= nw || result_slot != write_slots[written] || result_be != 8'(write_be[written]) ||
              ((result_data ^ expected_write[written]) & keep) !== 0)
            $fatal(1, "QKFPU commit bits/slot/BE mismatch case=%0d word=%0d", cid, written);
          written++;
        end
      end
      if (qbs_valid && qbs_ready) qbs_issued++;
      if (qbs_return_valid) begin
        for (int c = 0; c < 4; c++) begin
          logic [63:0] a;
          int expected_pair;
          a = 64'h04030201fffe807f;
          expected_pair = 127 * int'($signed(a[16*c+:8])) - 128 * int'($signed(a[16*c+8+:8]));
          if (qbs_pair[c] !== 17'(expected_pair)) $fatal(1, "QKFPU post-owner actual multiplier mismatch");
        end
        qbs_returned++;
      end
    end else held_return = 0;
  end

  task automatic wait_owner;
    int age;
    @(negedge clk); format32 = mode == 1; acquire = 1; qbs_lease = 1;
    age = 0;
    do begin @(negedge clk); age++; end while (!owned && age < 100);
    if (!owned || qbs_owned) $fatal(1, "QKFPU simultaneous acquisition failed");
    acquire = 0;
    repeat (7) begin
      @(negedge clk);
      if (!owned || qbs_owned || fvalid || private_return_valid || busy)
        $fatal(1, "QKFPU pre-start/inactive owner was not idle");
      prestart_cycles++;
    end
  endtask

  task automatic release_and_borrow;
    int age;
    @(negedge clk); release_owner = 1;
    age = 0;
    do begin @(negedge clk); age++; end while (owned && age < 100);
    if (owned || pending != 0 || private_return_valid) $fatal(1, "QKFPU release before drain");
    release_owner = 0;
    age = 0;
    do begin @(negedge clk); age++; end while (!qbs_ready && age < 100);
    if (!qbs_owned || !qbs_ready) $fatal(1, "QKFPU pending QBS lease made no progress");
    qbs_before = qbs_issued; qbs_return_before = qbs_returned;
    qbs_valid = 1;
    @(negedge clk); qbs_valid = 0;
    age = 0;
    do begin @(negedge clk); age++; end while (qbs_returned == qbs_return_before && age < 20);
    if (qbs_issued != qbs_before + 1 || qbs_returned != qbs_return_before + 1)
      $fatal(1, "QKFPU borrowed work did not return once");
    qbs_lease = 0;
    age = 0;
    do begin @(negedge clk); age++; end while (qbs_owned && age < 20);
    if (qbs_owned) $fatal(1, "QKFPU borrowed owner did not release");
  endtask

  task automatic run_case;
    int si, pi, age;
    checking = 1; issued = 0; returned = 0; written = 0; accepted_flags = 0; pending = 0;
    wait_owner();
    if (elements == 0) begin
      if (ns || np || nf || nw) $fatal(1, "QKFPU inactive vector contains work");
      inactive_done++;
      release_and_borrow();
    end else begin
      @(negedge clk); cmd_valid = 1;
      if (!cmd_ready) $fatal(1, "QKFPU controller not ready after acquisition");
      @(negedge clk); cmd_valid = 0;
      si = 0; pi = 0; age = 0;
      while (!done_valid && age < 30000) begin
        if (si < ns) begin seed_valid = 1; seed_data = seed_words[si]; end
        else seed_valid = 0;
        if (pi < np) begin stream_valid = 1; stream_kind = 1'(packet_kind[pi]); stream_data = packet_data[pi]; end
        else stream_valid = 0;
        write_enable = 1;
        if (action != 0 && issued >= 7 && pending != 0) begin
          if (action == 1) abort_command = 1;
          else begin
            cancelled = $countones(pending); cancelled_total += cancelled;
            if (written != 0) $fatal(1, "QKFPU reset followed commit");
            checking = 0; rst = 0; seed_valid = 0; stream_valid = 0;
            qbs_lease = 0; acquire = 0; pending = 0;
            repeat (3) @(negedge clk);
            rst = 1;
            repeat (3) @(negedge clk);
            if (owned || busy || private_return_valid || result_valid || !cmd_ready)
              $fatal(1, "QKFPU reset leaked old private work");
            resets_done++;
            break;
          end
        end
        @(posedge clk);
        if (seed_valid && seed_ready) si++;
        if (stream_valid && stream_ready) pi++;
        @(negedge clk); age++;
      end
      seed_valid = 0; stream_valid = 0; write_enable = 0;
      if (action != 2) begin
        if (!done_valid || done_error !== (action == 1) || pending != 0 || issued != returned ||
            done_flags !== 5'(accepted_flags) || (action == 0 &&
            (issued != nf || written != nw || accepted_flags != expected_flags)) ||
            (action == 1 && (issued == 0 || written != 0)))
          $fatal(1, "QKFPU terminal work/flags/drain mismatch case=%0d issue=%0d return=%0d writes=%0d flags=%0d", cid, issued, returned, written, done_flags);
        if (action == 1) aborts_done++;
        repeat (5) begin
          @(negedge clk);
          if (!owned || !done_valid || private_return_valid || qbs_owned)
            $fatal(1, "QKFPU terminal did not retain ownership");
        end
        done_ready = 1;
        @(negedge clk); done_ready = 0; abort_command = 0;
        release_and_borrow();
      end
    end
    checking = 0; cases_done++;
    $display("QKFPU_CASE id=%0d mode=%0d elements=%0d heads=%0d iterations=%0d rm=%0d action=%0d issued=%0d returned=%0d writes=%0d flags=%0d cancelled=%0d",
             cid, mode, elements, heads, iterations, rm, action, issued, returned, written, accepted_flags,
             action == 2 ? cancelled : 0);
  endtask

  initial begin : vectors
    string path, token;
    int f, rc, slot_value, mask_value, flag_value;
    logic [63:0] a, b, c, value;
    if (!$value$plusargs("VECTOR=%s", path)) $fatal(1, "QKFPU missing vectors");
    f = $fopen(path, "r"); if (!f) $fatal(1, "QKFPU cannot open vectors");
    rc = $fscanf(f, "%s", token); if (rc != 1 || token != "QKFPU1") $fatal(1, "QKFPU bad schema");
    repeat (4) @(negedge clk); rst = 1;
    while (1) begin
      rc = $fscanf(f, "%s", token); if (rc != 1) $fatal(1, "QKFPU truncated vector");
      if (token == "END") break;
      if (token != "C") $fatal(1, "QKFPU expected case");
      rc = $fscanf(f, "%d %d %d %d %d %d %d %d %d %d %d %d", cid, mode, elements, heads,
                  iterations, rm, action, ns, np, nf, nw, expected_flags);
      if (rc != 12 || cid != cases_done || ns > 16 || np > 1024 || nf > 4096 || nw > 16)
        $fatal(1, "QKFPU malformed case");
      for (int i = 0; i < ns; i++) begin
        rc = $fscanf(f, "%s %d %h", token, seed_slots[i], seed_words[i]);
        if (rc != 3 || token != "S") $fatal(1, "QKFPU malformed seed");
      end
      for (int i = 0; i < np; i++) begin
        rc = $fscanf(f, "%s %d %h", token, packet_kind[i], packet_data[i]);
        if (rc != 3 || token != "P") $fatal(1, "QKFPU malformed packet");
      end
      for (int i = 0; i < nf; i++) begin
        rc = $fscanf(f, "%s %d %h %h %h %h %h %d", token, slot_value, mask_value, a, b, c, value, flag_value);
        if (rc != 8 || token != "F") $fatal(1, "QKFPU malformed FMA");
        expected_fma[i] = '{4'(slot_value), 4'(mask_value), a, b, c, value, 5'(flag_value)};
      end
      for (int i = 0; i < nw; i++) begin
        rc = $fscanf(f, "%s %d %h %h", token, write_slots[i], write_be[i], expected_write[i]);
        if (rc != 4 || token != "W") $fatal(1, "QKFPU malformed output");
      end
      rc = $fscanf(f, "%s", token); if (rc != 1 || token != "E") $fatal(1, "QKFPU missing case end");
      run_case();
    end
    $fclose(f);
    if (cases_done != 26 || inactive_done != 2 || aborts_done != 1 || resets_done != 1 ||
        prestart_cycles != 26 * 7 || qbs_issued != 25 || qbs_returned != qbs_issued ||
        cancelled_total == 0 || stalled_returns == 0)
      $fatal(1, "QKFPU incomplete focused coverage");
    $display("QKFPU_PASS cases=%0d inactive=%0d aborts=%0d resets=%0d prestart=%0d qbs_issued=%0d qbs_returned=%0d reset_cancelled=%0d return_stalls=%0d scope=controller_vmfpu_not_soc",
             cases_done, inactive_done, aborts_done, resets_done, prestart_cycles,
             qbs_issued, qbs_returned, cancelled_total, stalled_returns);
    $finish;
  end
endmodule
