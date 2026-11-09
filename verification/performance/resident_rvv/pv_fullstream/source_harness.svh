// Testbench-only source transport. No arrays or edits in the production importer.
typedef logic [$clog2(1024+1)-1:0] vlen_t;
typedef struct packed {
  rvv_pkg::vew_e eew;
  vlen_t elem_count;
  opqueue_conversion_e conv;
  logic [1:0] ntr_red;
  logic is_reduct;
  target_fu_e target_fu;
} operand_queue_cmd_t;
operand_queue_cmd_t source_command;
logic [3:0] source_command_valid=0, source_issued=0, source_returned=0;
logic [3:0] source_credit, source_valid, source_ready, source_pop, source_take;
logic [3:0][63:0] source_operand=0, source_data, source_pending_data;
logic [3:0] source_pending=0, import_seed_valid, seed_gate=0;
logic import_coefficient_valid, coefficient_gate=0;
logic import_ready, import_done, import_error, import_busy, import_done_ready;
logic commit_permit_i;
logic reader_complete_q, reader_failed_q;
logic source_native=0, source_owned=0, import_seen=0;
bit guard_run=0, guard_cancel=0, tail_released=0;
int guard_mode=0, gap_start, gap_cycles, tail_release_cycle, cancel_cycle;
int cancel_terminal_start, cancel_terminal_wait;
int source_sent[4], source_received[4], source_consumed[4], source_commands[4];
int source_sentinels[4], source_issue_cycle[4];
int source_first_cycle, source_done_cycle, transaction_done_cycle, source_latency;
int source_credit_stalls, source_skew, source_coef_stalls;
target_fu_e source_target[4];

// Reader done may retire before the fixed source tail. Preserve its admission result.
always_ff @(posedge clk_i or negedge rst_ni) begin
  if (!rst_ni) begin reader_complete_q<=0; reader_failed_q<=0; end
  else if (start_valid_i && start_ready_o) begin reader_complete_q<=0; reader_failed_q<=0; end
  else if (reader_done) begin reader_complete_q<=1; reader_failed_q<=reader_error; end
end
assign commit_permit_i = import_done && !import_error && reader_complete_q && !reader_failed_q;
assign import_done_ready = done_valid_o && done_ready_i;
assign seed_valid_i = import_seed_valid & seed_gate;
assign coefficient_valid = import_coefficient_valid && coefficient_gate;
assign source_take = source_native ? 4'hf : source_ready;
akv_resident_pv_import source_import (
  .clk_i, .rst_ni, .start_valid_i(start_valid_i), .start_ready_o(import_ready),
  .words_i(reader_words), .two_heads_i(cmd_two_heads_i), .tokens_i(reader_tokens),
  .cancel_i(abort_i), .source_valid_i(source_valid), .source_ready_o(source_ready),
  .source_data_i(source_data), .seed_valid_o(import_seed_valid),
  .seed_ready_i(seed_ready_o & seed_gate), .seed_data_o(seed_data_i),
  .coefficient_valid_o(import_coefficient_valid),
  .coefficient_ready_i(coefficient_ready && coefficient_gate), .coefficient_o(coefficient),
  .done_valid_o(import_done), .done_ready_i(import_done_ready),
  .done_error_o(import_error), .busy_o(import_busy)
);
for (genvar q=0; q<4; q++) begin : gen_source
  operand_queue #(
    .CmdBufDepth(VstuInsnQueueDepth+MaskuInsnQueueDepth), .DataBufDepth(2),
    .FPUSupport(FPUSupportNone), .NrLanes(4), .VLEN(1024), .NrSlaves(1),
    .AccessCmdPop(1), .operand_queue_cmd_t(operand_queue_cmd_t)
  ) queue_i (
    .clk_i, .rst_ni, .flush_i(1'b0), .lane_id_i(2'(q)),
    .operand_queue_cmd_i(source_command), .operand_queue_cmd_valid_i(source_command_valid[q]),
    .cmd_pop_o(source_pop[q]), .operand_i(source_operand[q]),
    .operand_valid_i(source_returned[q]), .operand_issued_i(source_issued[q]),
    .operand_queue_ready_o(source_credit[q]), .operand_o(source_data[q]),
    .operand_target_fu_o(source_target[q]), .operand_valid_o(source_valid[q]),
    .operand_ready_i(source_take[q])
  );
end

function automatic logic [63:0] native_sentinel(input int lane);
  return 64'hdeadbeef00001234 ^ (64'(id)<<20) ^ 64'(lane*177);
endfunction

function automatic logic [15:0] coefficient_half(input int natural_index);
  int token_index;
  token_index=natural_index/2;
  if (token_index<tokens)
    return packets[0][token_index*(words+1)][16*(natural_index%2)+:16];
  return 16'hbadd ^ 16'(id*997+natural_index*37);
endfunction

