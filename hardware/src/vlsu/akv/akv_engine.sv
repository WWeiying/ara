// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// Bounded Attention/KV residency and replay engine. The engine intentionally
// performs no vector arithmetic: fills use the existing translated VLSU read
// path and local loads return captured F16 payload through the normal LDU
// result interface. Existing sequencer hazards and lane completion therefore
// remain authoritative for every architectural VRF write.
module akv_engine import ara_pkg::*; import rvv_pkg::*; import qbs_pkg::*;
  import akv_pkg::*; #(
    parameter int unsigned AxiDataWidth = 128,
    parameter int unsigned AxiAddrWidth = 64,
    parameter int unsigned VAddrWidth = 64,
    parameter int unsigned PAddrWidth = 56,
    parameter int unsigned NrLanes = 4,
    parameter int unsigned VLEN = 1024,
    parameter type         vid_t = logic,
    parameter type         vaddr_t = logic,
    parameter type         axi_ar_t = logic,
    parameter type         axi_r_t = logic,
    parameter type         exception_t = logic
  ) (
    input  logic                         clk_i,
    input  logic                         rst_ni,

    input  logic                         command_valid_i,
    output logic                         command_ready_o,
    input  akv_command_e                 command_i,
    input  vid_t                         command_id_i,
    input  logic [4:0]                   command_vd_i,
    input  logic [15:0]                  command_head_dim_i,
    input  logic [VAddrWidth-1:0]        command_descriptor_address_i,
    input  logic [VAddrWidth-1:0]        command_tile_start_i,
    input  logic [VAddrWidth-1:0]        command_selector_i,
    input  axi_pkg::cache_t              command_cache_i,
    input  axi_pkg::prot_t               command_prot_i,

    // Pulses with acceptance of a valid local load. Fill, refill, release,
    // and invalid loads acknowledge only with their terminal response.
    output logic                         command_early_ack_o,
    output logic                         success_valid_o,
    output logic                         fault_valid_o,
    input  logic                         terminal_ready_i,
    output logic                         fault_is_validation_o,
    output akv_validation_error_e        validation_error_o,
    output qbs_read_fault_e              read_fault_kind_o,
    output logic [VAddrWidth-1:0]        fault_vaddr_o,
    output exception_t                   fault_mmu_exception_o,
    output logic                         context_ready_o,

    input  logic                         core_st_pending_i,
    input  logic                         en_ld_st_translation_i,
    output logic                         mmu_req_o,
    output logic [VAddrWidth-1:0]        mmu_vaddr_o,
    output logic                         mmu_is_store_o,
    input  logic                         mmu_valid_i,
    input  logic [PAddrWidth-1:0]        mmu_paddr_i,
    input  logic                         mmu_exception_valid_i,
    input  exception_t                   mmu_exception_i,

    output logic                         physical_check_valid_o,
    output logic [AxiAddrWidth-1:0]      physical_check_addr_o,
    output logic [12:0]                  physical_check_bytes_o,
    input  logic                         physical_range_allowed_i,

    output axi_ar_t                      axi_ar_o,
    output logic                         axi_ar_valid_o,
    input  logic                         axi_ar_ready_i,
    input  axi_r_t                       axi_r_i,
    input  logic                         axi_r_valid_i,
    output logic                         axi_r_ready_o,

    output logic [NrLanes-1:0]          ldu_result_req_o,
    output vid_t [NrLanes-1:0]          ldu_result_id_o,
    output vaddr_t [NrLanes-1:0]        ldu_result_addr_o,
    output logic [63:0]                 ldu_result_wdata_o [NrLanes],
    output logic [7:0]                  ldu_result_be_o [NrLanes],
    input  logic [NrLanes-1:0]          ldu_result_gnt_i,
    input  logic [NrLanes-1:0]          ldu_result_final_gnt_i,

    output logic                         busy_o,
    output logic [31:0]                  command_cycles_o,
    output logic [31:0]                  full_count_o,
    output logic [31:0]                  refill_count_o,
    output logic [31:0]                  load_count_o,
    output logic [31:0]                  release_count_o,
    output logic [31:0]                  v2_full_count_o,
    output logic [31:0]                  v2_refill_count_o,
    output logic [31:0]                  v2_query_update_count_o,
    output logic [31:0]                  v2_query_update_fault_count_o,
    output logic [31:0]                  v2_row_load_count_o,
    output logic [31:0]                  v2_column_load_count_o,
    output logic [31:0]                  v2_k_view_bank_cycles_o,
    output logic [31:0]                  v2_bank_conflict_cycles_o,
    output logic [31:0]                  v2_rejected_count_o,
    output logic [31:0]                  q_external_bytes_o,
    output logic [31:0]                  kv_external_bytes_o,
    output logic [31:0]                  replay_bytes_o,
    output logic [31:0]                  replay_backpressure_cycles_o,
    output logic [31:0]                  read_range_count_o,
    output logic [31:0]                  read_translation_count_o,
    output logic [31:0]                  read_ar_count_o,
    output logic [31:0]                  read_beat_count_o,
    output logic [31:0]                  read_payload_bytes_o,
    output logic [31:0]                  read_store_wait_cycles_o,
    output logic [31:0]                  read_backpressure_cycles_o,
    output logic [31:0]                  read_outstanding_occupancy_sum_o,
    output logic [1:0]                   read_outstanding_max_o,
    output logic [31:0]                  read_outstanding_full_cycles_o
  );

  localparam int unsigned RangeBytesWidth = 16;
  localparam int unsigned ContextBytesPerWord = 32;
  localparam int unsigned SlotBytes = AkvMaxHeadDim * 2;
  localparam int unsigned WordsPerRegister =
      VLEN / 8 / ContextBytesPerWord;

  typedef enum logic [1:0] {
    AKV_RANGE_DESCRIPTOR,
    AKV_RANGE_Q,
    AKV_RANGE_K,
    AKV_RANGE_V
  } akv_range_role_e;

  typedef struct packed {
    akv_range_role_e role;
    logic [5:0]      index;
  } akv_range_tag_t;

  typedef enum logic [3:0] {
    AKV_ENGINE_IDLE,
    AKV_ENGINE_DESCRIPTOR_REQUEST,
    AKV_ENGINE_DESCRIPTOR_WAIT,
    AKV_ENGINE_VALIDATE,
    AKV_ENGINE_PAYLOAD,
    AKV_ENGINE_COLUMN_GATHER,
    AKV_ENGINE_REPLAY_READ,
    AKV_ENGINE_REPLAY_WRITE,
    AKV_ENGINE_SUCCESS,
    AKV_ENGINE_FAULT
  } akv_engine_state_e;

  akv_engine_state_e state_d, state_q;

  vid_t id_q;
  logic [4:0] vd_q;
  logic [VAddrWidth-1:0] descriptor_address_q;
  logic [VAddrWidth-1:0] requested_tile_start_q;
  axi_pkg::cache_t cache_q;
  axi_pkg::prot_t prot_q;
  akv_command_e active_command_q;

  logic [511:0] descriptor_q;
  logic [63:0] descriptor_byte_valid_q;
  akv_descriptor_v1_t descriptor;
  akv_validation_error_e descriptor_error;
  logic descriptor_valid;

  logic context_ready_q;
  logic [7:0] context_q_rows_q;
  logic [15:0] context_head_dim_q;
  logic [15:0] context_kv_length_q;
  logic [31:0] context_q_stride_q;
  logic [31:0] context_k_stride_q;
  logic [31:0] context_v_stride_q;
  logic [63:0] context_q_base_q;
  logic [63:0] context_k_base_q;
  logic [63:0] context_v_base_q;
  logic [6:0] context_tile_count_q;
  logic context_v2_q;

  logic [15:0] fill_tile_start_q;
  logic [6:0] fill_tile_count_q;
  logic [7:0] range_issue_index_q;
  logic [7:0] range_completion_count_q;

  logic [4:0] replay_slot_q;
  akv_stream_e replay_stream_q;
  logic [5:0] replay_token_q;
  logic replay_use_v2_q;
  logic replay_column_q;
  logic [3:0] replay_word_q;
  logic [255:0] replay_data;
  logic [255:0] v1_replay_data;
  logic [255:0] v2_row_data;
  logic [1023:0] v2_column_data;
  logic v2_column_busy, v2_column_valid;
  logic v2_column_bank_cycle, v2_context_conflict;
  logic [NrLanes-1:0] replay_accepted_q;
  logic [NrLanes-1:0] replay_final_seen_q;

  logic fault_is_validation_q;
  akv_validation_error_e validation_error_q;
  qbs_read_fault_e read_fault_kind_q;
  logic [VAddrWidth-1:0] fault_vaddr_q;
  exception_t fault_mmu_exception_q;

  logic command_fire;
  akv_validation_error_e command_load_error;
  logic command_load_valid;
  logic [4:0] command_load_slot;
  logic command_load_use_v2_row;
  akv_stream_e command_load_stream;
  logic [5:0] command_load_token;
  akv_validation_error_e command_column_error;
  logic command_column_valid;

  logic read_range_valid, read_range_ready;
  logic [VAddrWidth-1:0] read_range_vaddr;
  logic [RangeBytesWidth-1:0] read_range_bytes;
  akv_range_tag_t read_range_tag;
  logic read_data_valid, read_data_ready;
  logic [AxiDataWidth-1:0] read_data;
  logic [AxiDataWidth/8-1:0] read_data_strb;
  logic [RangeBytesWidth-1:0] read_data_offset;
  akv_range_tag_t read_data_tag;
  logic read_completion_valid, read_completion_ready;
  akv_range_tag_t read_completion_tag;
  logic read_fault_valid, read_fault_ready;
  qbs_read_fault_e read_fault_kind;
  logic [VAddrWidth-1:0] read_fault_vaddr;
  akv_range_tag_t read_fault_tag;
  exception_t read_fault_mmu_exception;
  logic read_busy;
  logic read_range_fire, read_data_fire, read_completion_fire;
  logic [4:0] context_write_slot;
  logic context_write_busy;
  logic v1_context_write_busy;
  logic v2_context_write_busy;
  logic v1_context_write_valid;
  logic v2_context_write_valid;
  akv_stream_e v2_context_write_stream;

  logic [7:0] payload_range_count;
  logic [15:0] payload_row_bytes;
  logic payload_complete;
  logic [NrLanes-1:0] replay_request_fire;
  logic [NrLanes-1:0] replay_accepted_next;
  logic [NrLanes-1:0] replay_final_next;
  logic [3:0] replay_word_count;
  logic [6:0] replay_word_bytes;
  logic active_command_is_full;
  logic active_command_is_v2;
  logic active_command_has_q;
  logic active_command_has_kv;
  akv_validation_error_e command_query_update_error;
  logic command_query_update_valid;
  logic v2_column_start;

  assign command_ready_o = state_q == AKV_ENGINE_IDLE;
  assign command_fire = command_valid_i && command_ready_o;
  assign busy_o = state_q != AKV_ENGINE_IDLE;
  assign success_valid_o = state_q == AKV_ENGINE_SUCCESS;
  assign fault_valid_o = state_q == AKV_ENGINE_FAULT;
  assign fault_is_validation_o = fault_is_validation_q;
  assign validation_error_o = validation_error_q;
  assign read_fault_kind_o = read_fault_kind_q;
  assign fault_vaddr_o = fault_vaddr_q;
  assign fault_mmu_exception_o = fault_mmu_exception_q;
  assign context_ready_o = context_ready_q;
  assign active_command_is_full = active_command_q inside {
      AKV_COMMAND_FULL, AKV_COMMAND_V2_FULL};
  assign active_command_is_v2 = active_command_q inside {
      AKV_COMMAND_V2_FULL, AKV_COMMAND_V2_REFILL,
      AKV_COMMAND_V2_QUERY_UPDATE, AKV_COMMAND_V2_COLUMN_LOAD};
  assign active_command_has_q = active_command_is_full ||
      active_command_q == AKV_COMMAND_V2_QUERY_UPDATE;
  assign active_command_has_kv = active_command_q inside {
      AKV_COMMAND_FULL, AKV_COMMAND_REFILL,
      AKV_COMMAND_V2_FULL, AKV_COMMAND_V2_REFILL};

  always_comb begin : validate_query_update_command
    automatic logic [64:0] query_last;

    command_query_update_error = AKV_VALIDATION_OK;
    query_last = '0;
    if (!context_ready_q || !context_v2_q)
      command_query_update_error = AKV_VALIDATION_CONTEXT;
    else if (command_tile_start_i != '0)
      command_query_update_error = AKV_VALIDATION_COMMAND;
    else if (command_descriptor_address_i == '0 ||
             command_descriptor_address_i[
                 AkvV2PayloadAlignmentLog2-1:0] != '0)
      command_query_update_error = AKV_VALIDATION_STRIDE;
    else begin
      query_last = 65'(command_descriptor_address_i) +
          65'(context_q_stride_q) *
              65'(unsigned'(context_q_rows_q) - 1) +
          (65'(context_head_dim_q) << 1) - 1'b1;
      if (query_last[64])
        command_query_update_error = AKV_VALIDATION_RANGE_OVERFLOW;
    end
  end
  assign command_query_update_valid =
      command_query_update_error == AKV_VALIDATION_OK;

  always_comb begin : validate_load_command
    automatic logic [1:0] stream;
    automatic logic [5:0] index;

    stream = command_selector_i[1:0];
    index = command_selector_i[7:2];
    command_load_error = AKV_VALIDATION_OK;
    command_load_slot = '0;
    command_load_use_v2_row = 1'b0;
    command_load_stream = akv_stream_e'(stream);
    command_load_token = index;

    if (!context_ready_q)
      command_load_error = AKV_VALIDATION_CONTEXT;
    else if (!(command_head_dim_i inside {16'd64, 16'd128}) &&
             !(context_v2_q && command_head_dim_i == 16'd96))
      command_load_error = AKV_VALIDATION_HEAD_DIM;
    else if (command_head_dim_i != context_head_dim_q)
      command_load_error = AKV_VALIDATION_HEAD_DIM;
    else if ((context_v2_q
                  ? command_selector_i[VAddrWidth-1:8] != '0
                  : command_selector_i[VAddrWidth-1:5] != '0) ||
             stream == 2'b11)
      command_load_error = AKV_VALIDATION_SELECTOR;
    else if (command_head_dim_i > 64 &&
             (command_vd_i[0] || command_vd_i > 5'd30))
      command_load_error = AKV_VALIDATION_DESTINATION;
    else begin
      unique case (akv_stream_e'(stream))
        AKV_STREAM_Q: begin
          if (unsigned'(index) >= unsigned'(context_q_rows_q))
            command_load_error = AKV_VALIDATION_SELECTOR;
          else
            command_load_slot = 5'(index);
        end
        AKV_STREAM_K: begin
          if (unsigned'(index) >= unsigned'(context_tile_count_q))
            command_load_error = AKV_VALIDATION_SELECTOR;
          else if (context_v2_q)
            command_load_use_v2_row = 1'b1;
          else
            command_load_slot = 5'(AkvMaxQRows + unsigned'(index));
        end
        AKV_STREAM_V: begin
          if (unsigned'(index) >= unsigned'(context_tile_count_q))
            command_load_error = AKV_VALIDATION_SELECTOR;
          else if (context_v2_q)
            command_load_use_v2_row = 1'b1;
          else
            command_load_slot =
                5'(AkvMaxQRows + AkvTileTokens + unsigned'(index));
        end
        default: command_load_error = AKV_VALIDATION_SELECTOR;
      endcase
    end
  end

  assign command_load_valid = command_load_error == AKV_VALIDATION_OK;
  always_comb begin : validate_column_command
    command_column_error = AKV_VALIDATION_OK;
    if (!context_ready_q || !context_v2_q)
      command_column_error = AKV_VALIDATION_CONTEXT;
    else if (command_selector_i[VAddrWidth-1:8] != '0 ||
             8'({1'b0, command_selector_i[6:0]}) >=
                 context_head_dim_q[7:0])
      command_column_error = AKV_VALIDATION_SELECTOR;
  end
  assign command_column_valid =
      command_column_error == AKV_VALIDATION_OK;
  assign command_early_ack_o = command_fire &&
      ((command_i == AKV_COMMAND_LOAD && command_load_valid) ||
       (command_i == AKV_COMMAND_V2_COLUMN_LOAD && command_column_valid));
  assign v2_column_start = command_fire &&
      command_i == AKV_COMMAND_V2_COLUMN_LOAD && command_column_valid;

  assign descriptor = akv_descriptor_v1_t'(descriptor_q);

  always_comb begin : validate_descriptor
    automatic logic [64:0] q_last;
    automatic logic [64:0] k_last;
    automatic logic [64:0] v_last;
    automatic logic [64:0] row_bytes;

    row_bytes = 65'(descriptor.head_dim) << 1;
    q_last = 65'(descriptor.q_base) +
        65'(descriptor.q_row_stride_bytes) *
            65'(unsigned'(descriptor.q_rows) - 1) + row_bytes - 1'b1;
    k_last = 65'(descriptor.k_base) +
        65'(descriptor.k_token_stride_bytes) *
            65'(unsigned'(descriptor.kv_length) - 1) + row_bytes - 1'b1;
    v_last = 65'(descriptor.v_base) +
        65'(descriptor.v_token_stride_bytes) *
            65'(unsigned'(descriptor.kv_length) - 1) + row_bytes - 1'b1;

    descriptor_error = AKV_VALIDATION_OK;
    if (descriptor.version != AkvDescriptorVersion)
      descriptor_error = AKV_VALIDATION_DESCRIPTOR_VERSION;
    else if (descriptor.element_format != AKV_ELEMENT_FORMAT_F16)
      descriptor_error = AKV_VALIDATION_DESCRIPTOR_FORMAT;
    else if (!(descriptor.q_rows inside {[1:AkvMaxQRows]}))
      descriptor_error = AKV_VALIDATION_Q_ROWS;
    else if (!(descriptor.head_dim inside {16'd64, 16'd128}) &&
             !(active_command_q == AKV_COMMAND_V2_FULL &&
               descriptor.head_dim == 16'd96))
      descriptor_error = AKV_VALIDATION_HEAD_DIM;
    else if (descriptor.kv_length == 0)
      descriptor_error = AKV_VALIDATION_KV_LENGTH;
    else if (descriptor.flags != 0 || descriptor.reserved0 != 0 ||
             descriptor.reserved1 != 0 || descriptor.reserved2 != 0)
      descriptor_error = AKV_VALIDATION_RESERVED;
    else if (active_command_q == AKV_COMMAND_V2_FULL &&
             (descriptor.q_row_stride_bytes[
                  AkvV2PayloadAlignmentLog2-1:0] != '0 ||
              descriptor.k_token_stride_bytes[
                  AkvV2PayloadAlignmentLog2-1:0] != '0 ||
              descriptor.v_token_stride_bytes[
                  AkvV2PayloadAlignmentLog2-1:0] != '0 ||
              descriptor.q_base[AkvV2PayloadAlignmentLog2-1:0] != '0 ||
              descriptor.k_base[AkvV2PayloadAlignmentLog2-1:0] != '0 ||
              descriptor.v_base[AkvV2PayloadAlignmentLog2-1:0] != '0))
      descriptor_error = AKV_VALIDATION_STRIDE;
    else if (descriptor.q_row_stride_bytes[0] ||
             descriptor.k_token_stride_bytes[0] ||
             descriptor.v_token_stride_bytes[0] ||
             descriptor.q_row_stride_bytes < row_bytes ||
             descriptor.k_token_stride_bytes < row_bytes ||
             descriptor.v_token_stride_bytes < row_bytes ||
             descriptor.q_base[0] || descriptor.k_base[0] ||
             descriptor.v_base[0])
      descriptor_error = AKV_VALIDATION_STRIDE;
    else if (q_last[64] || k_last[64] || v_last[64])
      descriptor_error = AKV_VALIDATION_RANGE_OVERFLOW;
    else if (requested_tile_start_q >= descriptor.kv_length)
      descriptor_error = AKV_VALIDATION_TILE_RANGE;
  end

  assign descriptor_valid = descriptor_error == AKV_VALIDATION_OK;
  assign payload_row_bytes = context_head_dim_q << 1;
  always_comb begin
    payload_range_count = '0;
    if (active_command_has_q)
      payload_range_count += 8'(context_q_rows_q);
    if (active_command_has_kv)
      payload_range_count += 8'(2 * unsigned'(fill_tile_count_q));
  end

  always_comb begin : form_read_range
    automatic int unsigned logical_index;
    automatic logic [63:0] token_index;
    automatic logic [63:0] byte_offset;

    read_range_valid = 1'b0;
    read_range_vaddr = '0;
    read_range_bytes = '0;
    read_range_tag = '{role: AKV_RANGE_DESCRIPTOR, index: '0};
    logical_index = unsigned'(range_issue_index_q);
    token_index = '0;
    byte_offset = '0;

    if (state_q == AKV_ENGINE_DESCRIPTOR_REQUEST) begin
      read_range_valid = 1'b1;
      read_range_vaddr = descriptor_address_q;
      read_range_bytes = RangeBytesWidth'(AkvDescriptorBytes);
      read_range_tag = '{role: AKV_RANGE_DESCRIPTOR, index: '0};
    end else if (state_q == AKV_ENGINE_PAYLOAD &&
                 range_issue_index_q < payload_range_count) begin
      read_range_valid = 1'b1;
      read_range_bytes = RangeBytesWidth'(payload_row_bytes);
      if (active_command_has_q &&
          logical_index < unsigned'(context_q_rows_q)) begin
        read_range_tag = '{role: AKV_RANGE_Q, index: 6'(logical_index)};
        byte_offset = 64'(logical_index) * context_q_stride_q;
        read_range_vaddr = VAddrWidth'(
            (active_command_q == AKV_COMMAND_V2_QUERY_UPDATE
                 ? descriptor_address_q : context_q_base_q) + byte_offset);
      end else begin
        if (active_command_has_q)
          logical_index -= unsigned'(context_q_rows_q);
        if (logical_index < unsigned'(fill_tile_count_q)) begin
          token_index = 64'(fill_tile_start_q) + 64'(logical_index);
          read_range_tag = '{role: AKV_RANGE_K,
                            index: 6'(logical_index)};
          byte_offset = token_index * context_k_stride_q;
          read_range_vaddr = VAddrWidth'(context_k_base_q + byte_offset);
        end else begin
          logical_index -= unsigned'(fill_tile_count_q);
          token_index = 64'(fill_tile_start_q) + 64'(logical_index);
          read_range_tag = '{role: AKV_RANGE_V,
                            index: 6'(logical_index)};
          byte_offset = token_index * context_v_stride_q;
          read_range_vaddr = VAddrWidth'(context_v_base_q + byte_offset);
        end
      end
    end
  end

  assign read_range_fire = read_range_valid && read_range_ready;
  assign read_data_ready = state_q inside {
      AKV_ENGINE_DESCRIPTOR_WAIT, AKV_ENGINE_PAYLOAD};
  assign read_data_fire = read_data_valid && read_data_ready;
  assign read_completion_ready =
      (state_q == AKV_ENGINE_DESCRIPTOR_WAIT &&
       read_completion_tag.role == AKV_RANGE_DESCRIPTOR) ||
      (state_q == AKV_ENGINE_PAYLOAD &&
       read_completion_tag.role != AKV_RANGE_DESCRIPTOR);
  assign read_completion_fire =
      read_completion_valid && read_completion_ready;
  assign read_fault_ready = state_q inside {
      AKV_ENGINE_DESCRIPTOR_WAIT, AKV_ENGINE_PAYLOAD};
  assign payload_complete = state_q == AKV_ENGINE_PAYLOAD &&
      range_issue_index_q == payload_range_count &&
      (range_completion_count_q + read_completion_fire ==
       payload_range_count) && !context_write_busy;

  qbs_read_engine #(
    .AxiDataWidth    (AxiDataWidth),
    .AxiAddrWidth    (AxiAddrWidth),
    .VAddrWidth      (VAddrWidth),
    .PAddrWidth      (PAddrWidth),
    .RangeBytesWidth (RangeBytesWidth),
    .ReadOutstanding (2),
    .axi_ar_t        (axi_ar_t),
    .axi_r_t         (axi_r_t),
    .exception_t     (exception_t),
    .tag_t           (akv_range_tag_t)
  ) i_read_engine (
    .clk_i,
    .rst_ni,
    .range_valid_i                  (read_range_valid),
    .range_ready_o                  (read_range_ready),
    .range_vaddr_i                  (read_range_vaddr),
    .range_bytes_i                  (read_range_bytes),
    .range_tag_i                    (read_range_tag),
    .range_cache_i                  (cache_q),
    .range_prot_i                   (prot_q),
    .data_valid_o                   (read_data_valid),
    .data_ready_i                   (read_data_ready),
    .data_o                         (read_data),
    .data_strb_o                    (read_data_strb),
    .data_offset_o                  (read_data_offset),
    .data_tag_o                     (read_data_tag),
    .completion_valid_o             (read_completion_valid),
    .completion_ready_i             (read_completion_ready),
    .completion_tag_o               (read_completion_tag),
    .fault_valid_o                  (read_fault_valid),
    .fault_ready_i                  (read_fault_ready),
    .fault_kind_o                   (read_fault_kind),
    .fault_vaddr_o                  (read_fault_vaddr),
    .fault_tag_o                    (read_fault_tag),
    .fault_mmu_exception_o          (read_fault_mmu_exception),
    .core_st_pending_i,
    .en_ld_st_translation_i,
    .mmu_req_o,
    .mmu_vaddr_o,
    .mmu_is_store_o,
    .mmu_valid_i,
    .mmu_paddr_i,
    .mmu_exception_valid_i,
    .mmu_exception_i,
    .physical_check_valid_o,
    .physical_check_addr_o,
    .physical_check_bytes_o,
    .physical_range_allowed_i,
    .axi_ar_o,
    .axi_ar_valid_o,
    .axi_ar_ready_i,
    .axi_r_i,
    .axi_r_valid_i,
    .axi_r_ready_o,
    .counters_clear_i              (command_fire),
    .range_count_o                 (read_range_count_o),
    .translation_count_o           (read_translation_count_o),
    .ar_count_o                    (read_ar_count_o),
    .r_beat_count_o                (read_beat_count_o),
    .payload_byte_count_o          (read_payload_bytes_o),
    .store_wait_cycles_o           (read_store_wait_cycles_o),
    .r_backpressure_cycles_o       (read_backpressure_cycles_o),
    .outstanding_occupancy_sum_o   (read_outstanding_occupancy_sum_o),
    .outstanding_max_o             (read_outstanding_max_o),
    .outstanding_full_cycles_o     (read_outstanding_full_cycles_o),
    .busy_o                        (read_busy)
  );

  always_comb begin
    unique case (read_data_tag.role)
      AKV_RANGE_Q:
        context_write_slot = 5'(unsigned'(read_data_tag.index));
      AKV_RANGE_K:
        context_write_slot =
            5'(AkvMaxQRows + unsigned'(read_data_tag.index));
      default:
        context_write_slot = 5'(AkvMaxQRows + AkvTileTokens +
                                unsigned'(read_data_tag.index));
    endcase
  end

  assign v1_context_write_valid = read_data_fire &&
      read_data_tag.role != AKV_RANGE_DESCRIPTOR &&
      (!active_command_is_v2 || read_data_tag.role == AKV_RANGE_Q);
  assign v2_context_write_valid = read_data_fire && active_command_is_v2 &&
      read_data_tag.role inside {AKV_RANGE_K, AKV_RANGE_V};
  assign v2_context_write_stream = read_data_tag.role == AKV_RANGE_K
      ? AKV_STREAM_K : AKV_STREAM_V;
  assign context_write_busy =
      v1_context_write_busy || v2_context_write_busy;

  akv_context i_context (
    .clk_i,
    .rst_ni,
    .write_valid_i  (v1_context_write_valid),
    .write_slot_i   (context_write_slot),
    .write_offset_i (read_data_offset[7:0]),
    .write_data_i   (read_data),
    .write_strb_i   (read_data_strb),
    .write_busy_o   (v1_context_write_busy),
    .replay_read_i  (state_q == AKV_ENGINE_REPLAY_READ &&
                     !replay_use_v2_q && !replay_column_q),
    .replay_slot_i  (replay_slot_q),
    .replay_word_i  (replay_word_q),
    .replay_data_o  (v1_replay_data)
  );

  akv_v2_context i_v2_context (
    .clk_i,
    .rst_ni,
    .write_valid_i       (v2_context_write_valid),
    .write_stream_i      (v2_context_write_stream),
    .write_token_i       (read_data_tag.index),
    .write_offset_i      (read_data_offset[7:0]),
    .write_data_i        (read_data),
    .write_strb_i        (read_data_strb),
    .write_busy_o        (v2_context_write_busy),
    .row_read_i          (state_q == AKV_ENGINE_REPLAY_READ &&
                          replay_use_v2_q && !replay_column_q),
    .row_stream_i        (replay_stream_q),
    .row_token_i         (replay_token_q),
    .row_word_i          (replay_word_q),
    .row_data_o          (v2_row_data),
    .column_start_i      (v2_column_start),
    .column_stream_i     (command_selector_i[AkvV2ColumnSegmentBit]
                              ? AKV_STREAM_V : AKV_STREAM_K),
    .column_dimension_i  (command_selector_i[6:0]),
    .column_token_count_i(context_tile_count_q),
    .column_busy_o       (v2_column_busy),
    .column_valid_o      (v2_column_valid),
    .column_data_o       (v2_column_data),
    .column_bank_cycle_o (v2_column_bank_cycle),
    .conflict_o          (v2_context_conflict)
  );

  always_comb begin
    if (replay_column_q)
      replay_data = v2_column_data[unsigned'(replay_word_q)*256 +: 256];
    else if (replay_use_v2_q)
      replay_data = v2_row_data;
    else
      replay_data = v1_replay_data;
  end

  always_comb begin : form_replay_result
    for (int unsigned lane = 0; lane < NrLanes; lane++) begin
      ldu_result_req_o[lane] = state_q == AKV_ENGINE_REPLAY_WRITE &&
                               !replay_accepted_q[lane];
      ldu_result_id_o[lane] = id_q;
      ldu_result_addr_o[lane] = vaddr_t'(
          unsigned'(vd_q) * WordsPerRegister + unsigned'(replay_word_q));
      ldu_result_wdata_o[lane] = '0;
      ldu_result_be_o[lane] = '0;
    end

    for (int unsigned logical_byte = 0;
         logical_byte < ContextBytesPerWord; logical_byte++) begin
      automatic int unsigned physical_byte =
          shuffle_index(logical_byte, NrLanes, EW16);
      automatic int unsigned lane = physical_byte / 8;
      automatic int unsigned lane_byte = physical_byte % 8;
      automatic int unsigned replay_byte =
          unsigned'(replay_word_q) * ContextBytesPerWord + logical_byte;
      if (!replay_column_q ||
          replay_byte < unsigned'(context_tile_count_q) * 2) begin
        ldu_result_wdata_o[lane][lane_byte*8 +: 8] =
            replay_data[logical_byte*8 +: 8];
        ldu_result_be_o[lane][lane_byte] = 1'b1;
      end
    end
  end

  assign replay_request_fire = ldu_result_req_o & ldu_result_gnt_i;
  assign replay_accepted_next = replay_accepted_q | replay_request_fire;
  assign replay_final_next = replay_final_seen_q |
      (ldu_result_final_gnt_i & (replay_accepted_q | replay_request_fire));
  assign replay_word_count = replay_column_q ? 4'd4 :
      4'(unsigned'(context_head_dim_q) >> 4);
  always_comb begin
    replay_word_bytes = '0;
    for (int unsigned lane = 0; lane < NrLanes; lane++)
      replay_word_bytes += 7'($countones(ldu_result_be_o[lane]));
  end

  always_comb begin
    state_d = state_q;
    unique case (state_q)
      AKV_ENGINE_IDLE: begin
        if (command_valid_i) begin
          unique case (command_i)
            AKV_COMMAND_FULL, AKV_COMMAND_V2_FULL: begin
              if (command_descriptor_address_i[
                    AkvDescriptorAlignmentLog2-1:0] != '0)
                state_d = AKV_ENGINE_FAULT;
              else
                state_d = AKV_ENGINE_DESCRIPTOR_REQUEST;
            end
            AKV_COMMAND_REFILL, AKV_COMMAND_V2_REFILL: begin
              if (!context_ready_q ||
                  (command_i == AKV_COMMAND_V2_REFILL) != context_v2_q ||
                  command_tile_start_i >= context_kv_length_q)
                state_d = AKV_ENGINE_FAULT;
              else
                state_d = AKV_ENGINE_PAYLOAD;
            end
            AKV_COMMAND_V2_QUERY_UPDATE: begin
              if (command_query_update_valid)
                state_d = AKV_ENGINE_PAYLOAD;
              else
                state_d = AKV_ENGINE_FAULT;
            end
            AKV_COMMAND_LOAD: begin
              if (command_load_valid)
                state_d = AKV_ENGINE_REPLAY_READ;
              else
                state_d = AKV_ENGINE_FAULT;
            end
            AKV_COMMAND_V2_COLUMN_LOAD: begin
              if (command_column_valid)
                state_d = AKV_ENGINE_COLUMN_GATHER;
              else
                state_d = AKV_ENGINE_FAULT;
            end
            AKV_COMMAND_RELEASE: state_d = AKV_ENGINE_SUCCESS;
            default: state_d = AKV_ENGINE_FAULT;
          endcase
        end
      end

      AKV_ENGINE_DESCRIPTOR_REQUEST: begin
        if (read_range_fire)
          state_d = AKV_ENGINE_DESCRIPTOR_WAIT;
      end

      AKV_ENGINE_DESCRIPTOR_WAIT: begin
        if (read_fault_valid)
          state_d = AKV_ENGINE_FAULT;
        else if (read_completion_valid) begin
          if (&descriptor_byte_valid_q)
            state_d = AKV_ENGINE_VALIDATE;
          else
            state_d = AKV_ENGINE_FAULT;
        end
      end

      AKV_ENGINE_VALIDATE: begin
        state_d = descriptor_valid
            ? AKV_ENGINE_PAYLOAD : AKV_ENGINE_FAULT;
      end

      AKV_ENGINE_PAYLOAD: begin
        if (read_fault_valid)
          state_d = AKV_ENGINE_FAULT;
        else if (payload_complete)
          state_d = AKV_ENGINE_SUCCESS;
      end

      AKV_ENGINE_COLUMN_GATHER: begin
        if (v2_column_valid)
          state_d = AKV_ENGINE_REPLAY_WRITE;
      end

      AKV_ENGINE_REPLAY_READ: state_d = AKV_ENGINE_REPLAY_WRITE;

      AKV_ENGINE_REPLAY_WRITE: begin
        if (&replay_accepted_next && &replay_final_next)
          state_d = unsigned'(replay_word_q) + 1 == replay_word_count
              ? AKV_ENGINE_SUCCESS : AKV_ENGINE_REPLAY_READ;
      end

      AKV_ENGINE_SUCCESS: begin
        if (terminal_ready_i)
          state_d = AKV_ENGINE_IDLE;
      end

      AKV_ENGINE_FAULT: begin
        if (terminal_ready_i)
          state_d = AKV_ENGINE_IDLE;
      end

      default: state_d = AKV_ENGINE_IDLE;
    endcase
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      state_q <= AKV_ENGINE_IDLE;
      id_q <= '0;
      vd_q <= '0;
      descriptor_address_q <= '0;
      requested_tile_start_q <= '0;
      cache_q <= '0;
      prot_q <= '0;
      active_command_q <= AKV_COMMAND_FULL;
      descriptor_q <= '0;
      descriptor_byte_valid_q <= '0;
      context_ready_q <= 1'b0;
      context_q_rows_q <= '0;
      context_head_dim_q <= '0;
      context_kv_length_q <= '0;
      context_q_stride_q <= '0;
      context_k_stride_q <= '0;
      context_v_stride_q <= '0;
      context_q_base_q <= '0;
      context_k_base_q <= '0;
      context_v_base_q <= '0;
      context_tile_count_q <= '0;
      context_v2_q <= 1'b0;
      fill_tile_start_q <= '0;
      fill_tile_count_q <= '0;
      range_issue_index_q <= '0;
      range_completion_count_q <= '0;
      replay_slot_q <= '0;
      replay_stream_q <= AKV_STREAM_Q;
      replay_token_q <= '0;
      replay_use_v2_q <= 1'b0;
      replay_column_q <= 1'b0;
      replay_word_q <= '0;
      replay_accepted_q <= '0;
      replay_final_seen_q <= '0;
      fault_is_validation_q <= 1'b0;
      validation_error_q <= AKV_VALIDATION_OK;
      read_fault_kind_q <= QBS_READ_FAULT_NONE;
      fault_vaddr_q <= '0;
      fault_mmu_exception_q <= '0;
      command_cycles_o <= '0;
      full_count_o <= '0;
      refill_count_o <= '0;
      load_count_o <= '0;
      release_count_o <= '0;
      v2_full_count_o <= '0;
      v2_refill_count_o <= '0;
      v2_query_update_count_o <= '0;
      v2_query_update_fault_count_o <= '0;
      v2_row_load_count_o <= '0;
      v2_column_load_count_o <= '0;
      v2_k_view_bank_cycles_o <= '0;
      v2_bank_conflict_cycles_o <= '0;
      v2_rejected_count_o <= '0;
      q_external_bytes_o <= '0;
      kv_external_bytes_o <= '0;
      replay_bytes_o <= '0;
      replay_backpressure_cycles_o <= '0;
    end else begin
      state_q <= state_d;

      if (command_fire) begin
        id_q <= command_id_i;
        vd_q <= command_vd_i;
        descriptor_address_q <= command_descriptor_address_i;
        requested_tile_start_q <= command_tile_start_i;
        cache_q <= command_cache_i;
        prot_q <= command_prot_i;
        active_command_q <= command_i;
        descriptor_q <= '0;
        descriptor_byte_valid_q <= '0;
        range_issue_index_q <= '0;
        range_completion_count_q <= '0;
        replay_word_q <= '0;
        replay_accepted_q <= '0;
        replay_final_seen_q <= '0;
        fault_is_validation_q <= 1'b0;
        validation_error_q <= AKV_VALIDATION_OK;
        read_fault_kind_q <= QBS_READ_FAULT_NONE;
        fault_vaddr_q <= '0;
        fault_mmu_exception_q <= '0;
        command_cycles_o <= '0;
        full_count_o <= command_i == AKV_COMMAND_FULL;
        refill_count_o <= command_i == AKV_COMMAND_REFILL;
        load_count_o <= command_i == AKV_COMMAND_LOAD;
        release_count_o <= command_i == AKV_COMMAND_RELEASE;
        v2_full_count_o <= command_i == AKV_COMMAND_V2_FULL;
        v2_refill_count_o <= command_i == AKV_COMMAND_V2_REFILL;
        v2_query_update_count_o <=
            command_i == AKV_COMMAND_V2_QUERY_UPDATE;
        v2_query_update_fault_count_o <= '0;
        v2_row_load_count_o <=
            command_i == AKV_COMMAND_LOAD && context_v2_q;
        v2_column_load_count_o <=
            command_i == AKV_COMMAND_V2_COLUMN_LOAD;
        v2_k_view_bank_cycles_o <= '0;
        v2_bank_conflict_cycles_o <= '0;
        v2_rejected_count_o <= '0;
        q_external_bytes_o <= '0;
        kv_external_bytes_o <= '0;
        replay_bytes_o <= '0;
        replay_backpressure_cycles_o <= '0;

        unique case (command_i)
          AKV_COMMAND_FULL, AKV_COMMAND_V2_FULL: begin
            context_ready_q <= 1'b0;
            if (command_descriptor_address_i[
                  AkvDescriptorAlignmentLog2-1:0] != '0) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= AKV_VALIDATION_DESCRIPTOR_ALIGNMENT;
              if (command_i == AKV_COMMAND_V2_FULL)
                v2_rejected_count_o <= 32'd1;
            end
          end
          AKV_COMMAND_REFILL, AKV_COMMAND_V2_REFILL: begin
            context_ready_q <= 1'b0;
            fill_tile_start_q <= 16'(command_tile_start_i);
            if (!context_ready_q) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= AKV_VALIDATION_CONTEXT;
              if (command_i == AKV_COMMAND_V2_REFILL)
                v2_rejected_count_o <= 32'd1;
            end else if ((command_i == AKV_COMMAND_V2_REFILL) !=
                         context_v2_q) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= AKV_VALIDATION_CONTEXT;
              if (command_i == AKV_COMMAND_V2_REFILL)
                v2_rejected_count_o <= 32'd1;
            end else if (command_tile_start_i >= context_kv_length_q) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= AKV_VALIDATION_TILE_RANGE;
              if (command_i == AKV_COMMAND_V2_REFILL)
                v2_rejected_count_o <= 32'd1;
            end else begin
              fill_tile_count_q <=
                  unsigned'(context_kv_length_q) -
                          unsigned'(command_tile_start_i) >=
                              (command_i == AKV_COMMAND_V2_REFILL
                                   ? AkvV2TileTokens : AkvTileTokens)
                      ? 7'(command_i == AKV_COMMAND_V2_REFILL
                               ? AkvV2TileTokens : AkvTileTokens)
                      : 7'(unsigned'(context_kv_length_q) -
                           unsigned'(command_tile_start_i));
            end
          end
          AKV_COMMAND_V2_QUERY_UPDATE: begin
            context_ready_q <= 1'b0;
            if (!command_query_update_valid) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= command_query_update_error;
              fault_vaddr_q <= command_descriptor_address_i;
              v2_query_update_fault_count_o <= 32'd1;
              v2_rejected_count_o <= 32'd1;
            end
          end
          AKV_COMMAND_LOAD: begin
            replay_slot_q <= command_load_slot;
            replay_stream_q <= command_load_stream;
            replay_token_q <= command_load_token;
            replay_use_v2_q <= command_load_use_v2_row;
            replay_column_q <= 1'b0;
            if (!command_load_valid) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= command_load_error;
              if (context_v2_q)
                v2_rejected_count_o <= 32'd1;
            end
          end
          AKV_COMMAND_V2_COLUMN_LOAD: begin
            replay_stream_q <= AKV_STREAM_K;
            replay_token_q <= '0;
            replay_use_v2_q <= 1'b0;
            replay_column_q <= 1'b1;
            if (!command_column_valid) begin
              fault_is_validation_q <= 1'b1;
              validation_error_q <= command_column_error;
              v2_rejected_count_o <= 32'd1;
            end
          end
          AKV_COMMAND_RELEASE: begin
            context_ready_q <= 1'b0;
            context_v2_q <= 1'b0;
          end
          default: begin
            fault_is_validation_q <= 1'b1;
            validation_error_q <= AKV_VALIDATION_COMMAND;
          end
        endcase
      end else if (busy_o) begin
        command_cycles_o <= command_cycles_o + 1'b1;
      end

      if (state_q == AKV_ENGINE_DESCRIPTOR_REQUEST) begin
        descriptor_q <= '0;
        descriptor_byte_valid_q <= '0;
      end else if (read_data_fire &&
                   read_data_tag.role == AKV_RANGE_DESCRIPTOR) begin
        for (int unsigned byte_lane = 0;
             byte_lane < AxiDataWidth / 8; byte_lane++) begin
          automatic int unsigned descriptor_offset =
              unsigned'(read_data_offset) + byte_lane;
          if (read_data_strb[byte_lane] && descriptor_offset < 64) begin
            descriptor_q[descriptor_offset*8 +: 8] <=
                read_data[byte_lane*8 +: 8];
            descriptor_byte_valid_q[descriptor_offset] <= 1'b1;
          end
        end
      end

      if (state_q == AKV_ENGINE_VALIDATE) begin
        if (descriptor_valid) begin
          context_q_rows_q <= descriptor.q_rows;
          context_head_dim_q <= descriptor.head_dim;
          context_kv_length_q <= descriptor.kv_length;
          context_q_stride_q <= descriptor.q_row_stride_bytes;
          context_k_stride_q <= descriptor.k_token_stride_bytes;
          context_v_stride_q <= descriptor.v_token_stride_bytes;
          context_q_base_q <= descriptor.q_base;
          context_k_base_q <= descriptor.k_base;
          context_v_base_q <= descriptor.v_base;
          context_v2_q <= active_command_q == AKV_COMMAND_V2_FULL;
          fill_tile_start_q <= 16'(requested_tile_start_q);
          fill_tile_count_q <=
              unsigned'(descriptor.kv_length) -
                      unsigned'(requested_tile_start_q) >=
                          (active_command_q == AKV_COMMAND_V2_FULL
                               ? AkvV2TileTokens : AkvTileTokens)
                  ? 7'(active_command_q == AKV_COMMAND_V2_FULL
                           ? AkvV2TileTokens : AkvTileTokens)
                  : 7'(unsigned'(descriptor.kv_length) -
                       unsigned'(requested_tile_start_q));
          range_issue_index_q <= '0;
          range_completion_count_q <= '0;
        end else begin
          fault_is_validation_q <= 1'b1;
          validation_error_q <= descriptor_error;
          fault_vaddr_q <= descriptor_address_q;
          if (active_command_q == AKV_COMMAND_V2_FULL)
            v2_rejected_count_o <= 32'd1;
        end
      end

      if (state_q == AKV_ENGINE_PAYLOAD) begin
        if (read_range_fire)
          range_issue_index_q <= range_issue_index_q + 1'b1;
        if (read_completion_fire)
          range_completion_count_q <= range_completion_count_q + 1'b1;
        if (payload_complete) begin
          context_ready_q <= 1'b1;
          if (active_command_q == AKV_COMMAND_V2_QUERY_UPDATE)
            context_q_base_q <= descriptor_address_q;
          else
            context_tile_count_q <= fill_tile_count_q;
        end
      end

      if (read_fault_valid && read_fault_ready) begin
        context_ready_q <= 1'b0;
        fault_is_validation_q <= 1'b0;
        validation_error_q <= AKV_VALIDATION_OK;
        read_fault_kind_q <= read_fault_kind;
        fault_vaddr_q <= read_fault_vaddr;
        fault_mmu_exception_q <= read_fault_mmu_exception;
        if (active_command_q == AKV_COMMAND_V2_QUERY_UPDATE)
          v2_query_update_fault_count_o <= 32'd1;
      end else if (state_q == AKV_ENGINE_DESCRIPTOR_WAIT &&
                   read_completion_valid && !&descriptor_byte_valid_q) begin
        context_ready_q <= 1'b0;
        fault_is_validation_q <= 1'b0;
        read_fault_kind_q <= QBS_READ_FAULT_REQUEST;
        fault_vaddr_q <= descriptor_address_q;
        fault_mmu_exception_q <= '0;
      end

      if (v2_column_bank_cycle)
        v2_k_view_bank_cycles_o <= v2_k_view_bank_cycles_o + 1'b1;
      if (v2_context_conflict)
        v2_bank_conflict_cycles_o <=
            v2_bank_conflict_cycles_o + 1'b1;

      if (read_data_fire && read_data_tag.role != AKV_RANGE_DESCRIPTOR) begin
        if (read_data_tag.role == AKV_RANGE_Q)
          q_external_bytes_o <= q_external_bytes_o +
              32'($countones(read_data_strb));
        else
          kv_external_bytes_o <= kv_external_bytes_o +
              32'($countones(read_data_strb));
      end

      if (state_q == AKV_ENGINE_REPLAY_WRITE) begin
        replay_accepted_q <= replay_accepted_next;
        replay_final_seen_q <= replay_final_next;
        if (|ldu_result_req_o && !(&replay_accepted_next &&
                                   &replay_final_next))
          replay_backpressure_cycles_o <=
              replay_backpressure_cycles_o + 1'b1;
        if (&replay_accepted_next && &replay_final_next) begin
          replay_bytes_o <= replay_bytes_o + replay_word_bytes;
          replay_accepted_q <= '0;
          replay_final_seen_q <= '0;
          if (unsigned'(replay_word_q) + 1 != replay_word_count)
            replay_word_q <= replay_word_q + 1'b1;
        end
      end
    end
  end

`ifndef SYNTHESIS
  // Observation-only probe for token-axis fill/gather diagnosis.
  always_ff @(posedge clk_i) begin
    if (rst_ni && $test$plusargs("AKV_V2_TOKEN_PROBE")) begin
      if (state_q == AKV_ENGINE_VALIDATE && descriptor_valid &&
          active_command_q == AKV_COMMAND_V2_FULL) begin
        automatic int unsigned probe_tile_count =
            unsigned'(descriptor.kv_length) - unsigned'(requested_tile_start_q);
        if (probe_tile_count > AkvV2TileTokens)
          probe_tile_count = AkvV2TileTokens;
        $display("[AKV_V2_CONTEXT_PROBE] t=%0t q=%h k=%h v=%h rows=%0d dim=%0d kv=%0d tile_start=%0d tile_count=%0d",
                 $time, descriptor.q_base, descriptor.k_base,
                 descriptor.v_base, descriptor.q_rows, descriptor.head_dim,
                 descriptor.kv_length, requested_tile_start_q,
                 probe_tile_count);
      end
      if (v2_context_write_valid && read_data_tag.index == 6'd5) begin
        $display("[AKV_V2_TOKEN_WRITE] t=%0t stream=%0d token=%0d offset=%0d strb=%h data=%h",
                 $time, v2_context_write_stream, read_data_tag.index,
                 read_data_offset, read_data_strb, read_data);
      end
    end
  end

  if (AkvEnable) begin : gen_akv_configuration_assertions
    initial begin
      assert (NrLanes == 4)
        else $fatal(1, "AKV v1 requires four lanes");
      assert (VLEN == 1024)
        else $fatal(1, "AKV v1 requires VLEN=1024");
      assert (AxiDataWidth == 128)
        else $fatal(1, "AKV v1 requires a 128-bit AXI read interface");
      assert (VAddrWidth == 64)
        else $fatal(1, "AKV v1 requires 64-bit virtual addresses");
      assert (AkvContextBytes % ContextBytesPerWord == 0);
      assert (SlotBytes % ContextBytesPerWord == 0);
    end
  end

  always_ff @(posedge clk_i) begin
    if (rst_ni) begin
      assert (!(success_valid_o && fault_valid_o));
      assert (range_issue_index_q <= payload_range_count);
      assert (range_completion_count_q <= range_issue_index_q);
      if (command_early_ack_o)
        assert ((command_i == AKV_COMMAND_LOAD && command_load_valid) ||
                (command_i == AKV_COMMAND_V2_COLUMN_LOAD &&
                 command_column_valid));
      if (|ldu_result_req_o) begin
        assert (state_q == AKV_ENGINE_REPLAY_WRITE &&
                active_command_q inside {
                    AKV_COMMAND_LOAD, AKV_COMMAND_V2_COLUMN_LOAD});
        for (int unsigned lane = 0; lane < NrLanes; lane++)
          if (ldu_result_req_o[lane])
            assert (ldu_result_id_o[lane] == id_q);
      end
      if (read_data_fire && read_data_tag.role != AKV_RANGE_DESCRIPTOR)
        assert (unsigned'(read_data_offset) + $countones(read_data_strb) <=
                unsigned'(payload_row_bytes));
      if (state_q inside {AKV_ENGINE_SUCCESS, AKV_ENGINE_FAULT})
        assert (!read_busy);
      if (active_command_q == AKV_COMMAND_V2_COLUMN_LOAD &&
          state_q == AKV_ENGINE_REPLAY_WRITE)
        assert (v2_column_valid);
      if (active_command_q == AKV_COMMAND_V2_QUERY_UPDATE &&
          state_q == AKV_ENGINE_PAYLOAD) begin
        assert (active_command_has_q && !active_command_has_kv);
        assert (payload_range_count == 8'(context_q_rows_q));
        assert (!v2_context_write_valid);
        if (read_range_fire)
          assert (read_range_tag.role == AKV_RANGE_Q);
        if (read_data_fire)
          assert (read_data_tag.role == AKV_RANGE_Q);
      end
      if (active_command_q == AKV_COMMAND_V2_QUERY_UPDATE &&
          state_q == AKV_ENGINE_SUCCESS) begin
        assert (context_ready_q && context_v2_q);
        assert (context_q_base_q == descriptor_address_q);
        assert (q_external_bytes_o ==
                32'(unsigned'(context_q_rows_q) *
                    unsigned'(payload_row_bytes)));
        assert (kv_external_bytes_o == 0);
      end
    end
  end
`endif

endmodule : akv_engine
