// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// A narrow logical client on a wide physical reader. Its ranges must request
// at most 16-byte AXI transfers, already compacted by the reader. No fragment
// buffer or serial conversion is inserted in the wide weight path.
module qbs_reader_narrow_view #(
  parameter type wide_rsp_t = logic,
  parameter type narrow_rsp_t = logic
) (
  input logic clk_i, rst_ni,
  input wide_rsp_t wide_i,
  output narrow_rsp_t narrow_o
);
  assign narrow_o = '{
    range_ready: wide_i.range_ready,
    data_valid: wide_i.data_valid,
    data: wide_i.data[127:0],
    data_strb: wide_i.data_strb[15:0],
    data_offset: wide_i.data_offset,
    data_tag: wide_i.data_tag,
    completion_valid: wide_i.completion_valid,
    completion_tag: wide_i.completion_tag,
    fault_valid: wide_i.fault_valid,
    fault_kind: wide_i.fault_kind,
    fault_vaddr: wide_i.fault_vaddr,
    fault_tag: wide_i.fault_tag,
    fault_mmu_exception: wide_i.fault_mmu_exception,
    range_count: wide_i.range_count,
    translation_count: wide_i.translation_count,
    ar_count: wide_i.ar_count,
    r_beat_count: wide_i.r_beat_count,
    payload_byte_count: wide_i.payload_byte_count,
    store_wait_cycles: wide_i.store_wait_cycles,
    r_backpressure_cycles: wide_i.r_backpressure_cycles,
    outstanding_occupancy_sum: wide_i.outstanding_occupancy_sum,
    outstanding_max: wide_i.outstanding_max,
    outstanding_full_cycles: wide_i.outstanding_full_cycles,
    busy: wide_i.busy
  };

`ifndef SYNTHESIS
  initial begin
    assert ($bits(wide_i.data) inside {128, 256} &&
            $bits(wide_i.data_strb)*8 == $bits(wide_i.data) &&
            $bits(narrow_o.data) == 128 && $bits(narrow_o.data_strb) == 16 &&
            $bits(wide_i.fault_vaddr) == $bits(narrow_o.fault_vaddr) &&
            $bits(wide_i.fault_mmu_exception) == $bits(narrow_o.fault_mmu_exception))
      else $fatal(1, "QBS_READER_NARROW_VIEW_WIDTH");
  end
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      wide_i.data_valid |-> (wide_i.data_strb >> 16) == 0)
    else $fatal(1, "QBS_READER_NARROW_VIEW_NONNARROW_PAYLOAD");
`endif
endmodule
