`timescale 1ns/1ps
// Observation only. Bind to the local engine; no production RTL modification.
module qbs_tile_boundary_probe (
  input logic clk_i, rst_ni,
  input logic start_fire, done, read_valid,
  input logic [7:0] read_k,
  input logic [8:0] block_elements,
  input logic compute_active, issue_active, s0_valid, dot_valid,
  input logic [2:0] dot_meta_valid,
  input logic context_id,
  input logic [1:0] context_valid,
  input logic correction_empty,
  input logic weight_bank,
  input logic [2:0] m,
  input logic [31:0] parent_state
);
  integer cycle, remaining, windows, records;
  bit enabled;
  initial enabled=$test$plusargs("QBS_TILE_BOUNDARY_TRACE");
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      cycle=0; remaining=0; windows=0; records=0;
    end else if (enabled) begin
      cycle=cycle+1;
      if (!remaining && windows<8 && read_valid &&
          unsigned'(read_k)+8>=unsigned'(block_elements)) begin
        remaining=16; windows=windows+1;
      end
      if (remaining && records<128) begin
        $display("QBS_TILE_BOUNDARY cycle=%0d window=%0d state=%0d m=%0d bank=%0d start=%0d done=%0d read=%0d k=%0d block=%0d compute=%0d issue=%0d s0=%0d meta=%0d dot=%0d ctx=%0d live=%0d correction_empty=%0d",
          cycle,windows,parent_state,m,weight_bank,start_fire,done,read_valid,
          read_k,block_elements,compute_active,issue_active,s0_valid,dot_meta_valid,
          dot_valid,context_id,context_valid,correction_empty);
        remaining=remaining-1; records=records+1;
      end
    end
  end
endmodule

bind qbs_compute_engine qbs_tile_boundary_probe i_tile_boundary_probe (
  .clk_i(clk_i), .rst_ni(rst_ni),
  .start_fire(integer_start_fire), .done(integer_done),
  .read_valid(buffer_read_valid), .read_k(buffer_read_k_base),
  .block_elements(i_profile_engine_int.block_elements_q),
  .compute_active(i_profile_engine_int.compute_active_q),
  .issue_active(i_profile_engine_int.issue_active_q),
  .s0_valid(i_profile_engine_int.s0_valid_q),
  .dot_valid(i_profile_engine_int.dot_valid),
  .dot_meta_valid(i_profile_engine_int.dot_metadata_valid_q),
  .context_id(i_profile_engine_int.compute_context_q),
  .context_valid(i_profile_engine_int.context_valid_q),
  .correction_empty(i_profile_engine_int.correction_drain_empty),
  .weight_bank(active_weight_bank_q), .m(i_profile_engine_int.m_q),
  .parent_state(32'(state_q))
);
