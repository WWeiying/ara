// Experimental legacy-F16 write adapter; not connected to production SRAM.
module akv_legacy_repacker (
  input logic clk_i, rst_ni, abort_i,
  input logic fragment_valid_i,
  input logic [15:0] fragment_tag_i,
  input logic [8:0] fragment_offset_i, row_bytes_i,
  input logic [127:0] fragment_data_i,
  input logic [15:0] fragment_strb_i,
  output logic write_valid_o,
  output logic [15:0] write_tag_o,
  output logic [8:0] write_offset_o,
  output logic [127:0] write_data_o,
  output logic write_last_o,
  output logic busy_o
);
  logic stage_valid_q, emit_valid_q, active_q;
  logic [15:0] stage_tag_q, stage_strb_q, tag_q;
  logic [8:0] stage_offset_q, stage_row_bytes_q, next_offset_q, row_bytes_q;
  logic [127:0] stage_data_q, pending_q;
  logic [3:0] pending_count_q;
  logic [255:0] joined;
  logic [127:0] compact_data;
  logic [5:0] fragment_count, combined_count;

  always_comb begin
    fragment_count = '0;
    compact_data = '0;
    for (int i = 0; i < 16; i++) begin
      fragment_count += 6'(stage_strb_q[i]);
      if (stage_strb_q[i]) compact_data[i*8 +: 8] = stage_data_q[i*8 +: 8];
    end
    combined_count = {2'b0, pending_count_q} + fragment_count;
    joined = {128'b0, pending_q} |
             ({128'b0, compact_data} << (8 * unsigned'(pending_count_q)));
  end

  // Abort suppresses an unconsumed registered write at this same SRAM edge.
  assign write_valid_o = emit_valid_q && !abort_i;
  assign busy_o = fragment_valid_i || stage_valid_q || active_q || emit_valid_q;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      stage_valid_q <= 1'b0;
      emit_valid_q <= 1'b0;
      active_q <= 1'b0;
      pending_count_q <= '0;
      pending_q <= '0;
      next_offset_q <= '0;
      tag_q <= '0;
      row_bytes_q <= '0;
      write_tag_o <= '0;
      write_offset_o <= '0;
      write_data_o <= '0;
      write_last_o <= 1'b0;
    end else if (abort_i) begin
      stage_valid_q <= 1'b0;
      emit_valid_q <= 1'b0;
      active_q <= 1'b0;
      pending_count_q <= '0;
      pending_q <= '0;
      next_offset_q <= '0;
    end else begin
      stage_valid_q <= fragment_valid_i;
      if (fragment_valid_i) begin
        stage_tag_q <= fragment_tag_i;
        stage_offset_q <= fragment_offset_i;
        stage_row_bytes_q <= row_bytes_i;
        stage_data_q <= fragment_data_i;
        stage_strb_q <= fragment_strb_i;
      end
      emit_valid_q <= 1'b0;
      if (stage_valid_q) begin
        tag_q <= stage_tag_q;
        row_bytes_q <= stage_row_bytes_q;
        next_offset_q <= stage_offset_q + 9'(fragment_count);
        active_q <= stage_offset_q + 9'(fragment_count) != stage_row_bytes_q;
        if (combined_count >= 16) begin
          emit_valid_q <= 1'b1;
          write_tag_o <= stage_tag_q;
          write_offset_o <= stage_offset_q - 9'(pending_count_q);
          write_data_o <= joined[127:0];
          write_last_o <= stage_offset_q + 9'(fragment_count) == stage_row_bytes_q;
          pending_q <= joined[255:128];
          pending_count_q <= 4'(combined_count - 16);
        end else begin
          pending_q <= joined[127:0];
          pending_count_q <= 4'(combined_count);
        end
      end
    end
  end

`ifndef SYNTHESIS
  always @(posedge clk_i) if (rst_ni && !abort_i && stage_valid_q) begin
    assert (fragment_count >= 2 && fragment_count <= 16 && !fragment_count[0] &&
            stage_strb_q == 16'((32'd1 << fragment_count) - 1) &&
            !stage_offset_q[0] &&
            (stage_row_bytes_q == 128 || stage_row_bytes_q == 192 || stage_row_bytes_q == 256) &&
            stage_offset_q + 9'(fragment_count) <= stage_row_bytes_q)
      else $fatal(1, "REPACK_FRAGMENT_CONTRACT");
    assert ((!active_q && stage_offset_q == 0 && pending_count_q == 0) ||
            (active_q && stage_tag_q == tag_q && stage_row_bytes_q == row_bytes_q &&
             stage_offset_q == next_offset_q))
      else $fatal(1, "REPACK_STREAM_CONTINUITY");
    assert (stage_offset_q + 9'(fragment_count) != stage_row_bytes_q || combined_count == 16)
      else $fatal(1, "REPACK_FINAL_PARTIAL");
  end
`endif
endmodule
