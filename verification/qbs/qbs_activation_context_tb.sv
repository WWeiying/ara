`timescale 1ns/1ps

module qbs_activation_context_tb;
  import qbs_pkg::*;

  logic clk;
  logic rst_n;

  logic fill_begin;
  logic [3:0] fill_context_id;
  logic [7:0] fill_generation;
  qbs_activation_profile_e fill_profile;
  qbs_activation_layout_e fill_layout;
  logic [2:0] fill_m;
  logic [8:0] fill_k_blocks;
  logic fill_write_valid;
  logic [7:0] fill_write_k_block;
  logic [10:0] fill_write_offset;
  logic [127:0] fill_write_data;
  logic [15:0] fill_write_strb;
  logic fill_block_complete;
  logic [7:0] fill_complete_k_block;
  logic fill_commit;
  logic fill_abort;

  logic lookup_valid;
  logic [3:0] lookup_context_id;
  logic [7:0] lookup_generation;
  qbs_activation_profile_e lookup_profile;
  qbs_activation_layout_e lookup_layout;
  logic [2:0] lookup_m;
  logic [8:0] lookup_k_blocks;
  logic lookup_match;
  qbs_validation_error_e lookup_error;

  logic release_context;
  logic replay_start_valid;
  logic replay_start_ready;
  logic [7:0] replay_k_block;
  logic replay_data_valid;
  logic replay_data_ready;
  logic [127:0] replay_data;
  logic [15:0] replay_strb;
  logic [10:0] replay_offset;
  logic replay_last;
  logic replay_done;
  logic replay_busy;
  logic context_valid;
  logic fill_in_progress;
  logic fill_ready_to_commit;

  always #5 clk = ~clk;

  qbs_activation_context dut (
    .clk_i                       (clk),
    .rst_ni                      (rst_n),
    .fill_begin_i                (fill_begin),
    .fill_context_id_i           (fill_context_id),
    .fill_generation_i           (fill_generation),
    .fill_profile_i              (fill_profile),
    .fill_layout_i               (fill_layout),
    .fill_m_i                    (fill_m),
    .fill_k_blocks_i             (fill_k_blocks),
    .fill_write_valid_i          (fill_write_valid),
    .fill_write_k_block_i        (fill_write_k_block),
    .fill_write_offset_i         (fill_write_offset),
    .fill_write_data_i           (fill_write_data),
    .fill_write_strb_i           (fill_write_strb),
    .fill_block_complete_i       (fill_block_complete),
    .fill_complete_k_block_i     (fill_complete_k_block),
    .fill_commit_i               (fill_commit),
    .fill_abort_i                (fill_abort),
    .lookup_valid_i              (lookup_valid),
    .lookup_context_id_i         (lookup_context_id),
    .lookup_generation_i         (lookup_generation),
    .lookup_profile_i            (lookup_profile),
    .lookup_layout_i             (lookup_layout),
    .lookup_m_i                  (lookup_m),
    .lookup_k_blocks_i           (lookup_k_blocks),
    .lookup_match_o              (lookup_match),
    .lookup_error_o              (lookup_error),
    .release_i                   (release_context),
    .replay_start_valid_i        (replay_start_valid),
    .replay_start_ready_o        (replay_start_ready),
    .replay_k_block_i            (replay_k_block),
    .replay_data_valid_o         (replay_data_valid),
    .replay_data_ready_i         (replay_data_ready),
    .replay_data_o               (replay_data),
    .replay_strb_o               (replay_strb),
    .replay_offset_o             (replay_offset),
    .replay_last_o               (replay_last),
    .replay_done_o               (replay_done),
    .replay_busy_o               (replay_busy),
    .context_valid_o             (context_valid),
    .fill_in_progress_o          (fill_in_progress),
    .fill_ready_to_commit_o      (fill_ready_to_commit)
  );

  function automatic logic [7:0] expected_byte(
      input int unsigned block, input int unsigned offset);
    return 8'((block * 8'h61 + offset * 8'h17 + 8'h3d) & 8'hff);
  endfunction

  task automatic pulse_fill_begin(input logic [7:0] generation,
                                  input int unsigned blocks);
    @(negedge clk);
    fill_generation = generation;
    fill_k_blocks = 9'(blocks);
    fill_begin = 1'b1;
    @(negedge clk);
    fill_begin = 1'b0;
    if (!fill_in_progress || context_valid)
      $fatal(1, "FILL did not start atomically");
  endtask

  task automatic write_chunk(input int unsigned block,
                             input int unsigned offset,
                             input int unsigned bytes);
    @(negedge clk);
    fill_write_k_block = 8'(block);
    fill_write_offset = 11'(offset);
    fill_write_data = '0;
    fill_write_strb = '0;
    for (int unsigned lane = 0; lane < bytes; lane++) begin
      fill_write_data[lane * 8 +: 8] = expected_byte(block, offset + lane);
      fill_write_strb[lane] = 1'b1;
    end
    fill_write_valid = 1'b1;
    @(negedge clk);
    fill_write_valid = 1'b0;
  endtask

  task automatic fill_block(input int unsigned block,
                            input int unsigned first_chunk);
    automatic int unsigned offset = 0;
    automatic int unsigned bytes = first_chunk;
    while (offset < QbsQ8KBlockBytes) begin
      if (bytes > QbsQ8KBlockBytes - offset)
        bytes = QbsQ8KBlockBytes - offset;
      write_chunk(block, offset, bytes);
      offset += bytes;
      bytes = 16;
    end
    @(negedge clk);
    fill_complete_k_block = 8'(block);
    fill_block_complete = 1'b1;
    @(negedge clk);
    fill_block_complete = 1'b0;
  endtask

  task automatic check_lookup(input logic [7:0] generation,
                              input int unsigned blocks,
                              input logic expected_match,
                              input qbs_validation_error_e expected_error);
    lookup_generation = generation;
    lookup_k_blocks = 9'(blocks);
    lookup_valid = 1'b1;
    #1;
    if (lookup_match != expected_match || lookup_error != expected_error)
      $fatal(1, "lookup mismatch match=%0b/%0b error=%0d/%0d",
             lookup_match, expected_match, lookup_error, expected_error);
    lookup_valid = 1'b0;
  endtask

  task automatic replay_and_check(input int unsigned block);
    automatic int unsigned accepted_bytes = 0;
    automatic int unsigned ready_cycle = 0;
    @(negedge clk);
    replay_k_block = 8'(block);
    replay_start_valid = 1'b1;
    while (!replay_start_ready) @(negedge clk);
    @(negedge clk);
    replay_start_valid = 1'b0;

    while (!replay_done) begin
      replay_data_ready = (ready_cycle % 3) != 1;
      @(posedge clk);
      if (replay_data_valid && replay_data_ready) begin
        for (int unsigned lane = 0; lane < 16; lane++) begin
          const int unsigned offset = unsigned'(replay_offset) + lane;
          const logic expected_valid = offset < QbsQ8KBlockBytes;
          if (replay_strb[lane] != expected_valid)
            $fatal(1, "replay strobe mismatch block=%0d offset=%0d",
                   block, offset);
          if (expected_valid && replay_data[lane * 8 +: 8] !=
                                expected_byte(block, offset))
            $fatal(1, "replay data mismatch block=%0d offset=%0d got=%02x",
                   block, offset, replay_data[lane * 8 +: 8]);
          if (expected_valid) accepted_bytes++;
        end
        if (replay_last !=
            (unsigned'(replay_offset) + 16 >= QbsQ8KBlockBytes))
          $fatal(1, "replay last mismatch at offset %0d", replay_offset);
      end
      @(negedge clk);
      ready_cycle++;
    end
    replay_data_ready = 1'b0;
    if (accepted_bytes != QbsQ8KBlockBytes)
      $fatal(1, "replay byte count got=%0d expected=%0d",
             accepted_bytes, QbsQ8KBlockBytes);
  endtask

  initial begin
    clk = 1'b0;
    rst_n = 1'b0;
    fill_begin = 1'b0;
    fill_context_id = '0;
    fill_generation = '0;
    fill_profile = QBS_ACTIVATION_PROFILE_Q8_K;
    fill_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    fill_m = 3'd1;
    fill_k_blocks = '0;
    fill_write_valid = 1'b0;
    fill_write_k_block = '0;
    fill_write_offset = '0;
    fill_write_data = '0;
    fill_write_strb = '0;
    fill_block_complete = 1'b0;
    fill_complete_k_block = '0;
    fill_commit = 1'b0;
    fill_abort = 1'b0;
    lookup_valid = 1'b0;
    lookup_context_id = '0;
    lookup_generation = '0;
    lookup_profile = QBS_ACTIVATION_PROFILE_Q8_K;
    lookup_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    lookup_m = 3'd1;
    lookup_k_blocks = '0;
    release_context = 1'b0;
    replay_start_valid = 1'b0;
    replay_k_block = '0;
    replay_data_ready = 1'b0;

    repeat (3) @(negedge clk);
    rst_n = 1'b1;

    pulse_fill_begin(8'h35, 2);
    fill_block(0, 12);
    if (fill_ready_to_commit)
      $fatal(1, "context became complete before all blocks arrived");
    fill_block(1, 8);
    if (!fill_ready_to_commit)
      $fatal(1, "complete context was not committable");
    @(negedge clk);
    fill_commit = 1'b1;
    @(negedge clk);
    fill_commit = 1'b0;
    if (!context_valid || fill_in_progress)
      $fatal(1, "context commit failed");

    check_lookup(8'h35, 2, 1'b1, QBS_VALIDATION_OK);
    check_lookup(8'h36, 2, 1'b0, QBS_VALIDATION_CONTEXT_GENERATION);

    lookup_context_id = 4'd1;
    check_lookup(8'h35, 2, 1'b0, QBS_VALIDATION_CONTEXT_INVALID);
    lookup_context_id = 4'd0;

    lookup_profile = QBS_ACTIVATION_PROFILE_Q8_0;
    check_lookup(8'h35, 2, 1'b0, QBS_VALIDATION_CONTEXT_METADATA);
    lookup_profile = QBS_ACTIVATION_PROFILE_Q8_K;

    lookup_layout = QBS_ACTIVATION_LAYOUT_M4_INTERLEAVED;
    check_lookup(8'h35, 2, 1'b0, QBS_VALIDATION_CONTEXT_METADATA);
    lookup_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;

    lookup_m = 3'd2;
    check_lookup(8'h35, 2, 1'b0, QBS_VALIDATION_CONTEXT_METADATA);
    lookup_m = 3'd1;

    check_lookup(8'h35, 1, 1'b0, QBS_VALIDATION_CONTEXT_METADATA);
    replay_and_check(0);
    replay_and_check(1);

    @(negedge clk);
    release_context = 1'b1;
    @(negedge clk);
    release_context = 1'b0;
    check_lookup(8'h35, 2, 1'b0, QBS_VALIDATION_CONTEXT_INVALID);

    pulse_fill_begin(8'h36, 1);
    fill_block(0, 4);
    @(negedge clk);
    fill_abort = 1'b1;
    @(negedge clk);
    fill_abort = 1'b0;
    if (fill_in_progress || context_valid)
      $fatal(1, "aborted FILL left a reusable context");

    $display("QBS activation context PASS");
    $finish;
  end

endmodule : qbs_activation_context_tb