// Same explicit natural-halfword mapping as accepted import01; independent
// expected FMA/stream/seed bytes continue to come from the original corpus.
function automatic logic [63:0] source_word(input int lane, word_index);
  int base;
  if (word_index==24) return native_sentinel(lane);
  if (word_index<16) begin
    if (word_index/8<heads && word_index%8<words)
      return seeds[lane][(word_index/8)*words+word_index%8];
    return 64'hbaddf00ddeadbeef ^ (64'(id)<<24) ^ 64'(word_index*177+lane*31);
  end
  base=16*(word_index-16)+lane;
  return {coefficient_half(base+12),coefficient_half(base+4),
          coefficient_half(base+8),coefficient_half(base)};
endfunction

task automatic source_begin;
  if (!import_ready || source_valid!=0 || source_credit!=15)
    $fatal(1,"Source reuse not clean");
  source_owned=1; source_native=0; import_seen=0;
  source_pending=0; source_issued=0; source_returned=0;
  seed_gate=0; coefficient_gate=0; abort_i=0;
  source_first_cycle=-1; source_done_cycle=-1; transaction_done_cycle=-1;
  source_latency=0; source_credit_stalls=0; source_skew=0; source_coef_stalls=0;
  guard_cancel=0; tail_released=0;
  gap_start=0; gap_cycles=0; tail_release_cycle=0; cancel_cycle=0;
  cancel_terminal_start=0; cancel_terminal_wait=0;
  source_command='0;
  source_command.eew=EW16; source_command.elem_count=96;
  source_command.conv=OpQueueConversionNone; source_command.target_fu=ALU_SLDU;
  source_command_valid=15;
  for (int l=0;l<4;l++) begin
    source_sent[l]=0; source_received[l]=0; source_consumed[l]=0;
    source_commands[l]=0; source_sentinels[l]=0; source_issue_cycle[l]=-1;
  end
endtask

task automatic guard_drive;
  bit fp_complete;
  abort_i=0;
  fp_complete=dut.lane_result_valid==15;
  for (int l=0;l<4;l++) fp_complete &= issued[l]==nop[l] && returned[l]==nop[l];
  if (guard_mode inside {1,2} && !guard_cancel && !tail_released && fp_complete) begin
    if (!gap_start) gap_start=clock_cycle;
    result_ready_i=15; // External ready is deliberately high; authorization must be blocked.
    final_ack_i=0;
    if (clock_cycle-gap_start>=12) begin
      if (guard_mode==2) begin
        abort_i=1; guard_cancel=1; cancel_cycle=clock_cycle;
      end else begin tail_released=1; tail_release_cycle=clock_cycle; end
    end
  end
  // Error terminal is intentionally earlier than source drain. Keep the tail
  // withheld for twelve full terminal cycles, not just twelve cycles after abort.
  if (guard_cancel && !tail_released && done_valid_o) begin
    if (!cancel_terminal_start) cancel_terminal_start=clock_cycle;
    if (clock_cycle-cancel_terminal_start>=12) begin
      tail_released=1; tail_release_cycle=clock_cycle;
    end
  end
endtask

task automatic source_drive;
  source_returned=source_pending;
  source_operand=source_pending_data;
  source_issued=0;
  for (int l=0;l<4;l++)
    if (source_sent[l]<25 && source_credit[l] &&
        (no_stalls || (clock_cycle+2*l)%(l+2)==0) &&
        (!(guard_mode inside {1,2}) || tail_released || source_sent[l]<18))
      source_issued[l]=1;
endtask

