// SPDX-License-Identifier: SHL-0.51
module shared_fma_tagpack_soc_monitor #(
  parameter int InputBits=1, StoredBits=1
) ();
  initial begin
    assert (StoredBits == InputBits-64 && StoredBits >= 16)
      else $fatal(1,"ADDMUL tag compaction not active %m");
    $display("FMA_TAGPACK_CONFIG %m external=%0d stored=%0d",InputBits,StoredBits);
  end
endmodule
bind simd_fma_shared shared_fma_tagpack_soc_monitor #(
  .InputBits($bits(TagType)),.StoredBits(TagBits)
) i_tagpack_config ();
