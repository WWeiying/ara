// Read-only demand trace for deciding whether ordered adders can be shared.
// A request histogram is a necessary capacity check, not a timing proof.
module ordered_area_profile #(
  parameter int LaneWidth = 2,
  parameter int DescriptorBits = 1
)(
  input logic clk_i, rst_ni,
  input logic [LaneWidth-1:0] lane_i,
  input logic request_i, ready_i, response_i, response_ready_i,
  input logic [2:0] id_i
);
  bit enabled;
  longint unsigned cycle_q, requests, accepted, blocked, responses;
  initial enabled = $test$plusargs("AREA_ORDERED_PROFILE");
  always @(posedge clk_i) begin
    if (!rst_ni) begin
      cycle_q = 0; requests = 0; accepted = 0; blocked = 0; responses = 0;
    end else begin
      cycle_q++;
      if (enabled) begin
        if (request_i) begin
          requests++;
          if (ready_i) accepted++; else blocked++;
          $display("[AREA_ORDERED] cycle=%0d lane=%0d id=%0d fire=%0d", cycle_q, lane_i, id_i, ready_i);
        end
        if (response_i && response_ready_i) responses++;
      end
    end
  end
  final if (enabled)
    $display("[AREA_ORDERED_SUMMARY] lane=%0d descriptor_bits=%0d requests=%0d accepted=%0d blocked=%0d responses=%0d", lane_i, DescriptorBits, requests, accepted, blocked, responses);
endmodule

`ifdef ARA_RED_ORDERED_FAST_4LANE
bind vmfpu ordered_area_profile #(.LaneWidth($bits(lane_id_i)), .DescriptorBits($bits(vinsn_issue_q)))
  i_ordered_area_profile (
    .clk_i, .rst_ni, .lane_i(lane_id_i), .id_i(vinsn_issue_q.id),
    .request_i(fpu_gen.ordered_fast_in_valid), .ready_i(fpu_gen.ordered_fast_in_ready),
    .response_i(fpu_gen.ordered_fast_out_valid), .response_ready_i(fpu_gen.ordered_fast_out_ready)
  );
`endif
