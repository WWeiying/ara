// Verification-only: distinguish instruction payloads from exception responses.
`ifndef SYNTHESIS
module ifetch_payload_probe #(
  parameter type response_t = logic
) (
  input logic clk_i, rst_ni,
  input response_t response
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned cycles = 0, normal = 0, exceptions = 0, unknown_data = 0;
  longint unsigned legacy_warnings = 0, errors = 0;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, response;
  endclocking
  always @(cb) begin
    cycles++;
    if (cb.rst_ni === 1'b1 && cb.response.valid === 1'b1) begin
      if (cb.response.ex.valid === 1'b1) exceptions++;
      else normal++;
      if ($isunknown(cb.response.data)) unknown_data++;
      if ((|cb.response.data) === 1'bx) legacy_warnings++;
      if ($isunknown(cb.response.ex.valid) ||
          (cb.response.ex.valid !== 1'b1 && $isunknown(cb.response.data))) begin
        errors++;
        $error("[IFETCH_PAYLOAD] unknown non-exception payload/control");
      end
      if (cb.response.ex.valid === 1'b1 || $isunknown(cb.response.data))
        $display("[IFETCH_PAYLOAD] cycle=%0d va=%h ex=%b cause=%h tval=%h unknown=%0d legacy_warning=%0d",
          cycles, cb.response.vaddr, cb.response.ex.valid, cb.response.ex.cause,
          cb.response.ex.tval, $isunknown(cb.response.data), (|cb.response.data) === 1'bx);
    end
  end
  final $display("[IFETCH_PAYLOAD_END] normal=%0d exceptions=%0d unknown=%0d legacy_warnings=%0d errors=%0d",
    normal, exceptions, unknown_data, legacy_warnings, errors);
endmodule

bind wt_cache_subsystem ifetch_payload_probe #(.response_t(icache_drsp_t))
  i_ifetch_payload_probe (.clk_i(clk_i), .rst_ni(rst_ni), .response(icache_dreq_o));
`endif
