`timescale 1ns/1ps
module unified_storage_tb;
  import akv_pkg::*;
  logic clk = 0, rst_n = 0, abort_write = 0;
  always #5 clk = ~clk;
  logic legacy_valid = 0, direct_valid = 0;
  logic [4:0] legacy_slot = 0;
  logic [7:0] legacy_offset = 0, direct_offset = 0;
  logic [8:0] row_bytes = 256;
  logic [127:0] legacy_data = 0, direct_data = 0;
  logic [15:0] legacy_strb = 0, direct_strb = '1;
  akv_stream_e direct_stream = AKV_STREAM_K;
  logic [5:0] direct_token = 0;
  logic legacy_busy, direct_busy, busy;
  logic legacy_read = 0, row_read = 0;
  logic [4:0] read_slot = 0;
  logic [3:0] read_word = 0;
  akv_stream_e row_stream = AKV_STREAM_K;
  logic [5:0] row_token = 0;
  logic [255:0] legacy_output, row_output, old_legacy_output, old_row_output;
  logic column_start = 0;
  akv_stream_e column_stream = AKV_STREAM_K;
  logic [6:0] dimension = 0, token_count = 0;
  logic [2:0] column_count = 1;
  logic column_busy, column_valid, column_cycle, conflict;
  logic old_column_busy, old_column_valid, old_column_cycle, old_conflict;
  logic [3:0][1023:0] column_output, old_column_output;
  logic old_legacy_busy, old_direct_busy;
  bit record_legacy = 1, compare_v2 = 0;
  int cycle = 0, legacy_rows = 0, direct_writes = 0, latency_checks = 0;
  int row_checks = 0, column_checks = 0, aborts = 0, legacy_writes = 0;
  int q_direct_overlap = 0;
  int last_capture [24];
  byte unsigned expected [3][64][256];

  akv_unified_context dut (
    .clk_i(clk), .rst_ni(rst_n), .abort_i(abort_write),
    .legacy_write_valid_i(legacy_valid), .legacy_write_slot_i(legacy_slot),
    .legacy_write_offset_i(legacy_offset), .legacy_row_bytes_i(row_bytes),
    .legacy_write_data_i(legacy_data), .legacy_write_strb_i(legacy_strb),
    .legacy_write_busy_o(legacy_busy),
    .v2_write_valid_i(direct_valid), .v2_write_stream_i(direct_stream),
    .v2_write_token_i(direct_token), .v2_write_offset_i(direct_offset),
    .v2_write_data_i(direct_data), .v2_write_strb_i(direct_strb), .v2_write_busy_o(direct_busy),
    .write_busy_o(busy), .legacy_replay_read_i(legacy_read),
    .legacy_replay_slot_i(read_slot), .legacy_replay_word_i(read_word),
    .legacy_replay_data_o(legacy_output), .v2_row_read_i(row_read),
    .v2_row_stream_i(row_stream), .v2_row_token_i(row_token), .v2_row_word_i(read_word),
    .v2_row_data_o(row_output), .column_start_i(column_start), .column_stream_i(column_stream),
    .column_dimension_i(dimension), .column_count_i(column_count), .column_token_count_i(token_count),
    .column_busy_o(column_busy), .column_valid_o(column_valid), .column_data_o(column_output),
    .column_bank_cycle_o(column_cycle), .conflict_o(conflict)
  );
  akv_context old_legacy (
    .clk_i(clk), .rst_ni(rst_n), .write_valid_i(legacy_valid && record_legacy && !abort_write),
    .write_slot_i(legacy_slot), .write_offset_i(legacy_offset), .write_data_i(legacy_data),
    .write_strb_i(legacy_strb), .write_busy_o(old_legacy_busy), .replay_read_i(legacy_read),
    .replay_slot_i(read_slot), .replay_word_i(read_word), .replay_data_o(old_legacy_output)
  );
  akv_v2_context old_v2 (
    .clk_i(clk), .rst_ni(rst_n), .write_valid_i(direct_valid && !abort_write),
    .write_stream_i(direct_stream), .write_token_i(direct_token), .write_offset_i(direct_offset),
    .write_data_i(direct_data), .write_strb_i(direct_strb), .write_busy_o(old_direct_busy),
    .row_read_i(row_read), .row_stream_i(row_stream), .row_token_i(row_token), .row_word_i(read_word),
    .row_data_o(old_row_output), .column_start_i(column_start), .column_stream_i(column_stream),
    .column_dimension_i(dimension), .column_count_i(column_count), .column_token_count_i(token_count),
    .column_busy_o(old_column_busy), .column_valid_o(old_column_valid),
    .column_data_o(old_column_output), .column_bank_cycle_o(old_column_cycle), .conflict_o(old_conflict)
  );

  function automatic byte unsigned payload(input int epoch, stream, token, offset);
    return 8'((epoch*37 + stream*71 + token*19 + offset*13) ^ (offset >> 3) ^ (token << 2));
  endfunction
  function automatic int slot_stream(input int slot);
    return slot < 8 ? 0 : slot < 16 ? 1 : 2;
  endfunction
  function automatic int slot_token(input int slot);
    return slot % 8;
  endfunction

  // Oracle uses accepted logical coordinates, never the candidate's SRAM address.
  // Aborted fragments are tested separately with a prefilled retention oracle.
  always @(posedge clk) if (rst_n) begin : monitor
    int count, slot;
    cycle++;
    assert (!conflict) else $fatal(1, "UNIT_STORAGE_CONFLICT");
    if (legacy_valid && record_legacy && !abort_write) begin
      count = $countones(legacy_strb);
      for (int b=0; b<count; b++)
        expected[slot_stream(legacy_slot)][slot_token(legacy_slot)][int'(legacy_offset)+b] =
            legacy_data[b*8 +: 8];
      if (int'(legacy_offset)+count == int'(row_bytes)) begin
        last_capture[legacy_slot] = cycle;
        legacy_rows++;
      end
    end
    if (dut.packed_valid) begin
      assert (dut.q_write || dut.kv_write) else $fatal(1, "UNIT_DROPPED_EMISSION");
      legacy_writes++;
      if (dut.packed_last) begin
        slot = int'(dut.packed_tag);
        assert (last_capture[slot] >= 0 && cycle == last_capture[slot]+2)
          else $fatal(1, "UNIT_FINAL_WRITE_LATENCY");
        latency_checks++;
        last_capture[slot] = -1;
      end
    end
    if (abort_write)
      assert (!dut.q_write && !dut.kv_write) else $fatal(1, "UNIT_ABORT_CONSUMED_WRITE");
    if (direct_valid && !abort_write) begin
      if (legacy_busy) q_direct_overlap++;
      for (int b=0; b<16; b++) if (direct_strb[b])
        expected[int'(direct_stream)][direct_token][int'(direct_offset)+b] = direct_data[b*8 +: 8];
      assert (direct_busy && dut.kv_write && dut.kv_write_data === direct_data &&
              dut.kv_write_strb === direct_strb && dut.kv_write_offset === direct_offset &&
              dut.kv_write_stream === direct_stream && dut.kv_write_token === direct_token)
        else $fatal(1, "UNIT_DIRECT_BYPASS");
      for (int bank=0; bank<8; bank++)
        assert ({dut.i_kv_store.bank_req[bank], dut.i_kv_store.bank_we[bank],
                 dut.i_kv_store.bank_addr[bank], dut.i_kv_store.bank_wdata[bank], dut.i_kv_store.bank_be[bank]} ===
                {old_v2.bank_req[bank], old_v2.bank_we[bank], old_v2.bank_addr[bank],
                 old_v2.bank_wdata[bank], old_v2.bank_be[bank]})
          else $fatal(1, "UNIT_DIRECT_BANK_CYCLE");
      direct_writes++;
    end
    if (compare_v2)
      assert ({column_busy, column_valid, column_cycle, direct_busy} ===
              {old_column_busy, old_column_valid, old_column_cycle, old_direct_busy})
        else $fatal(1, "UNIT_V2_CONTROL_LATENCY");
  end

  task automatic tick(input int n=1);
    repeat (n) @(negedge clk);
  endtask
  task automatic drain();
    int n;
    n = 0;
    while (busy || old_legacy_busy) begin
      tick(); n++;
      assert (n <= 4) else $fatal(1, "UNIT_WRITE_DRAIN_TIMEOUT");
    end
  endtask
  task automatic fragment(input int slot, offset, count, epoch);
    legacy_valid = 1;
    legacy_slot = 5'(slot);
    legacy_offset = 8'(offset);
    legacy_strb = 16'((1<<count)-1);
    legacy_data = '1;
    for (int b=0; b<count; b++)
      legacy_data[b*8 +: 8] = payload(epoch, slot_stream(slot), slot_token(slot), offset+b);
    tick();
    legacy_valid = 0;
  endtask
  task automatic fill_legacy(input int slot, bytes, alignment, epoch, gaps);
    int offset, count;
    row_bytes = 9'(bytes);
    offset = 0;
    while (offset < bytes) begin
      count = 16 - ((alignment+offset)%16);
      if (count > bytes-offset) count = bytes-offset;
      fragment(slot, offset, count, epoch);
      offset += count;
      if (gaps && offset < bytes && offset%32 == 16) tick(2);
    end
  endtask
  task automatic check_row(input int stream, token, word, input bit legacy, compare_old);
    logic [255:0] actual;
    assert (!busy && !old_legacy_busy) else $fatal(1, "UNIT_READ_BEFORE_DRAIN");
    read_word = 4'(word);
    if (legacy) begin
      legacy_read = 1;
      read_slot = 5'(stream*8+token);
    end else begin
      row_read = 1;
      row_stream = akv_stream_e'(stream);
      row_token = 6'(token);
    end
    @(posedge clk); #1;
    actual = legacy ? legacy_output : row_output;
    if (compare_old)
      assert (actual === (legacy ? old_legacy_output : old_row_output))
        else $fatal(1, "UNIT_ORIGINAL_ROW_MISMATCH stream=%0d token=%0d word=%0d", stream, token, word);
    for (int b=0; b<32; b++)
      assert (actual[b*8 +: 8] === expected[stream][token][word*32+b])
        else $fatal(1, "UNIT_ORACLE_ROW_MISMATCH stream=%0d token=%0d word=%0d byte=%0d", stream, token, word, b);
    row_checks++;
    tick(); legacy_read = 0; row_read = 0;
  endtask
  task automatic check_q();
    for (int token=0; token<8; token++)
      for (int word=0; word<8; word++) check_row(0, token, word, 1, 1);
  endtask
  task automatic fill_direct(input int stream, token, epoch);
    direct_stream = akv_stream_e'(stream);
    direct_token = 6'(token);
    for (int offset=0; offset<256; offset+=16) begin
      direct_valid = 1; direct_offset = 8'(offset);
      for (int b=0; b<16; b++) direct_data[b*8 +: 8] = payload(epoch, stream, token, offset+b);
      tick();
    end
    direct_valid = 0;
  endtask
  task automatic check_column(input int stream, tokens, dim, count);
    int elapsed;
    column_stream = akv_stream_e'(stream); token_count = 7'(tokens);
    dimension = 7'(dim); column_count = 3'(count); column_start = 1;
    tick(); column_start = 0;
    elapsed = 0;
    while (!column_valid) begin
      tick(); elapsed++;
      assert (elapsed <= 10) else $fatal(1, "UNIT_COLUMN_TIMEOUT");
    end
    assert (column_output === old_column_output) else $fatal(1, "UNIT_ORIGINAL_COLUMN_MISMATCH");
    for (int c=0; c<4; c++)
      for (int t=0; t<64; t++) begin
        if (c<count && t<tokens)
          assert (column_output[c][t*16 +: 16] ===
                  {expected[stream][t][(dim+c)*2+1], expected[stream][t][(dim+c)*2]})
            else $fatal(1, "UNIT_COLUMN_ORACLE");
        else assert (column_output[c][t*16 +: 16] === 16'b0)
          else $fatal(1, "UNIT_COLUMN_PADDING");
      end
    column_checks++;
  endtask
  task automatic abort_pending();
    assert (busy) else $fatal(1, "UNIT_NO_PENDING_ABORT");
    abort_write = 1;
    tick(); legacy_valid = 0; abort_write = 0;
    #1;
    assert (!busy) else $fatal(1, "UNIT_ABORT_DEADLOCK");
    tick(3);
    for (int word=0; word<8; word++) check_row(1,0,word,1,0);
    check_q();
    aborts++;
  endtask

  initial begin
    int tokens, dim;
    for (int i=0; i<24; i++) last_capture[i] = -1;
    tick(3); rst_n = 1; tick();
    // All 24 legacy slots at full length, chained without inter-row idle.
    for (int slot=0; slot<24; slot++) fill_legacy(slot,256,0,1,0);
    drain();
    for (int slot=0; slot<24; slot++)
      for (int word=0; word<8; word++) check_row(slot_stream(slot),slot_token(slot),word,1,1);
    // All even physical alignments, all row lengths, all Q/K/V mappings.
    // D96 is adapter coverage, not an extension to the legacy instruction ABI.
    for (int stream=0; stream<3; stream++)
      for (int length=128; length<=256; length+=64)
        for (int align=0; align<16; align+=2) begin
          fill_legacy(stream*8+align/2,length,align,2+length/64,1);
          drain();
          for (int word=0; word<8; word++) check_row(stream,align/2,word,1,1);
        end

    // V2 Q still occupies the separate eight-row Q store. K/V do not touch it.
    for (int token=0; token<8; token++) fill_legacy(token,192,0,7,0);
    // No artificial drain between final Q input and first direct K input.
    compare_v2 = 1;
    for (int stream=1; stream<=2; stream++)
      for (int token=0; token<64; token++) fill_direct(stream,token,8);
    #1;
    assert (!busy) else $fatal(1, "UNIT_DIRECT_ADDED_LATENCY");
    check_q();
    for (int stream=1; stream<=2; stream++)
      for (int token=0; token<64; token++)
        for (int word=0; word<8; word++) check_row(stream,token,word,0,1);
    // These low-token reads must see the SAME KV bytes through legacy addressing.
    for (int stream=1; stream<=2; stream++)
      for (int token=0; token<8; token++)
        for (int word=0; word<8; word++) check_row(stream,token,word,1,0);
    for (int stream=1; stream<=2; stream++)
      for (int tail=0; tail<6; tail++) begin
        case (tail)
          0: tokens=1; 1: tokens=7; 2: tokens=8; 3: tokens=9; 4: tokens=63; 5: tokens=64;
        endcase
        for (int d=0; d<6; d++) begin
          case (d)
            0: dim=0; 1: dim=12; 2: dim=16; 3: dim=60; 4: dim=124; 5: dim=15;
          endcase
          check_column(stream,tokens,dim,d==5 ? 1 : 4);
        end
      end
    compare_v2 = 0;

    // Failed REFILL: no Q writes, incomplete pending K fragments must abort.
    record_legacy = 0;
    for (int count=2; count<16; count+=2) begin
      row_bytes = 256; fragment(8,0,count,9); tick(2);
      abort_pending();
    end
    // Mask an older registered emission while also clearing its younger stage.
    fragment(8,0,16,10); fragment(8,16,16,10);
    assert (dut.packed_valid) else $fatal(1, "UNIT_MISSING_REGISTERED_EMIT");
    abort_pending();
    // Abort cannot roll back a write already consumed at an earlier edge.
    record_legacy = 1;
    fragment(8,0,16,11); tick(3);
    record_legacy = 0;
    fragment(8,16,6,11); tick(2); abort_pending();
    // Complete a new row after fault cleanup, with the original reference again.
    record_legacy = 1;
    fill_legacy(8,256,14,12,1); drain();
    for (int word=0; word<8; word++) check_row(1,0,word,1,1);
    check_q();
    assert (legacy_rows==105 && latency_checks==105 && legacy_writes==1361 &&
            direct_writes==2048 && row_checks==2704 && column_checks==72 && aborts==9 &&
            q_direct_overlap==2)
      else $fatal(1, "UNIT_TOTALS rows=%0d latency=%0d writes=%0d direct=%0d replay=%0d columns=%0d aborts=%0d",
                  legacy_rows,latency_checks,legacy_writes,direct_writes,row_checks,column_checks,aborts);
    $display("UNIFIED_STORAGE_PASS legacy_rows=105 latency_checks=105 legacy_writes=1361 direct_writes=2048 row_checks=2704 column_checks=72 aborts=9 q_direct_overlap=2 q_bytes=2048 kv_bytes=32768");
    $finish;
  end
  initial begin
    #500000;
    $fatal(1, "UNIFIED_STORAGE_TIMEOUT");
  end
endmodule
