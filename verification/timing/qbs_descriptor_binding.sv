// Copyright 2026
// SPDX-License-Identifier: SHL-0.51
bind qbs_engine descriptor_alignment_checker #(
  .Bytes(16), .DataWidth(AxiDataWidth), .OffsetWidth(RangeBytesWidth)
) i_descriptor_alignment_check (.*);
