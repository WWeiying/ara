// Isolated composition candidate: 2 KiB Q plus ONE unchanged 32 KiB v2 K/V store.
module akv_unified_context
  import akv_pkg::*;
(
  input logic clk_i, rst_ni,
  input logic abort_i,
  // Accepted compact payload fragments; includes v2 Q, excludes descriptors.
  input logic legacy_write_valid_i,
  input logic [4:0] legacy_write_slot_i,
  input logic [7:0] legacy_write_offset_i,
  input logic [8:0] legacy_row_bytes_i,
  input logic [127:0] legacy_write_data_i,
  input logic [15:0] legacy_write_strb_i,
  output logic legacy_write_busy_o,
  // Existing aligned v2 K/V path, no adapter or added write register.
  input logic v2_write_valid_i,
  input akv_stream_e v2_write_stream_i,
  input logic [5:0] v2_write_token_i,
  input logic [7:0] v2_write_offset_i,
  input logic [127:0] v2_write_data_i,
  input logic [15:0] v2_write_strb_i,
  output logic v2_write_busy_o,
  output logic write_busy_o,

  input logic legacy_replay_read_i,
  input logic [4:0] legacy_replay_slot_i,
  input logic [3:0] legacy_replay_word_i,
  output logic [255:0] legacy_replay_data_o,
  input logic v2_row_read_i,
  input akv_stream_e v2_row_stream_i,
  input logic [5:0] v2_row_token_i,
  input logic [3:0] v2_row_word_i,
  output logic [255:0] v2_row_data_o,

  input logic column_start_i,
  input akv_stream_e column_stream_i,
  input logic [6:0] column_dimension_i,
  input logic [2:0] column_count_i,
  input logic [6:0] column_token_count_i,
  output logic column_busy_o, column_valid_o,
  output logic [3:0][1023:0] column_data_o,
  output logic column_bank_cycle_o,
  output logic conflict_o
);
  localparam int QBytes = 8 * 256;
  localparam int KVBytes = 2 * 64 * 256;
  logic packed_valid, packed_last;
  logic [15:0] packed_tag;
  logic [8:0] packed_offset;
  logic [127:0] packed_data;
  logic q_write, kv_write, kv_write_busy, kv_conflict;
  logic [4:0] packed_slot;
  logic q_read, kv_row_read, legacy_q_q;
  logic [255:0] q_data, kv_data;
  akv_stream_e kv_write_stream, kv_row_stream;
  logic [5:0] kv_write_token, kv_row_token;
  logic [7:0] kv_write_offset;
  logic [127:0] kv_write_data;
  logic [15:0] kv_write_strb;
  logic [3:0] kv_row_word;

  akv_legacy_repacker i_legacy_repacker (
    .clk_i, .rst_ni, .abort_i,
    .fragment_valid_i(legacy_write_valid_i && !abort_i),
    .fragment_tag_i({11'b0, legacy_write_slot_i}),
    .fragment_offset_i({1'b0, legacy_write_offset_i}), .row_bytes_i(legacy_row_bytes_i),
    .fragment_data_i(legacy_write_data_i), .fragment_strb_i(legacy_write_strb_i),
    .write_valid_o(packed_valid), .write_tag_o(packed_tag), .write_offset_o(packed_offset),
    .write_data_o(packed_data), .write_last_o(packed_last), .busy_o(legacy_write_busy_o)
  );
  assign packed_slot = packed_tag[4:0];
  assign q_write = packed_valid && packed_slot < 8;
  assign kv_write = !abort_i && (v2_write_valid_i || (packed_valid && packed_slot >= 8));
  assign v2_write_busy_o = v2_write_valid_i && !abort_i;
  assign write_busy_o = legacy_write_busy_o || v2_write_busy_o || kv_write_busy;

  // Decode only emission-registered metadata, never the younger input fragment.
  always_comb begin
    kv_write_stream = packed_slot < 16 ? AKV_STREAM_K : AKV_STREAM_V;
    kv_write_token = packed_slot < 16 ? 6'(packed_slot - 8) : 6'(packed_slot - 16);
    kv_write_offset = packed_offset[7:0];
    kv_write_data = packed_data;
    kv_write_strb = '1;
    if (v2_write_valid_i) begin
      kv_write_stream = v2_write_stream_i;
      kv_write_token = v2_write_token_i;
      kv_write_offset = v2_write_offset_i;
      kv_write_data = v2_write_data_i;
      kv_write_strb = v2_write_strb_i;
    end
  end

  assign q_read = legacy_replay_read_i && legacy_replay_slot_i < 8;
  assign kv_row_read = v2_row_read_i || (legacy_replay_read_i && legacy_replay_slot_i >= 8);
  always_comb begin
    kv_row_stream = legacy_replay_slot_i < 16 ? AKV_STREAM_K : AKV_STREAM_V;
    kv_row_token = legacy_replay_slot_i < 16 ? 6'(legacy_replay_slot_i - 8) :
                                            6'(legacy_replay_slot_i - 16);
    kv_row_word = legacy_replay_word_i;
    if (v2_row_read_i) begin
      kv_row_stream = v2_row_stream_i;
      kv_row_token = v2_row_token_i;
      kv_row_word = v2_row_word_i;
    end
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) legacy_q_q <= 1'b0;
    else if (legacy_replay_read_i) legacy_q_q <= legacy_replay_slot_i < 8;
  end
  assign legacy_replay_data_o = legacy_q_q ? q_data : kv_data;
  assign v2_row_data_o = kv_data;

  akv_q_store i_q_store (
    .clk_i, .rst_ni, .write_valid_i(q_write), .write_slot_i(packed_slot[2:0]),
    .write_offset_i(packed_offset[7:0]), .write_data_i(packed_data),
    .read_i(q_read), .read_slot_i(legacy_replay_slot_i[2:0]),
    .read_word_i(legacy_replay_word_i), .read_data_o(q_data)
  );
  akv_v2_context i_kv_store (
    .clk_i, .rst_ni, .write_valid_i(kv_write), .write_stream_i(kv_write_stream),
    .write_token_i(kv_write_token), .write_offset_i(kv_write_offset),
    .write_data_i(kv_write_data), .write_strb_i(kv_write_strb), .write_busy_o(kv_write_busy),
    .row_read_i(kv_row_read), .row_stream_i(kv_row_stream), .row_token_i(kv_row_token),
    .row_word_i(kv_row_word), .row_data_o(kv_data),
    .column_start_i, .column_stream_i, .column_dimension_i, .column_count_i, .column_token_count_i,
    .column_busy_o, .column_valid_o, .column_data_o, .column_bank_cycle_o, .conflict_o(kv_conflict)
  );
  assign conflict_o = kv_conflict ||
      // V2 K/V can follow the last Q fragment immediately: Q drains separately.
      (v2_write_valid_i && (legacy_write_valid_i || (packed_valid && packed_slot >= 8))) ||
      ((legacy_replay_read_i || v2_row_read_i || column_start_i || column_busy_o) && write_busy_o) ||
      (legacy_replay_read_i && (v2_row_read_i || column_start_i || column_busy_o));

`ifndef SYNTHESIS
  initial begin
    assert (AkvMaxQRows == 8 && AkvTileTokens == 8 && AkvMaxHeadDim == 128 &&
            AkvV2TileTokens == 64 && QBytes == 2048 && KVBytes == 32768)
      else $fatal(1, "UNIFIED_CAPACITY_CONTRACT");
  end
  always @(posedge clk_i) if (rst_ni) begin
    assert (!$isunknown({abort_i, legacy_write_valid_i, v2_write_valid_i,
                         legacy_replay_read_i, v2_row_read_i, column_start_i}))
      else $fatal(1, "UNIFIED_UNKNOWN_CONTROL");
    assert (!conflict_o) else $fatal(1, "UNIFIED_STORAGE_CONFLICT");
    if (legacy_write_valid_i && !abort_i)
      assert (legacy_write_slot_i < 24) else $fatal(1, "UNIFIED_LEGACY_SLOT");
    if (legacy_replay_read_i)
      assert (!abort_i && legacy_replay_slot_i < 24 && legacy_replay_word_i < 8)
        else $fatal(1, "UNIFIED_LEGACY_REPLAY");
    if (packed_valid)
      assert (packed_tag < 24 && packed_offset < 256 && packed_offset[3:0] == 0)
        else $fatal(1, "UNIFIED_EMISSION_IDENTITY");
    if (abort_i)
      assert (!q_write && !kv_write && !v2_row_read_i && !column_start_i && !column_busy_o)
        else $fatal(1, "UNIFIED_ABORT_WRITE_OR_REPLAY");
  end
`endif
endmodule
