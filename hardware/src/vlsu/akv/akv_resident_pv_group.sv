// SPDX-License-Identifier: Apache-2.0
// Standalone barrier only: the parent owns command launch, IDs and write drain.
module akv_resident_pv_group #(
  parameter int unsigned NrLanes = 4
) (
  input  logic clk_i,
  input  logic rst_ni,
  input  logic start_valid_i,
  output logic start_ready_o,
  input  logic [NrLanes-1:0] start_active_i,
  input  logic abort_i,
  output logic abort_rejected_o,
  output logic busy_o,
  output logic [NrLanes-1:0] active_o,
  output logic commit_authorized_o,
  output logic fatal_error_o,
  output logic [NrLanes-1:0] lane_abort_o,
  input  logic [NrLanes-1:0] lane_result_valid_i,
  output logic [NrLanes-1:0] lane_result_ready_o,
  input  logic [NrLanes-1:0][63:0] lane_result_data_i,
  input  logic [NrLanes-1:0][3:0] lane_result_slot_i,
  input  logic [NrLanes-1:0][7:0] lane_result_be_i,
  output logic [NrLanes-1:0] result_valid_o,
  input  logic [NrLanes-1:0] result_ready_i,
  output logic [NrLanes-1:0][63:0] result_data_o,
  output logic [NrLanes-1:0][3:0] result_slot_o,
  output logic [NrLanes-1:0][7:0] result_be_o,
  input  logic [NrLanes-1:0] lane_done_valid_i,
  output logic [NrLanes-1:0] lane_done_ready_o,
  input  logic [NrLanes-1:0] lane_done_error_i,
  input  logic [NrLanes-1:0][4:0] lane_done_flags_i,
  output logic done_valid_o,
  input  logic done_ready_i,
  output logic done_error_o,
  output logic [4:0] done_flags_o
);
  typedef enum logic [2:0] {Idle, Barrier, Commit, Cancel, Terminal} state_t;
  state_t state_q;
  logic [NrLanes-1:0] active_q, done_q, done_fire, result_enable;
  logic authorized_q, error_q, fatal_q;
  logic [4:0] flags_q, flags_next;
  logic cancel_now, all_done, done_error;

  assign start_ready_o = state_q == Idle;
  assign busy_o = state_q != Idle;
  assign active_o = active_q;
  assign commit_authorized_o = authorized_q;
  assign fatal_error_o = fatal_q;
  assign abort_rejected_o = abort_i && authorized_q;
  // Even a successful done before the first result is an invalid lane contract.
  // Do not wait forever for a lane whose terminal has already been consumed.
  assign cancel_now = state_q == Barrier &&
                      (abort_i || |(lane_done_valid_i & active_q));
  assign lane_abort_o = (state_q == Cancel || cancel_now) ? active_q : '0;
  assign lane_done_ready_o = (state_q == Barrier || state_q == Commit ||
                             state_q == Cancel) ? (active_q & ~done_q) : '0;
  assign done_fire = lane_done_valid_i & lane_done_ready_o;
  assign all_done = ((done_q | done_fire) & active_q) == active_q;
  assign done_error = |(done_fire & lane_done_error_i);
  assign result_enable = (state_q == Commit && authorized_q) ?
                         (active_q & ~done_q) : '0;
  assign result_valid_o = lane_result_valid_i & result_enable;
  assign lane_result_ready_o = result_ready_i & result_enable;
  for (genvar lane = 0; lane < NrLanes; lane++) begin : gen_results
    assign result_data_o[lane] = result_valid_o[lane] ? lane_result_data_i[lane] : '0;
    assign result_slot_o[lane] = result_valid_o[lane] ? lane_result_slot_i[lane] : '0;
    assign result_be_o[lane] = result_valid_o[lane] ? lane_result_be_i[lane] : '0;
  end
  // A post-authorization protocol fault cannot be retired as a recoverable error.
  assign done_valid_o = state_q == Terminal && !fatal_q;
  assign done_error_o = done_valid_o && error_q;
  assign done_flags_o = done_valid_o && !error_q ? flags_q : '0;

  always_comb begin
    flags_next = flags_q;
    for (int lane = 0; lane < NrLanes; lane++)
      if (done_fire[lane] && !lane_done_error_i[lane])
        flags_next |= lane_done_flags_i[lane];
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= Idle;
      active_q <= '0;
      done_q <= '0;
      authorized_q <= 1'b0;
      error_q <= 1'b0;
      fatal_q <= 1'b0;
      flags_q <= '0;
    end else begin
      done_q <= done_q | done_fire;
      flags_q <= flags_next;
      if (done_error && !authorized_q) error_q <= 1'b1;
      if (done_error && authorized_q) fatal_q <= 1'b1;
      case (state_q)
        Idle: if (start_valid_i) begin
          active_q <= start_active_i;
          done_q <= '0;
          authorized_q <= 1'b0;
          flags_q <= '0;
          error_q <= abort_i || start_active_i == '0;
          if (start_active_i == '0) state_q <= Terminal;
          else if (abort_i) state_q <= Cancel;
          else state_q <= Barrier;
        end
        Barrier: begin
          if (cancel_now) begin
            error_q <= 1'b1;
            state_q <= all_done ? Terminal : Cancel;
          end else if ((lane_result_valid_i & active_q) == active_q) begin
            // Irrevocable BEFORE any external valid, irrespective of ready/grant.
            authorized_q <= 1'b1;
            state_q <= Commit;
          end
        end
        Commit: if (all_done) state_q <= Terminal;
        Cancel: if (all_done) state_q <= Terminal;
        Terminal: if (done_ready_i && !fatal_q) begin
          state_q <= Idle;
          active_q <= '0;
          authorized_q <= 1'b0;
        end
        default: state_q <= Idle;
      endcase
    end
  end

  // synthesis translate_off
  always_ff @(posedge clk_i) if (rst_ni)
    assert (!(authorized_q && done_error))
      else $fatal(1, "Resident PV group post-authorization lane error");
  // synthesis translate_on
endmodule
