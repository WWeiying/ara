// SPDX-License-Identifier: SHL-0.51
// Instantiate only in the dual-DDR profile, before the 31-bit MIG address truncation.
`include "axi/typedef.svh"
module ara_ddr_router #(
  parameter type req_t = logic,
  parameter type rsp_t = logic,
  parameter int unsigned MaxTrans = 24
) (
  input logic clk_i,
  input logic rst_ni,
  input req_t req_i,
  output rsp_t rsp_o,
  output req_t [1:0] req_o,
  input rsp_t [1:0] rsp_i
);
  localparam int unsigned AddrWidth = $bits(req_i.aw.addr);
  localparam int unsigned IdWidth = $bits(req_i.aw.id);
  typedef logic [AddrWidth-1:0] addr_t;
  typedef logic [IdWidth-1:0] id_t;
  typedef logic [$bits(req_i.w.data)-1:0] data_t;
  typedef logic [$bits(req_i.w.strb)-1:0] strb_t;
  typedef logic [$bits(req_i.aw.user)-1:0] user_t;
  `AXI_TYPEDEF_ALL(router, addr_t, id_t, data_t, strb_t, user_t)
  typedef struct packed {
    int unsigned idx;
    addr_t start_addr;
    addr_t end_addr;
  } rule_t;
  // Explicit indices avoid reversing C1/C2 through packed-array concatenation.
  localparam rule_t [1:0] AddrMap = '{
    0: '{idx: 0, start_addr: addr_t'(64'h8000_0000), end_addr: addr_t'(64'h1_0000_0000)},
    1: '{idx: 1, start_addr: addr_t'(64'h1_0000_0000), end_addr: addr_t'(64'h1_8000_0000)}
  };
  localparam axi_pkg::xbar_cfg_t XbarCfg = '{
    NoSlvPorts: 1,
    NoMstPorts: 2,
    MaxMstTrans: MaxTrans,
    MaxSlvTrans: MaxTrans,
    FallThrough: 0,
    LatencyMode: axi_pkg::CUT_ALL_PORTS,
    PipelineStages: 0,
    AxiIdWidthSlvPorts: IdWidth,
    AxiIdUsedSlvPorts: IdWidth,
    UniqueIds: 0,
    AxiAddrWidth: AddrWidth,
    AxiDataWidth: $bits(req_i.w.data),
    NoAddrRules: 2
  };
  req_t [0:0] req;
  rsp_t [0:0] rsp;
  assign req[0] = req_i;
  assign rsp_o = rsp[0];

  // The xbar retains AW/W ownership and same-ID ordering, and terminates
  // unmapped requests with DECERR. Legal AXI bursts cannot cross 4 KiB,
  // hence cannot cross these 2 GiB-aligned bank boundaries. This is not a
  // malformed-burst firewall; the producer must obey the AXI burst contract.
  // Cheshire's LLC atomic shim has already consumed ATOPs at this boundary.
  axi_xbar #(
    .Cfg(XbarCfg), .ATOPs(1'b0),
    .slv_aw_chan_t(router_aw_chan_t), .mst_aw_chan_t(router_aw_chan_t), .w_chan_t(router_w_chan_t),
    .slv_b_chan_t(router_b_chan_t), .mst_b_chan_t(router_b_chan_t),
    .slv_ar_chan_t(router_ar_chan_t), .mst_ar_chan_t(router_ar_chan_t),
    .slv_r_chan_t(router_r_chan_t), .mst_r_chan_t(router_r_chan_t),
    .slv_req_t(req_t), .mst_req_t(req_t),
    .slv_resp_t(rsp_t), .mst_resp_t(rsp_t), .rule_t(rule_t)
  ) i_xbar (
    .clk_i, .rst_ni, .test_i(1'b0),
    .slv_ports_req_i(req), .slv_ports_resp_o(rsp),
    .mst_ports_req_o(req_o), .mst_ports_resp_i(rsp_i),
    .addr_map_i(AddrMap), .en_default_mst_port_i('0), .default_mst_port_i('0)
  );

  // pragma translate_off
  initial begin
    if (AddrWidth < 33 || IdWidth < 1 || MaxTrans < 1)
      $fatal(1, "DDR router requires >=33 address bits, IDs and transaction storage");
  end
  // pragma translate_on
endmodule
