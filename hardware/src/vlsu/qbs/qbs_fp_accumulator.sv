// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

module qbs_fp_accumulator
  import qbs_pkg::*;
  import fpnew_pkg::*;
#(
  parameter int unsigned NumAccumulators = QbsMaxM * QbsMaxN,
  parameter int unsigned AccIndexWidth = $clog2(NumAccumulators)
) (
  input  logic                 clk_i,
  input  logic                 rst_ni,

  input  logic                 clear_i,

  input  logic                 request_valid_i,
  output logic                 request_ready_o,
  input  logic [3:0]           request_slot_i,
  input  qbs_weight_profile_e  request_profile_i,
  input  qbs_activation_profile_e request_activation_profile_i,
  input  logic [AccIndexWidth-1:0] request_accumulator_index_i,
  input  logic                 request_first_block_i,
  input  logic signed [31:0]   request_dot_i,
  input  logic signed [31:0]   request_aux_i,
  input  logic [15:0]          request_weight_d_i,
  input  logic [15:0]          request_weight_dmin_i,
  input  logic [31:0]          request_activation_d_i,

  input  logic [AccIndexWidth-1:0] read_index_i,
  output logic                 read_valid_o,
  output logic [31:0]          read_data_o,
  input  logic [3:0]           bank_read_row_i,
  output logic [7:0]           bank_read_valid_o,
  output logic [31:0]          bank_read_data_o [8],

  output logic                 update_valid_o,
  output logic [AccIndexWidth-1:0] update_index_o,
  output logic [31:0]          update_data_o,
  output logic [4:0]           fflags_o,
  output logic                 busy_o,

  output logic [31:0]          fp_uop_issue_o,
  output logic [31:0]          table_occupancy_sum_o,
  output logic [4:0]           table_occupancy_max_o,
  output logic [31:0]          table_full_cycles_o,
  output logic [31:0]          accumulator_updates_o
);

  localparam int unsigned NumEntries = 16;

  typedef enum logic [2:0] {
    FP_DOT_CONVERT,
    FP_AUX_CONVERT,
    FP_SCALE_MULTIPLY,
    FP_MIN_SCALE_MULTIPLY,
    FP_ACCUMULATE_DOT,
    FP_ACCUMULATE_MIN
  } fp_state_e;

  typedef struct packed {
    fp_state_e state;
    logic [3:0] slot;
  } fp_tag_t;

  typedef logic [4:0] fflags_t;

  localparam fpu_features_t FpuFeatures = '{
    Width:          32,
    EnableVectors: 1'b0,
    EnableNanBox:  1'b0,
    FpFmtMask:     6'b100000,
    IntFmtMask:    4'b0010
  };

  localparam fpu_implementation_t FpuImplementation = '{
    PipeRegs: '{
      '{default: 2},
      '{default: 0},
      '{default: 0},
      '{default: 1},
      '{default: 0}
    },
    UnitTypes: '{
      '{default: PARALLEL},
      '{default: DISABLED},
      '{default: DISABLED},
      '{default: MERGED},
      '{default: DISABLED}
    },
    PipeConfig: DISTRIBUTED
  };

  logic [NumAccumulators-1:0] accumulator_valid_q;
  logic [31:0] accumulator_data_q [8][16];

  logic [NumEntries-1:0] entry_valid_q;
  logic [NumEntries-1:0] entry_inflight_q;
  logic entry_affine_q [NumEntries];
  logic [AccIndexWidth-1:0] entry_accumulator_index_q [NumEntries];
  fp_state_e entry_state_q [NumEntries];
  logic signed [31:0] entry_dot_q [NumEntries];
  logic signed [31:0] entry_aux_q [NumEntries];
  logic [31:0] entry_weight_d_q [NumEntries];
  logic [31:0] entry_weight_dmin_q [NumEntries];
  logic [31:0] entry_activation_d_q [NumEntries];
  logic [31:0] entry_accumulator_q [NumEntries];
  logic [31:0] entry_dot_float_q [NumEntries];
  logic [31:0] entry_aux_float_q [NumEntries];
  logic [31:0] entry_scale_q [NumEntries];
  logic [31:0] entry_min_scale_q [NumEntries];
  logic [31:0] entry_positive_q [NumEntries];

  logic [3:0] schedule_rr_q;
  fflags_t fflags_q;

  logic [2:0][31:0] fp_operands;
  roundmode_e fp_round_mode;
  operation_e fp_operation;
  logic fp_operation_modifier;
  fp_tag_t fp_tag_in;
  logic fp_in_valid;
  logic fp_in_ready;
  logic fp_fire;
  logic [31:0] fp_result;
  status_t fp_status;
  fp_tag_t fp_tag_out;
  logic fp_out_valid;
  logic fp_busy;
  logic [4:0] entry_occupancy;
  logic request_accumulator_conflict;

  function automatic logic [31:0] fp16_to_fp32(input logic [15:0] value);
    logic sign;
    logic [4:0] exponent;
    logic [9:0] fraction;
    logic [7:0] exponent32;
    logic [22:0] fraction32;
    logic [31:0] normalized;
    int leading_index;
    begin
      sign = value[15];
      exponent = value[14:10];
      fraction = value[9:0];
      exponent32 = '0;
      fraction32 = '0;
      leading_index = -1;

      if (exponent == 0) begin
        if (fraction != 0) begin
          for (int bit_index = 9; bit_index >= 0; bit_index--)
            if (leading_index == -1 && fraction[bit_index])
              leading_index = bit_index;
          exponent32 = 8'(leading_index + 103);
          normalized = {22'b0, fraction} << (23 - leading_index);
          fraction32 = normalized[22:0];
        end
      end else if (exponent == 5'h1f) begin
        exponent32 = 8'hff;
        fraction32 = {fraction, 13'b0};
        if (fraction != 0) fraction32[22] = 1'b1;
      end else begin
        exponent32 = 8'(unsigned'(exponent) + 112);
        fraction32 = {fraction, 13'b0};
      end
      fp16_to_fp32 = {sign, exponent32, fraction32};
    end
  endfunction

  always_comb begin
    entry_occupancy = '0;
    for (int entry = 0; entry < NumEntries; entry++)
      entry_occupancy += entry_valid_q[entry];
  end

  always_comb begin
    request_accumulator_conflict = 1'b0;
    for (int entry = 0; entry < NumEntries; entry++) begin
      if (entry_valid_q[entry] &&
          entry_accumulator_index_q[entry] == request_accumulator_index_i)
        request_accumulator_conflict = 1'b1;
    end
  end

  assign request_ready_o = !clear_i && !entry_valid_q[request_slot_i] &&
                           !request_accumulator_conflict;
  assign read_valid_o = accumulator_valid_q[read_index_i];
  assign read_data_o = accumulator_data_q[read_index_i[2:0]][read_index_i[6:3]];
  always_comb begin
    for (int bank = 0; bank < 8; bank++) begin
      bank_read_valid_o[bank] =
          accumulator_valid_q[{bank_read_row_i, 3'(bank)}];
      bank_read_data_o[bank] = accumulator_data_q[bank][bank_read_row_i];
    end
  end
  assign fflags_o = fflags_q;
  assign busy_o = (|entry_valid_q) || fp_busy;
  assign fp_fire = fp_in_valid && fp_in_ready;

  always_comb begin
    logic found;
    found = 1'b0;
    fp_in_valid = 1'b0;
    fp_operands = '0;
    fp_round_mode = roundmode_e'(QbsNumericalRoundingMode);
    fp_operation = I2F;
    fp_operation_modifier = 1'b0;
    fp_tag_in = '0;

    for (int offset = 0; offset < NumEntries; offset++) begin
      automatic logic [3:0] entry = schedule_rr_q + 4'(offset);
      if (entry_valid_q[entry] && !entry_inflight_q[entry] && !found) begin
        found = 1'b1;
        fp_in_valid = 1'b1;
        fp_tag_in = '{state: entry_state_q[entry], slot: entry};
        unique case (entry_state_q[entry])
          FP_DOT_CONVERT: begin
            fp_operation = I2F;
            fp_operands[0] = entry_dot_q[entry];
          end
          FP_AUX_CONVERT: begin
            fp_operation = I2F;
            fp_operands[0] = entry_aux_q[entry];
          end
          FP_SCALE_MULTIPLY: begin
            fp_operation = MUL;
            fp_operands[0] = entry_weight_d_q[entry];
            fp_operands[1] = entry_activation_d_q[entry];
          end
          FP_MIN_SCALE_MULTIPLY: begin
            fp_operation = MUL;
            fp_operands[0] = entry_weight_dmin_q[entry];
            fp_operands[1] = entry_activation_d_q[entry];
          end
          FP_ACCUMULATE_DOT: begin
            fp_operation = FMADD;
            fp_operands[0] = entry_scale_q[entry];
            fp_operands[1] = entry_dot_float_q[entry];
            fp_operands[2] = entry_accumulator_q[entry];
          end
          FP_ACCUMULATE_MIN: begin
            fp_operation = FMADD;
            fp_operands[0] = {
              !entry_min_scale_q[entry][31],
              entry_min_scale_q[entry][30:0]
            };
            fp_operands[1] = entry_aux_float_q[entry];
            fp_operands[2] = entry_positive_q[entry];
          end
          default: fp_in_valid = 1'b0;
        endcase
      end
    end
  end

  fpnew_top #(
    .Features       (FpuFeatures),
    .Implementation (FpuImplementation),
    .DivSqrtSel     (THMULTI),
    .TagType        (fp_tag_t)
  ) i_fpnew (
    .clk_i,
    .rst_ni,
    .hart_id_i      ('0),
    .operands_i     (fp_operands),
    .rnd_mode_i     (fp_round_mode),
    .op_i           (fp_operation),
    .op_mod_i       (fp_operation_modifier),
    .src_fmt_i      (FP32),
    .dst_fmt_i      (FP32),
    .int_fmt_i      (INT32),
    .vectorial_op_i (1'b0),
    .tag_i          (fp_tag_in),
    .simd_mask_i    (1'b1),
    .in_valid_i     (fp_in_valid),
    .in_ready_o     (fp_in_ready),
    .flush_i        (1'b0),
    .result_o       (fp_result),
    .status_o       (fp_status),
    .tag_o          (fp_tag_out),
    .out_valid_o    (fp_out_valid),
    .out_ready_i    (1'b1),
    .busy_o         (fp_busy)
  );

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      accumulator_valid_q <= '0;
      entry_valid_q <= '0;
      entry_inflight_q <= '0;
      schedule_rr_q <= '0;
      fflags_q <= '0;
      update_valid_o <= 1'b0;
      update_index_o <= '0;
      update_data_o <= '0;
      fp_uop_issue_o <= '0;
      table_occupancy_sum_o <= '0;
      table_occupancy_max_o <= '0;
      table_full_cycles_o <= '0;
      accumulator_updates_o <= '0;
    end else begin
      update_valid_o <= 1'b0;

      if (clear_i) begin
        accumulator_valid_q <= '0;
        entry_valid_q <= '0;
        entry_inflight_q <= '0;
        schedule_rr_q <= '0;
        fflags_q <= '0;
        fp_uop_issue_o <= '0;
        table_occupancy_sum_o <= '0;
        table_occupancy_max_o <= '0;
        table_full_cycles_o <= '0;
        accumulator_updates_o <= '0;
      end else begin
        if (busy_o) begin
          table_occupancy_sum_o <= table_occupancy_sum_o + entry_occupancy;
          if (entry_occupancy > table_occupancy_max_o)
            table_occupancy_max_o <= entry_occupancy;
          if (&entry_valid_q)
            table_full_cycles_o <= table_full_cycles_o + 1'b1;
        end

        if (request_valid_i && request_ready_o) begin
          entry_valid_q[request_slot_i] <= 1'b1;
          entry_inflight_q[request_slot_i] <= 1'b0;
          entry_affine_q[request_slot_i] <=
              qbs_weight_correction_mode(request_profile_i) ==
                  QBS_CORRECTION_AFFINE_MIN;
          entry_accumulator_index_q[request_slot_i] <=
              request_accumulator_index_i;
          entry_state_q[request_slot_i] <= FP_DOT_CONVERT;
          entry_dot_q[request_slot_i] <= request_dot_i;
          entry_aux_q[request_slot_i] <= request_aux_i;
          entry_weight_d_q[request_slot_i] <=
              fp16_to_fp32(request_weight_d_i);
          entry_weight_dmin_q[request_slot_i] <=
              fp16_to_fp32(request_weight_dmin_i);
          entry_activation_d_q[request_slot_i] <=
              qbs_activation_scale_format(request_activation_profile_i) ==
                  QBS_SCALE_FP16
              ? fp16_to_fp32(request_activation_d_i[15:0])
              : request_activation_d_i;
          entry_accumulator_q[request_slot_i] <= request_first_block_i
              ? '0 : accumulator_data_q[request_accumulator_index_i[2:0]]
                                         [request_accumulator_index_i[6:3]];
        end

        if (fp_fire) begin
          entry_inflight_q[fp_tag_in.slot] <= 1'b1;
          schedule_rr_q <= fp_tag_in.slot + 1'b1;
          fp_uop_issue_o <= fp_uop_issue_o + 1'b1;
        end

        if (fp_out_valid) begin
          entry_inflight_q[fp_tag_out.slot] <= 1'b0;
          fflags_q <= fflags_q | fflags_t'(fp_status);
          unique case (fp_tag_out.state)
            FP_DOT_CONVERT: begin
              entry_dot_float_q[fp_tag_out.slot] <= fp_result;
              entry_state_q[fp_tag_out.slot] <=
                  entry_affine_q[fp_tag_out.slot]
                      ? FP_AUX_CONVERT : FP_SCALE_MULTIPLY;
            end
            FP_AUX_CONVERT: begin
              entry_aux_float_q[fp_tag_out.slot] <= fp_result;
              entry_state_q[fp_tag_out.slot] <= FP_SCALE_MULTIPLY;
            end
            FP_SCALE_MULTIPLY: begin
              entry_scale_q[fp_tag_out.slot] <= fp_result;
              entry_state_q[fp_tag_out.slot] <=
                  entry_affine_q[fp_tag_out.slot]
                      ? FP_MIN_SCALE_MULTIPLY : FP_ACCUMULATE_DOT;
            end
            FP_MIN_SCALE_MULTIPLY: begin
              entry_min_scale_q[fp_tag_out.slot] <= fp_result;
              entry_state_q[fp_tag_out.slot] <= FP_ACCUMULATE_DOT;
            end
            FP_ACCUMULATE_DOT: begin
              if (entry_affine_q[fp_tag_out.slot]) begin
                entry_positive_q[fp_tag_out.slot] <= fp_result;
                entry_state_q[fp_tag_out.slot] <= FP_ACCUMULATE_MIN;
              end else begin
                accumulator_data_q[
                    entry_accumulator_index_q[fp_tag_out.slot][2:0]][
                    entry_accumulator_index_q[fp_tag_out.slot][6:3]] <= fp_result;
                accumulator_valid_q[entry_accumulator_index_q[fp_tag_out.slot]] <=
                    1'b1;
                entry_valid_q[fp_tag_out.slot] <= 1'b0;
                update_valid_o <= 1'b1;
                update_index_o <=
                    entry_accumulator_index_q[fp_tag_out.slot];
                update_data_o <= fp_result;
                accumulator_updates_o <= accumulator_updates_o + 1'b1;
              end
            end
            FP_ACCUMULATE_MIN: begin
              accumulator_data_q[
                  entry_accumulator_index_q[fp_tag_out.slot][2:0]][
                  entry_accumulator_index_q[fp_tag_out.slot][6:3]] <= fp_result;
              accumulator_valid_q[entry_accumulator_index_q[fp_tag_out.slot]] <=
                  1'b1;
              entry_valid_q[fp_tag_out.slot] <= 1'b0;
              update_valid_o <= 1'b1;
              update_index_o <= entry_accumulator_index_q[fp_tag_out.slot];
              update_data_o <= fp_result;
              accumulator_updates_o <= accumulator_updates_o + 1'b1;
            end
            default: ;
          endcase
        end
      end

`ifndef SYNTHESIS
      if (clear_i)
        assert (!busy_o)
          else $fatal(1, "QBS accumulator cleared while FP work is active");
      if (request_valid_i && request_ready_o) begin
        assert (qbs_weight_block_bytes(request_profile_i) != 0);
        assert (qbs_profiles_compatible(request_profile_i,
                                        request_activation_profile_i));
        if (!request_first_block_i)
          assert (accumulator_valid_q[request_accumulator_index_i])
            else $fatal(1, "QBS accumulator continuation without prior value");
      end
      if (fp_out_valid) begin
        assert (entry_valid_q[fp_tag_out.slot] &&
                entry_inflight_q[fp_tag_out.slot])
          else $fatal(1, "QBS FP response for inactive entry");
        assert (entry_state_q[fp_tag_out.slot] == fp_tag_out.state)
          else $fatal(1, "QBS FP response state mismatch");
      end
      for (int left = 0; left < NumEntries; left++) begin
        for (int right = left + 1; right < NumEntries; right++) begin
          if (entry_valid_q[left] && entry_valid_q[right])
            assert (entry_accumulator_index_q[left] !=
                    entry_accumulator_index_q[right])
              else $fatal(1, "duplicate QBS accumulator update in flight");
        end
      end
`endif
    end
  end

endmodule : qbs_fp_accumulator
