`timescale 1ns/1ps

module qbs_activation_tile_context_tb;
  import qbs_pkg::*;

  localparam int CapacityBytes = 4672;
  localparam int MaxBlocks = 32;
  localparam int MaxPayload = 2336;
  localparam int ReplayTimeout = 2048;

  logic clk = 0;
  logic rst_n = 0;
  logic fill_begin = 0;
  logic [3:0] fill_context_id = 0;
  logic [7:0] fill_generation = 0;
  qbs_activation_profile_e fill_profile = QBS_ACTIVATION_PROFILE_Q8_K;
  qbs_activation_layout_e fill_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  logic [3:0] fill_m = 1;
  logic [8:0] fill_k_blocks = 1;
  logic fill_write_valid = 0;
  logic [7:0] fill_write_k_block = 0;
  logic [11:0] fill_write_offset = 0;
  logic [127:0] fill_write_data = 0;
  logic [15:0] fill_write_strb = 0;
  logic fill_block_complete = 0;
  logic [7:0] fill_complete_k_block = 0;
  logic fill_commit = 0;
  logic fill_abort = 0;
  logic lookup_valid = 0;
  logic [3:0] lookup_context_id = 0;
  logic [7:0] lookup_generation = 0;
  qbs_activation_profile_e lookup_profile = QBS_ACTIVATION_PROFILE_Q8_K;
  qbs_activation_layout_e lookup_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
  logic [3:0] lookup_m = 1;
  logic [8:0] lookup_k_blocks = 1;
  logic lookup_match;
  qbs_validation_error_e lookup_error;
  logic release_context = 0;
  logic replay_start_valid = 0;
  logic replay_abort = 0;
  logic replay_start_ready;
  logic [7:0] replay_k_block = 0;
  logic replay_data_valid;
  logic replay_data_ready = 0;
  logic [127:0] replay_data;
  logic [15:0] replay_strb;
  logic [11:0] replay_offset;
  logic replay_last, replay_done, replay_busy;
  logic context_valid, fill_in_progress, fill_ready_to_commit;

  // Logical [K][byte] storage: no DUT hierarchy, bank mapping or address helper.
  logic [7:0] golden [MaxBlocks][MaxPayload];
  bit written [MaxBlocks][MaxPayload];
  qbs_activation_profile_e model_profile;
  qbs_activation_layout_e model_layout;
  int model_m, model_blocks, model_payload, model_seed;
  logic [7:0] model_generation;
  int case_count = 0;
  int replay_count = 0;
  int checked_bytes = 0;
  int stalled_cycles = 0;
  int stalled_last_cycles = 0;
  int full_capacity_cases = 0;
  int max_k_cases = 0;
  int high_offset_beats = 0;
  bit [7:0] first_chunk_seen = 0;

  always #5 clk = ~clk;

  qbs_activation_context #(.ExtendedShapes(1'b1)) dut (
    .clk_i(clk), .rst_ni(rst_n),
    .fill_begin_i(fill_begin), .fill_context_id_i(fill_context_id),
    .fill_generation_i(fill_generation), .fill_profile_i(fill_profile),
    .fill_layout_i(fill_layout), .fill_m_i(fill_m),
    .fill_k_blocks_i(fill_k_blocks), .fill_write_valid_i(fill_write_valid),
    .fill_write_k_block_i(fill_write_k_block),
    .fill_write_offset_i(fill_write_offset), .fill_write_data_i(fill_write_data),
    .fill_write_strb_i(fill_write_strb),
    .fill_block_complete_i(fill_block_complete),
    .fill_complete_k_block_i(fill_complete_k_block),
    .fill_commit_i(fill_commit), .fill_abort_i(fill_abort),
    .lookup_valid_i(lookup_valid), .lookup_context_id_i(lookup_context_id),
    .lookup_generation_i(lookup_generation), .lookup_profile_i(lookup_profile),
    .lookup_layout_i(lookup_layout), .lookup_m_i(lookup_m),
    .lookup_k_blocks_i(lookup_k_blocks), .lookup_match_o(lookup_match),
    .lookup_error_o(lookup_error), .release_i(release_context),
    .replay_start_valid_i(replay_start_valid),
    .replay_abort_i(replay_abort),
    .replay_start_ready_o(replay_start_ready), .replay_k_block_i(replay_k_block),
    .replay_data_valid_o(replay_data_valid), .replay_data_ready_i(replay_data_ready),
    .replay_data_o(replay_data), .replay_strb_o(replay_strb),
    .replay_offset_o(replay_offset), .replay_last_o(replay_last),
    .replay_done_o(replay_done), .replay_busy_o(replay_busy),
    .context_valid_o(context_valid), .fill_in_progress_o(fill_in_progress),
    .fill_ready_to_commit_o(fill_ready_to_commit)
  );

  function automatic int payload_size(input qbs_activation_profile_e profile,
                                      input qbs_activation_layout_e layout,
                                      input int m);
    int bytes_per_row;
    case (profile)
      QBS_ACTIVATION_PROFILE_Q8_K: bytes_per_row = 292;
      QBS_ACTIVATION_PROFILE_Q8_0: bytes_per_row = 34;
      default: $fatal(1, "TB unsupported profile");
    endcase
    case (layout)
      QBS_ACTIVATION_LAYOUT_ROW_MAJOR:
        if (m == 1) return bytes_per_row;
      QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED:
        if (m == 4) return 4 * bytes_per_row;
      QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED:
        if (m >= 5 && m <= 8) return 8 * bytes_per_row;
      default: ;
    endcase
    $fatal(1, "TB unsupported layout/M");
    return 0;
  endfunction

  function automatic logic [7:0] pattern_byte(input int block,
                                             input int offset,
                                             input int seed);
    logic [31:0] value;
    // Mix high address bits too: an 8-bit ramp would hide 256-byte aliasing.
    value = 32'(seed) ^ (32'(block + 1) * 32'h9e3779b9) ^
            (32'(offset + 1) * 32'h85ebca6b);
    value = (value ^ (value >> 16)) * 32'h7feb352d;
    value = (value ^ (value >> 15)) * 32'h846ca68b;
    value ^= value >> 16;
    return value[7:0];
  endfunction

  task automatic set_lookup;
    lookup_context_id = 0;
    lookup_generation = model_generation;
    lookup_profile = model_profile;
    lookup_layout = model_layout;
    lookup_m = 4'(model_m);
    lookup_k_blocks = 9'(model_blocks);
  endtask

  task automatic expect_lookup(input bit match,
                               input qbs_validation_error_e error_code);
    lookup_valid = 1;
    #1;
    if (lookup_match !== match || lookup_error !== error_code)
      $fatal(1, "lookup case=%0d match=%b/%b error=%0d/%0d",
             case_count, lookup_match, match, lookup_error, error_code);
    lookup_valid = 0;
    #1;
    if (lookup_match !== 1'b0 || lookup_error !== QBS_VALIDATION_OK)
      $fatal(1, "inactive lookup has result/error");
  endtask

  task automatic begin_fill(input qbs_activation_profile_e profile,
                             input qbs_activation_layout_e layout,
                             input int m, input int blocks, input int seed);
    model_payload = payload_size(profile, layout, m);
    if (blocks < 1 || blocks > MaxBlocks || model_payload * blocks > CapacityBytes)
      $fatal(1, "TB attempted inadmissible shape");
    model_profile = profile;
    model_layout = layout;
    model_m = m;
    model_blocks = blocks;
    model_seed = seed;
    model_generation = 8'(seed);
    for (int k = 0; k < blocks; k++)
      for (int b = 0; b < model_payload; b++) begin
        golden[k][b] = pattern_byte(k, b, seed);
        written[k][b] = 0;
      end
    @(negedge clk);
    fill_context_id = 0;
    fill_generation = model_generation;
    fill_profile = profile;
    fill_layout = layout;
    fill_m = 4'(m);
    fill_k_blocks = 9'(blocks);
    fill_begin = 1;
    @(negedge clk);
    fill_begin = 0;
    if (fill_in_progress !== 1'b1 || context_valid !== 1'b0 ||
        fill_ready_to_commit !== 1'b0 || replay_start_ready !== 1'b0)
      $fatal(1, "begin did not invalidate old context/reset completion bits");
    // Change idle ports to prove metadata is captured at begin, not at commit.
    fill_context_id = 15;
    fill_generation = ~model_generation;
    fill_profile = profile == QBS_ACTIVATION_PROFILE_Q8_K
        ? QBS_ACTIVATION_PROFILE_Q8_0 : QBS_ACTIVATION_PROFILE_Q8_K;
    fill_layout = layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
        ? QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED : QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    fill_m = m == 8 ? 1 : 8;
    fill_k_blocks = blocks == 32 ? 1 : 32;
    set_lookup();
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
    @(negedge clk);
  endtask

  // Caller is on a negedge. Consecutive calls exercise back-to-back SRAM writes.
  task automatic write_piece(input int block, input int offset,
                              input logic [15:0] mask, input bit patch_data);
    if (block < 0 || block >= model_blocks || offset < 0 || offset % 2 != 0)
      $fatal(1, "TB bad write coordinate");
    for (int pair = 0; pair < 8; pair++)
      if (!(mask[pair*2 +: 2] inside {2'b00, 2'b11}))
        $fatal(1, "TB bad halfword mask");
    fill_write_k_block = 8'(block);
    fill_write_offset = 12'(offset);
    fill_write_data = {16{8'hd7}};
    fill_write_strb = mask;
    for (int lane = 0; lane < 16; lane++)
      if (mask[lane]) begin
        if (offset + lane >= model_payload) $fatal(1, "TB write outside payload");
        if (patch_data)
          golden[block][offset + lane] =
              pattern_byte(block, offset + lane, model_seed ^ 32'h5432ab19);
        fill_write_data[lane*8 +: 8] = golden[block][offset + lane];
        written[block][offset + lane] = 1;
      end
    fill_write_valid = 1;
    @(negedge clk);
    fill_write_valid = 0;
  endtask

  task automatic fill_block(input int block, input int first_chunk);
    int offset, bytes;
    logic [15:0] mask;
    offset = 0;
    bytes = first_chunk;
    first_chunk_seen[first_chunk/2 - 1] = 1;
    while (offset < model_payload) begin
      if (bytes > model_payload - offset) bytes = model_payload - offset;
      mask = 16'((32'h1 << bytes) - 1);
      write_piece(block, offset, mask, 0);
      offset += bytes;
      bytes = 16;
    end
    // Disabled halfwords carry poison; selected halfwords must not damage peers.
    write_piece(block, 2, 16'h3333, 1);
    write_piece(block, model_payload - 2, 16'h0003, 1);
    for (int b = 0; b < model_payload; b++)
      if (!written[block][b]) $fatal(1, "TB incomplete byte scoreboard");
    fill_complete_k_block = 8'(block);
    fill_block_complete = 1;
    @(negedge clk);
    fill_block_complete = 0;
  endtask

  task automatic commit_fill;
    if (fill_ready_to_commit !== 1'b1 || context_valid !== 1'b0)
      $fatal(1, "complete fill not ready, or published before commit");
    fill_commit = 1;
    @(negedge clk);
    fill_commit = 0;
    if (context_valid !== 1'b1 || fill_in_progress !== 1'b0 ||
        fill_ready_to_commit !== 1'b0)
      $fatal(1, "commit state mismatch");
    set_lookup();
    expect_lookup(1, QBS_VALIDATION_OK);
  endtask

  task automatic check_metadata;
    set_lookup();
    lookup_generation ^= 8'h80;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_GENERATION);
    set_lookup();
    lookup_context_id = 1;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
    set_lookup();
    lookup_profile = model_profile == QBS_ACTIVATION_PROFILE_Q8_K
        ? QBS_ACTIVATION_PROFILE_Q8_0 : QBS_ACTIVATION_PROFILE_Q8_K;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_METADATA);
    set_lookup();
    lookup_layout = model_layout == QBS_ACTIVATION_LAYOUT_ROW_MAJOR
        ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED : QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_METADATA);
    set_lookup();
    lookup_m = model_m == 8 ? 5 : 8;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_METADATA);
    set_lookup();
    lookup_k_blocks = model_blocks == 32 ? 31 : model_blocks + 1;
    expect_lookup(0, QBS_VALIDATION_CONTEXT_METADATA);
    set_lookup();
    expect_lookup(1, QBS_VALIDATION_OK);
  endtask

  task automatic start_replay(input int block);
    int cycles;
    cycles = 0;
    @(negedge clk);
    replay_k_block = 8'(block);
    replay_start_valid = 1;
    while (replay_start_ready !== 1'b1) begin
      if (cycles++ >= 32) $fatal(1, "replay start timeout");
      @(negedge clk);
    end
    @(negedge clk);
    replay_start_valid = 0;
    replay_k_block = 8'hff;
  endtask

  task automatic replay_and_check(input int block, input bit backpressure);
    int accepted, cycles, last_stalls, valid_bytes;
    bit held, last_fire;
    logic [127:0] held_data;
    logic [15:0] held_strb, expected_strb;
    logic [11:0] held_offset;
    logic held_last;
    accepted = 0;
    cycles = 0;
    last_stalls = 0;
    held = 0;
    replay_data_ready = 0;
    start_replay(block);
    forever begin
      if (cycles++ >= ReplayTimeout) $fatal(1, "replay timeout block=%0d", block);
      replay_data_ready = !backpressure || (cycles % 5 >= 3);
      if (backpressure && replay_data_valid === 1'b1 &&
          replay_last === 1'b1 && last_stalls < 3) begin
        replay_data_ready = 0;
        last_stalls++;
      end
      @(posedge clk);
      if (held && (replay_data_valid !== 1'b1 || replay_data !== held_data ||
                   replay_strb !== held_strb || replay_offset !== held_offset ||
                   replay_last !== held_last))
        $fatal(1, "backpressured replay changed block=%0d accepted=%0d", block, accepted);
      if (replay_data_valid !== 1'b0 && replay_data_valid !== 1'b1)
        $fatal(1, "unknown replay valid");
      last_fire = 0;
      held = replay_data_valid === 1'b1 && !replay_data_ready;
      if (replay_data_valid === 1'b1) begin
        if (replay_busy !== 1'b1 || replay_start_ready !== 1'b0)
          $fatal(1, "replay ownership lost before last handshake");
        if (accepted >= model_payload || replay_offset !== 12'(accepted))
          $fatal(1, "offset sequence block=%0d got=%0d expected=%0d",
                 block, replay_offset, accepted);
        valid_bytes = model_payload - accepted;
        if (valid_bytes > 16) valid_bytes = 16;
        expected_strb = 16'((32'h1 << valid_bytes) - 1);
        if (replay_strb !== expected_strb ||
            replay_last !== (accepted + valid_bytes == model_payload))
          $fatal(1, "replay mask/last mismatch block=%0d offset=%0d", block, accepted);
        for (int lane = 0; lane < valid_bytes; lane++)
          if (replay_data[lane*8 +: 8] !== golden[block][accepted + lane])
            $fatal(1, "byte mismatch case=%0d K=%0d byte=%0d got=%02x expected=%02x",
                   case_count, block, accepted + lane,
                   replay_data[lane*8 +: 8], golden[block][accepted + lane]);
        if (held) begin
          held_data = replay_data;
          held_strb = replay_strb;
          held_offset = replay_offset;
          held_last = replay_last;
          stalled_cycles++;
          if (replay_last) stalled_last_cycles++;
        end else begin
          if (accepted >= 2048) high_offset_beats++;
          accepted += valid_bytes;
          checked_bytes += valid_bytes;
          last_fire = replay_last;
        end
      end
      #1;
      if (replay_done !== last_fire)
        $fatal(1, "done must pulse exactly after final handshake");
      if (last_fire) break;
      @(negedge clk);
    end
    if (accepted != model_payload || (backpressure && last_stalls != 3))
      $fatal(1, "incomplete replay/backpressure exercise");
    @(negedge clk);
    replay_data_ready = 0;
    repeat (2) begin
      @(posedge clk);
      #1;
      if (replay_done !== 1'b0 || replay_busy !== 1'b0 ||
          replay_data_valid !== 1'b0 || context_valid !== 1'b1)
        $fatal(1, "replay did not drain or destroyed resident context");
    end
    replay_count++;
  endtask

  task automatic release_and_check;
    @(negedge clk);
    release_context = 1;
    @(negedge clk);
    release_context = 0;
    if (context_valid !== 1'b0) $fatal(1, "release kept context valid");
    set_lookup();
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
  endtask

  task automatic abort_replay_and_retry(input bit at_last);
    int cycles;
    replay_data_ready = 0;
    start_replay(0);
    cycles = 0;
    // Stop either the first returned beat or the final, unconsumed beat.
    while (!(replay_data_valid && (!at_last || replay_last))) begin
      if (cycles++ >= ReplayTimeout) $fatal(1, "abort replay setup timeout");
      replay_data_ready = at_last && !replay_last;
      @(negedge clk);
    end
    replay_data_ready = 0;
    @(negedge clk);
    replay_abort = 1;
    @(negedge clk);
    replay_abort = 0;
    if (replay_busy !== 1'b0 || replay_done !== 1'b0 ||
        replay_data_valid !== 1'b0 || context_valid !== 1'b1)
      $fatal(1, "replay abort retained transient state or retired context");
    set_lookup();
    expect_lookup(1, QBS_VALIDATION_OK);
    replay_and_check(0, 1);
  endtask

  task automatic abort_and_check;
    @(negedge clk);
    fill_abort = 1;
    @(negedge clk);
    fill_abort = 0;
    if (context_valid !== 1'b0 || fill_in_progress !== 1'b0 ||
        fill_ready_to_commit !== 1'b0)
      $fatal(1, "abort retained fill/context state");
    set_lookup();
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
  endtask

  task automatic reset_and_check;
    @(negedge clk);
    rst_n = 0;
    fill_begin = 0;
    fill_write_valid = 0;
    fill_block_complete = 0;
    fill_commit = 0;
    fill_abort = 0;
    release_context = 0;
    replay_start_valid = 0;
    replay_abort = 0;
    replay_data_ready = 0;
    lookup_valid = 0;
    repeat (3) @(negedge clk);
    if (context_valid !== 1'b0 || fill_in_progress !== 1'b0 ||
        fill_ready_to_commit !== 1'b0 || replay_data_valid !== 1'b0 ||
        replay_busy !== 1'b0 || replay_done !== 1'b0)
      $fatal(1, "reset retained context/fill/replay state");
    rst_n = 1;
    repeat (2) @(negedge clk);
    if (replay_start_ready !== 1'b1 || replay_data_valid !== 1'b0 ||
        replay_done !== 1'b0) $fatal(1, "stale response after reset");
  endtask

  task automatic run_case(input qbs_activation_profile_e profile,
                           input qbs_activation_layout_e layout,
                           input int m, input int blocks, input int first_chunk,
                           input bit reverse_k);
    int block;
    case_count++;
    begin_fill(profile, layout, m, blocks, 32'h1c03 + case_count * 131);
    for (int index = 0; index < blocks; index++) begin
      block = reverse_k ? blocks - 1 - index : index;
      fill_block(block, first_chunk);
      if (fill_ready_to_commit !== (index == blocks - 1) || context_valid !== 1'b0)
        $fatal(1, "completion bitmap/premature publication case=%0d K=%0d", case_count, block);
    end
    commit_fill();
    check_metadata();
    abort_replay_and_retry(0);
    abort_replay_and_retry(1);
    for (int k = blocks - 1; k >= 0; k--) replay_and_check(k, 1);
    for (int k = 0; k < blocks; k++) replay_and_check(k, 0);
    if (model_payload * blocks == CapacityBytes) full_capacity_cases++;
    if (blocks == MaxBlocks) max_k_cases++;
    $display("tile context case=%0d profile=%0d layout=%0d M=%0d K=%0d bytes=%0d first=%0d reverse=%0d",
             case_count, profile, layout, m, blocks, model_payload * blocks, first_chunk, reverse_k);
  endtask

  initial begin : test
    qbs_activation_profile_e profile;
    qbs_activation_layout_e layout;
    int m, blocks, timeout_cycles;
    reset_and_check();
    // Each supported tuple gets K=1 and its capacity/maxK boundary, with all
    // even initial beat lengths. Invalid shapes belong to decoder admission.
    for (int p = 0; p < 2; p++) begin
      profile = p == 0 ? QBS_ACTIVATION_PROFILE_Q8_K : QBS_ACTIVATION_PROFILE_Q8_0;
      for (int shape = 0; shape < 6; shape++) begin
        m = shape == 0 ? 1 : shape + 3;
        layout = m == 1 ? QBS_ACTIVATION_LAYOUT_ROW_MAJOR :
                 m == 4 ? QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED :
                          QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED;
        blocks = CapacityBytes / payload_size(profile, layout, m);
        if (blocks > MaxBlocks) blocks = MaxBlocks;
        for (int first = 2; first <= 16; first += 2) begin
          run_case(profile, layout, m, 1, first, 0);
          release_and_check();
          run_case(profile, layout, m, blocks, first, (first % 4) == 2);
        end
      end
    end
    if (case_count != 192) $fatal(1, "shape matrix incomplete");
    run_case(QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 28, 2, 1);
    run_case(QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 3, 6, 1);
    run_case(QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 16, 14, 1);

    begin_fill(QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 2, 811);
    write_piece(1, 2334, 16'h0003, 0);
    abort_and_check();
    run_case(QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 32, 2, 1);
    release_and_check();
    begin_fill(QBS_ACTIVATION_PROFILE_Q8_0, QBS_ACTIVATION_LAYOUT_ROW_MAJOR, 1, 1, 812);
    fill_block(0, 16);
    if (fill_ready_to_commit !== 1'b1) $fatal(1, "complete-abort setup failed");
    abort_and_check();

    begin_fill(QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 4, 813);
    fill_block(3, 2);
    reset_and_check();
    set_lookup();
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
    run_case(QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED, 4, 4, 14, 1);
    start_replay(3);
    timeout_cycles = 0;
    while (replay_data_valid !== 1'b1) begin
      if (timeout_cycles++ >= 32) $fatal(1, "reset-during-replay setup timeout");
      @(negedge clk);
    end
    repeat (3) @(negedge clk);
    reset_and_check();
    set_lookup();
    expect_lookup(0, QBS_VALIDATION_CONTEXT_INVALID);
    run_case(QBS_ACTIVATION_PROFILE_Q8_K, QBS_ACTIVATION_LAYOUT_M8_INTERLEAVED, 8, 2, 2, 1);
    release_and_check();

    if (case_count != 198 || first_chunk_seen != 8'hff || full_capacity_cases == 0 ||
        max_k_cases == 0 || high_offset_beats == 0 || stalled_cycles == 0 ||
        stalled_last_cycles == 0 || replay_count == 0 || checked_bytes == 0)
      $fatal(1, "required coverage missing");
    $display("QBS activation tile context PASS: cases=%0d replays=%0d bytes=%0d full=%0d maxK=%0d high_offset=%0d stalls=%0d last_stalls=%0d",
             case_count, replay_count, checked_bytes, full_capacity_cases,
             max_k_cases, high_offset_beats, stalled_cycles, stalled_last_cycles);
    $finish;
  end

  initial begin
    repeat (2000000) @(posedge clk);
    $fatal(1, "tile context global watchdog");
  end
endmodule
