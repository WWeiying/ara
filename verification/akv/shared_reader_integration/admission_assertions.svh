// Successor-only VLSU assertions. Not included in the live snapshot-01 compile.
// Include inside vlsu after the engine instances are declared.
`ifndef SYNTHESIS
always @(posedge clk_i) begin
  if (rst_ni) begin
    assert (!$isunknown({qbs_active_q, akv_active_q,
                         qbs_command_fire, akv_command_fire}))
      else $fatal(1, "SHARED_VLSU_UNKNOWN_OWNER_OR_FIRE");
    if (qbs_command_fire || akv_command_fire) begin
      // A fault terminal may precede local write-pipeline drain. Admission of
      // the next command, not the fault terminal, is the required boundary.
      assert (i_akv_engine.context_write_busy === 1'b0 &&
              i_akv_engine.v1_context_write_valid === 1'b0 &&
              i_akv_engine.v2_context_write_valid === 1'b0)
        else $fatal(1, "SHARED_VLSU_ADMIT_WITH_AKV_WRITE_PENDING");
    end
  end
end
`endif
