`timescale 1ns/1ps

module qbs_profile_engine_tb;
  import qbs_pkg::*;
  import fpnew_pkg::*;

  logic clk;
  logic rst_n;
  logic weight_write_valid;
  logic [1:0] weight_write_row;
  logic [7:0] weight_write_offset;
  logic [127:0] weight_write_data;
  logic [15:0] weight_write_strb;
  logic block_clear_weight;
  logic block_clear_activation;
  logic activation_write_valid;
  logic [1:0] activation_write_context;
  logic [10:0] activation_write_offset;
  logic [127:0] activation_write_data;
  logic [15:0] activation_write_strb;
  logic start_valid;
  logic start_ready;
  qbs_weight_profile_e start_profile;
  qbs_activation_profile_e start_activation_profile;
  logic [2:0] start_m;
  logic [2:0] start_rows;
  logic busy;
  logic done;
  logic result_valid;
  logic result_ready;
  logic [3:0] result_stream;
  logic signed [31:0] result_dot;
  logic signed [31:0] result_aux;
  logic [15:0] result_weight_d;
  logic [15:0] result_weight_dmin;
  logic [31:0] result_activation_d;
  logic decode_valid;
  logic [7:0] decode_k_base;
  logic [3:0] decode_k_per;
  logic [15:0] decode_stream_valid;
  logic signed [7:0] decode_weight_quant [4][8];
  logic signed [7:0] decode_activation_quant [4][8];
  logic [15:0] group_valid;
  logic [3:0] group_index [16];
  logic signed [31:0] group_dot [16];
  logic signed [15:0] group_aux [16];
  logic signed [7:0] group_scale [16];
  logic [7:0] group_min [16];
  logic [31:0] useful_pairs;
  logic [31:0] pair_capacity;
  logic [15:0] dot_active_cycles;
  logic fp_clear;
  logic fp_first_block;
  logic fp_request_ready;
  logic [6:0] fp_request_accumulator_index;
  logic [6:0] fp_read_index;
  logic fp_read_valid;
  logic [31:0] fp_read_data;
  logic [7:0] fp_bank_read_valid;
  logic [31:0] fp_bank_read_data [8];
  logic fp_update_valid;
  logic [6:0] fp_update_index;
  logic [31:0] fp_update_data;
  logic [4:0] fp_fflags;
  logic fp_busy;
  logic [31:0] fp_uop_issue;
  logic [31:0] fp_table_occupancy_sum;
  logic [4:0] fp_table_occupancy_max;
  logic [31:0] fp_table_full_cycles;
  logic [31:0] fp_accumulator_updates;
  logic [7:0] adapter_weight_block [4][QbsMaxWeightBlockBytes];
  logic [7:0] adapter_activation_block [4][QbsMaxActivationBlockBytes];
  logic [3:0] adapter_weight_complete;
  logic [3:0] adapter_activation_complete;
  logic adapter_all_weight_complete;
  logic adapter_all_activation_complete;
  logic [31:0] adapter_weight_bytes;
  logic [31:0] adapter_activation_bytes;

  integer expected_weight_quant [4][256];
  integer expected_activation_quant [4][256];
  integer expected_group_dot [16][16];
  integer expected_group_aux [16][16];
  integer expected_group_scale [16][16];
  integer expected_group_min [16][16];
  bit expected_group_valid [16][16];
  bit observed_group [16][16];
  integer expected_result_dot [16];
  integer expected_result_aux [16];
  logic [15:0] expected_result_weight_d [16];
  logic [15:0] expected_result_weight_dmin [16];
  logic [31:0] expected_result_activation_d [16];
  logic [31:0] expected_result_fp [16];
  logic [31:0] expected_repeated_result_fp [16];
  bit expected_result_valid [16];
  bit observed_result [16];

  assign result_ready = fp_request_ready;
  assign fp_request_accumulator_index =
      {result_stream[1:0], 5'b0} + {5'b0, result_stream[3:2]};

  qbs_block_adapter i_block_adapter (
    .clk_i                         (clk),
    .rst_ni                        (rst_n),
    .clear_weight_i                (block_clear_weight),
    .clear_activation_i            (block_clear_activation),
    .weight_profile_i              (start_profile),
    .activation_profile_i          (start_activation_profile),
    .weight_row_count_i            (start_rows),
    .activation_layout_i           (QBS_ACTIVATION_LAYOUT_ROW_MAJOR),
    .m_i                           (start_m),
    .weight_write_valid_i          (weight_write_valid),
    .weight_write_group_i          (1'b0),
    .weight_write_row_i            (weight_write_row),
    .weight_write_offset_i         ({2'b0, weight_write_offset}),
    .weight_write_data_i           (weight_write_data),
    .weight_write_strb_i           (weight_write_strb),
    .activation_write_valid_i      (activation_write_valid),
    .activation_write_context_i    (activation_write_context),
    .activation_write_offset_i     (activation_write_offset),
    .activation_write_data_i       (activation_write_data),
    .activation_write_strb_i       (activation_write_strb),
    .weight_block_o                (adapter_weight_block),
    .activation_block_o            (adapter_activation_block),
    .weight_complete_o             (adapter_weight_complete),
    .activation_complete_o         (adapter_activation_complete),
    .all_weight_complete_o         (adapter_all_weight_complete),
    .all_activation_complete_o     (adapter_all_activation_complete),
    .accepted_weight_bytes_o       (adapter_weight_bytes),
    .accepted_activation_bytes_o   (adapter_activation_bytes)
  );

  qbs_profile_engine_int dut (
    .clk_i                         (clk),
    .rst_ni                        (rst_n),
    .weight_block_i                (adapter_weight_block),
    .activation_block_i            (adapter_activation_block),
    .start_valid_i                 (start_valid),
    .start_ready_o                 (start_ready),
    .start_profile_i               (start_profile),
    .start_activation_profile_i    (start_activation_profile),
    .start_m_i                     (start_m),
    .start_row_count_i             (start_rows),
    .start_row_base_i              ('0),
    .start_first_block_i           (1'b1),
    .busy_o                        (busy),
    .done_o                        (done),
    .result_valid_o                (result_valid),
    .result_ready_i                (result_ready),
    .result_stream_o               (result_stream),
    .result_row_base_o             (),
    .result_row_count_o            (),
    .result_first_block_o          (),
    .result_dot_o                  (result_dot),
    .result_aux_o                  (result_aux),
    .result_weight_d_o             (result_weight_d),
    .result_weight_dmin_o          (result_weight_dmin),
    .result_activation_d_o         (result_activation_d),
    .decode_valid_o                (decode_valid),
    .decode_k_base_o               (decode_k_base),
    .decode_k_per_context_o        (decode_k_per),
    .decode_stream_valid_o         (decode_stream_valid),
    .decode_weight_quant_o         (decode_weight_quant),
    .decode_activation_quant_o     (decode_activation_quant),
    .group_valid_o                 (group_valid),
    .group_index_o                 (group_index),
    .group_dot_o                   (group_dot),
    .group_aux_o                   (group_aux),
    .group_scale_o                 (group_scale),
    .group_min_o                   (group_min),
    .useful_pairs_o                (useful_pairs),
    .pair_capacity_o               (pair_capacity),
    .dot_active_cycles_o           (dot_active_cycles)
  );

  qbs_fp_accumulator i_fp_accumulator (
    .clk_i                         (clk),
    .rst_ni                        (rst_n),
    .clear_i                       (fp_clear),
    .request_valid_i               (result_valid),
    .request_ready_o               (fp_request_ready),
    .request_slot_i                (result_stream),
    .request_profile_i             (start_profile),
    .request_activation_profile_i  (start_activation_profile),
    .request_accumulator_index_i   (fp_request_accumulator_index),
    .request_first_block_i         (fp_first_block),
    .request_dot_i                 (result_dot),
    .request_aux_i                 (result_aux),
    .request_weight_d_i            (result_weight_d),
    .request_weight_dmin_i         (result_weight_dmin),
    .request_activation_d_i        (result_activation_d),
    .request_round_mode_i          (RNE),
    .read_index_i                  (fp_read_index),
    .read_valid_o                  (fp_read_valid),
    .read_data_o                   (fp_read_data),
    .bank_read_row_i               (fp_read_index[6:3]),
    .bank_read_valid_o             (fp_bank_read_valid),
    .bank_read_data_o              (fp_bank_read_data),
    .update_valid_o                (fp_update_valid),
    .update_index_o                (fp_update_index),
    .update_data_o                 (fp_update_data),
    .fflags_o                      (fp_fflags),
    .busy_o                        (fp_busy),
    .fp_uop_issue_o                (fp_uop_issue),
    .table_occupancy_sum_o         (fp_table_occupancy_sum),
    .table_occupancy_max_o         (fp_table_occupancy_max),
    .table_full_cycles_o           (fp_table_full_cycles),
    .accumulator_updates_o         (fp_accumulator_updates)
  );

  always #5 clk = ~clk;

  task automatic fail(input string message, input integer case_id);
    $error("case %0d: %s", case_id, message);
  endtask

  task automatic read_token(input integer fd, input string expected,
                            input integer case_id);
    string token;
    integer rc;
    rc = $fscanf(fd, "%s", token);
    if (rc != 1 || token != expected)
      $fatal(1, "case %0d: expected token %s, got %s", case_id, expected,
             token);
  endtask

  task automatic write_weight_beat(input integer row, input integer offset,
                                   input logic [15:0] strb,
                                   input logic [127:0] data);
    @(negedge clk);
    weight_write_valid = 1'b1;
    weight_write_row = row[1:0];
    weight_write_offset = offset[7:0];
    weight_write_strb = strb;
    weight_write_data = data;
    @(negedge clk);
    weight_write_valid = 1'b0;
  endtask

  task automatic write_activation_beat(input integer ctx,
                                       input integer offset,
                                       input logic [15:0] strb,
                                       input logic [127:0] data);
    @(negedge clk);
    activation_write_valid = 1'b1;
    activation_write_context = ctx[1:0];
    activation_write_offset = offset[8:0];
    activation_write_strb = strb;
    activation_write_data = data;
    @(negedge clk);
    activation_write_valid = 1'b0;
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
    weight_write_valid = 1'b0;
    weight_write_row = '0;
    weight_write_offset = '0;
    weight_write_data = '0;
    weight_write_strb = '0;
    activation_write_valid = 1'b0;
    activation_write_context = '0;
    activation_write_offset = '0;
    activation_write_data = '0;
    activation_write_strb = '0;
    block_clear_weight = 1'b0;
    block_clear_activation = 1'b0;
    start_valid = 1'b0;
    start_profile = QBS_WEIGHT_PROFILE_INVALID;
    start_activation_profile = QBS_ACTIVATION_PROFILE_INVALID;
    start_m = '0;
    start_rows = '0;
    fp_clear = 1'b0;
    fp_first_block = 1'b1;
    fp_read_index = '0;
    total_errors = 0;

    if (!$value$plusargs("QBS_VECTOR_FILE=%s", vector_file))
      vector_file = "../qbs_rtl_vectors.txt";
    fd = $fopen(vector_file, "r");
    if (fd == 0) $fatal(1, "cannot open QBS vector file %s", vector_file);
    rc = $fscanf(fd, "%s %d", token, case_count);
    if (rc != 2 || token != "QBSV1") $fatal(1, "bad QBS vector header");

    repeat (4) @(posedge clk);
    rst_n = 1'b1;

    for (integer case_ordinal = 0; case_ordinal < case_count;
         case_ordinal++) begin
      integer case_id;
      integer profile;
      integer m;
      integer rows;
      integer pattern;
      integer block_bytes;
      integer block_elements;
      integer weight_beats;
      integer activation_beats;
      integer activation_block_bytes;
      integer groups;
      integer expected_useful;
      integer expected_capacity;
      integer expected_cycles;
      integer expected_fflags;
      integer expected_repeated_fflags;
      integer uops_per_output;
      integer case_errors;
      integer monitor_cycles;
      logic [15:0] expected_stream_mask;
      bit integer_done_seen;

      rc = $fscanf(fd, "%s %d %d %d %d %d", token, case_id, profile, m,
                   rows, pattern);
      if (rc != 6 || token != "CASE")
        $fatal(1, "bad CASE record at ordinal %0d", case_ordinal);
      if (case_id != case_ordinal)
        $fatal(1, "non-sequential case id %0d", case_id);

      start_profile = qbs_weight_profile_e'(profile);
      uops_per_output = qbs_weight_correction_mode(start_profile) ==
          QBS_CORRECTION_AFFINE_MIN ? 6 : 3;
      start_activation_profile = qbs_default_activation_profile(
          qbs_weight_profile_e'(profile));
      start_m = m[2:0];
      start_rows = rows[2:0];
      @(negedge clk);
      block_clear_weight = 1'b1;
      block_clear_activation = 1'b1;
      @(negedge clk);
      block_clear_weight = 1'b0;
      block_clear_activation = 1'b0;

      for (int stream = 0; stream < 16; stream++) begin
        expected_result_valid[stream] = 1'b0;
        observed_result[stream] = 1'b0;
        for (int group = 0; group < 16; group++) begin
          expected_group_valid[stream][group] = 1'b0;
          observed_group[stream][group] = 1'b0;
        end
      end

      block_bytes = qbs_weight_block_bytes(start_profile);
      block_elements = qbs_weight_block_elements(start_profile);
      weight_beats = (block_bytes + 15) / 16;
      activation_block_bytes =
          qbs_activation_block_bytes(start_activation_profile);
      activation_beats = (activation_block_bytes + 15) / 16;
      groups = qbs_weight_subgroup_count(start_profile);

      for (int beat = 0; beat < rows * weight_beats; beat++) begin
        integer row;
        integer offset;
        logic [15:0] strb;
        logic [127:0] data;
        rc = $fscanf(fd, "%s %d %d %h %h", token, row, offset, strb, data);
        if (rc != 5 || token != "W")
          $fatal(1, "case %0d: bad weight beat", case_id);
        write_weight_beat(row, offset, strb, data);
      end
      for (int beat = 0; beat < m * activation_beats; beat++) begin
        integer ctx;
        integer offset;
        logic [15:0] strb;
        logic [127:0] data;
        rc = $fscanf(fd, "%s %d %d %h %h", token, ctx, offset, strb, data);
        if (rc != 5 || token != "A")
          $fatal(1, "case %0d: bad activation beat", case_id);
        write_activation_beat(ctx, offset, strb, data);
      end
      for (int row = 0; row < rows; row++) begin
        integer record_row;
        read_token(fd, "QW", case_id);
        rc = $fscanf(fd, "%d", record_row);
        if (rc != 1 || record_row != row)
          $fatal(1, "case %0d: bad QW row", case_id);
        for (int element = 0; element < block_elements; element++) begin
          rc = $fscanf(fd, "%d", expected_weight_quant[row][element]);
          if (rc != 1) $fatal(1, "case %0d: short QW", case_id);
        end
      end
      for (int ctx = 0; ctx < m; ctx++) begin
        integer record_ctx;
        read_token(fd, "QA", case_id);
        rc = $fscanf(fd, "%d", record_ctx);
        if (rc != 1 || record_ctx != ctx)
          $fatal(1, "case %0d: bad QA context", case_id);
        for (int element = 0; element < block_elements; element++) begin
          rc = $fscanf(fd, "%d", expected_activation_quant[ctx][element]);
          if (rc != 1) $fatal(1, "case %0d: short QA", case_id);
        end
      end
      for (int record = 0; record < rows * m * groups; record++) begin
        integer stream;
        integer group;
        integer dot;
        integer aux;
        integer scale;
        integer min_value;
        rc = $fscanf(fd, "%s %d %d %d %d %d %d", token, stream, group,
                     dot, aux, scale, min_value);
        if (rc != 7 || token != "G")
          $fatal(1, "case %0d: bad group record", case_id);
        expected_group_dot[stream][group] = dot;
        expected_group_aux[stream][group] = aux;
        expected_group_scale[stream][group] = scale;
        expected_group_min[stream][group] = min_value;
        expected_group_valid[stream][group] = 1'b1;
      end
      for (int record = 0; record < rows * m; record++) begin
        integer stream;
        integer dot;
        integer aux;
        logic [15:0] weight_d;
        logic [15:0] weight_dmin;
        logic [31:0] activation_d;
        logic [31:0] fp_result_bits;
        logic [31:0] repeated_fp_result_bits;
        rc = $fscanf(fd, "%s %d %d %d %h %h %h %h %h", token, stream,
                     dot, aux, weight_d, weight_dmin, activation_d,
                     fp_result_bits, repeated_fp_result_bits);
        if (rc != 9 || token != "R")
          $fatal(1, "case %0d: bad result record", case_id);
        expected_result_dot[stream] = dot;
        expected_result_aux[stream] = aux;
        expected_result_weight_d[stream] = weight_d;
        expected_result_weight_dmin[stream] = weight_dmin;
        expected_result_activation_d[stream] = activation_d;
        expected_result_fp[stream] = fp_result_bits;
        expected_repeated_result_fp[stream] = repeated_fp_result_bits;
        expected_result_valid[stream] = 1'b1;
      end
      rc = $fscanf(fd, "%s %h %h", token, expected_fflags,
                   expected_repeated_fflags);
      if (rc != 3 || token != "F")
        $fatal(1, "case %0d: bad fflags record", case_id);
      rc = $fscanf(fd, "%s %d %d %d", token, expected_useful,
                   expected_capacity, expected_cycles);
      if (rc != 4 || token != "C")
        $fatal(1, "case %0d: bad counter record", case_id);
      read_token(fd, "END", case_id);

      if (!adapter_all_weight_complete ||
          !adapter_all_activation_complete ||
          adapter_weight_bytes != rows * block_bytes ||
          adapter_activation_bytes != m * activation_block_bytes)
        $fatal(1,
               "case %0d: incomplete block assembly w=%b/%0d a=%b/%0d",
               case_id, adapter_all_weight_complete, adapter_weight_bytes,
               adapter_all_activation_complete, adapter_activation_bytes);

      case_errors = 0;
      expected_stream_mask = '0;
      for (int row = 0; row < rows; row++)
        for (int ctx = 0; ctx < m; ctx++)
          expected_stream_mask[row * 4 + ctx] = 1'b1;

      @(negedge clk);
      fp_clear = 1'b1;
      @(negedge clk);
      fp_clear = 1'b0;
      fp_first_block = 1'b1;
      start_valid = 1'b1;
      @(negedge clk);
      start_valid = 1'b0;

      monitor_cycles = 0;
      integer_done_seen = 1'b0;
      while ((!integer_done_seen || busy || fp_busy) && monitor_cycles < 4096) begin
        @(posedge clk);
        #1;
        ++monitor_cycles;
        if (done) integer_done_seen = 1'b1;
        if (decode_valid) begin
          if (decode_stream_valid != expected_stream_mask) begin
            fail($sformatf("decode stream mask got=%h expected=%h",
                           decode_stream_valid, expected_stream_mask), case_id);
            ++case_errors;
          end
          for (int row = 0; row < rows; row++) begin
            for (int lane = 0; lane < decode_k_per; lane++) begin
              if ($signed(decode_weight_quant[row][lane]) !=
                  expected_weight_quant[row][decode_k_base + lane]) begin
                fail($sformatf(
                    "weight quant row=%0d k=%0d got=%0d expected=%0d", row,
                    decode_k_base + lane,
                    $signed(decode_weight_quant[row][lane]),
                    expected_weight_quant[row][decode_k_base + lane]),
                     case_id);
                ++case_errors;
              end
            end
          end
          for (int ctx = 0; ctx < m; ctx++) begin
            for (int lane = 0; lane < decode_k_per; lane++) begin
              if ($signed(decode_activation_quant[ctx][lane]) !=
                  expected_activation_quant[ctx][decode_k_base + lane]) begin
                fail($sformatf(
                    "activation quant ctx=%0d k=%0d got=%0d expected=%0d",
                    ctx, decode_k_base + lane,
                    $signed(decode_activation_quant[ctx][lane]),
                    expected_activation_quant[ctx][decode_k_base + lane]),
                     case_id);
                ++case_errors;
              end
            end
          end
        end

        for (int stream = 0; stream < 16; stream++) begin
          if (group_valid[stream]) begin
            automatic int group = group_index[stream];
            if (!expected_group_valid[stream][group] ||
                observed_group[stream][group] ||
                $signed(group_dot[stream]) != expected_group_dot[stream][group] ||
                $signed(group_aux[stream]) != expected_group_aux[stream][group] ||
                $signed(group_scale[stream]) !=
                    expected_group_scale[stream][group] ||
                unsigned'(group_min[stream]) !=
                    expected_group_min[stream][group]) begin
              fail($sformatf(
                  "group mismatch stream=%0d group=%0d dot=%0d/%0d aux=%0d/%0d scale=%0d/%0d min=%0d/%0d",
                  stream, group, $signed(group_dot[stream]),
                  expected_group_dot[stream][group], $signed(group_aux[stream]),
                  expected_group_aux[stream][group],
                  $signed(group_scale[stream]),
                  expected_group_scale[stream][group], group_min[stream],
                  expected_group_min[stream][group]), case_id);
              ++case_errors;
            end
            observed_group[stream][group] = 1'b1;
          end
        end

        if (result_valid) begin
          if (!expected_result_valid[result_stream] ||
              observed_result[result_stream] ||
              $signed(result_dot) != expected_result_dot[result_stream] ||
              $signed(result_aux) != expected_result_aux[result_stream] ||
              result_weight_d != expected_result_weight_d[result_stream] ||
              result_weight_dmin != expected_result_weight_dmin[result_stream] ||
              result_activation_d !=
                  expected_result_activation_d[result_stream]) begin
            fail($sformatf(
                "result mismatch stream=%0d dot=%0d/%0d aux=%0d/%0d wd=%h/%h wdmin=%h/%h ad=%h/%h",
                result_stream, $signed(result_dot),
                expected_result_dot[result_stream], $signed(result_aux),
                expected_result_aux[result_stream], result_weight_d,
                expected_result_weight_d[result_stream], result_weight_dmin,
                expected_result_weight_dmin[result_stream], result_activation_d,
                expected_result_activation_d[result_stream]), case_id);
            ++case_errors;
          end
          observed_result[result_stream] = 1'b1;
        end
      end

      if (!integer_done_seen || fp_busy) begin
        fail("timeout", case_id);
        ++case_errors;
      end
      for (int stream = 0; stream < 16; stream++) begin
        if (expected_result_valid[stream] && !observed_result[stream]) begin
          fail($sformatf("missing result stream=%0d", stream), case_id);
          ++case_errors;
        end
        for (int group = 0; group < groups; group++) begin
          if (expected_group_valid[stream][group] &&
              !observed_group[stream][group]) begin
            fail($sformatf("missing group stream=%0d group=%0d", stream,
                           group), case_id);
            ++case_errors;
          end
        end
      end
      if (useful_pairs != expected_useful ||
          pair_capacity != expected_capacity ||
          dot_active_cycles != expected_cycles) begin
        fail($sformatf(
            "counter mismatch useful=%0d/%0d capacity=%0d/%0d cycles=%0d/%0d",
            useful_pairs, expected_useful, pair_capacity, expected_capacity,
            dot_active_cycles, expected_cycles), case_id);
        ++case_errors;
      end
      if (fp_uop_issue != rows * m * uops_per_output ||
          fp_accumulator_updates != rows * m ||
          fp_fflags != expected_fflags[4:0]) begin
        fail($sformatf(
            "FP counter/flags mismatch uops=%0d/%0d updates=%0d/%0d flags=%h/%h",
            fp_uop_issue,
            rows * m * uops_per_output,
            fp_accumulator_updates, rows * m, fp_fflags,
            expected_fflags[4:0]), case_id);
        ++case_errors;
      end
      for (int stream = 0; stream < 16; stream++) begin
        if (expected_result_valid[stream]) begin
          fp_read_index = {stream[1:0], 5'b0} + {5'b0, stream[3:2]};
          #1;
          if (!fp_read_valid || fp_read_data != expected_result_fp[stream] ||
              !fp_bank_read_valid[fp_read_index[2:0]] ||
              fp_bank_read_data[fp_read_index[2:0]] !=
                  expected_result_fp[stream]) begin
            fail($sformatf(
                "FP result mismatch stream=%0d index=%0d got=%h valid=%0d expected=%h",
                stream, fp_read_index, fp_read_data, fp_read_valid,
                expected_result_fp[stream]), case_id);
            ++case_errors;
          end
        end
      end

      fp_first_block = 1'b0;
      @(negedge clk);
      start_valid = 1'b1;
      @(negedge clk);
      start_valid = 1'b0;
      integer_done_seen = 1'b0;
      monitor_cycles = 0;
      while ((!integer_done_seen || busy || fp_busy) && monitor_cycles < 4096) begin
        @(posedge clk);
        #1;
        ++monitor_cycles;
        if (done) integer_done_seen = 1'b1;
      end
      if (!integer_done_seen || fp_busy) begin
        fail("repeated-block timeout", case_id);
        ++case_errors;
      end
      if (fp_uop_issue != 2 * rows * m * uops_per_output ||
          fp_accumulator_updates != 2 * rows * m ||
          fp_fflags != expected_repeated_fflags[4:0]) begin
        fail($sformatf(
            "repeated FP counter/flags mismatch uops=%0d/%0d updates=%0d/%0d flags=%h/%h",
            fp_uop_issue,
            2 * rows * m * uops_per_output,
            fp_accumulator_updates, 2 * rows * m, fp_fflags,
            expected_repeated_fflags[4:0]), case_id);
        ++case_errors;
      end
      for (int stream = 0; stream < 16; stream++) begin
        if (expected_result_valid[stream]) begin
          fp_read_index = {stream[1:0], 5'b0} + {5'b0, stream[3:2]};
          #1;
          if (!fp_read_valid ||
              fp_read_data != expected_repeated_result_fp[stream] ||
              !fp_bank_read_valid[fp_read_index[2:0]] ||
              fp_bank_read_data[fp_read_index[2:0]] !=
                  expected_repeated_result_fp[stream]) begin
            fail($sformatf(
                "repeated FP result mismatch stream=%0d index=%0d got=%h valid=%0d expected=%h",
                stream, fp_read_index, fp_read_data, fp_read_valid,
                expected_repeated_result_fp[stream]), case_id);
            ++case_errors;
          end
        end
      end

      if (case_errors == 0)
        $display("QBS RTL case %0d PASS profile=%0d M=%0d rows=%0d pattern=%0d",
                 case_id, profile, m, rows, pattern);
      total_errors += case_errors;
      @(posedge clk);
    end

    $fclose(fd);
    if (total_errors != 0)
      $fatal(1, "QBS profile engine failed with %0d errors", total_errors);
    $display("QBS profile engine PASS: %0d cases", case_count);
    $finish;
  end

endmodule : qbs_profile_engine_tb
