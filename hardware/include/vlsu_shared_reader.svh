// Included only by the isolated VLSU overlay, after client declarations.
`include "shared_reader_types.svh"
`QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(shared_read_req_t, CVA6Cfg.VLEN)
`QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(shared_read_rsp_t, AxiDataWidth, CVA6Cfg.VLEN, exception_t)
shared_read_req_t shared_read_req [2];
shared_read_rsp_t shared_read_rsp [2];
logic shared_read_clk, shared_read_clk_en;
logic shared_mmu_req, shared_mmu_is_store;
logic [CVA6Cfg.VLEN-1:0] shared_mmu_vaddr;
logic shared_physical_check_valid, shared_physical_range_allowed;
logic [AxiAddrWidth-1:0] shared_physical_check_addr;
logic [12:0] shared_physical_check_bytes;
axi_ar_t shared_axi_ar;
axi_r_t shared_axi_r;
logic shared_axi_ar_valid, shared_axi_ar_ready, shared_axi_r_valid, shared_axi_r_ready;

// OR the original enables BEFORE one clock gate, never OR gated clocks.
// Includes acceptance with owner=0 and the whole command through terminal.
assign shared_read_clk_en = qbs_clk_en || akv_clk_en;
tc_clk_gating #(.IS_FUNCTIONAL(1'b1)) i_shared_read_clk_gate (
  .clk_i, .en_i(shared_read_clk_en), .test_en_i(1'b0), .clk_o(shared_read_clk)
);
qbs_akv_shared_reader #(
  .AxiDataWidth(AxiDataWidth), .AxiAddrWidth(AxiAddrWidth),
  .VAddrWidth(CVA6Cfg.VLEN), .PAddrWidth(CVA6Cfg.PLEN),
  .req_t(shared_read_req_t), .rsp_t(shared_read_rsp_t),
  .axi_ar_t(axi_ar_t), .axi_r_t(axi_r_t), .exception_t(exception_t)
) i_shared_reader (
  .clk_i(shared_read_clk), .rst_ni,
  .owner_i({akv_active_q, qbs_active_q}),
  .command_fire_i({akv_command_fire, qbs_command_fire}),
  .client_req_i(shared_read_req), .client_rsp_o(shared_read_rsp),
  .core_st_pending_i, .en_ld_st_translation_i,
  .mmu_req_o(shared_mmu_req), .mmu_vaddr_o(shared_mmu_vaddr),
  .mmu_is_store_o(shared_mmu_is_store), .mmu_valid_i, .mmu_paddr_i,
  .mmu_exception_valid_i(mmu_exception_i.valid), .mmu_exception_i,
  .physical_check_valid_o(shared_physical_check_valid),
  .physical_check_addr_o(shared_physical_check_addr),
  .physical_check_bytes_o(shared_physical_check_bytes),
  .physical_range_allowed_i(shared_physical_range_allowed),
  .axi_ar_o(shared_axi_ar), .axi_ar_valid_o(shared_axi_ar_valid),
  .axi_ar_ready_i(shared_axi_ar_ready), .axi_r_i(shared_axi_r),
  .axi_r_valid_i(shared_axi_r_valid), .axi_r_ready_o(shared_axi_r_ready)
);

// Keep the existing VLSU AXI/MMU ownership mux and cut unchanged. These aliases
// also preserve per-owner interface probes; there is no extra arbitration/state.
assign qbs_axi_ar = qbs_active_q ? shared_axi_ar : axi_ar_t'('0);
assign akv_axi_ar = akv_active_q ? shared_axi_ar : axi_ar_t'('0);
assign qbs_axi_ar_valid = qbs_active_q && shared_axi_ar_valid;
assign akv_axi_ar_valid = akv_active_q && shared_axi_ar_valid;
assign qbs_axi_r_ready = qbs_active_q && shared_axi_r_ready;
assign akv_axi_r_ready = akv_active_q && shared_axi_r_ready;
assign shared_axi_ar_ready = qbs_axi_ar_ready || akv_axi_ar_ready;
assign shared_axi_r = qbs_active_q ? qbs_axi_r : akv_axi_r;
assign shared_axi_r_valid = qbs_axi_r_valid || akv_axi_r_valid;
assign qbs_mmu_req = qbs_active_q && shared_mmu_req;
assign akv_mmu_req = akv_active_q && shared_mmu_req;
assign qbs_mmu_vaddr = qbs_active_q ? shared_mmu_vaddr : '0;
assign akv_mmu_vaddr = akv_active_q ? shared_mmu_vaddr : '0;
assign qbs_mmu_is_store = qbs_active_q && shared_mmu_is_store;
assign akv_mmu_is_store = akv_active_q && shared_mmu_is_store;
assign qbs_physical_check_valid = qbs_active_q && shared_physical_check_valid;
assign akv_physical_check_valid = akv_active_q && shared_physical_check_valid;
assign qbs_physical_check_addr = qbs_active_q ? shared_physical_check_addr : '0;
assign akv_physical_check_addr = akv_active_q ? shared_physical_check_addr : '0;
assign qbs_physical_check_bytes = qbs_active_q ? shared_physical_check_bytes : '0;
assign akv_physical_check_bytes = akv_active_q ? shared_physical_check_bytes : '0;
assign shared_physical_range_allowed = qbs_range_is_cacheable_idempotent(
    shared_physical_check_addr, shared_physical_check_bytes);

`ifndef SYNTHESIS
// These are integration invariants, not a new drain/ownership state machine.
always @(posedge clk_i) begin
  if (rst_ni) begin
    assert ($onehot0({akv_active_q, qbs_active_q}) &&
            $onehot0({akv_command_fire, qbs_command_fire}))
      else $fatal(1, "SHARED_VLSU_OWNERSHIP");
    if (qbs_terminal || akv_terminal)
      assert (!i_shared_reader.reader_rsp.busy && !shared_axi_ar_valid &&
              !i_shared_reader.i_read_engine.ar_stalled_q &&
              !i_shared_reader.i_read_engine.response_drain_q)
        else $fatal(1, "SHARED_VLSU_PREMATURE_RELEASE");
    if (i_shared_reader.reader_rsp.busy || shared_axi_ar_valid || shared_mmu_req)
      assert (shared_read_clk_en && (qbs_active_q || akv_active_q))
        else $fatal(1, "SHARED_VLSU_CLOCK_OR_OWNER_LOST");
  end
end
`endif
