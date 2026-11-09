// SPDX-License-Identifier: Apache-2.0
// Four-lane resident-PV owner. Arithmetic and accumulator storage live in lanes.
module akv_resident_pv_control
  import ara_pkg::*;
  import akv_pkg::*;
(
  input logic clk_i, rst_ni,
  input logic command_valid_i,
  output logic command_ready_o,
  input vid_t command_id_i,
  input logic [8:0] command_control_i,
  input logic [2:0] command_rm_i,
  input logic context_valid_i,
  input logic [15:0] context_dimension_i,
  input logic [6:0] context_tokens_i,
  input logic abort_i,
  output logic lease_o, acquire_o, start_o, release_o, commit_o,
  output logic [3:0] lane_abort_o,
  input logic [3:0] lane_owned_i, lane_ready_i,
  input logic [3:0] lane_result_valid_i,
  input logic [3:0] lane_done_valid_i, lane_done_error_i,
  input logic [3:0][4:0] lane_done_flags_i,
  output logic [3:0] lane_done_ready_o,
  input logic [3:0] source_valid_i,
  output logic [3:0] source_ready_o,
  input logic [3:0][63:0] source_data_i,
  output logic row_read_o,
  output logic [5:0] row_token_o,
  output logic [3:0] row_word_o,
  input logic [255:0] row_data_i,
  // These payloads reuse the LDU data wires, but are not VRF writes.
  output logic [3:0] payload_valid_o,
  output logic [3:0][63:0] payload_data_o,
  output logic payload_seed_o, payload_value_o,
  input logic [3:0] lane_grant_i, lane_final_grant_i,
  output logic terminal_o, error_o, fatal_o,
  output logic [4:0] flags_o,
  output vid_t id_o
);
  typedef enum logic [2:0] {Idle, Acquire, Launch, Run, Drain, Release, Terminal, Fatal} state_t;
  state_t state_q;
  logic command_fire, error_q, launched_q, cancel_request, launch;
  logic [3:0] command_words, words_q;
  logic [15:0] command_dimension;
  logic dimension_valid;
  logic [6:0] tokens_q, command_tokens;
  vid_t id_q;
  logic import_ready, import_done, import_error;
  logic [3:0] seed_valid, seed_ready;
  logic [3:0][63:0] seed_data;
  logic coefficient_valid, coefficient_ready;
  logic [31:0] coefficient;
  logic reader_ready, reader_done, reader_error, reader_complete_q, reader_failed_q;
  logic stream_valid, stream_ready, stream_kind;
  logic [3:0][63:0] stream_data;
  logic fanout_ready, fanout_empty, payload_kind;
  logic [3:0] payload_valid, payload_ready;
  logic [3:0][63:0] payload_data;
  logic private_enable, commit_permit;
  logic group_ready, group_done, group_error, group_fatal, group_authorized;
  logic [4:0] group_flags;
  logic [3:0] group_abort, group_result_valid, accepted, ack_owned;
  logic [3:0][4:0] outstanding_q;
  logic count_fault_q;

  always_comb begin
    command_words = 8;
    command_dimension = 128;
    dimension_valid = 1'b1;
    unique case (command_control_i[8:7])
      2'(AkvHeadDimCode64): begin command_words=4; command_dimension=64; end
      2'(AkvHeadDimCode128): begin command_words=8; command_dimension=128; end
      2'(AkvHeadDimCode96): begin command_words=6; command_dimension=96; end
      default: dimension_valid=1'b0;
    endcase
  end
  assign command_tokens = {1'b0,command_control_i[5:0]}+7'd1;
  assign command_ready_o = state_q == Idle && import_ready && reader_ready &&
                           group_ready && !abort_i && !count_fault_q;
  assign command_fire = command_valid_i && command_ready_o;
  assign lease_o = state_q != Idle;
  assign acquire_o = state_q == Acquire && !cancel_request;
  assign release_o = state_q == Release;
  assign launch = state_q == Launch && !cancel_request;
  assign start_o = launch;
  assign commit_o = group_authorized;
  assign cancel_request = lease_o &&
      (abort_i || error_q || import_error || (reader_done && reader_error) ||
       (launched_q && !group_authorized && (|lane_done_valid_i)));
  assign lane_abort_o = launched_q ? group_abort : {4{cancel_request}};
  assign private_enable = state_q == Run && !cancel_request &&
                          !group_authorized && !group_done && !(|group_abort);
  assign commit_permit = import_done && !import_error &&
                         reader_complete_q && !reader_failed_q && !error_q;
  assign terminal_o = state_q == Terminal;
  assign error_o = terminal_o && (error_q || (launched_q && group_error));
  assign flags_o = terminal_o && !error_o ? group_flags : '0;
  assign fatal_o = state_q == Fatal || group_fatal || count_fault_q;
  assign id_o = id_q;

  akv_resident_pv_import i_import (
    .clk_i, .rst_ni, .start_valid_i(command_fire), .start_ready_o(import_ready),
    .words_i(command_words), .two_heads_i(command_control_i[6]),
    .tokens_i(command_tokens), .cancel_i(cancel_request),
    .source_valid_i, .source_ready_o, .source_data_i,
    .seed_valid_o(seed_valid), .seed_ready_i(seed_ready), .seed_data_o(seed_data),
    .coefficient_valid_o(coefficient_valid),
    .coefficient_ready_i(coefficient_ready && private_enable), .coefficient_o(coefficient),
    .done_valid_o(import_done), .done_ready_i(terminal_o), .done_error_o(import_error), .busy_o()
  );
  akv_resident_pv_reader i_reader (
    .clk_i, .rst_ni, .start_valid_i(launch), .start_ready_o(reader_ready),
    .cancel_i(cancel_request), .tokens_i(tokens_q), .words_i(words_q),
    .coefficient_valid_i(coefficient_valid && private_enable),
    .coefficient_ready_o(coefficient_ready), .coefficient_i(coefficient),
    .row_read_o, .row_token_o, .row_word_o, .row_data_i,
    .stream_valid_o(stream_valid), .stream_ready_i(stream_ready),
    .stream_is_value_o(stream_kind), .stream_data_o(stream_data),
    .done_valid_o(reader_done), .done_ready_i(lease_o), .done_error_o(reader_error), .busy_o()
  );
  resident_payload_fanout i_payload (
    .clk_i, .rst_ni, .cancel_i(!private_enable),
    .valid_i(stream_valid && private_enable), .ready_o(fanout_ready), .active_i(4'hf),
    .is_value_i(stream_kind), .data_i(stream_data), .valid_o(payload_valid),
    .ready_i(payload_ready), .is_value_o(payload_kind), .data_o(payload_data), .empty_o(fanout_empty)
  );
  assign stream_ready = private_enable && fanout_ready;
  assign payload_seed_o = |seed_valid;
  assign payload_value_o = payload_kind;
  assign payload_valid_o = private_enable ? ((|seed_valid) ? seed_valid : payload_valid) : '0;
  assign payload_data_o = (|seed_valid) ? seed_data : payload_data;
  assign seed_ready = lane_grant_i & {4{private_enable && (|seed_valid)}};
  assign payload_ready = lane_grant_i & {4{private_enable && !(|seed_valid)}};

  // Only control crosses back from lane-local results; data takes the local
  // existing LDU write port, not a round trip through this central barrier.
  akv_resident_pv_group i_group (
    .clk_i, .rst_ni, .start_valid_i(launch), .start_ready_o(group_ready),
    .start_active_i(4'hf), .abort_i(cancel_request), .abort_rejected_o(), .busy_o(), .active_o(),
    .commit_authorized_o(group_authorized), .fatal_error_o(group_fatal), .lane_abort_o(group_abort),
    .lane_result_valid_i(lane_result_valid_i & {4{commit_permit || group_authorized}}),
    .lane_result_ready_o(), .lane_result_data_i('0), .lane_result_slot_i('0), .lane_result_be_i('0),
    .result_valid_o(group_result_valid), .result_ready_i(lane_grant_i),
    .result_data_o(), .result_slot_o(), .result_be_o(),
    .lane_done_valid_i, .lane_done_ready_o, .lane_done_error_i, .lane_done_flags_i,
    .done_valid_o(group_done), .done_ready_i(terminal_o && launched_q),
    .done_error_o(group_error), .done_flags_o(group_flags)
  );
  assign accepted = group_result_valid & lane_grant_i;
  for (genvar l=0; l<4; l++) begin : gen_debt
    assign ack_owned[l] = group_authorized && (outstanding_q[l] != 0 || accepted[l]);
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) outstanding_q[l] <= 0;
      else if (command_fire) outstanding_q[l] <= 0;
      else case ({accepted[l],lane_final_grant_i[l] && ack_owned[l]})
        2'b10: if (outstanding_q[l]<16) outstanding_q[l] <= outstanding_q[l]+1'b1;
        2'b01: outstanding_q[l] <= outstanding_q[l]-1'b1;
        default: ;
      endcase
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) count_fault_q <= 0;
    else for (int l=0; l<4; l++) begin
      if (accepted[l] && outstanding_q[l]==16 && !lane_final_grant_i[l]) count_fault_q <= 1;
      if (group_authorized && lane_final_grant_i[l] && !ack_owned[l]) count_fault_q <= 1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q<=Idle; error_q<=0; launched_q<=0; words_q<=0;
      tokens_q<=0; id_q<='0; reader_complete_q<=0; reader_failed_q<=0;
    end else begin
      if (command_fire) begin
        words_q<=command_words; tokens_q<=command_tokens;
        id_q<=command_id_i; launched_q<=0;
        reader_complete_q<=0; reader_failed_q<=0;
        error_q<=!dimension_valid || command_rm_i>4 || !context_valid_i ||
                  context_dimension_i!=command_dimension || command_tokens>context_tokens_i;
      end else begin
        if (cancel_request) error_q<=1;
        if (reader_done) begin reader_complete_q<=1; reader_failed_q<=reader_error; end
      end
      case (state_q)
        Idle: if (command_fire) state_q<=Acquire;
        Acquire: begin
          if (cancel_request) state_q<=Drain;
          else if (&lane_owned_i && &lane_ready_i && group_ready && reader_ready) state_q<=Launch;
        end
        Launch: begin
          if (cancel_request) state_q<=Drain;
          else begin state_q<=Run; launched_q<=1; end
        end
        Run: if (cancel_request || group_done) state_q<=Drain;
        Drain: if (import_done && (!launched_q || (reader_complete_q && group_done)) &&
                   outstanding_q=='0) state_q<=Release;
        Release: if (lane_owned_i=='0) state_q<=Terminal;
        Terminal: state_q<=Idle;
        Fatal: ;
        default: state_q<=Fatal;
      endcase
      if (group_fatal || count_fault_q || (abort_i && group_authorized)) state_q<=Fatal;
    end
  end

  // synthesis translate_off
  longint unsigned probe_clock_q=0, probe_begin_q=0, probe_sequence_q=0;
  logic [8:0] probe_control_q;
  int probe_source_q, probe_seed_q, probe_coefficient_q, probe_value_q;
  int probe_result_q, probe_ack_q, probe_reads_q;
  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      probe_clock_q<=0; probe_begin_q<=0; probe_sequence_q<=0; probe_control_q<=0;
      probe_source_q<=0; probe_seed_q<=0; probe_coefficient_q<=0; probe_value_q<=0;
      probe_result_q<=0; probe_ack_q<=0; probe_reads_q<=0;
    end else begin
      probe_clock_q<=probe_clock_q+1;
      if (command_fire) begin
        probe_begin_q<=probe_clock_q; probe_sequence_q<=probe_sequence_q+1;
        probe_control_q<=command_control_i;
        probe_source_q<=0; probe_seed_q<=0; probe_coefficient_q<=0; probe_value_q<=0;
        probe_result_q<=0; probe_ack_q<=0; probe_reads_q<=0;
      end else if (lease_o) begin
        probe_source_q<=probe_source_q+$countones(source_valid_i & source_ready_o);
        probe_seed_q<=probe_seed_q+(payload_seed_o ? $countones(payload_valid_o & lane_grant_i) : 0);
        probe_coefficient_q<=probe_coefficient_q+(!payload_seed_o && !payload_value_o ?
            $countones(payload_valid_o & lane_grant_i) : 0);
        probe_value_q<=probe_value_q+(!payload_seed_o && payload_value_o ?
            $countones(payload_valid_o & lane_grant_i) : 0);
        probe_result_q<=probe_result_q+$countones(accepted);
        probe_ack_q<=probe_ack_q+$countones(lane_final_grant_i & ack_owned);
        probe_reads_q<=probe_reads_q+int'(row_read_o);
      end
      if (terminal_o && $test$plusargs("RESIDENT_PV_PERF")) begin
        $display("[RESIDENT_PV_PERF] seq=%0d vid=%0d control=%0d tokens=%0d words=%0d heads=%0d cycles=%0d error=%0d flags=%0d source_words=%0d seed_words=%0d coefficients=%0d value_words=%0d result_words=%0d final_acks=%0d row_reads=%0d",
            probe_sequence_q,id_q,probe_control_q,tokens_q,words_q,
            1+int'(probe_control_q[6]),probe_clock_q-probe_begin_q+1,error_o,flags_o,
            probe_source_q,probe_seed_q,probe_coefficient_q,probe_value_q,
            probe_result_q,probe_ack_q,probe_reads_q);
      end
      if ($test$plusargs("RESIDENT_PV_WATCHDOG") && lease_o &&
          probe_clock_q-probe_begin_q>=32768)
        $fatal(1,"Resident PV bounded-test watchdog state=%0d owned=%b ready=%b import=%b reader=%b group=%b sources=%0d reads=%0d results=%0d acks=%0d",
            state_q,lane_owned_i,lane_ready_i,import_done,reader_complete_q,group_done,
            probe_source_q,probe_reads_q,probe_result_q,probe_ack_q);
      if (terminal_o) begin
        assert (probe_source_q==96) else $fatal(1,"Resident PV source request not fully drained");
        if (!error_o) assert (
            probe_seed_q==4*int'(words_q)*(1+int'(probe_control_q[6])) &&
            probe_coefficient_q==4*int'(tokens_q) && probe_value_q==4*int'(tokens_q)*int'(words_q) &&
            probe_result_q==4*int'(words_q)*(1+int'(probe_control_q[6])) && probe_ack_q==probe_result_q &&
            probe_reads_q==int'(tokens_q)*int'(words_q))
          else $fatal(1,"Resident PV completed with different source/payload/result work");
      end
    end
  end
  always_ff @(posedge clk_i) if (rst_ni) begin
    assert (!(launch && (!( &lane_owned_i) || !( &lane_ready_i) || !group_ready || !reader_ready)))
      else $fatal(1,"Resident PV non-atomic launch");
    if (group_authorized) assert (import_done && !import_error && reader_complete_q &&
                                  !reader_failed_q && fanout_empty)
      else $fatal(1,"Resident PV committed before successful source/reader drain");
    if (terminal_o) assert (outstanding_q=='0 && lane_owned_i=='0 && import_done &&
                            (!launched_q || (reader_complete_q && group_done)))
      else $fatal(1,"Resident PV terminal before complete ownership drain");
    assert (!fatal_o) else $fatal(1,"Resident PV irrecoverable post-commit protocol fault");
  end
  // synthesis translate_on
endmodule
