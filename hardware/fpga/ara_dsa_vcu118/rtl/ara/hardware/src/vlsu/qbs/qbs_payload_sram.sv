// Copyright 2026
// SPDX-License-Identifier: SHL-0.51

// One synchronous read or byte-masked write per cycle. Payload is not reset;
// ownership and byte-valid state in the adapter qualify all consumers.
module qbs_payload_sram #(
  parameter int unsigned NumWords = 8,
  parameter int unsigned DataWidth = 256,
  localparam int unsigned AddrWidth = $clog2(NumWords)
) (
  input logic clk_i, rst_ni,
  input logic req_i, we_i,
  input logic [2:0] addr_i,
  input logic [DataWidth-1:0] wdata_i,
  input logic [DataWidth/8-1:0] be_i,
  output logic [DataWidth-1:0] rdata_o
);
`ifndef TARGET_SRAM_MC
  tc_sram #(
    .NumWords(NumWords), .DataWidth(DataWidth), .ByteWidth(8), .NumPorts(1),
    .Latency(1), .SimInit("none"), .ImplKey("qbs_payload_1p")
  ) i_sram (
    .clk_i, .rst_ni, .req_i, .we_i, .addr_i(addr_i[AddrWidth-1:0]),
    .wdata_i, .be_i, .rdata_o
  );
`else
  logic [DataWidth-1:0] bweb;
  for (genvar b = 0; b < DataWidth/8; b++) begin : gen_bweb
    assign bweb[8*b +: 8] = {8{!be_i[b]}};
  end
  if (DataWidth == 128) begin : gen_weight
    TS1N28HPCPUHDSVTB8X128M1SWBSO i_sram (
      .CLK(clk_i), .SLP(1'b0), .SD(1'b0), .CEB(!req_i), .WEB(!we_i),
      .A(addr_i), .D(wdata_i), .BWEB(bweb), .Q(rdata_o),
      .CEBM(1'b1), .WEBM(1'b1), .AM('0), .DM('0), .BWEBM('1),
      .BIST(1'b0), .RTSEL(2'b01), .WTSEL(2'b00)
    );
  end else begin : gen_activation
    TS1N28HPCPUHDSVTB8X256M1SWBSO i_sram (
    .CLK(clk_i), .SLP(1'b0), .SD(1'b0), .CEB(!req_i), .WEB(!we_i),
    .A(addr_i), .D(wdata_i), .BWEB(bweb), .Q(rdata_o),
    .CEBM(1'b1), .WEBM(1'b1), .AM('0), .DM('0), .BWEBM('1),
    .BIST(1'b0), .RTSEL(2'b01), .WTSEL(2'b00)
  );
  end
`endif
`ifndef SYNTHESIS
  initial assert (NumWords inside {2, 4, 8});
  initial assert (DataWidth inside {128, 256});
  assert property (@(posedge clk_i) disable iff (!rst_ni)
      req_i |-> unsigned'(addr_i) < NumWords)
    else $fatal(1, "QBS payload SRAM address exceeds logical depth");
`endif
endmodule