task automatic source_check;
  if (source_owned) begin
    if (!busy_o || active_o!=15 || start_ready_o)
      $fatal(1,"Parent released before import/FP/final acknowledgements");
    if (!commit_permit_i && (commit_authorized_o || result_valid_o!=0))
      $fatal(1,"Commit authorization bypassed source/reader drain/error");
    if (guard_cancel && (commit_permit_i || commit_authorized_o || result_valid_o!=0))
      $fatal(1,"Gap cancellation committed architecture");
    if (gap_start && !guard_cancel && !tail_released) begin
      if (import_done || dut.lane_result_valid!=15 || dut.lane_result_ready!=0 ||
          result_ready_i!=15 || commit_authorized_o || result_valid_o!=0)
        $fatal(1,"Delayed tail did not block authorization itself");
      for (int l=0;l<4;l++)
        if (source_consumed[l]!=18 || source_commands[l]!=0 || returned[l]!=nop[l])
          $fatal(1,"Gap lacks complete FP and undrained source");
      gap_cycles++;
    end
    if (guard_cancel && !tail_released && done_valid_o) begin
      if (!done_error_o || done_ready_i || import_done_ready || import_done ||
          !import_busy || !reader_complete_q || !reader_retired || outstanding_o!=0)
        $fatal(1,"Error terminal bypassed outstanding source drain");
      for (int l=0;l<4;l++)
        if (source_consumed[l]!=18 || source_commands[l]!=0 || issued[l]!=returned[l])
          $fatal(1,"Cancel terminal missing source debt or FP drain");
      cancel_terminal_wait++;
    end
    if (import_seen && !import_done) $fatal(1,"Import done withdrawn before overall completion");
    if (import_done) begin
      if (import_error!==guard_cancel || !import_busy || import_ready)
        $fatal(1,"Import completion/error mismatch");
      for (int l=0;l<4;l++)
        if (source_consumed[l]!=24 || source_commands[l]!=1)
          $fatal(1,"Import done without 24 source words and one command pop per lane");
      if (!import_seen) source_done_cycle=clock_cycle;
      import_seen=1;
    end
  end
  if (source_valid!=0 && source_valid!=15) source_skew++;
  if (import_coefficient_valid && !(coefficient_ready && coefficient_gate)) source_coef_stalls++;
  for (int l=0;l<4;l++) begin
    if (source_credit[l] !== (source_sent[l]-source_consumed[l]<2))
      $fatal(1,"Source credits differ from independent ledger");
    if (!source_credit[l]) source_credit_stalls++;
    if (source_returned[l]!==source_pending[l]) $fatal(1,"Source response without issue");
    if (source_returned[l]) begin
      if (clock_cycle!=source_issue_cycle[l]+1 || source_received[l]>=source_sent[l] ||
          source_operand[l]!==source_word(l,source_received[l]))
        $fatal(1,"Source one-cycle return/order mismatch");
      source_received[l]++; source_latency++;
    end
    if (source_pop[l] !== (source_valid[l] && source_take[l] &&
                           (source_consumed[l]==23 || source_native)))
      $fatal(1,"Source command pop boundary mismatch");
    if (source_valid[l] && source_take[l]) begin
      if (source_data[l]!==source_word(l,source_consumed[l]) ||
          source_consumed[l]>=source_received[l] || source_consumed[l]>24)
        $fatal(1,"Source stale word/overpop");
      if (source_native) begin
        if (source_consumed[l]!=24 || source_target[l]!=ALU_SLDU)
          $fatal(1,"Following native command corrupted");
        source_sentinels[l]++;
      end else begin
        if (source_consumed[l]>=24) $fatal(1,"Importer consumed following native command");
        if (source_pop[l]) source_commands[l]++;
      end
      source_consumed[l]++;
    end
    if (source_issued[l]) begin
      if (!source_credit[l]) $fatal(1,"Source issued without credit");
      if (source_first_cycle<0) source_first_cycle=clock_cycle;
      source_issue_cycle[l]=clock_cycle;
      source_pending_data[l]=source_word(l,source_sent[l]);
      source_sent[l]++;
    end
    if (source_sent[l]-source_consumed[l]>2 || source_consumed[l]>source_sent[l])
      $fatal(1,"Source credit bounds");
  end
  source_pending=source_issued;
endtask

task automatic source_finish;
  source_native=1;
  for (int age=0; age<100; age++) begin
    if (source_sentinels[0]+source_sentinels[1]+source_sentinels[2]+source_sentinels[3]==4) break;
    source_drive();
    @(posedge clk_i); source_check();
    #1; @(negedge clk_i);
  end
  source_native=0; source_issued=0; source_returned=0;
  for (int l=0;l<4;l++)
    if (source_sent[l]!=25 || source_received[l]!=25 || source_consumed[l]!=25 ||
        source_commands[l]!=1 || source_sentinels[l]!=1)
      $fatal(1,"Source/sentinel exact counts at final release");
  if (source_valid!=0 || source_credit!=15 || import_busy || !import_ready)
    $fatal(1,"Source not reusable without reset");
endtask

task automatic source_receipt;
  if (guard_mode inside {1,2} && (gap_cycles<12 || source_done_cycle<=tail_release_cycle ||
      last_return>gap_start || last_return>=source_done_cycle)) $fatal(1,"Unproven source/FP gap");
  if (guard_cancel && (cancel_terminal_wait<12 || tail_release_cycle-cancel_cycle<12 ||
      tail_release_cycle-cancel_terminal_start<12)) $fatal(1,"Cancelled terminal was not held for source drain");
  $display("PV_FULLSTREAM_CASE id=%0d guard=%0d words=96 cmdpops=4 sentinels=4 latency=%0d source_first=%0d import_done=%0d reader_done=%0d last_fp=%0d last_ack=%0d transaction_done=%0d final_drain=%0d first_write=%0d gap_start=%0d gap_cycles=%0d tail_release=%0d cancel_cycle=%0d cancel_terminal=%0d cancel_wait=%0d writes=%0d error=%0d credit_stalls=%0d skew=%0d coefficient_stalls=%0d",
    id,guard_mode,source_latency,source_first_cycle,source_done_cycle,reader_done_cycle,last_return,
    guard_cancel ? 0 : last_ack,transaction_done_cycle,drain_cycle,
    guard_cancel ? 0 : first_write,gap_start,gap_cycles,tail_release_cycle,cancel_cycle,
    cancel_terminal_start,cancel_terminal_wait,
    written[0]+written[1]+written[2]+written[3],guard_cancel,
    source_credit_stalls,source_skew,source_coef_stalls);
endtask
