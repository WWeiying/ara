`timescale 1ns/1ps
module ordered_reduction_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  localparam int N = 4, VLEN = 1024;
  localparam config_pkg::cva6_cfg_t CVA6Cfg =
    build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [15:0] vaddr_t;
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

  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  operation_t [N-1:0] operation;
  logic [N-1:0] request, ready, result_req, result_gnt;
  logic [N-1:0][NrVInsn-1:0] done;
  elen_t [N-1:0][2:0] operands;
  logic [N-1:0][2:0] operand_valid, operand_ready;
  elen_t [N-1:0] result, slide_in;
  logic [N-1:0][7:0] result_be, mask;
  logic [N-1:0] red_valid, red_ready, slide_valid, slide_ready;
  logic [N-1:0] transport_valid, transport_ready;
  elen_t [N-1:0] transport_data;
  logic [N-1:0] mask_valid, mask_ready, flags_valid;
  logic [N-1:0][4:0] flags;
  logic [N-1:0][15:0] result_addr;
  vid_t [N-1:0] result_id;

  // Only aliases are dumped: no recursive multiplier/divider or unrelated RTL.
  logic [N-1:0][3:0] local_index;
  logic [N-1:0][7:0] issue_be, in_tag_mask, out_tag_mask;
  logic [N-1:0] fp_in_valid, fp_in_ready, fp_out_valid, fp_out_ready, selected_active;
  logic [N-1:0][4:0] raw_status, collapsed_status, gated_status;
  elen_t [N-1:0] selected_operand, accumulator, fp_result;
  int cycle = 0, case_id = -1, trace_fd, results_fd, case_count = 0;
  int word_index[N], seed_acks[N], mask_acks[N], done_count[N];
  int accepted[N], fp_accepted[N], fp_completed[N], flag_events[N];
  int vl, sew, elements_per_word, token_count, write_count, start_cycle;
  int captured_tokens;
  int input_mode, selected_count, raw_nv_count, lost_nv_count;
  int link_delay, grant_delay;
  logic [31:0] predicate;
  bit unmasked, running = 0;
  logic [4:0] sticky_flags;
  elen_t observed_result, seed;
  logic [7:0] observed_be;
  logic [N-1:0] done_seen;
  vew_e ew;
  string case_name;

  for (genvar lane = 0; lane < N; lane++) begin : lanes
    // Real SLDU buffers every input before its ordered-token scheduler.
    spill_register #(.T(elen_t)) slide_input_buffer (
      .clk_i(clk), .rst_ni(rst_n), .data_i(result[lane]),
      .valid_i(red_valid[lane]), .ready_o(red_ready[lane]),
      .data_o(transport_data[lane]), .valid_o(transport_valid[lane]),
      .ready_i(transport_ready[lane])
    );
    vmfpu #(.NrLanes(N), .VLEN(VLEN), .CVA6Cfg(CVA6Cfg), .vaddr_t(vaddr_t),
            .vfu_operation_t(operation_t)) dut (
      .clk_i(clk), .rst_ni(rst_n), .lane_id_i(2'(lane)),
      .mfpu_vxsat_o(), .mfpu_vxrm_i('0),
      .fflags_ex_o(flags[lane]), .fflags_ex_valid_o(flags_valid[lane]),
      .vfu_operation_i(operation[lane]), .vfu_operation_valid_i(request[lane]),
      .mfpu_ready_o(ready[lane]), .mfpu_vinsn_done_o(done[lane]),
      .fpu_red_complete_o(), .reduction_any_active_o(), .reduction_global_any_active_i(1'b1),
      .mfpu_operand_i(operands[lane]), .mfpu_operand_valid_i(operand_valid[lane]),
      .mfpu_operand_ready_o(operand_ready[lane]), .mfpu_result_req_o(result_req[lane]),
      .mfpu_result_id_o(result_id[lane]), .mfpu_result_addr_o(result_addr[lane]),
      .mfpu_result_wdata_o(result[lane]), .mfpu_result_be_o(result_be[lane]),
      .mfpu_result_gnt_i(result_gnt[lane]), .mfpu_red_valid_o(red_valid[lane]),
      .mfpu_red_ready_i(red_ready[lane]), .sldu_operand_i(slide_in[lane]),
      .sldu_mfpu_valid_i(slide_valid[lane]), .sldu_mfpu_ready_o(slide_ready[lane]),
      .mask_operand_o(), .mask_operand_valid_o(), .mask_operand_ready_i(1'b1),
      .mask_i(mask[lane]), .mask_valid_i(mask_valid[lane]), .mask_ready_o(mask_ready[lane])
    );
    assign local_index[lane] = dut.osum_issue_cnt_q;
    assign issue_be[lane] = dut.issue_be;
    assign selected_operand[lane] = dut.operand_c;
    assign accumulator[lane] = dut.operand_b;
    assign selected_active[lane] = dut.osum_element_active(dut.osum_issue_cnt_q,
      dut.vinsn_issue_q.vtype.vsew, ~dut.vinsn_issue_q.vm, mask[lane]);
    assign fp_in_valid[lane] = dut.vfpu_in_valid;
    assign fp_in_ready[lane] = dut.vfpu_in_ready;
    assign fp_out_valid[lane] = dut.vfpu_out_valid;
    assign fp_out_ready[lane] = dut.vfpu_out_ready;
    assign in_tag_mask[lane] = dut.vfpu_tag_in.flag_mask;
    assign out_tag_mask[lane] = dut.vfpu_tag_out.flag_mask;
    assign collapsed_status[lane] = dut.vfpu_ex_flag_fn;
    assign gated_status[lane] = dut.vfpu_ex_flag;
    assign fp_result[lane] = dut.vfpu_result;
    wire [4:0] raw32 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[0].active_format.i_fmt_slice.lane_status[0];
    wire [4:0] raw16 = dut.fpu_gen.i_fpnew_bulk.gen_operation_groups[0].i_opgroup_block.gen_parallel_slices[2].active_format.i_fmt_slice.lane_status[0];
    assign raw_status[lane] = sew == 16 ? raw16 : raw32;
  end

  function automatic elen_t input_element(int index);
    if (input_mode == 1) return sew == 16 ? 64'h7c55 : 64'h7f812345;
    if (input_mode == 2) return sew == 16 ? 64'h3c00 : 64'h3f800000;
    if (sew == 16) return index % 2 ? 64'hfc00 : 64'h7c00;
    return index % 2 ? 64'hff800000 : 64'h7f800000;
  endfunction

  // Model the existing striped operand queue layout, not the DUT's selection helper.
  task automatic drive_operands;
    int index, position;
    elen_t value;
    for (int lane = 0; lane < N; lane++) begin
      operands[lane] = '0;
      operands[lane][0] = seed;
      operand_valid[lane] = '0;
      operand_valid[lane][0] = seed_acks[lane] == 0;
      mask[lane] = '0;
      for (int slot = 0; slot < elements_per_word; slot++) begin
        index = (word_index[lane] * elements_per_word + slot) * N + lane;
        value = input_element(index);
        for (int byte_no = 0; byte_no < sew/8; byte_no++) begin
          position = shuffle_index(16'(slot * sew/8 + byte_no), 1, ew);
          operands[lane][2][8*position +: 8] = value[8*byte_no +: 8];
          mask[lane][position] = index < vl && predicate[index % 32];
        end
      end
      operand_valid[lane][2] = word_index[lane] * elements_per_word < (vl + N-1-lane)/N;
      mask_valid[lane] = operand_valid[lane][2];
    end
  endtask

  // External slide transport: exactly one token, in architectural element order.
  // This does not instantiate or test SLDU, MASKU, dispatcher, or VRF.
  always_comb begin
    int source, target;
    transport_ready = '0;
    slide_valid = '0;
    slide_in = '0;
    result_gnt = '0;
    source = token_count % N;
    target = token_count == vl-1 ? 0 : (source+1) % N;
    if (running && token_count < vl && (link_delay == 0 || cycle % 3 != 0)) begin
      slide_in[target] = transport_data[source];
      slide_valid[target] = transport_valid[source];
      transport_ready[source] = slide_ready[target];
    end
    if (running && (grant_delay == 0 || cycle % 5 == 0))
      result_gnt = result_req;
  end

  always @(posedge clk) begin
    cycle <= cycle + 1;
    if (rst_n && running) begin
      for (int lane = 0; lane < N; lane++) begin
        if (request[lane] && ready[lane]) accepted[lane]++;
        if (operand_valid[lane][0] && operand_ready[lane][0]) seed_acks[lane]++;
        if (operand_valid[lane][2] && operand_ready[lane][2]) word_index[lane]++;
        if (mask_valid[lane] && mask_ready[lane]) mask_acks[lane]++;
        if (fp_in_valid[lane] && fp_in_ready[lane]) fp_accepted[lane]++;
        if (fp_out_valid[lane] && fp_out_ready[lane]) begin
          fp_completed[lane]++;
          if (raw_status[lane][4]) raw_nv_count++;
          if (raw_status[lane][4] && !collapsed_status[lane][4]) lost_nv_count++;
        end
        if (flags_valid[lane]) begin
          sticky_flags |= flags[lane];
          flag_events[lane]++;
        end
        if (|done[lane]) begin
          if (done[lane] !== {{(NrVInsn-1){1'b0}}, 1'b1}) $fatal(1, "HARNESS wrong done id");
          done_seen[lane] = 1;
          done_count[lane]++;
        end
        if (result_req[lane] && result_gnt[lane]) begin
          if (lane != 0 || result_id[lane] != 0 || result_addr[lane] != vaddr(24,N,VLEN))
            $fatal(1, "HARNESS wrong architectural write target");
          observed_result = result[lane];
          observed_be = result_be[lane];
          write_count++;
        end
        $fdisplay(trace_fd, "%0d,%0d,%0d,%0d,%02h,%0d,%016h,%016h,%02h,%0d,%0d,%02h,%0d,%0d,%02h,%02h,%02h,%02h,%016h,%0d,%02h,%0d,%0d,%0d",
          case_id, cycle, lane, local_index[lane], mask[lane], selected_active[lane],
          selected_operand[lane], accumulator[lane], issue_be[lane], fp_in_valid[lane],
          fp_in_ready[lane], in_tag_mask[lane], fp_out_valid[lane], fp_out_ready[lane],
          out_tag_mask[lane], raw_status[lane], collapsed_status[lane], gated_status[lane],
          fp_result[lane], flags_valid[lane], flags[lane], transport_valid[lane] && transport_ready[lane],
          result_req[lane] && result_gnt[lane], |done[lane]);
      end
      if (|(transport_valid & transport_ready)) token_count <= token_count + 1;
      captured_tokens += $countones(red_valid & red_ready);
    end
  end

  task automatic run_case(input int id, input string name, input int width, length,
      input logic [31:0] pred, input bit vm, input int rm, prior, mode, stalls,
      input elen_t expected_result, input logic [4:0] expected_flags);
    int steps, expected_words, expected_active;
    bit result_match;
    @(negedge clk);
    rst_n = 0; running = 0; request = '0; operand_valid = '0; mask_valid = '0;
    operation = '0;
    case_id = id; case_name = name; sew = width; vl = length;
    ew = width == 16 ? EW16 : EW32;
    predicate = pred; unmasked = vm; input_mode = mode;
    elements_per_word = 64/width; token_count = 0; write_count = 0;
    captured_tokens = 0;
    raw_nv_count = 0; lost_nv_count = 0; done_seen = 0; selected_count = 0;
    link_delay = stalls; grant_delay = stalls;
    sticky_flags = 5'(prior); observed_result = 'x; observed_be = 'x;
    seed = mode == 2 ? 0 : width == 16 ? 64'h7c00 : 64'h7f800000;
    for (int lane = 0; lane < N; lane++) begin
      word_index[lane] = 0; seed_acks[lane] = 0; mask_acks[lane] = 0;
      done_count[lane] = 0; accepted[lane] = 0; fp_accepted[lane] = 0;
      fp_completed[lane] = 0; flag_events[lane] = 0;
    end
    repeat (4) @(negedge clk);
    rst_n = 1; running = 1; start_cycle = cycle;
    for (int lane = 0; lane < N; lane++) begin
      operation[lane].id = 0;
      operation[lane].op = VFREDOSUM;
      operation[lane].vfu = VFU_MFpu;
      operation[lane].vm = vm;
      operation[lane].use_vs1 = 1;
      operation[lane].use_vs2 = 1;
      operation[lane].swap_vs2_vd_op = 1;
      operation[lane].use_vd = 1;
      operation[lane].vd = 24;
      operation[lane].fp_rm = roundmode_e'(rm);
      operation[lane].vtype.vsew = ew;
      operation[lane].vl = vlen_t'((vl + N-1-lane)/N);
    end
    drive_operands();
    request = '1;
    @(negedge clk);
    request = '0;
    for (steps = 0; steps < 10000 && done_seen != '1; steps++) begin
      drive_operands();
      @(negedge clk);
    end
    if (done_seen != '1) $fatal(1, "HARNESS completion timeout case=%s tokens=%0d", name, token_count);
    repeat (8) begin drive_operands(); @(negedge clk); end
    if (token_count != vl || captured_tokens != vl || |transport_valid || write_count != 1 ||
        observed_be !== (width == 16 ? 8'h03 : 8'h0f))
      $fatal(1, "HARNESS write/token accounting case=%s tokens=%0d writes=%0d be=%h", name, token_count, write_count, observed_be);
    for (int lane = 0; lane < N; lane++) begin
      expected_words = (((vl+N-1-lane)/N) + elements_per_word-1)/elements_per_word;
      expected_active = 0;
      for (int index = lane; index < vl; index += N)
        if (vm || pred[index % 32]) expected_active++;
      selected_count += expected_active;
      if (accepted[lane] != 1 || done_count[lane] != 1 || seed_acks[lane] != 1 ||
          word_index[lane] != expected_words || mask_acks[lane] != (vm ? 0 : expected_words) ||
          fp_accepted[lane] != expected_active || fp_completed[lane] != expected_active ||
          flag_events[lane] != expected_active)
        $fatal(1, "HARNESS lane=%0d case=%s req=%0d done=%0d seed=%0d words=%0d masks=%0d fp=%0d/%0d flags=%0d expected_active=%0d",
          lane, name, accepted[lane], done_count[lane], seed_acks[lane], word_index[lane],
          mask_acks[lane], fp_accepted[lane], fp_completed[lane], flag_events[lane], expected_active);
    end
    result_match = width == 16 ? observed_result[15:0] === expected_result[15:0] :
                                observed_result[31:0] === expected_result[31:0];
    $fdisplay(results_fd, "%0d,%s,%0d,%0d,%08h,%0d,%0d,%0d,%0d,%0d,%016h,%02h,%016h,%02h,%0d,%0d,%0d,%0d,%0d",
      id, name, width, length, pred, vm, rm, prior, mode, stalls,
      observed_result, sticky_flags, expected_result, expected_flags, result_match,
      sticky_flags === expected_flags, cycle-start_cycle, raw_nv_count, lost_nv_count);
    $display("RESULT case=%s result=%016h flags=%02h expected=%016h/%02h match=%0d/%0d cycles=%0d raw_nv=%0d lost_nv=%0d",
      name, observed_result, sticky_flags, expected_result, expected_flags, result_match,
      sticky_flags === expected_flags, cycle-start_cycle, raw_nv_count, lost_nv_count);
    case_count++;
    running = 0;
  endtask

  initial begin
    trace_fd = $fopen("trace.csv", "w");
    results_fd = $fopen("results.csv", "w");
    if (!trace_fd || !results_fd) $fatal(1, "HARNESS cannot open evidence");
    $fdisplay(trace_fd, "case_id,cycle,lane,local_index,mask,active,operand,accumulator,issue_be,in_valid,in_ready,in_tag,out_valid,out_ready,out_tag,raw_status,collapsed_status,gated_status,fp_result,flags_valid,flags,slide_fire,write_fire,done");
    $fdisplay(results_fd, "id,name,sew,vl,mask,vm,rm,prior,mode,stalls,result,flags,expected_result,expected_flags,result_match,flags_match,cycles,raw_nv,lost_nv");
    if ($test$plusargs("FSDB")) begin
      $fsdbDumpfile("ordered_reduction.fsdb");
      $fsdbDumpvars(1, ordered_reduction_tb);
    end
    `include "cases.svh"
    $display("ORDERED_REDUCTION_COMPLETE cases=%0d", case_count);
    $fclose(trace_fd); $fclose(results_fd);
    $finish;
  end
  initial begin #20000000; $fatal(1, "HARNESS global watchdog"); end
endmodule
