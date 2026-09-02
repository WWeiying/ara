`timescale 1ns/1ps

module akv_engine_tb;
  import axi_pkg::*;
  import ara_pkg::*;
  import rvv_pkg::*;
  import qbs_pkg::*;
  import akv_pkg::*;

  `include "axi/typedef.svh"

  localparam int unsigned AxiDataWidth = 128;
  localparam int unsigned BeatBytes = AxiDataWidth / 8;
  localparam int unsigned NrLanes = 4;
  localparam int unsigned VLEN = 1024;
  localparam int unsigned WordsPerRegister = VLEN / 8 / (NrLanes * 8);
  localparam logic [63:0] DescriptorBase = 64'h0000_0000_0000_4000;
  localparam logic [63:0] QBase = 64'h0000_0000_0010_0000;
  localparam logic [63:0] KBase = 64'h0000_0000_0020_0000;
  localparam logic [63:0] VBase = 64'h0000_0000_0030_0000;

  typedef logic [63:0] axi_addr_t;
  typedef logic [AxiDataWidth-1:0] axi_data_t;
  typedef logic [0:0] axi_id_t;
  typedef logic [0:0] axi_user_t;
  typedef logic [3:0] vid_t;
  typedef logic [7:0] vaddr_t;
  typedef struct packed {
    logic [63:0] cause;
    logic [63:0] tval;
    logic        valid;
  } exception_t;

  `AXI_TYPEDEF_AR_CHAN_T(axi_ar_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_R_CHAN_T(axi_r_t, axi_data_t, axi_id_t, axi_user_t)

  logic clk;
  logic rst_n;

  logic command_valid;
  logic command_ready;
  akv_command_e command;
  vid_t command_id;
  logic [4:0] command_vd;
  logic [15:0] command_head_dim;
  logic [63:0] command_descriptor_address;
  logic [63:0] command_tile_start;
  logic [63:0] command_selector;
  logic [2:0] command_column_count;
  logic command_early_ack;
  logic success_valid;
  logic fault_valid;
  logic terminal_ready;
  logic fault_is_validation;
  akv_validation_error_e validation_error;
  qbs_read_fault_e read_fault_kind;
  logic [63:0] fault_vaddr;
  exception_t fault_mmu_exception;
  logic context_ready;

  logic core_st_pending;
  logic translation_enable;
  logic mmu_req;
  logic [63:0] mmu_vaddr;
  logic mmu_is_store;
  logic mmu_valid;
  logic [63:0] mmu_paddr;
  logic mmu_exception_valid;
  exception_t mmu_exception;
  logic physical_check_valid;
  logic [63:0] physical_check_addr;
  logic [12:0] physical_check_bytes;
  logic physical_range_allowed;

  axi_ar_t axi_ar;
  logic axi_ar_valid;
  logic axi_ar_ready;
  axi_r_t axi_r;
  logic axi_r_valid;
  logic axi_r_ready;

  logic [NrLanes-1:0] ldu_result_req;
  vid_t [NrLanes-1:0] ldu_result_id;
  vaddr_t [NrLanes-1:0] ldu_result_addr;
  logic [63:0] ldu_result_wdata [NrLanes];
  logic [7:0] ldu_result_be [NrLanes];
  logic [NrLanes-1:0] ldu_result_gnt;
  logic [NrLanes-1:0] ldu_result_final_gnt;

  logic busy;
  logic [31:0] command_cycles;
  logic [31:0] full_count;
  logic [31:0] refill_count;
  logic [31:0] load_count;
  logic [31:0] release_count;
  logic [31:0] v2_full_count;
  logic [31:0] v2_refill_count;
  logic [31:0] v2_row_load_count;
  logic [31:0] v2_column_load_count;
  logic [31:0] v2_column_panel_count;
  logic [31:0] v2_logical_column_count;
  logic [31:0] v2_k_view_bank_cycles;
  logic [31:0] v2_bank_conflict_cycles;
  logic [31:0] v2_rejected_count;
  logic [31:0] q_external_bytes;
  logic [31:0] kv_external_bytes;
  logic [31:0] replay_bytes;
  logic [31:0] replay_backpressure_cycles;
  logic [31:0] read_range_count;
  logic [31:0] read_translation_count;
  logic [31:0] read_ar_count;
  logic [31:0] read_beat_count;
  logic [31:0] read_payload_bytes;
  logic [31:0] read_store_wait_cycles;
  logic [31:0] read_backpressure_cycles;
  logic [31:0] read_outstanding_occupancy_sum;
  logic [1:0] read_outstanding_max;
  logic [31:0] read_outstanding_full_cycles;

  akv_engine #(
    .AxiDataWidth (AxiDataWidth),
    .AxiAddrWidth (64),
    .VAddrWidth   (64),
    .PAddrWidth   (64),
    .NrLanes      (NrLanes),
    .VLEN         (VLEN),
    .vid_t        (vid_t),
    .vaddr_t      (vaddr_t),
    .axi_ar_t     (axi_ar_t),
    .axi_r_t      (axi_r_t),
    .exception_t  (exception_t)
  ) dut (
    .clk_i                              (clk),
    .rst_ni                             (rst_n),
    .command_valid_i                    (command_valid),
    .command_ready_o                    (command_ready),
    .command_i                          (command),
    .command_id_i                       (command_id),
    .command_vd_i                       (command_vd),
    .command_head_dim_i                 (command_head_dim),
    .command_descriptor_address_i       (command_descriptor_address),
    .command_tile_start_i               (command_tile_start),
    .command_selector_i                 (command_selector),
    .command_column_count_i             (command_column_count),
    .command_cache_i                    (CACHE_MODIFIABLE),
    .command_prot_i                     ('0),
    .command_early_ack_o                (command_early_ack),
    .success_valid_o                    (success_valid),
    .fault_valid_o                      (fault_valid),
    .terminal_ready_i                   (terminal_ready),
    .fault_is_validation_o              (fault_is_validation),
    .validation_error_o                 (validation_error),
    .read_fault_kind_o                  (read_fault_kind),
    .fault_vaddr_o                      (fault_vaddr),
    .fault_mmu_exception_o              (fault_mmu_exception),
    .context_ready_o                    (context_ready),
    .core_st_pending_i                  (core_st_pending),
    .en_ld_st_translation_i             (translation_enable),
    .mmu_req_o                          (mmu_req),
    .mmu_vaddr_o                        (mmu_vaddr),
    .mmu_is_store_o                     (mmu_is_store),
    .mmu_valid_i                        (mmu_valid),
    .mmu_paddr_i                        (mmu_paddr),
    .mmu_exception_valid_i              (mmu_exception_valid),
    .mmu_exception_i                    (mmu_exception),
    .physical_check_valid_o             (physical_check_valid),
    .physical_check_addr_o              (physical_check_addr),
    .physical_check_bytes_o             (physical_check_bytes),
    .physical_range_allowed_i           (physical_range_allowed),
    .axi_ar_o                           (axi_ar),
    .axi_ar_valid_o                     (axi_ar_valid),
    .axi_ar_ready_i                     (axi_ar_ready),
    .axi_r_i                            (axi_r),
    .axi_r_valid_i                      (axi_r_valid),
    .axi_r_ready_o                      (axi_r_ready),
    .ldu_result_req_o                   (ldu_result_req),
    .ldu_result_id_o                    (ldu_result_id),
    .ldu_result_addr_o                  (ldu_result_addr),
    .ldu_result_wdata_o                 (ldu_result_wdata),
    .ldu_result_be_o                    (ldu_result_be),
    .ldu_result_gnt_i                   (ldu_result_gnt),
    .ldu_result_final_gnt_i             (ldu_result_final_gnt),
    .busy_o                             (busy),
    .command_cycles_o                   (command_cycles),
    .full_count_o                       (full_count),
    .refill_count_o                     (refill_count),
    .load_count_o                       (load_count),
    .release_count_o                    (release_count),
    .v2_full_count_o                    (v2_full_count),
    .v2_refill_count_o                  (v2_refill_count),
    .v2_row_load_count_o                (v2_row_load_count),
    .v2_column_load_count_o             (v2_column_load_count),
    .v2_column_panel_count_o            (v2_column_panel_count),
    .v2_logical_column_count_o          (v2_logical_column_count),
    .v2_k_view_bank_cycles_o            (v2_k_view_bank_cycles),
    .v2_bank_conflict_cycles_o          (v2_bank_conflict_cycles),
    .v2_rejected_count_o                (v2_rejected_count),
    .q_external_bytes_o                 (q_external_bytes),
    .kv_external_bytes_o                (kv_external_bytes),
    .replay_bytes_o                     (replay_bytes),
    .replay_backpressure_cycles_o       (replay_backpressure_cycles),
    .read_range_count_o                 (read_range_count),
    .read_translation_count_o           (read_translation_count),
    .read_ar_count_o                    (read_ar_count),
    .read_beat_count_o                  (read_beat_count),
    .read_payload_bytes_o               (read_payload_bytes),
    .read_store_wait_cycles_o           (read_store_wait_cycles),
    .read_backpressure_cycles_o         (read_backpressure_cycles),
    .read_outstanding_occupancy_sum_o   (read_outstanding_occupancy_sum),
    .read_outstanding_max_o             (read_outstanding_max),
    .read_outstanding_full_cycles_o     (read_outstanding_full_cycles)
  );

  always #5 clk = ~clk;

  byte unsigned memory [longint unsigned];
  logic [31:0] memory_epoch;

  function automatic byte unsigned memory_byte(input longint unsigned address);
    if (memory.exists(address))
      return memory[address];
    return 8'h00;
  endfunction

  function automatic akv_descriptor_v1_t valid_descriptor(
      input logic [15:0] head_dim,
      input logic [15:0] kv_length,
      input logic [7:0] q_rows
  );
    akv_descriptor_v1_t descriptor;
    descriptor = '0;
    descriptor.version = AkvDescriptorVersion;
    descriptor.element_format = AKV_ELEMENT_FORMAT_F16;
    descriptor.q_rows = q_rows;
    descriptor.head_dim = head_dim;
    descriptor.kv_length = kv_length;
    descriptor.q_row_stride_bytes = 32'(head_dim * 2);
    descriptor.k_token_stride_bytes = 32'(head_dim * 2);
    descriptor.v_token_stride_bytes = 32'(head_dim * 2);
    descriptor.q_base = QBase;
    descriptor.k_base = KBase;
    descriptor.v_base = VBase;
    return descriptor;
  endfunction

  task automatic put_descriptor(input logic [63:0] address,
                                input akv_descriptor_v1_t descriptor);
    logic [511:0] raw;
    raw = descriptor;
    for (int unsigned index = 0; index < AkvDescriptorBytes; index++)
      memory[longint'(address + index)] = raw[index*8 +: 8];
    memory_epoch++;
  endtask

  task automatic fill_pattern(input logic [63:0] address,
                              input int unsigned bytes,
                              input byte unsigned seed);
    for (int unsigned index = 0; index < bytes; index++)
      memory[longint'(address + index)] =
          seed ^ byte'(index) ^ byte'(index >> 8);
    memory_epoch++;
  endtask

  // One-cycle identity MMU with range-selective fault injection.
  logic mmu_pending;
  logic [63:0] mmu_pending_vaddr;
  logic inject_mmu_fault;
  logic [63:0] inject_fault_start;
  logic [63:0] inject_fault_end;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      mmu_pending <= 1'b0;
      mmu_pending_vaddr <= '0;
      mmu_valid <= 1'b0;
      mmu_paddr <= '0;
      mmu_exception <= '0;
    end else begin
      mmu_valid <= 1'b0;
      mmu_exception <= '0;
      if (!mmu_pending && mmu_req) begin
        mmu_pending <= 1'b1;
        mmu_pending_vaddr <= mmu_vaddr;
      end else if (mmu_pending) begin
        mmu_pending <= 1'b0;
        if (inject_mmu_fault && mmu_pending_vaddr >= inject_fault_start &&
            mmu_pending_vaddr < inject_fault_end) begin
          mmu_exception.valid <= 1'b1;
          mmu_exception.cause <= 64'd13;
          mmu_exception.tval <= mmu_pending_vaddr;
        end else begin
          mmu_valid <= 1'b1;
          mmu_paddr <= mmu_pending_vaddr;
        end
      end
    end
  end

  assign mmu_exception_valid = mmu_exception.valid;

  logic inject_pma_fault;
  always_comb begin
    physical_range_allowed = 1'b1;
    if (inject_pma_fault && physical_check_addr < inject_fault_end &&
        physical_check_addr + physical_check_bytes > inject_fault_start)
      physical_range_allowed = 1'b0;
  end

  // Ordered two-entry AXI read response model.
  logic [63:0] response_addr [2];
  logic [7:0] response_len [2];
  logic [8:0] response_beat;
  logic response_rd;
  logic response_wr;
  logic [1:0] response_count;
  logic inject_axi_fault;

  assign axi_ar_ready = response_count < 2;
  assign axi_r_valid = response_count != 0;

  always_comb begin
    axi_r = '0;
    axi_r.data = {128{memory_epoch[0]}};
    for (int unsigned byte_lane = 0; byte_lane < BeatBytes; byte_lane++)
      axi_r.data[byte_lane*8 +: 8] = memory_byte(
          response_addr[response_rd] + response_beat * BeatBytes + byte_lane);
    axi_r.resp = inject_axi_fault &&
                 response_addr[response_rd] < inject_fault_end &&
                 response_addr[response_rd] +
                     (64'(response_len[response_rd]) + 1) * BeatBytes >
                         inject_fault_start &&
                 response_beat == 0 ? RESP_SLVERR : RESP_OKAY;
    axi_r.last = response_beat == {1'b0, response_len[response_rd]};
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      response_addr[0] <= '0;
      response_addr[1] <= '0;
      response_len[0] <= '0;
      response_len[1] <= '0;
      response_beat <= '0;
      response_rd <= '0;
      response_wr <= '0;
      response_count <= '0;
    end else begin
      if (axi_ar_valid && axi_ar_ready) begin
        response_addr[response_wr] <= axi_ar.addr;
        response_len[response_wr] <= axi_ar.len;
        response_wr <= response_wr + 1'b1;
      end
      if (axi_r_valid && axi_r_ready) begin
        if (axi_r.last) begin
          response_rd <= response_rd + 1'b1;
          response_beat <= '0;
        end else begin
          response_beat <= response_beat + 1'b1;
        end
      end
      unique case ({axi_ar_valid && axi_ar_ready,
                    axi_r_valid && axi_r_ready && axi_r.last})
        2'b10: response_count <= response_count + 1'b1;
        2'b01: response_count <= response_count - 1'b1;
        default: ;
      endcase
    end
  end

  logic grant_replay;
  assign ldu_result_gnt = grant_replay ? ldu_result_req : '0;
  assign ldu_result_final_gnt = grant_replay ? ldu_result_req : '0;

  logic score_replay;
  logic score_column;
  logic [63:0] score_source_base;
  logic [15:0] score_bytes;
  logic [31:0] score_source_stride;
  logic [6:0] score_column_dimension;
  logic [2:0] score_column_count;
  logic [4:0] score_vd;
  vid_t score_id;
  integer replay_word_seen;
  integer aggregate_write_count;
  integer early_ack_count;

  always @(posedge clk or negedge rst_n) begin : check_replay
    if (!rst_n) begin
      replay_word_seen <= 0;
      aggregate_write_count <= 0;
      early_ack_count <= 0;
    end else begin
      if (command_early_ack)
        early_ack_count <= early_ack_count + 1;
      if (|(ldu_result_req & ldu_result_gnt)) begin
        automatic int unsigned words_per_column =
            (unsigned'(score_bytes) + 31) / 32;
        automatic int unsigned panel_column = score_column
            ? replay_word_seen / words_per_column : 0;
        automatic int unsigned word_in_column = score_column
            ? replay_word_seen % words_per_column : replay_word_seen;
        if (!score_replay)
          $fatal(1, "unexpected AKV replay write");
        if (score_column && panel_column >= unsigned'(score_column_count))
          $fatal(1, "AKV replay exceeded the expected column panel");
        if ((ldu_result_req & ldu_result_gnt) != '1)
          $fatal(1, "AKV replay lanes did not complete together");
        for (int unsigned lane = 0; lane < NrLanes; lane++) begin
          if (ldu_result_id[lane] != score_id ||
              ldu_result_addr[lane] !=
                  vaddr_t'(unsigned'(score_vd) * WordsPerRegister +
                           panel_column * WordsPerRegister +
                           word_in_column))
            $fatal(1,
                   "AKV replay metadata mismatch word=%0d lane=%0d id=%0d/%0d addr=%0d/%0d",
                   replay_word_seen, lane, ldu_result_id[lane], score_id,
                   ldu_result_addr[lane],
                   vaddr_t'(unsigned'(score_vd) * WordsPerRegister +
                            panel_column * WordsPerRegister +
                            word_in_column));
        end
        for (int unsigned logical_byte = 0; logical_byte < 32;
             logical_byte++) begin
          automatic int unsigned physical_byte =
              shuffle_index(logical_byte, NrLanes, EW16);
          automatic int unsigned lane = physical_byte / 8;
          automatic int unsigned lane_byte = physical_byte % 8;
          automatic int unsigned source_offset =
              word_in_column * 32 + logical_byte;
          automatic logic expected_enable = source_offset < score_bytes;
          automatic logic [63:0] expected_address = score_column
              ? score_source_base + (source_offset / 2) * score_source_stride +
                    (unsigned'(score_column_dimension) + panel_column) * 2 +
                    source_offset[0]
              : score_source_base + source_offset;
          if (ldu_result_be[lane][lane_byte] != expected_enable)
            $fatal(1,
                   "AKV replay byte-enable mismatch word=%0d byte=%0d got=%0b expected=%0b",
                   replay_word_seen, logical_byte,
                   ldu_result_be[lane][lane_byte], expected_enable);
          if (expected_enable &&
              ldu_result_wdata[lane][lane_byte*8 +: 8] !=
                  memory_byte(expected_address))
            $fatal(1,
                   "AKV replay data mismatch word=%0d byte=%0d got=%h expected=%h",
                   replay_word_seen, logical_byte,
                   ldu_result_wdata[lane][lane_byte*8 +: 8],
                   memory_byte(expected_address));
        end
        replay_word_seen <= replay_word_seen + 1;
        aggregate_write_count <= aggregate_write_count + 1;
      end
    end
  end

  task automatic send_command(
      input akv_command_e next_command,
      input logic [63:0] descriptor_address,
      input logic [63:0] tile_start,
      input logic [63:0] selector,
      input logic [15:0] head_dim,
      input logic [4:0] vd,
      input vid_t id
  );
    integer timeout;
    timeout = 0;
    while (!command_ready && timeout < 1000) begin
      @(posedge clk);
      timeout++;
    end
    if (!command_ready)
      $fatal(1, "timeout waiting for AKV command ready");
    @(negedge clk);
    command = next_command;
    command_descriptor_address = descriptor_address;
    command_tile_start = tile_start;
    command_selector = selector;
    command_head_dim = head_dim;
    command_vd = vd;
    command_id = id;
    command_valid = 1'b1;
    @(negedge clk);
    command_valid = 1'b0;
  endtask

  task automatic acknowledge_terminal;
    @(negedge clk);
    terminal_ready = 1'b1;
    @(negedge clk);
    terminal_ready = 1'b0;
  endtask

  task automatic wait_success;
    integer timeout;
    timeout = 0;
    while (!success_valid && !fault_valid && timeout < 200000) begin
      @(posedge clk);
      timeout++;
    end
    if (!success_valid)
      $fatal(1,
             "AKV command did not succeed fault=%0b validation=%0b error=%0d read=%0d vaddr=%h",
             fault_valid, fault_is_validation, validation_error,
             read_fault_kind, fault_vaddr);
  endtask

  task automatic expect_validation_fault(
      input akv_validation_error_e expected_error,
      input logic [63:0] expected_vaddr,
      input integer write_count_before
  );
    integer timeout;
    timeout = 0;
    while (!fault_valid && !success_valid && timeout < 100000) begin
      @(posedge clk);
      timeout++;
    end
    if (!fault_valid || !fault_is_validation ||
        validation_error != expected_error ||
        read_fault_kind != QBS_READ_FAULT_NONE ||
        fault_vaddr != expected_vaddr)
      $fatal(1,
             "AKV validation mismatch got valid=%0b validation=%0b error=%0d read=%0d vaddr=%h expected error=%0d vaddr=%h",
             fault_valid, fault_is_validation, validation_error,
             read_fault_kind, fault_vaddr, expected_error, expected_vaddr);
    if (aggregate_write_count != write_count_before)
      $fatal(1, "faulting AKV command wrote the VRF");
    acknowledge_terminal();
  endtask

  task automatic expect_read_fault(
      input qbs_read_fault_e expected_kind,
      input logic [63:0] expected_vaddr,
      input integer write_count_before
  );
    integer timeout;
    timeout = 0;
    while (!fault_valid && !success_valid && timeout < 100000) begin
      @(posedge clk);
      timeout++;
    end
    if (!fault_valid || fault_is_validation ||
        validation_error != AKV_VALIDATION_OK ||
        read_fault_kind != expected_kind || fault_vaddr != expected_vaddr)
      $fatal(1,
             "AKV read fault mismatch got valid=%0b validation=%0b error=%0d read=%0d vaddr=%h expected read=%0d vaddr=%h",
             fault_valid, fault_is_validation, validation_error,
             read_fault_kind, fault_vaddr, expected_kind, expected_vaddr);
    if (aggregate_write_count != write_count_before)
      $fatal(1, "faulting AKV fill wrote the VRF");
    acknowledge_terminal();
  endtask

  task automatic run_valid_full(input logic [15:0] head_dim,
                                input logic [15:0] kv_length,
                                input logic [7:0] q_rows,
                                input logic [63:0] tile_start);
    akv_descriptor_v1_t descriptor;
    descriptor = valid_descriptor(head_dim, kv_length, q_rows);
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_FULL, DescriptorBase, tile_start, 0,
                 head_dim, 0, 4'h2);
    wait_success();
    if (!context_ready)
      $fatal(1, "successful AKV full did not commit context");
    acknowledge_terminal();
  endtask

  task automatic run_valid_load(input akv_stream_e stream,
                                input logic [5:0] index,
                                input logic [15:0] head_dim,
                                input logic [4:0] vd,
                                input vid_t id,
                                input logic [63:0] source_base,
                                input integer stall_cycles);
    integer ack_before;
    score_replay = 1'b1;
    score_column = 1'b0;
    score_source_base = source_base;
    score_bytes = head_dim * 2;
    score_source_stride = '0;
    score_column_dimension = '0;
    score_column_count = 3'd1;
    score_vd = vd;
    score_id = id;
    replay_word_seen = 0;
    ack_before = early_ack_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {56'b0, index, stream}, head_dim, vd, id);
    if (stall_cycles != 0) begin
      grant_replay = 1'b0;
      repeat (stall_cycles) @(posedge clk);
      @(negedge clk);
      grant_replay = 1'b1;
    end
    wait_success();
    if (early_ack_count != ack_before + 1)
      $fatal(1, "valid AKV load did not produce exactly one early ack");
    if (replay_word_seen != (head_dim >> 4) ||
        replay_bytes != head_dim * 2)
      $fatal(1, "AKV replay length mismatch words=%0d bytes=%0d",
             replay_word_seen, replay_bytes);
    if (stall_cycles != 0 && replay_backpressure_cycles == 0)
      $fatal(1, "AKV replay backpressure was not observed");
    acknowledge_terminal();
    score_replay = 1'b0;
  endtask

  task automatic run_valid_v2_full(input logic [15:0] head_dim,
                                   input logic [15:0] kv_length,
                                   input logic [7:0] q_rows,
                                   input logic [63:0] tile_start);
    akv_descriptor_v1_t descriptor;
    descriptor = valid_descriptor(head_dim, kv_length, q_rows);
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_V2_FULL, DescriptorBase, tile_start, 0,
                 head_dim, 0, 4'h2);
    wait_success();
    if (!context_ready || v2_full_count != 1 ||
        v2_bank_conflict_cycles != 0)
      $fatal(1, "successful AKV-v2 full did not commit a conflict-free context");
    acknowledge_terminal();
  endtask

  task automatic run_valid_v2_column_mapped(
      input logic [7:0] selector,
      input logic [6:0] tile_count,
      input logic [63:0] tile_start,
      input logic [15:0] head_dim,
      input logic [4:0] vd,
      input vid_t id,
      input integer stall_cycles,
      input logic [63:0] source_base,
      input logic [31:0] source_stride
  );
    integer ack_before;
    score_replay = 1'b1;
    score_column = 1'b1;
    score_source_base = source_base;
    score_bytes = tile_count * 2;
    score_source_stride = source_stride;
    score_column_dimension = selector[6:0];
    score_column_count = 3'd1;
    score_vd = vd;
    score_id = id;
    replay_word_seen = 0;
    ack_before = early_ack_count;
    send_command(AKV_COMMAND_V2_COLUMN_LOAD, 0, 0, selector,
                 head_dim, vd, id);
    if (stall_cycles != 0) begin
      grant_replay = 1'b0;
      repeat (stall_cycles) @(posedge clk);
      @(negedge clk);
      grant_replay = 1'b1;
    end
    wait_success();
    if (early_ack_count != ack_before + 1)
      $fatal(1, "valid AKV-v2 column did not produce exactly one early ack");
    if (replay_word_seen != (tile_count + 15) / 16 ||
        replay_bytes != tile_count * 2)
      $fatal(1,
             "AKV-v2 column replay mismatch words=%0d bytes=%0d expected_bytes=%0d",
             replay_word_seen, replay_bytes, tile_count * 2);
    if (v2_column_load_count != 1 || v2_column_panel_count != 0 ||
        v2_logical_column_count != 1 ||
        v2_k_view_bank_cycles != (tile_count + 7) / 8 ||
        v2_bank_conflict_cycles != 0)
      $fatal(1,
             "AKV-v2 column accounting mismatch commands=%0d bank_cycles=%0d conflicts=%0d",
             v2_column_load_count, v2_k_view_bank_cycles,
             v2_bank_conflict_cycles);
    acknowledge_terminal();
    score_replay = 1'b0;
    score_column = 1'b0;
  endtask

  task automatic run_valid_v2_column_panel4(
      input logic [7:0] selector,
      input logic [6:0] tile_count,
      input logic [63:0] tile_start,
      input logic [15:0] head_dim,
      input logic [4:0] vd,
      input vid_t id,
      input integer stall_cycles
  );
    integer ack_before;
    automatic logic [63:0] stream_base = selector[7] ? VBase : KBase;
    score_replay = 1'b1;
    score_column = 1'b1;
    score_source_base = stream_base + tile_start * head_dim * 2;
    score_bytes = tile_count * 2;
    score_source_stride = head_dim * 2;
    score_column_dimension = selector[6:0];
    score_column_count = 3'd4;
    score_vd = vd;
    score_id = id;
    replay_word_seen = 0;
    ack_before = early_ack_count;
    command_column_count = 3'd4;
    send_command(AKV_COMMAND_V2_COLUMN_LOAD, 0, 0, selector,
                 head_dim, vd, id);
    if (stall_cycles != 0) begin
      grant_replay = 1'b0;
      repeat (stall_cycles) @(posedge clk);
      @(negedge clk);
      grant_replay = 1'b1;
    end
    wait_success();
    if (early_ack_count != ack_before + 1)
      $fatal(1, "valid AKV-v2 column panel did not produce one early ack");
    if (replay_word_seen != 4 * ((tile_count + 15) / 16) ||
        replay_bytes != 4 * tile_count * 2)
      $fatal(1,
             "AKV-v2 panel replay mismatch words=%0d bytes=%0d",
             replay_word_seen, replay_bytes);
    if (v2_column_load_count != 1 || v2_column_panel_count != 1 ||
        v2_logical_column_count != 4 ||
        v2_k_view_bank_cycles != (tile_count + 7) / 8 ||
        v2_bank_conflict_cycles != 0)
      $fatal(1,
             "AKV-v2 panel accounting mismatch commands=%0d panels=%0d columns=%0d bank_cycles=%0d conflicts=%0d",
             v2_column_load_count, v2_column_panel_count,
             v2_logical_column_count, v2_k_view_bank_cycles,
             v2_bank_conflict_cycles);
    acknowledge_terminal();
    command_column_count = 3'd1;
    score_replay = 1'b0;
    score_column = 1'b0;
    score_column_count = 3'd1;
  endtask

  task automatic run_valid_v2_column(
      input logic [7:0] selector,
      input logic [6:0] tile_count,
      input logic [63:0] tile_start,
      input logic [15:0] head_dim,
      input logic [4:0] vd,
      input vid_t id,
      input integer stall_cycles
  );
    automatic logic [63:0] stream_base = selector[7] ? VBase : KBase;
    run_valid_v2_column_mapped(
        selector, tile_count, tile_start, head_dim, vd, id, stall_cycles,
        stream_base + tile_start * head_dim * 2, head_dim * 2);
  endtask

  task automatic run_descriptor_validation(
      input akv_descriptor_v1_t descriptor,
      input akv_validation_error_e expected_error,
      input logic [63:0] tile_start
  );
    integer writes_before;
    writes_before = aggregate_write_count;
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_FULL, DescriptorBase, tile_start, 0,
                 descriptor.head_dim, 0, 4'h3);
    expect_validation_fault(expected_error, DescriptorBase, writes_before);
    if (context_ready)
      $fatal(1, "descriptor validation fault retained a ready context");
  endtask

  task automatic run_v2_shape_traffic(
      input logic [15:0] head_dim,
      input logic [15:0] kv_length,
      input logic [7:0] q_rows
  );
    akv_descriptor_v1_t descriptor;
    int unsigned tile_start;
    int unsigned tile_count;
    int unsigned row_bytes;
    int unsigned expected_ranges;

    descriptor = valid_descriptor(head_dim, kv_length, q_rows);
    put_descriptor(DescriptorBase, descriptor);
    row_bytes = head_dim * 2;
    tile_start = 0;
    while (tile_start < kv_length) begin
      tile_count = kv_length - tile_start;
      if (tile_count > AkvV2TileTokens)
        tile_count = AkvV2TileTokens;
      if (tile_start == 0)
        send_command(AKV_COMMAND_V2_FULL, DescriptorBase, 0, 0,
                     head_dim, 0, 4'h2);
      else
        send_command(AKV_COMMAND_V2_REFILL, 0, tile_start, 0,
                     head_dim, 0, 4'h3);
      wait_success();
      // The read engine sees one range per logical row.  FULL additionally
      // fetches the descriptor; REFILL contains only K and V token rows.
      expected_ranges = 2 * tile_count;
      if (tile_start == 0)
        expected_ranges += 1 + q_rows;
      if (!context_ready || dut.context_tile_count_q != tile_count ||
          q_external_bytes != (tile_start == 0 ? q_rows * row_bytes : 0) ||
          kv_external_bytes != 2 * tile_count * row_bytes ||
          read_range_count != expected_ranges ||
          v2_bank_conflict_cycles != 0 ||
          (tile_start == 0 ? v2_full_count != 1 : v2_refill_count != 1))
        $fatal(1,
               "AKV-v2 shape traffic mismatch D=%0d GQA=%0d KV=%0d tile=%0d count=%0d q_bytes=%0d kv_bytes=%0d ranges=%0d",
               head_dim, q_rows, kv_length, tile_start, tile_count,
               q_external_bytes, kv_external_bytes, read_range_count);
      acknowledge_terminal();
      tile_start += tile_count;
    end
    send_command(AKV_COMMAND_RELEASE, 0, 0, 0, 0, 0, 4'h4);
    wait_success();
    acknowledge_terminal();
    if (context_ready)
      $fatal(1, "AKV-v2 shape matrix release retained context");
  endtask

  task automatic run_v2_shape_matrix;
    int unsigned q_index;
    int unsigned d_index;
    int unsigned kv_index;
    logic [7:0] q_rows;
    logic [15:0] head_dim;
    logic [15:0] kv_length;

    for (q_index = 0; q_index < AkvMaxQRows; q_index++) begin
      q_rows = q_index + 1;
      for (d_index = 0; d_index < 3; d_index++) begin
        case (d_index)
          0: head_dim = 64;
          1: head_dim = 96;
          default: head_dim = 128;
        endcase
        for (kv_index = 0; kv_index < 7; kv_index++) begin
          case (kv_index)
            0: kv_length = 16;
            1: kv_length = 63;
            2: kv_length = 64;
            3: kv_length = 65;
            4: kv_length = 128;
            5: kv_length = 256;
            default: kv_length = 1024;
          endcase
          run_v2_shape_traffic(head_dim, kv_length, q_rows);
        end
      end
    end
  endtask

  initial begin : run_tests
    akv_descriptor_v1_t descriptor;
    integer writes_before;
    integer ack_before;

    clk = 1'b0;
    rst_n = 1'b0;
    command_valid = 1'b0;
    command = AKV_COMMAND_FULL;
    command_id = '0;
    command_vd = '0;
    command_head_dim = 16'd128;
    command_descriptor_address = '0;
    command_tile_start = '0;
    command_selector = '0;
    command_column_count = 3'd1;
    terminal_ready = 1'b0;
    core_st_pending = 1'b0;
    translation_enable = 1'b0;
    inject_mmu_fault = 1'b0;
    inject_pma_fault = 1'b0;
    inject_axi_fault = 1'b0;
    inject_fault_start = '0;
    inject_fault_end = '0;
    grant_replay = 1'b1;
    score_replay = 1'b0;
    score_column = 1'b0;
    score_source_base = '0;
    score_bytes = '0;
    score_source_stride = '0;
    score_column_dimension = '0;
    score_column_count = 3'd1;
    score_vd = '0;
    score_id = '0;
    memory_epoch = '0;

    fill_pattern(QBase, 8 * 256, 8'h31);
    fill_pattern(KBase, 80 * 256, 8'h52);
    fill_pattern(VBase, 80 * 256, 8'h94);

    repeat (5) @(posedge clk);
    rst_n = 1'b1;
    repeat (3) @(posedge clk);

    // D128 full, replay, tail refill, Q preservation, and replay stalls.
    run_valid_full(128, 12, 3, 0);
    if (full_count != 1 || q_external_bytes != 3 * 256 ||
        kv_external_bytes != 16 * 256 || read_range_count != 20)
      $fatal(1, "AKV D128 full accounting mismatch");
    run_valid_load(AKV_STREAM_Q, 2, 128, 8, 4'h4,
                   QBase + 2 * 256, 3);
    run_valid_load(AKV_STREAM_K, 7, 128, 10, 4'h5,
                   KBase + 7 * 256, 0);
    run_valid_load(AKV_STREAM_V, 3, 128, 12, 4'h6,
                   VBase + 3 * 256, 0);

    send_command(AKV_COMMAND_REFILL, 0, 8, 0, 128, 0, 4'h7);
    wait_success();
    if (!context_ready || refill_count != 1 || q_external_bytes != 0 ||
        kv_external_bytes != 8 * 256 || read_range_count != 8)
      $fatal(1, "AKV refill accounting mismatch");
    acknowledge_terminal();
    run_valid_load(AKV_STREAM_Q, 1, 128, 14, 4'h8,
                   QBase + 1 * 256, 0);
    run_valid_load(AKV_STREAM_K, 3, 128, 16, 4'h9,
                   KBase + 11 * 256, 0);
    run_valid_load(AKV_STREAM_V, 2, 128, 18, 4'ha,
                   VBase + 10 * 256, 0);

    // Local command validation must not issue a partial write or destroy a
    // valid context.
    writes_before = aggregate_write_count;
    ack_before = early_ack_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {59'b0, 3'd7, AKV_STREAM_K}, 128, 8, 4'hb);
    expect_validation_fault(AKV_VALIDATION_SELECTOR, 0, writes_before);
    if (!context_ready || early_ack_count != ack_before)
      $fatal(1, "invalid selector changed context or early-acked");
    run_valid_load(AKV_STREAM_Q, 0, 128, 20, 4'hc, QBase, 0);

    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {59'b0, 3'd0, AKV_STREAM_Q}, 64, 8, 4'hd);
    expect_validation_fault(AKV_VALIDATION_HEAD_DIM, 0, writes_before);
    if (!context_ready)
      $fatal(1, "head-dimension load fault destroyed context");

    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {59'b0, 3'd0, AKV_STREAM_Q}, 128, 9, 4'he);
    expect_validation_fault(AKV_VALIDATION_DESTINATION, 0, writes_before);
    if (!context_ready)
      $fatal(1, "destination load fault destroyed context");

    // Release and refill-without-context behavior.
    send_command(AKV_COMMAND_RELEASE, 0, 0, 0, 0, 0, 4'h0);
    wait_success();
    if (context_ready || release_count != 1)
      $fatal(1, "AKV release did not clear context");
    acknowledge_terminal();
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_REFILL, 0, 0, 0, 128, 0, 4'h1);
    expect_validation_fault(AKV_VALIDATION_CONTEXT, 0, writes_before);

    // Descriptor and command validation matrix.
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase + 1, 0, 0,
                 128, 0, 4'h2);
    expect_validation_fault(AKV_VALIDATION_DESCRIPTOR_ALIGNMENT, 0,
                            writes_before);

    descriptor = valid_descriptor(128, 12, 3);
    descriptor.version = AkvDescriptorVersion + 1;
    run_descriptor_validation(descriptor,
                              AKV_VALIDATION_DESCRIPTOR_VERSION, 0);
    descriptor = valid_descriptor(128, 12, 3);
    descriptor.element_format = AKV_ELEMENT_FORMAT_INVALID;
    run_descriptor_validation(descriptor,
                              AKV_VALIDATION_DESCRIPTOR_FORMAT, 0);
    descriptor = valid_descriptor(128, 12, 0);
    run_descriptor_validation(descriptor, AKV_VALIDATION_Q_ROWS, 0);
    descriptor = valid_descriptor(96, 12, 3);
    run_descriptor_validation(descriptor, AKV_VALIDATION_HEAD_DIM, 0);
    descriptor = valid_descriptor(128, 0, 3);
    run_descriptor_validation(descriptor, AKV_VALIDATION_KV_LENGTH, 0);
    descriptor = valid_descriptor(128, 12, 3);
    descriptor.reserved2 = 64'h1;
    run_descriptor_validation(descriptor, AKV_VALIDATION_RESERVED, 0);
    descriptor = valid_descriptor(128, 12, 3);
    descriptor.q_row_stride_bytes = 32'd255;
    run_descriptor_validation(descriptor, AKV_VALIDATION_STRIDE, 0);
    descriptor = valid_descriptor(128, 12, 3);
    descriptor.q_base = 64'hffff_ffff_ffff_ff80;
    run_descriptor_validation(descriptor,
                              AKV_VALIDATION_RANGE_OVERFLOW, 0);
    descriptor = valid_descriptor(128, 12, 3);
    run_descriptor_validation(descriptor, AKV_VALIDATION_TILE_RANGE, 12);

    // A rejected refill invalidates the old tile to avoid mixed generations.
    run_valid_full(128, 12, 3, 0);
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_REFILL, 0, 12, 0, 128, 0, 4'h3);
    expect_validation_fault(AKV_VALIDATION_TILE_RANGE, 0, writes_before);
    if (context_ready)
      $fatal(1, "rejected refill retained an ambiguous context");

    // Shared read-path fault propagation: descriptor and every payload role.
    translation_enable = 1'b1;
    inject_mmu_fault = 1'b1;
    inject_fault_start = DescriptorBase;
    inject_fault_end = DescriptorBase + 64;
    descriptor = valid_descriptor(128, 12, 3);
    put_descriptor(DescriptorBase, descriptor);
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h4);
    expect_read_fault(QBS_READ_FAULT_MMU, DescriptorBase, writes_before);
    if (!fault_mmu_exception.valid || fault_mmu_exception.cause != 13 ||
        fault_mmu_exception.tval != DescriptorBase)
      $fatal(1, "AKV descriptor MMU metadata mismatch");

    inject_fault_start = QBase;
    inject_fault_end = QBase + 256;
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h5);
    expect_read_fault(QBS_READ_FAULT_MMU, QBase, writes_before);
    inject_fault_start = KBase;
    inject_fault_end = KBase + 256;
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h6);
    expect_read_fault(QBS_READ_FAULT_MMU, KBase, writes_before);
    inject_fault_start = VBase;
    inject_fault_end = VBase + 256;
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h7);
    expect_read_fault(QBS_READ_FAULT_MMU, VBase, writes_before);
    inject_mmu_fault = 1'b0;
    translation_enable = 1'b0;

    inject_pma_fault = 1'b1;
    inject_fault_start = KBase;
    inject_fault_end = KBase + 256;
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h8);
    expect_read_fault(QBS_READ_FAULT_PMA, KBase, writes_before);
    inject_pma_fault = 1'b0;

    inject_axi_fault = 1'b1;
    inject_fault_start = VBase;
    inject_fault_end = VBase + 256;
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 128, 0, 4'h9);
    expect_read_fault(QBS_READ_FAULT_AXI_RESPONSE, VBase, writes_before);
    inject_axi_fault = 1'b0;

    if (context_ready)
      $fatal(1, "read fault retained an AKV context");
    if (mmu_is_store)
      $fatal(1, "AKV requested a store translation");

    // D64 completes the second supported shape after all fault recovery.
    run_valid_full(64, 12, 3, 0);
    run_valid_load(AKV_STREAM_V, 7, 64, 8, 4'ha,
                   VBase + 7 * 128, 0);

    // Every source base need only be F16-aligned. Offset each stream by two
    // bytes so compact AXI beats repeatedly cross 32-byte context rows.
    descriptor = valid_descriptor(64, 12, 3);
    descriptor.q_base = QBase + 2;
    descriptor.k_base = KBase + 2;
    descriptor.v_base = VBase + 2;
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_FULL, DescriptorBase, 0, 0, 64, 0, 4'hb);
    wait_success();
    acknowledge_terminal();
    run_valid_load(AKV_STREAM_Q, 2, 64, 10, 4'hc,
                   QBase + 2 + 2 * 128, 0);
    run_valid_load(AKV_STREAM_K, 7, 64, 12, 4'hd,
                   KBase + 2 + 7 * 128, 0);
    run_valid_load(AKV_STREAM_V, 3, 64, 14, 4'he,
                   VBase + 2 + 3 * 128, 0);

    // AKV-v2 keeps row-major model storage, exposes 64-token K/V rows, and
    // gathers a K dimension across token banks without software packing.
    run_valid_v2_full(128, 69, 6, 0);
    if (q_external_bytes != 6 * 256 ||
        kv_external_bytes != 2 * 64 * 256 || read_range_count != 135)
      $fatal(1,
             "AKV-v2 D128 full accounting mismatch q=%0d/1536 kv=%0d/32768 ranges=%0d/135 tile_count=%0d",
             q_external_bytes, kv_external_bytes, read_range_count,
             dut.context_tile_count_q);
    run_valid_load(AKV_STREAM_Q, 5, 128, 8, 4'h1,
                   QBase + 5 * 256, 0);
    if (v2_row_load_count != 1)
      $fatal(1, "AKV-v2 Q row was not counted");
    run_valid_load(AKV_STREAM_K, 63, 128, 10, 4'h2,
                   KBase + 63 * 256, 0);
    if (v2_row_load_count != 1)
      $fatal(1, "AKV-v2 K row was not counted");
    run_valid_load(AKV_STREAM_V, 63, 128, 12, 4'h3,
                   VBase + 63 * 256, 0);
    run_valid_v2_column(0, 64, 0, 128, 14, 4'h4, 0);
    run_valid_v2_column(17, 64, 0, 128, 16, 4'h5, 2);
    run_valid_v2_column(127, 64, 0, 128, 18, 4'h6, 0);
    run_valid_v2_column(8'h91, 64, 0, 128, 20, 4'h7, 0);
    run_valid_v2_column_panel4(20, 64, 0, 128, 24, 4'h8, 2);

    // Refill the five-token tail. Inactive destination bytes must remain
    // disabled; stale values from the preceding full tile cannot escape.
    send_command(AKV_COMMAND_V2_REFILL, 0, 64, 0, 128, 0, 4'h7);
    wait_success();
    if (!context_ready || v2_refill_count != 1 || q_external_bytes != 0 ||
        kv_external_bytes != 2 * 5 * 256 || read_range_count != 10)
      $fatal(1, "AKV-v2 tail refill accounting mismatch");
    acknowledge_terminal();
    run_valid_load(AKV_STREAM_V, 4, 128, 20, 4'h8,
                   VBase + 68 * 256, 0);
    run_valid_v2_column(63, 5, 64, 128, 22, 4'h9, 0);
    run_valid_v2_column_panel4(60, 5, 64, 128, 24, 4'ha, 0);

    // Local validation is atomic: invalid row and dimension commands neither
    // write the VRF nor destroy the valid tail context.
    writes_before = aggregate_write_count;
    ack_before = early_ack_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {56'b0, 6'd5, AKV_STREAM_V}, 128, 24, 4'ha);
    expect_validation_fault(AKV_VALIDATION_SELECTOR, 0, writes_before);
    if (!context_ready || early_ack_count != ack_before ||
        v2_rejected_count != 1)
      $fatal(1, "invalid AKV-v2 row changed context or accounting");

    writes_before = aggregate_write_count;
    ack_before = early_ack_count;
    send_command(AKV_COMMAND_V2_COLUMN_LOAD, 0, 0, 256,
                 128, 24, 4'hb);
    expect_validation_fault(AKV_VALIDATION_SELECTOR, 0, writes_before);
    if (!context_ready || early_ack_count != ack_before ||
        v2_rejected_count != 1)
      $fatal(1, "invalid AKV-v2 column changed context or accounting");

    writes_before = aggregate_write_count;
    command_column_count = 3'd4;
    send_command(AKV_COMMAND_V2_COLUMN_LOAD, 0, 0, 126,
                 128, 24, 4'hb);
    expect_validation_fault(AKV_VALIDATION_SELECTOR, 0, writes_before);
    command_column_count = 3'd1;

    writes_before = aggregate_write_count;
    command_column_count = 3'd4;
    send_command(AKV_COMMAND_V2_COLUMN_LOAD, 0, 0, 124,
                 128, 25, 4'hb);
    expect_validation_fault(AKV_VALIDATION_DESTINATION, 0, writes_before);
    command_column_count = 3'd1;

    // The token-banked write path has a 32-byte row contract. Reject an
    // incompatible layout before issuing any payload range.
    descriptor = valid_descriptor(128, 69, 6);
    descriptor.q_base = QBase + 2;
    put_descriptor(DescriptorBase, descriptor);
    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_V2_FULL, DescriptorBase, 0, 0,
                 128, 0, 4'hc);
    expect_validation_fault(AKV_VALIDATION_STRIDE, DescriptorBase,
                            writes_before);
    if (context_ready || v2_rejected_count != 1)
      $fatal(1, "invalid AKV-v2 layout retained a context");

    // D64 and the minimum one-token tail exercise the other supported row
    // width and the narrowest legal column byte-enable mask.
    run_valid_v2_full(64, 65, 2, 0);
    if (q_external_bytes != 2 * 128 ||
        kv_external_bytes != 2 * 64 * 128 || read_range_count != 131)
      $fatal(1, "AKV-v2 D64 full accounting mismatch");
    run_valid_load(AKV_STREAM_K, 63, 64, 24, 4'hd,
                   KBase + 63 * 128, 0);
    run_valid_v2_column(63, 64, 0, 64, 25, 4'he, 0);
    send_command(AKV_COMMAND_V2_REFILL, 0, 64, 0, 64, 0, 4'hf);
    wait_success();
    if (!context_ready || v2_refill_count != 1 ||
        kv_external_bytes != 2 * 128 || read_range_count != 2)
      $fatal(1, "AKV-v2 one-token refill accounting mismatch");
    acknowledge_terminal();
    run_valid_load(AKV_STREAM_V, 0, 64, 26, 4'h0,
                   VBase + 64 * 128, 0);
    run_valid_v2_column(31, 1, 64, 64, 27, 4'h1, 0);

    // D96 is a v2-only D-axis tail. It reuses the D128 physical slot while
    // replaying exactly six valid 32-byte words into an LMUL=2 destination.
    run_valid_v2_full(96, 65, 4, 0);
    if (q_external_bytes != 4 * 192 ||
        kv_external_bytes != 2 * 64 * 192 || read_range_count != 133)
      $fatal(1, "AKV-v2 D96 full accounting mismatch");
    run_valid_load(AKV_STREAM_Q, 3, 96, 8, 4'h2,
                   QBase + 3 * 192, 0);
    run_valid_load(AKV_STREAM_K, 63, 96, 10, 4'h3,
                   KBase + 63 * 192, 0);
    run_valid_load(AKV_STREAM_V, 63, 96, 12, 4'h4,
                   VBase + 63 * 192, 2);
    run_valid_v2_column(95, 64, 0, 96, 14, 4'h5, 0);

    writes_before = aggregate_write_count;
    send_command(AKV_COMMAND_LOAD, 0, 0,
                 {56'b0, 6'd0, AKV_STREAM_Q}, 96, 9, 4'h6);
    expect_validation_fault(AKV_VALIDATION_DESTINATION, 0, writes_before);
    if (!context_ready)
      $fatal(1, "D96 destination fault destroyed the v2 context");

    // D256 uses the unchanged pair of D128 physical K/V regions twice. The
    // score descriptor maps K0/K1 to the two regions; after softmax, the value
    // descriptor maps V0/V1. Selector bit 7 chooses the second column segment.
    descriptor = valid_descriptor(128, 17, 4);
    descriptor.q_row_stride_bytes = 512;
    descriptor.k_token_stride_bytes = 512;
    descriptor.v_token_stride_bytes = 512;
    descriptor.v_base = KBase + 256;
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_V2_FULL, DescriptorBase, 0, 0,
                 128, 0, 4'h7);
    wait_success();
    if (!context_ready || q_external_bytes != 4 * 256 ||
        kv_external_bytes != 2 * 17 * 256 || read_range_count != 39)
      $fatal(1, "AKV-v2 D256 score-segment fill accounting mismatch");
    acknowledge_terminal();
    run_valid_v2_column_mapped(8'h11, 17, 0, 128, 16, 4'h8, 0,
                               KBase, 512);
    run_valid_v2_column_mapped(8'h91, 17, 0, 128, 18, 4'h9, 0,
                               KBase + 256, 512);

    descriptor.q_base = QBase + 256;
    descriptor.k_base = VBase;
    descriptor.v_base = VBase + 256;
    put_descriptor(DescriptorBase, descriptor);
    send_command(AKV_COMMAND_V2_FULL, DescriptorBase, 0, 0,
                 128, 0, 4'ha);
    wait_success();
    if (!context_ready || q_external_bytes != 4 * 256 ||
        kv_external_bytes != 2 * 17 * 256 || read_range_count != 39)
      $fatal(1, "AKV-v2 D256 value-segment fill accounting mismatch");
    acknowledge_terminal();
    run_valid_load(AKV_STREAM_K, 16, 128, 20, 4'hb,
                   VBase + 16 * 512, 0);
    run_valid_load(AKV_STREAM_V, 16, 128, 22, 4'hc,
                   VBase + 256 + 16 * 512, 0);

    // The software-supported AKV-v2 matrix must obey the same FULL/REFILL,
    // byte, range, and tail identities for every advertised shape.
    run_v2_shape_matrix();

    // A final v1 command proves that v2 state did not change the legacy
    // descriptor, tile-eight, and unaligned-row contract.
    run_valid_full(64, 12, 3, 0);
    run_valid_load(AKV_STREAM_K, 7, 64, 26, 4'hd,
                   KBase + 7 * 128, 0);

    $display("AKV engine PASS: v1 D64/D128 plus v2 D64/D96/D128 and segmented D256 row/column views, tails, counters, validation, and faults");
    $finish;
  end

endmodule : akv_engine_tb
