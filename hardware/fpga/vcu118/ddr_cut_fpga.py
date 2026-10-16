"""Preserve the reviewed VCU118 MIG read-response timing cut on every export."""


def patch_ddr_read_cut(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError("DDR read cut source changed: " + old)
        text = text.replace(old, new)

    replace("iresizer_cdc_req, cdc_dram_req;", "iresizer_cdc_req, cdc_cut_req, cdc_dram_req;")
    replace("iresizer_cdc_rsp, cdc_dram_rsp;", "iresizer_cdc_rsp, cdc_cut_rsp, cdc_dram_rsp;")
    replace(".dst_req_o  ( cdc_dram_req )", ".dst_req_o  ( cdc_cut_req )")
    replace(".dst_resp_i ( cdc_dram_rsp )", ".dst_resp_i ( cdc_cut_rsp )")
    replace("assign cdc_dram_req     = iresizer_cdc_req;", "assign cdc_cut_req      = iresizer_cdc_req;")
    replace("assign iresizer_cdc_rsp = cdc_dram_rsp;", "assign iresizer_cdc_rsp = cdc_cut_rsp;")
    marker = "  ////////////////////////////////\n  //  Map User, Resize Address  //"
    replace(marker, """`ifdef TARGET_VCU118
  // Isolate the CDC read-FIFO full detector from the MIG upsizer's RREADY path.
  axi_cut #(
    .Bypass     ( 1'b1                ),
    .BypassR    ( 1'b0                ),
    .aw_chan_t  ( axi_dw_iw_aw_chan_t ),
    .w_chan_t   ( axi_dw_iw_w_chan_t  ),
    .b_chan_t   ( axi_dw_iw_b_chan_t  ),
    .ar_chan_t  ( axi_dw_iw_ar_chan_t ),
    .r_chan_t   ( axi_dw_iw_r_chan_t  ),
    .axi_req_t  ( axi_dw_iw_req_t     ),
    .axi_resp_t ( axi_dw_iw_resp_t    )
  ) i_ddr_r_cut (
    .clk_i      ( dram_axi_clk ),
    .rst_ni     ( ui_resetn   ),
    .slv_req_i  ( cdc_cut_req ),
    .slv_resp_o ( cdc_cut_rsp ),
    .mst_req_o  ( cdc_dram_req ),
    .mst_resp_i ( cdc_dram_rsp )
  );
`else
  assign cdc_dram_req = cdc_cut_req;
  assign cdc_cut_rsp  = cdc_dram_rsp;
`endif

""" + marker)
    return text
