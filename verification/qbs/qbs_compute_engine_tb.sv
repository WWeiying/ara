`timescale 1ns/1ps

module qbs_compute_engine_tb;
  import qbs_pkg::*;
  import fpnew_pkg::*;

  logic clk;
  logic rst_n;
  logic command_valid;
  logic command_ready;
  qbs_weight_profile_e command_profile;
  qbs_activation_profile_e command_activation_profile;
  qbs_weight_layout_e command_weight_layout;
  qbs_activation_layout_e command_activation_layout;
  logic [2:0] command_m;
  logic [5:0] command_n;
  logic [8:0] command_k_blocks;
  logic fault;
  logic fault_done;
  logic weight_valid;
  logic weight_ready;
  logic [1:0] weight_row;
  logic [7:0] weight_offset;
  logic [127:0] weight_data;
  logic [15:0] weight_strb;
  logic activation_valid;
  logic activation_ready;
  logic [1:0] activation_context;
  logic [10:0] activation_offset;
  logic [127:0] activation_data;
  logic [15:0] activation_strb;
  logic [7:0] expected_k_block;
  logic [5:0] expected_row_base;
  logic [2:0] expected_row_count;
  logic expected_weight_bank;
  logic activation_needed;
  logic weight_needed;
  logic result_valid;
  logic result_consumed;
  logic [6:0] result_read_index;
  logic result_read_valid;
  logic [31:0] result_read_data;
  logic [3:0] result_bank_row;
  logic [7:0] result_bank_valid;
  logic [31:0] result_bank_data [8];
  logic [4:0] result_fflags;
  logic busy;
  logic [31:0] tiles_computed;
  logic [31:0] weight_bytes;
  logic [31:0] activation_bytes;
  logic [31:0] useful_pairs;
  logic [31:0] pair_capacity;
  logic [31:0] dot_active_cycles;
  logic [31:0] fp_uops;
  logic [31:0] fp_table_occ_sum;
  logic [4:0] fp_table_occ_max;
  logic [31:0] fp_table_full_cycles;
  logic [31:0] accumulator_updates;
  logic phase_activation_load;
  logic phase_weight_load;
  logic phase_compute;
  logic phase_drain;
  logic [31:0] weight_prefetch_wait_cycles;

  logic [31:0] expected_output [128];
  bit expected_output_valid [128];

  logic probe_clear;
  integer probe_integer_tail_cycles;
  integer probe_context_blocked_cycles;
  integer probe_result_blocked_cycles;
  integer probe_fp_input_blocked_cycles;
  integer probe_command_cycles;

  qbs_compute_engine dut (
    .clk_i                          (clk),
    .rst_ni                         (rst_n),
    .command_valid_i                (command_valid),
    .command_ready_o                (command_ready),
    .command_weight_profile_i       (command_profile),
    .command_activation_profile_i   (command_activation_profile),
    .command_weight_layout_i        (command_weight_layout),
    .command_activation_layout_i    (command_activation_layout),
    .command_m_i                    (command_m),
    .command_n_i                    (command_n),
    .command_k_blocks_i             (command_k_blocks),
    .command_round_mode_i           (RNE),
    .fault_i                        (fault),
    .fault_done_o                   (fault_done),
    .weight_write_valid_i           (weight_valid),
    .weight_write_ready_o           (weight_ready),
    .weight_write_bank_i            (expected_weight_bank),
    .weight_write_row_count_i       (expected_row_count),
    .weight_write_group_i           (1'b0),
    .weight_write_row_i             (weight_row),
    .weight_write_offset_i          ({2'b0, weight_offset}),
    .weight_write_data_i            (weight_data),
    .weight_write_strb_i            (weight_strb),
    .activation_write_valid_i       (activation_valid),
    .activation_write_ready_o       (activation_ready),
    .activation_write_context_i     (activation_context),
    .activation_write_offset_i      (activation_offset),
    .activation_write_data_i        (activation_data),
    .activation_write_strb_i        (activation_strb),
    .expected_k_block_o             (expected_k_block),
    .expected_row_base_o            (expected_row_base),
    .expected_row_count_o           (expected_row_count),
    .expected_weight_bank_o         (expected_weight_bank),
    .activation_block_needed_o      (activation_needed),
    .weight_block_needed_o          (weight_needed),
    .result_valid_o                 (result_valid),
    .result_consumed_i              (result_consumed),
    .result_read_index_i            (result_read_index),
    .result_read_valid_o            (result_read_valid),
    .result_read_data_o             (result_read_data),
    .result_bank_read_row_i         (result_bank_row),
    .result_bank_read_valid_o       (result_bank_valid),
    .result_bank_read_data_o        (result_bank_data),
    .result_fflags_o                (result_fflags),
    .busy_o                         (busy),
    .phase_activation_load_o        (phase_activation_load),
    .phase_weight_load_o            (phase_weight_load),
    .phase_compute_o                (phase_compute),
    .phase_drain_o                  (phase_drain),
    .weight_prefetch_wait_cycles_o  (weight_prefetch_wait_cycles),
    .tiles_computed_o               (tiles_computed),
    .weight_bytes_o                 (weight_bytes),
    .activation_bytes_o             (activation_bytes),
    .useful_pairs_o                 (useful_pairs),
    .pair_capacity_o                (pair_capacity),
    .dot_active_cycles_o            (dot_active_cycles),
    .fp_uop_issue_o                 (fp_uops),
    .fp_table_occupancy_sum_o       (fp_table_occ_sum),
    .fp_table_occupancy_max_o       (fp_table_occ_max),
    .fp_table_full_cycles_o         (fp_table_full_cycles),
    .accumulator_updates_o          (accumulator_updates)
  );

  always #5 clk = ~clk;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n || probe_clear) begin
      probe_integer_tail_cycles <= 0;
      probe_context_blocked_cycles <= 0;
      probe_result_blocked_cycles <= 0;
      probe_fp_input_blocked_cycles <= 0;
      probe_command_cycles <= 0;
    end else begin
      if (busy) probe_command_cycles <= probe_command_cycles + 1;
      if (dut.i_profile_engine_int.busy_q &&
          !dut.i_profile_engine_int.issue_active_q)
        probe_integer_tail_cycles <= probe_integer_tail_cycles + 1;
      if (dut.integer_start_valid && !dut.integer_start_ready)
        probe_context_blocked_cycles <= probe_context_blocked_cycles + 1;
      if (dut.i_profile_engine_int.result_valid_o &&
          !dut.i_profile_engine_int.result_ready_i)
        probe_result_blocked_cycles <= probe_result_blocked_cycles + 1;
      if (dut.i_fp_accumulator.fp_in_valid &&
          !dut.i_fp_accumulator.fp_in_ready)
        probe_fp_input_blocked_cycles <= probe_fp_input_blocked_cycles + 1;
    end
  end

  task automatic send_weight(input integer row, input integer offset,
                             input logic [15:0] strb,
                             input logic [127:0] data);
    while (!weight_ready) @(posedge clk);
    @(negedge clk);
    weight_valid = 1'b1;
    weight_row = row[1:0];
    weight_offset = offset[7:0];
    weight_strb = strb;
    weight_data = data;
    @(negedge clk);
    weight_valid = 1'b0;
  endtask

  task automatic send_activation(input integer ctx, input integer offset,
                                 input logic [15:0] strb,
                                 input logic [127:0] data);
    while (!activation_ready) @(posedge clk);
    @(negedge clk);
    activation_valid = 1'b1;
    activation_context = ctx[1:0];
    activation_offset = offset[10:0];
    activation_strb = strb;
    activation_data = data;
    @(negedge clk);
    activation_valid = 1'b0;
  endtask

  initial begin
    string vector_file;
    string token;
    integer fd;
    integer rc;
    integer case_count;
    integer total_errors;

    clk = 1'b0;
    rst_n = 1'b0;
    command_valid = 1'b0;
    command_profile = QBS_WEIGHT_PROFILE_INVALID;
    command_activation_profile = QBS_ACTIVATION_PROFILE_INVALID;
    command_weight_layout = QBS_WEIGHT_LAYOUT_INVALID;
    command_activation_layout = QBS_ACTIVATION_LAYOUT_INVALID;
    command_m = '0;
    command_n = '0;
    command_k_blocks = '0;
    fault = 1'b0;
    weight_valid = 1'b0;
    weight_row = '0;
    weight_offset = '0;
    weight_data = '0;
    weight_strb = '0;
    activation_valid = 1'b0;
    activation_context = '0;
    activation_offset = '0;
    activation_data = '0;
    activation_strb = '0;
    result_consumed = 1'b0;
    result_read_index = '0;
    result_bank_row = '0;
    probe_clear = 1'b0;
    total_errors = 0;

    if (!$value$plusargs("QBS_COMMAND_VECTOR_FILE=%s", vector_file))
      vector_file = "../qbs_command_vectors.txt";
    fd = $fopen(vector_file, "r");
    if (fd == 0) $fatal(1, "cannot open QBS command vector file %s",
                        vector_file);
    rc = $fscanf(fd, "%s %d", token, case_count);
    if (rc != 2 || token != "QBSCMD1") $fatal(1, "bad command header");

    repeat (4) @(posedge clk);
    rst_n = 1'b1;

    for (integer ordinal = 0; ordinal < case_count; ordinal++) begin
      integer case_id;
      integer profile;
      integer weight_layout;
      integer activation_layout;
      integer m;
      integer n;
      integer k_blocks;
      integer expected_flags;
      integer expected_tiles;
      integer expected_weight_bytes;
      integer expected_activation_bytes;
      integer expected_useful_pairs;
      integer expected_pair_capacity;
      integer expected_dot_cycles;
      integer expected_fp_uops;
      integer expected_updates;
      integer output_records;
      integer monitor_cycles;
      integer case_errors;

      rc = $fscanf(fd, "%s %d %d %d %d %d %d %d %h", token, case_id,
                   profile, weight_layout, activation_layout, m, n, k_blocks,
                   expected_flags);
      if (rc != 9 || token != "CMD" || case_id != ordinal)
        $fatal(1, "bad CMD record at ordinal %0d", ordinal);
      for (int index = 0; index < 128; index++) begin
        expected_output_valid[index] = 1'b0;
        expected_output[index] = '0;
      end

      @(negedge clk);
      probe_clear = 1'b1;
      @(negedge clk);
      probe_clear = 1'b0;

      while (!command_ready) @(posedge clk);
      @(negedge clk);
      command_profile = qbs_weight_profile_e'(profile);
      command_activation_profile =
          profile == QBS_WEIGHT_PROFILE_Q4_0 ||
                  profile == QBS_WEIGHT_PROFILE_Q8_0_WEIGHT
              ? QBS_ACTIVATION_PROFILE_Q8_0
              : QBS_ACTIVATION_PROFILE_Q8_K;
      command_weight_layout = qbs_weight_layout_e'(weight_layout);
      command_activation_layout = qbs_activation_layout_e'(activation_layout);
      command_m = m[2:0];
      command_n = n[5:0];
      command_k_blocks = k_blocks[8:0];
      command_valid = 1'b1;
      @(negedge clk);
      command_valid = 1'b0;

      for (int tile = 0; tile < k_blocks * ((n + 3) / 4); tile++) begin
        integer expected_k;
        integer expected_row;
        integer expected_rows;
        rc = $fscanf(fd, "%s %d %d %d", token, expected_k, expected_row,
                     expected_rows);
        if (rc != 4 || token != "T")
          $fatal(1, "case %0d: bad T record", case_id);
        while (!(busy && (activation_needed || weight_needed))) @(posedge clk);
        if (expected_k_block != expected_k ||
            expected_row_base != expected_row ||
            expected_row_count != expected_rows)
          $fatal(1,
                 "case %0d: scheduler cursor got=(%0d,%0d,%0d) expected=(%0d,%0d,%0d)",
                 case_id, expected_k_block, expected_row_base,
                 expected_row_count, expected_k, expected_row, expected_rows);

        while (1) begin
          rc = $fscanf(fd, "%s", token);
          if (rc != 1) $fatal(1, "case %0d: short tile", case_id);
          if (token == "ENDT") break;
          if (token == "W") begin
            integer row;
            integer offset;
            logic [15:0] strb;
            logic [127:0] data;
            rc = $fscanf(fd, "%d %d %h %h", row, offset, strb, data);
            if (rc != 4) $fatal(1, "case %0d: bad W beat", case_id);
            send_weight(row, offset, strb, data);
          end else if (token == "A") begin
            integer ctx;
            integer offset;
            logic [15:0] strb;
            logic [127:0] data;
            rc = $fscanf(fd, "%d %d %h %h", ctx, offset, strb, data);
            if (rc != 4) $fatal(1, "case %0d: bad A beat", case_id);
            send_activation(ctx, offset, strb, data);
          end else begin
            $fatal(1, "case %0d: unexpected tile token %s", case_id, token);
          end
        end

        monitor_cycles = 0;
        while (tiles_computed != tile + 1 && monitor_cycles < 8192) begin
          @(posedge clk);
          monitor_cycles++;
        end
        if (monitor_cycles == 8192)
          $fatal(1, "case %0d: tile %0d timeout", case_id, tile);
      end

      output_records = m * n;
      for (int record = 0; record < output_records; record++) begin
        integer index;
        logic [31:0] bits;
        rc = $fscanf(fd, "%s %d %h", token, index, bits);
        if (rc != 3 || token != "O")
          $fatal(1, "case %0d: bad O record", case_id);
        expected_output_valid[index] = 1'b1;
        expected_output[index] = bits;
      end
      rc = $fscanf(fd, "%s %d %d %d %d %d %d %d %d", token,
                   expected_tiles, expected_weight_bytes,
                   expected_activation_bytes, expected_useful_pairs,
                   expected_pair_capacity, expected_dot_cycles,
                   expected_fp_uops, expected_updates);
      if (rc != 9 || token != "C")
        $fatal(1, "case %0d: bad C record", case_id);
      rc = $fscanf(fd, "%s", token);
      if (rc != 1 || token != "END")
        $fatal(1, "case %0d: missing END", case_id);

      monitor_cycles = 0;
      while (!result_valid && monitor_cycles < 8192) begin
        @(posedge clk);
        monitor_cycles++;
      end
      if (!result_valid) $fatal(1, "case %0d: result timeout", case_id);

      case_errors = 0;
      if (result_fflags != expected_flags[4:0] ||
          tiles_computed != expected_tiles ||
          weight_bytes != expected_weight_bytes ||
          activation_bytes != expected_activation_bytes ||
          useful_pairs != expected_useful_pairs ||
          pair_capacity != expected_pair_capacity ||
          dot_active_cycles != expected_dot_cycles ||
          fp_uops != expected_fp_uops ||
          accumulator_updates != expected_updates) begin
        $error("case %0d: command counter/flags mismatch", case_id);
        case_errors++;
      end
      for (int index = 0; index < 128; index++) begin
        if (expected_output_valid[index]) begin
          result_read_index = index[6:0];
          result_bank_row = index[6:3];
          #1;
          if (!result_read_valid ||
              result_read_data != expected_output[index] ||
              !result_bank_valid[index[2:0]] ||
              result_bank_data[index[2:0]] != expected_output[index]) begin
            $error("case %0d: output %0d got=%h valid=%0b expected=%h",
                   case_id, index, result_read_data, result_read_valid,
                   expected_output[index]);
            case_errors++;
          end
        end
      end
      if (case_errors == 0)
        $display("QBS command case %0d PASS profile=%0d M=%0d N=%0d Kb=%0d layouts=%0d/%0d",
                 case_id, profile, m, n, k_blocks, weight_layout,
                 activation_layout);
      $display("QBS_DRAIN_PROBE case=%0d command_cycles=%0d integer_tail=%0d context_blocked=%0d result_blocked=%0d fp_input_blocked=%0d",
               case_id, probe_command_cycles, probe_integer_tail_cycles,
               probe_context_blocked_cycles,
               probe_result_blocked_cycles, probe_fp_input_blocked_cycles);
      total_errors += case_errors;

      @(negedge clk);
      result_consumed = 1'b1;
      @(negedge clk);
      result_consumed = 1'b0;
    end

    // Directed atomic-abort check while a command is waiting for data.
    while (!command_ready) @(posedge clk);
    @(negedge clk);
    command_profile = QBS_WEIGHT_PROFILE_Q4_K;
    command_activation_profile = QBS_ACTIVATION_PROFILE_Q8_K;
    command_weight_layout = QBS_WEIGHT_LAYOUT_ROW_MAJOR;
    command_activation_layout = QBS_ACTIVATION_LAYOUT_ROW_MAJOR;
    command_m = 1;
    command_n = 4;
    command_k_blocks = 2;
    command_valid = 1'b1;
    @(negedge clk);
    command_valid = 1'b0;
    while (!weight_ready) @(posedge clk);
    @(negedge clk);
    fault = 1'b1;
    @(negedge clk);
    fault = 1'b0;
    while (!fault_done) begin
      @(posedge clk);
      if (result_valid) $fatal(1, "faulted QBS command exposed a result");
    end
    @(posedge clk);
    if (!command_ready || result_valid)
      $fatal(1, "QBS command did not return cleanly after fault");
    $display("QBS command fault discard PASS");

    $fclose(fd);
    if (total_errors != 0)
      $fatal(1, "QBS command engine failed with %0d errors", total_errors);
    $display("QBS command engine PASS: %0d functional cases", case_count);
    $finish;
  end

endmodule : qbs_compute_engine_tb
