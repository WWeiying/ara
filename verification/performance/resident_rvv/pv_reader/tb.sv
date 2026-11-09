// SPDX-License-Identifier: Apache-2.0
module resident_pv_reader_tb;
  timeunit 1ns; timeprecision 1ps;
  import akv_pkg::*;
  logic clk = 0, rst = 0;
  always #5 clk = !clk;
  logic cancel = 0, start_valid = 0, start_ready, busy;
  logic [6:0] tokens = 0;
  logic [3:0] words = 0;
  logic coefficient_valid = 0, coefficient_ready;
  logic [31:0] coefficient = 0;
  logic row_read;
  logic [5:0] row_token;
  logic [3:0] row_word;
  logic [255:0] row_data;
  logic stream_valid, stream_ready = 0, stream_is_value;
  logic [3:0][63:0] stream_data;
  logic done_valid, done_ready = 0, done_error;
  logic write_valid = 0, write_busy;
  akv_stream_e write_stream = AKV_STREAM_K;
  logic [5:0] write_token = 0;
  logic [7:0] write_offset = 0;
  logic [127:0] write_data = 0;
  logic [15:0] write_strb = 0;
  logic column_busy, column_valid, column_cycle, conflict;

  akv_resident_pv_reader dut (
    .clk_i(clk), .rst_ni(rst), .cancel_i(cancel),
    .start_valid_i(start_valid), .start_ready_o(start_ready),
    .tokens_i(tokens), .words_i(words),
    .coefficient_valid_i(coefficient_valid), .coefficient_ready_o(coefficient_ready),
    .coefficient_i(coefficient), .row_read_o(row_read),
    .row_token_o(row_token), .row_word_o(row_word), .row_data_i(row_data),
    .stream_valid_o(stream_valid), .stream_ready_i(stream_ready),
    .stream_is_value_o(stream_is_value), .stream_data_o(stream_data),
    .done_valid_o(done_valid), .done_ready_i(done_ready),
    .done_error_o(done_error), .busy_o(busy)
  );
  akv_v2_context context_store (
    .clk_i(clk), .rst_ni(rst), .write_valid_i(write_valid),
    .write_stream_i(write_stream), .write_token_i(write_token),
    .write_offset_i(write_offset), .write_data_i(write_data),
    .write_strb_i(write_strb), .write_busy_o(write_busy),
    .row_read_i(row_read), .row_stream_i(AKV_STREAM_V),
    .row_token_i(row_token), .row_word_i(row_word), .row_data_o(row_data),
    .column_start_i(1'b0), .column_stream_i(AKV_STREAM_K),
    .column_dimension_i(7'b0), .column_count_i(3'd1),
    .column_token_count_i(7'b0), .column_busy_o(column_busy),
    .column_valid_o(column_valid), .column_data_o(),
    .column_bank_cycle_o(column_cycle), .conflict_o(conflict)
  );

  // Natural token/dimension arrays. No DUT permutation helper is used here.
  logic [15:0] natural_v [64][128];
  logic [15:0] natural_k [64][128];
  int active_tokens, active_words, accepted, coefficients, values, reads;
  int cases = 0, good_cases = 0, invalid_cases = 0, cancel_cases = 0;
  int total_reads = 0, total_values = 0, total_coefficients = 0;
  int latency_checks = 0, coefficient_stalls = 0, value_stalls = 0;
  int full_credit_cycles = 0, busy_rejects = 0, held_done = 0, writes = 0;
  int final_stalls = 0, max_credit = 0;
  bit active = 0, expect_error = 0, cancelled = 0;
  bit stalled = 0, stalled_kind, previous_read = 0;
  logic [255:0] stalled_data, previous_row;

  function automatic logic [31:0] coeff(input int token);
    return 32'h3f001234 ^ (32'h00010203 * token);
  endfunction

  function automatic logic [255:0] natural_row(input int token, word_index);
    logic [255:0] result;
    for (int h = 0; h < 16; h++) result[16*h+:16] = natural_v[token][16*word_index+h];
    return result;
  endfunction

  function automatic logic [255:0] expected_stream(input int token, word_index);
    logic [3:0][63:0] result;
    for (int lane = 0; lane < 4; lane++) begin
      result[lane][ 0+:16] = natural_v[token][16*word_index+lane+0];
      result[lane][16+:16] = natural_v[token][16*word_index+lane+8];
      result[lane][32+:16] = natural_v[token][16*word_index+lane+4];
      result[lane][48+:16] = natural_v[token][16*word_index+lane+12];
    end
    return result;
  endfunction

  // Sample handshakes before NBA, then check the real SRAM output after NBA.
  always @(posedge clk) begin : scoreboard
    bit request;
    logic [255:0] requested_row;
    int token_index, slot, credit;
    request = row_read;
    requested_row = natural_row(int'(row_token), int'(row_word));
    if (rst) begin
      if ($isunknown({start_ready,busy,done_valid,done_error,row_read,
                      coefficient_ready,stream_valid,stream_is_value,write_busy}))
        $fatal(1, "Unknown protocol metadata");
      if (write_busy !== write_valid || conflict || column_busy || column_valid || column_cycle)
        $fatal(1, "Context busy/conflict/column protocol");
      if (write_valid) begin
        if (write_offset[3:0] != 0 || write_strb != '1 || row_read || busy)
          $fatal(1, "Unaligned or conflicting context fill");
        writes++;
      end
      if (previous_read) begin
        if (row_data !== previous_row) $fatal(1, "SRAM response not available at reader capture");
        latency_checks++;
      end
      if (busy && start_ready) $fatal(1, "Busy admitted another start");
      if (busy && start_valid) busy_rejects++;
      if (cancel) begin
        if (row_read || stream_valid || coefficient_ready) $fatal(1, "Cancel did not suppress transfers");
        stalled = 0;
      end else begin
        if (stalled && (!stream_valid || stream_data !== stalled_data ||
                        stream_is_value !== stalled_kind))
          $fatal(1, "Stream changed while backpressured");
        stalled = stream_valid && !stream_ready;
        stalled_data = stream_data;
        stalled_kind = stream_is_value;
        if (stalled) begin
          if (stream_is_value) value_stalls++;
          else coefficient_stalls++;
        end
      end
      if (coefficient_ready !== (!cancel && stream_ready && !stream_is_value && busy && !done_valid))
        $fatal(1, "Coefficient handshake metadata");
      if (stream_valid) begin
        if (!active || expect_error || accepted >= active_tokens*(active_words+1))
          $fatal(1, "Unexpected stream");
        token_index = accepted / (active_words+1);
        slot = accepted % (active_words+1);
        if (stream_is_value !== (slot != 0)) $fatal(1, "Coefficient/value order");
        if (slot == 0) begin
          for (int lane = 0; lane < 4; lane++)
            if (stream_data[lane] !== {32'b0,coeff(token_index)})
              $fatal(1, "Coefficient raw bits token=%0d lane=%0d", token_index, lane);
        end else if (stream_data !== expected_stream(token_index, slot-1))
          $fatal(1, "Value raw bytes token=%0d word=%0d got=%h expected=%h",
                 token_index, slot-1, stream_data, expected_stream(token_index,slot-1));
        if (stream_ready) begin
          accepted++;
          if (slot == 0) begin coefficients++; total_coefficients++; end
          else begin values++; total_values++; end
        end
      end
      if (row_read) begin
        if (!active || expect_error || !busy || write_busy || cancelled)
          $fatal(1, "Illegal read admission");
        if (int'(row_token) != reads / active_words || int'(row_word) != reads % active_words ||
            reads >= active_tokens*active_words || coefficients != reads/active_words+1)
          $fatal(1, "Read request order/token/word");
        // A V read must select exactly one bank and the V half of its address space.
        if (context_store.bank_req !== (8'b1 << row_token[2:0]) ||
            context_store.bank_we !== 0 ||
            int'(context_store.bank_addr[row_token[2:0]]) != 64+8*(int'(row_token)/8)+int'(row_word))
          $fatal(1, "Inactive K accessed or wrong bank address");
        reads++; total_reads++;
      end
      if (active && !expect_error && !cancelled) begin
        credit = reads-values;
        if (credit < 0 || credit > 2) $fatal(1, "External read credit overflow %0d",credit);
        if (credit > max_credit) max_credit = credit;
        if (credit == 2 && !stream_ready) begin
          full_credit_cycles++;
          if (row_read) begin
            // The read that fills the last free entry is legal.
            if (dut.count_q+int'(dut.pending_q) >= 2) $fatal(1, "Read at full credit");
          end
        end
      end
      if (done_valid) begin
        if (!active || !busy || start_ready || row_read || stream_valid || coefficient_ready ||
            done_error !== expect_error) $fatal(1, "Done metadata");
        if (!expect_error && (accepted != active_tokens*(active_words+1) ||
                             reads != active_tokens*active_words || reads != values))
          $fatal(1, "Done before stream delivery");
        if (!done_ready) held_done++;
      end
    end
    previous_read = rst && request;
    previous_row = requested_row;
    #1;
    if (rst && request && row_data !== requested_row)
      $fatal(1, "Real SRAM is not latency one: got=%h expected=%h",row_data,requested_row);
  end

  // All stimulus changes occur away from the active edge.
  task automatic step;
    @(posedge clk); #2; @(negedge clk); #1;
  endtask

  task automatic idle_check;
    if ({start_ready,busy,done_valid,done_error,row_read,stream_valid,coefficient_ready}
        !== 7'b1000000) $fatal(1, "Idle/reset metadata");
  endtask

  task automatic launch(input int t, w, input bit invalid_config);
    idle_check();
    active_tokens=t; active_words=w; accepted=0; coefficients=0; values=0; reads=0;
    active=1; expect_error=invalid_config; cancelled=0;
    tokens=7'(t); words=4'(w); start_valid=1;
    coefficient_valid=0; stream_ready=0;
    step();
    // These hostile values must not replace the latched transaction metadata.
    tokens=0; words=15;
    if (!busy || start_ready) $fatal(1, "Start not accepted");
  endtask

  task automatic finish_case;
    int old_reads;
    old_reads=reads;
    if (!done_valid || done_error !== expect_error) $fatal(1, "Missing completion");
    coefficient_valid=0; stream_ready=1; cancel=0;
    repeat (6) begin
      step();
      if (!done_valid || !busy || done_error !== expect_error || reads != old_reads)
        $fatal(1, "Done did not hold");
    end
    start_valid=0; done_ready=1;
    step();
    active=0; done_ready=0;
    idle_check();
    repeat (3) step();
    cases++;
  endtask

  task automatic run_shape(input int t,w, input bit backpressure);
    int cycles, first_value_hold, final_hold;
    launch(t,w,0);
    cycles=0; first_value_hold=0; final_hold=0;
    while (!done_valid && cycles < 20000) begin
      coefficient_valid=(cycles >= 3);
      coefficient=coeff(coefficients);
      stream_ready=1;
      if (backpressure) begin
        stream_ready=(cycles%11 >= 4);
        if (coefficients == 0 && cycles < 9) stream_ready=0;
        if (coefficients == 1 && values == 0 && first_value_hold < 9) begin
          stream_ready=0; first_value_hold++;
        end
        if (accepted == t*(w+1)-1 && final_hold < 7) begin
          stream_ready=0; final_hold++; final_stalls++;
          if (done_valid) $fatal(1, "Done asserted on final undelivered word");
        end
      end
      step(); cycles++;
    end
    if (!done_valid) $fatal(1, "Bounded shape timeout t=%0d w=%0d",t,w);
    if (coefficients != t || values != t*w || reads != t*w) $fatal(1, "Exact counts");
    $display("READER_SHAPE_PASS tokens=%0d words=%0d stalls=%0d coefficients=%0d values=%0d reads=%0d",
             t,w,backpressure,coefficients,values,reads);
    good_cases++;
    finish_case();
  endtask

  task automatic cancel_outstanding(input int w);
    launch(9,w,0);
    coefficient_valid=1; coefficient=coeff(0); stream_ready=1;
    step();
    coefficient_valid=0; stream_ready=0;
    if (!row_read) $fatal(1, "Expected first SRAM request");
    step();
    if (!dut.pending_q || reads != 1 || values != 0)
      $fatal(1, "Cancel did not target an outstanding read");
    cancel=1; cancelled=1; expect_error=1;
    step();
    cancel_cases++;
    $display("READER_CANCEL_PASS words=%0d reads=%0d delivered=%0d",w,reads,values);
    finish_case();
    run_shape(9,w,1);
  endtask

  initial begin : stimulus
    int ts[3] = '{1,9,64};
    int ws[3] = '{4,6,8};
    // Every token/halfword is unique; K is a distinct bitwise-complement sentinel.
    for (int t=0;t<64;t++) for (int d=0;d<128;d++) begin
      natural_v[t][d]=16'((t*128+d)*40503+97);
      natural_k[t][d]=~natural_v[t][d];
    end
    repeat (3) step();
    rst=1; step(); idle_check();
    for (int s=0;s<2;s++) for (int t=0;t<64;t++) for (int beat=0;beat<16;beat++) begin
      write_valid=1; write_stream=(s==0 ? AKV_STREAM_K : AKV_STREAM_V);
      write_token=6'(t); write_offset=8'(16*beat); write_strb='1;
      for (int h=0;h<8;h++)
        write_data[16*h+:16]=(s==0 ? natural_k[t][8*beat+h] : natural_v[t][8*beat+h]);
      step();
    end
    write_valid=0; write_strb=0; step();
    for (int a=0;a<3;a++) for (int b=0;b<3;b++)
      for (int stall=0;stall<2;stall++) run_shape(ts[a],ws[b],1'(stall));
    for (int w=0;w<16;w++) if (!(w inside {4,6,8})) begin
      launch(9,w,1); finish_case(); invalid_cases++;
    end
    launch(0,4,1); finish_case(); invalid_cases++;
    launch(65,4,1); finish_case(); invalid_cases++;
    launch(127,4,1); finish_case(); invalid_cases++;
    for (int b=0;b<3;b++) cancel_outstanding(ws[b]);
    if (writes != 2048 || max_credit != 2 || !coefficient_stalls || !value_stalls ||
        !full_credit_cycles || !busy_rejects || !final_stalls || latency_checks != total_reads)
      $fatal(1, "Missing discriminating coverage");
    $display("READER_PASS cases=%0d good=%0d invalid=%0d cancelled=%0d writes=%0d reads=%0d values=%0d coefficients=%0d latency=%0d coefficient_stalls=%0d value_stalls=%0d full_credit=%0d busy_rejects=%0d held_done=%0d final_stalls=%0d max_credit=%0d",
      cases,good_cases,invalid_cases,cancel_cases,writes,total_reads,total_values,total_coefficients,
      latency_checks,coefficient_stalls,value_stalls,full_credit_cycles,busy_rejects,held_done,final_stalls,max_credit);
    $finish;
  end
  initial begin #5000000; $fatal(1,"Global cycle bound exceeded"); end
endmodule
