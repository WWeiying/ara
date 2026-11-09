// SPDX-License-Identifier: Apache-2.0
// PROTOCOL ONLY. XOR payload signatures are NOT floating-point arithmetic.
module resident_pv_cluster_tb;
  logic clk_i = 0;
  always #5 clk_i = !clk_i;
  logic rst_ni = 0, start_valid_i = 0, start_ready_o;
  logic [3:0] start_active_i = 0, active_o;
  logic [5:0] cmd_elements_i;
  logic cmd_two_heads_i;
  logic [6:0] cmd_tokens_i;
  logic [2:0] cmd_rm_i;
  logic abort_i = 0, abort_rejected_o, busy_o, commit_authorized_o, fatal_error_o;
  logic [3:0] seed_valid_i = 0, seed_ready_o;
  logic [3:0][63:0] seed_data_i;
  logic stream_valid_i = 0, stream_ready_o, stream_is_value_i;
  logic [3:0][63:0] stream_data_i;
  logic [3:0] fpu_valid_o, fpu_ready_i = 0, fpu_result_valid_i = 0, fpu_result_ready_o;
  logic [3:0][2:0][63:0] fpu_operands_o;
  logic [3:0][3:0] fpu_tag_o, fpu_mask_o, fpu_result_tag_i;
  logic [3:0][2:0] fpu_rm_o;
  logic [3:0][63:0] fpu_result_i;
  logic [3:0][4:0] fpu_result_flags_i;
  logic [3:0] result_valid_o, result_ready_i = 0, final_ack_i = 0, ack_rejected_o;
  logic [3:0][63:0] result_data_o;
  logic [3:0][3:0] result_slot_o;
  logic [3:0][7:0] result_be_o;
  logic [3:0][4:0] outstanding_o;
  logic done_valid_o, done_ready_i = 0, done_error_o;
  logic [4:0] done_flags_o;
  akv_resident_pv_cluster dut (.*);

  int id, words, heads, tokens, elements, mode, cyc, packets;
  int seeded[4], delivered[4], issued[4], written[4], acked[4];
  int due[4][16], ack_due[4][16];
  bit pending[4][16];
  logic [63:0] returned[4][16], accum[4][16];
  logic [4:0] returned_flags[4][16], expected_flags;
  bit stalled[4], fpu_stalled[4], lane_finished[4];
  logic [63:0] held_data[4];
  logic [3:0] held_slot[4];
  logic [7:0] held_be[4];
  logic [2:0][63:0] held_ops[4];
  logic [3:0] held_tag[4], held_mask[4];
  bit group_seen, aborted, post_abort, terminal_seen, stream_held;
  logic [4:0] held_flags;
  logic held_error;
  int terminal_cycles, totals_cases = 0, totals_terminals = 0;
  int cov_late = 0, cov_same = 0, cov_excess = 0, cov_stall = 0;
  int cov_cancel = 0, cov_reject = 0, cov_max = 0, cov_pending_cancel = 0;
  int cov_private_skew = 0, cov_done_stall = 0, cov_reset = 0;
  int cov_early = 0, cov_trailing = 0;
  bit negative_pending, negative_flags, negative_complete;

  function automatic logic [63:0] seed(input int l, s);
    return 64'h1020304050607080 ^ (64'(id) << 40) ^ (64'(l) << 24) ^ 64'(s);
  endfunction
  function automatic logic [63:0] packet(input int l, p);
    return 64'h123456789abcdef0 ^ (64'(id) << 44) ^ (64'(l) << 32) ^
           (64'(p) * 64'h0101010101010101);
  endfunction
  function automatic logic [3:0] mask(input int w);
    return (w == words-1 && elements%4 != 0) ? (4'b1111 >> (4-elements%4)) : 4'b1111;
  endfunction
  function automatic logic [63:0] signature(input logic [2:0][63:0] ops, input int l, s);
    return ops[0] ^ ops[1] ^ ops[2] ^ (64'(l+1) << 48) ^ 64'(s);
  endfunction
  task automatic idle_inputs;
    start_valid_i = 0; abort_i = 0; seed_valid_i = 0; stream_valid_i = 0;
    fpu_ready_i = 0; fpu_result_valid_i = 0; result_ready_i = 0;
    final_ack_i = 0; done_ready_i = 0;
  endtask
  task automatic reset_all;
    @(negedge clk_i); idle_inputs(); rst_ni = 0;
    repeat (2) @(negedge clk_i);
    rst_ni = 1;
    @(posedge clk_i); #1;
    if (busy_o || done_valid_o || outstanding_o != 0 || result_valid_o != 0)
      $fatal(1, "reset failed to flush cluster");
  endtask

  // mode: 0 success, 1 abort+start, 2 abort with FPU debt, 3 malformed kind,
  // 4 abort after external valid before accept, 5 reset with FPU debt,
  // 6 reset while final acknowledgments are outstanding.
  task automatic run_case(input int case_id, e, h, t, m, input logic [3:0] lanes);
    int w, s, tok, head, pick, balance, all_writes, reqs, total_writes;
    logic [63:0] coeff, expected_data;
    logic [3:0] wm;
    logic [7:0] be;
    bit expected_error, terminal_fire, some_pending, is_cancel;
    id = case_id; elements = e; words = (e+3)/4; heads = h; tokens = t; mode = m;
    packets = 0; expected_flags = 0; group_seen = 0; aborted = 0; post_abort = 0;
    terminal_seen = 0; terminal_cycles = 0; stream_held = 0; total_writes = 0;
    expected_error = m inside {1,2,3};
    for (int l = 0; l < 4; l++) begin
      seeded[l]=0; delivered[l]=0; issued[l]=0; written[l]=0; acked[l]=0;
      stalled[l]=0; fpu_stalled[l]=0; lane_finished[l]=0;
      for (int k = 0; k < 16; k++) begin
        pending[l][k]=0; due[l][k]=0; ack_due[l][k]=0; accum[l][k]=0;
      end
    end
    @(negedge clk_i);
    idle_inputs(); start_valid_i = 1; start_active_i = lanes;
    cmd_elements_i = e; cmd_two_heads_i = h == 2; cmd_tokens_i = t; cmd_rm_i = id%5;
    abort_i = m == 1;
    @(posedge clk_i);
    if (!start_ready_o || dut.lane_cmd_valid !== lanes ||
        (dut.lane_cmd_ready & lanes) !== lanes)
      $fatal(1, "non-atomic launch including abortstart id=%0d", id);
    #1;
    for (cyc = 0; cyc < 12000; cyc++) begin
      @(negedge clk_i);
      idle_inputs();
      // Changing the live launch mask must not change the retained active mask.
      start_active_i = ~lanes;
      some_pending = 0; all_writes = 1;
      for (int l = 0; l < 4; l++) begin
        for (int k = 0; k < 16; k++) some_pending |= pending[l][k];
        if (lanes[l] && written[l] != words*heads) all_writes = 0;
      end
      if (m == 2 && !aborted && some_pending) begin abort_i=1; aborted=1; end
      if (m == 4 && !post_abort && |result_valid_o) begin abort_i=1; post_abort=1; end
      if ((m == 5 && some_pending) || (m == 6 && all_writes && outstanding_o != 0)) begin
        reset_all(); cov_reset++;
        $display("PV_CLUSTER_CASE_PASS id=%0d reset=1", id);
        totals_cases++; return;
      end
      for (int l = 0; l < 4; l++) begin
        s = (seeded[l]/words)*8 + seeded[l]%words;
        seed_valid_i[l] = lanes[l] && seeded[l] < words*heads &&
                          cyc >= l*4 && (cyc%(l+2) == 0);
        seed_data_i[l] = seed(l,s);
        fpu_ready_i[l] = (cyc+l)%(l+3) != 0;
        pick = -1;
        // Highest ready tag first permits delayed and out-of-order tagged returns.
        for (int k = 0; k < 16; k++)
          if (pending[l][k] && due[l][k] <= cyc) pick = k;
        if (pick >= 0) begin
          fpu_result_valid_i[l]=1; fpu_result_tag_i[l]=pick;
          fpu_result_i[l]=returned[l][pick]; fpu_result_flags_i[l]=returned_flags[l][pick];
        end
        // First hold every external valid; lane 3 then has additional write stalls.
        result_ready_i[l] = cyc > 20 && (cyc+l)%4 != 0 &&
                            (m != 4 || (post_abort && !abort_i));
        if (l == 3) result_ready_i[l] &= cyc%7 < 2;
        // Lane 0: zero-latency acknowledgments. Others: independent final drain.
        if (l == 0) final_ack_i[l] = result_valid_o[l] && result_ready_i[l];
        else if (acked[l] < written[l] && ack_due[l][acked[l]] <= cyc)
          final_ack_i[l] = 1;
      end
      stream_valid_i = (stream_held || cyc%5 != 0) && !aborted;
      stream_is_value_i = packets%(words+1) != 0;
      if (m == 3 && packets == words+1) stream_is_value_i = 1;
      for (int l = 0; l < 4; l++) stream_data_i[l] = packet(l, packets);
      // Probe excess acknowledgments before any acceptance and at held terminal.
      if (cyc == 0 || (terminal_seen && terminal_cycles == 1)) final_ack_i = '1;
      done_ready_i = terminal_seen && terminal_cycles >= 4;
      @(posedge clk_i);
      if (active_o !== lanes || !busy_o || start_ready_o || fatal_error_o)
        $fatal(1, "active/busy ownership id=%0d", id);
      if (commit_authorized_o && |dut.lane_abort)
        $fatal(1, "abort forwarded after authorization");
      if (abort_i && commit_authorized_o) begin
        if (!abort_rejected_o) $fatal(1, "late abort not rejected");
        cov_reject++;
      end
      is_cancel = |dut.lane_abort;
      if (is_cancel) begin
        if (dut.lane_abort !== lanes) $fatal(1, "cancel missed controller");
        if (stream_ready_o || |seed_ready_o || |dut.payload_valid)
          $fatal(1, "private delivery during cancellation");
        cov_cancel++;
        if (some_pending) cov_pending_cancel++;
      end
      for (int l = 0; l < 4; l++) begin
        balance = written[l]-acked[l];
        if (outstanding_o[l] !== 5'(balance))
          $fatal(1, "final ack ledger mismatch lane=%0d got=%0d expected=%0d", l, outstanding_o[l], balance);
        if (balance == 16) cov_max++;
        if (stalled[l] && (!result_valid_o[l] || result_data_o[l] !== held_data[l] ||
            result_slot_o[l] !== held_slot[l] || result_be_o[l] !== held_be[l]))
          $fatal(1, "write beat changed while pending");
        if (fpu_stalled[l] && !is_cancel && (!fpu_valid_o[l] ||
            fpu_operands_o[l] !== held_ops[l] || fpu_tag_o[l] !== held_tag[l] ||
            fpu_mask_o[l] !== held_mask[l])) $fatal(1, "FPU request changed while pending");
        stalled[l] = result_valid_o[l] && !result_ready_i[l];
        fpu_stalled[l] = fpu_valid_o[l] && !fpu_ready_i[l];
        held_data[l]=result_data_o[l]; held_slot[l]=result_slot_o[l]; held_be[l]=result_be_o[l];
        held_ops[l]=fpu_operands_o[l]; held_tag[l]=fpu_tag_o[l]; held_mask[l]=fpu_mask_o[l];
        if (stalled[l]) cov_stall++;
        if (seed_valid_i[l] && seed_ready_o[l]) begin
          s=(seeded[l]/words)*8+seeded[l]%words; accum[l][s]=seed(l,s); seeded[l]++;
        end
        if (dut.payload_valid[l] && dut.payload_ready[l]) begin
          if (!lanes[l] || delivered[l] >= packets ||
              dut.payload_data[l] !== packet(l,delivered[l]))
            $fatal(1, "duplicate/misdirected private packet");
          if (dut.payload_kind !== ((m == 3 && delivered[l] == words+1) ||
                                    delivered[l]%(words+1) != 0))
            $fatal(1, "private packet kind changed");
          delivered[l]++;
        end
        if (fpu_result_valid_i[l] && fpu_result_ready_o[l]) begin
          s=fpu_result_tag_i[l];
          if (!pending[l][s]) $fatal(1, "duplicate tagged return");
          wm=mask(s%8);
          for (int k=0;k<4;k++) if (wm[k]) accum[l][s][16*k+:16]=returned[l][s][16*k+:16];
          expected_flags |= returned_flags[l][s]; pending[l][s]=0;
        end
        if (fpu_valid_o[l] && fpu_ready_i[l]) begin
          reqs=issued[l]; w=(reqs/heads)%words; head=reqs%heads;
          tok=reqs/(words*heads); s=head*8+w;
          coeff=packet(l,tok*(words+1)); wm=mask(w);
          if (!lanes[l] || tok >= tokens || pending[l][s] ||
              fpu_tag_o[l] !== 4'(s) || fpu_mask_o[l] !== wm || fpu_rm_o[l] !== 3'(id%5) ||
              fpu_operands_o[l][0] !== {4{head != 0 ? coeff[31:16] : coeff[15:0]}} ||
              fpu_operands_o[l][1] !== packet(l,tok*(words+1)+w+1) ||
              fpu_operands_o[l][2] !== accum[l][s])
            $fatal(1, "FPU protocol/operand signature mismatch id=%0d lane=%0d req=%0d", id,l,reqs);
          pending[l][s]=1;
          due[l][s]=cyc+3+l*3+(15-s)%5;
          returned[l][s]=signature(fpu_operands_o[l],l,s);
          returned_flags[l][s]=5'(1 << ((l+s+tok)%5));
          issued[l]++;
        end
        if (result_valid_o[l] && result_ready_i[l]) begin
          s=(written[l]/words)*8+written[l]%words; wm=mask(written[l]%words);
          for (int k=0;k<4;k++) be[2*k+:2]={2{wm[k]}};
          if (expected_error || !commit_authorized_o || written[l] >= words*heads ||
              (negative_pending && written[l] == 1 ? 4'b0 : result_slot_o[l]) !== 4'(s) ||
              result_be_o[l] !== be || result_data_o[l] !== accum[l][s])
            $fatal(1, "duplicate/incorrect accepted write");
          ack_due[l][written[l]]=cyc+40+l*20;
          written[l]++; total_writes++;
        end
        if (final_ack_i[l]) begin
          if (acked[l] == written[l]) begin
            if (!ack_rejected_o[l]) $fatal(1, "excess final ack not rejected");
            cov_excess++;
          end else begin
            if (ack_rejected_o[l]) $fatal(1, "owned final ack rejected");
            if (lane_finished[l]) cov_late++;
            if (result_valid_o[l] && result_ready_i[l]) cov_same++;
            acked[l]++;
          end
        end
        if (dut.lane_done[l] && dut.lane_done_ready[l]) lane_finished[l]=1;
      end
      if (delivered[0] != delivered[3] && lanes[0] && lanes[3]) cov_private_skew++;
      if (packets == tokens*(words+1) && stream_valid_i) begin
        if (stream_ready_o) $fatal(1, "accepted trailing packet beyond command bound");
        cov_trailing++;
      end
      if (stream_valid_i && stream_ready_o) begin
        for (int l=0;l<4;l++) if (lanes[l] && seeded[l] < words*heads) cov_early++;
        packets++;
      end
      stream_held = stream_valid_i && !stream_ready_o;
      if (done_valid_o) begin
        if (group_seen && (done_flags_o !== held_flags || done_error_o !== held_error))
          $fatal(1, "terminal flags changed while valid and stalled");
        group_seen=1; held_flags=done_flags_o; held_error=done_error_o;
      end
      if (!done_valid_o && (done_flags_o != 0 || done_error_o))
        $fatal(1, "terminal flags/error leaked without valid");
      if (done_valid_o || (negative_complete && dut.group_done)) begin
        for (int l=0;l<4;l++) begin
          if (written[l] != acked[l]) $fatal(1, "premature complete before final ack");
          for (int k=0;k<16;k++) if (pending[l][k]) $fatal(1, "premature complete before FPU drain");
          if (!expected_error && lanes[l] &&
              (written[l] != words*heads || issued[l] != words*heads*tokens ||
               delivered[l] != tokens*(words+1) || seeded[l] != words*heads))
            $fatal(1, "missing lane work at terminal");
        end
        if (negative_flags) expected_flags ^= 1;
        if (done_error_o !== expected_error ||
            done_flags_o !== (expected_error ? 5'b0 : expected_flags))
          $fatal(1, "incorrect terminal flags/error");
        terminal_seen=1; terminal_cycles++;
        if (!done_ready_i) cov_done_stall++;
      end
      terminal_fire=done_valid_o && done_ready_i;
      #1;
      if (terminal_fire) begin
        if (busy_o || active_o != 0 || done_valid_o) $fatal(1, "terminal not consumed once");
        totals_cases++; totals_terminals++;
        $display("PV_CLUSTER_CASE_PASS id=%0d reset=0 error=%0d writes=%0d flags=%0d", id, expected_error, total_writes, held_flags);
        return;
      end
    end
    $fatal(1, "bounded case timeout id=%0d", id);
  endtask

  initial begin
    negative_pending=$test$plusargs("BAD_PENDING");
    negative_flags=$test$plusargs("BAD_FLAGS");
    negative_complete=$test$plusargs("BAD_COMPLETE");
    reset_all();
    run_case(1, 5, 2, 3, 0, 4'b1111);
    run_case(2, 32, 2, 1, 0, 4'b1111);
    run_case(3, 7, 1, 9, 4, 4'b1010);
    run_case(4, 1, 1, 64, 0, 4'b0101);
    run_case(5, 6, 2, 3, 1, 4'b1111);
    run_case(6, 7, 2, 3, 2, 4'b1111);
    run_case(7, 6, 1, 3, 3, 4'b1101);
    run_case(8, 31, 2, 3, 5, 4'b1111);
    run_case(9, 32, 2, 1, 6, 4'b1111);
    run_case(10, 6, 2, 2, 0, 4'b1111);
    if (!(cov_late && cov_same && cov_excess && cov_stall && cov_cancel &&
          cov_reject && cov_max && cov_pending_cancel && cov_private_skew &&
          cov_done_stall && cov_reset == 2 && cov_early && cov_trailing)) $fatal(1, "missing required protocol exercise");
    $display("PV_CLUSTER_PASS cases=%0d terminals=%0d late=%0d same=%0d excess=%0d stalls=%0d cancel=%0d rejected=%0d max16=%0d pending_cancel=%0d skew=%0d done_stall=%0d resets=%0d early=%0d trailing=%0d",
      totals_cases,totals_terminals,cov_late,cov_same,cov_excess,cov_stall,cov_cancel,
      cov_reject,cov_max,cov_pending_cancel,cov_private_skew,cov_done_stall,cov_reset,cov_early,cov_trailing);
    $finish;
  end
endmodule
