// Verification-only binds; compile with cva6_state_prereq_probe.sv for its sink.
// All rows use the same pre-edge #1step phase, cycle origin and reset epochs.
// No force, no DUT writes. Bound is 8192 emitted rows PER source, including tails/reset.
// req is a translation request level, not an AXI handshake or retirement.
// PTW cache payload is packed in addition to named request/grant/data fields.
// AXI fire is valid && ready; PTW fire is data_req && data_gnt (no response ready).
// VRF req && gnt accepts a write; final_gnt is a separate, later completion event.
// *_d/*_n are pre-edge combinational next values, NOT another committed transaction.
// Bind kinds: mmu, mmu_route, addrgen, vlsu, ptw, seq, dispatcher.
// Precompile: the separate lifecycle probe starts at FIRST ACC and records every
// cycle (hard cap 65536). Put scalar initialization before even startup ACC/CSR
// instructions, or have its owner budget/adjust the trigger or cap before compile.
// Raising only its CYCLES plusarg above 65536 is fatal; this file does not change it.
`ifndef SYNTHESIS

module sv39_mmu_probe #(
  parameter config_pkg::cva6_cfg_t C = config_pkg::cva6_cfg_empty,
  parameter type ex_t = logic,
  parameter type ic_req_t = logic,
  parameter type ic_rsp_t = logic,
  parameter type dc_req_t = logic,
  parameter type dc_rsp_t = logic,
  parameter type pte_t = logic,
  parameter type update_t = logic
) (
  input logic clk_i, rst_ni, enable_i, enable_d, flush, flush_tlb,
  input logic [C.PPNW-1:0] root,
  input logic [C.ASID_WIDTH-1:0] asid,
  input riscv::priv_lvl_t priv, data_priv,
  input logic sum, mxr, req, store, hit, valid,
  input logic [C.VLEN-1:0] va,
  input logic [C.PLEN-1:0] pa,
  input ex_t ex, misaligned_q,
  input logic req_q, store_q, hit_q,
  input logic [C.VLEN-1:0] va_q, shared_va, update_va, sfence_va,
  input logic [C.ASID_WIDTH-1:0] sfence_asid,
  input logic [C.PtLevels-2:0] page_q,
  input pte_t pte_q,
  input logic shared_access, shared_hit, shared_miss, itlb_req,
  input logic ptw_active, walking_instr, ptw_error, ptw_access_exception,
  input logic itlb_miss, dtlb_miss, daccess_err, canonical_addr_check,
  input pte_t dtlb_content,
  input update_t update_itlb, update_dtlb, update_shared_tlb,
  input ic_req_t if_req,
  input ic_rsp_t if_rsp,
  input dc_req_t ptw_req,
  input dc_rsp_t ptw_rsp
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("mmu")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, enable_i, enable_d, flush, flush_tlb, root, asid;
    input priv, data_priv, sum, mxr, req, store, hit, valid, va, pa, ex;
    input req_q, store_q, hit_q, va_q, pte_q, page_q, misaligned_q;
    input shared_access, shared_hit, shared_miss, itlb_req, shared_va, update_va;
    input sfence_va, sfence_asid;
    input ptw_active, walking_instr, ptw_error, ptw_access_exception;
    input itlb_miss, dtlb_miss, daccess_err, canonical_addr_check;
    input dtlb_content, update_itlb, update_dtlb, update_shared_tlb;
    input if_req, if_rsp, ptw_req, ptw_rsp;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      (({cb.flush_tlb, cb.ptw_active, cb.ptw_error, cb.ptw_access_exception,
         cb.ex.valid, cb.if_rsp.fetch_exception.valid, cb.shared_access, cb.shared_miss,
         cb.update_itlb.valid, cb.update_dtlb.valid, cb.update_shared_tlb.valid} !== '0) ||
       ((cb.enable_d !== 1'b0) && ({cb.req, cb.req_q, cb.valid, cb.flush} !== '0)) ||
       ((cb.enable_i !== 1'b0) && (cb.itlb_miss !== 1'b0)));
    row = "";
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"en_i=%b en_d=%b root=%h asid=%h priv=%b data_priv=%b sum=%b mxr=%b flush=%b sfence=%b",
        " req=%b store=%b va=%h hit=%b valid=%b pa=%h ex_valid=%b cause=%h tval=%h",
        " walk=%b walk_i=%b walk_error=%b walk_access_error=%b imiss=%b dmiss=%b daccess_err=%b canonical=%b",
        " dtlb_pte=%h update_i=%h update_d=%h update_shared=%h if_req=%h if_rsp=%h",
        " ptw_req=%h ptw_rsp=%h cache_req=%b cache_gnt=%b cache_rvalid=%b cache_rdata=%h",
        " req_q=%b store_q=%b va_q=%h hit_q=%b pte_q=%h page_q=%b misaligned_q=%h",
        " shared_access=%b shared_hit=%b shared_miss=%b itlb_req=%b shared_va=%h update_va=%h",
        " sfence_va=%h sfence_asid=%h"},
        cb.enable_i, cb.enable_d, cb.root, cb.asid, cb.priv, cb.data_priv, cb.sum, cb.mxr, cb.flush, cb.flush_tlb,
        cb.req, cb.store, cb.va, cb.hit, cb.valid, cb.pa, cb.ex.valid, cb.ex.cause, cb.ex.tval,
        cb.ptw_active, cb.walking_instr, cb.ptw_error, cb.ptw_access_exception, cb.itlb_miss, cb.dtlb_miss,
        cb.daccess_err, cb.canonical_addr_check, cb.dtlb_content,
        cb.update_itlb, cb.update_dtlb, cb.update_shared_tlb, cb.if_req, cb.if_rsp,
        cb.ptw_req, cb.ptw_rsp, cb.ptw_req.data_req, cb.ptw_rsp.data_gnt,
        cb.ptw_rsp.data_rvalid, cb.ptw_rsp.data_rdata,
        cb.req_q, cb.store_q, cb.va_q, cb.hit_q, cb.pte_q, cb.page_q, cb.misaligned_q,
        cb.shared_access, cb.shared_hit, cb.shared_miss, cb.itlb_req, cb.shared_va, cb.update_va,
        cb.sfence_va, cb.sfence_asid);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_route_probe #(
  parameter config_pkg::cva6_cfg_t C = config_pkg::cva6_cfg_empty,
  parameter type req_t = logic, parameter type rsp_t = logic,
  parameter type ex_t = logic, parameter type fu_t = logic, parameter type ctrl_t = logic
) (
  input logic clk_i, rst_ni, enabled, scalar_valid, scalar_ready, flush,
  input fu_t scalar_fu,
  input req_t acc_req,
  input rsp_t acc_rsp,
  input logic selected_req, selected_store, selected_valid, scalar_req,
  input logic [C.VLEN-1:0] selected_va, scalar_va,
  input logic [C.PLEN-1:0] selected_pa, scalar_pa, pre_pmp_pa,
  input logic scalar_rsp_valid, pre_pmp_valid, pop_ld, pop_st,
  input ctrl_t ctrl_byp, ctrl,
  input ex_t selected_ex, scalar_ex, pre_pmp_ex
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("mmu_route")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, enabled, scalar_valid, scalar_ready, flush, scalar_fu;
    input acc_req, acc_rsp, selected_req, selected_store, selected_valid, scalar_req;
    input selected_va, scalar_va, selected_ex;
    input selected_pa, scalar_pa, pre_pmp_pa, scalar_rsp_valid, pre_pmp_valid;
    input pop_ld, pop_st, ctrl_byp, ctrl, scalar_ex, pre_pmp_ex;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      (({cb.acc_req.acc_mmu_req, cb.acc_rsp.acc_mmu_valid, cb.selected_ex.valid} !== '0) ||
       ((cb.enabled !== 1'b0) &&
        ({cb.scalar_valid, cb.selected_req, cb.selected_valid, cb.flush} !== '0)));
    row = "";
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"enabled=%b scalar_valid=%b scalar_ready=%b scalar_fu=%h flush=%b",
        " acc_req=%b acc_va=%h acc_store=%b acc_valid=%b acc_pa=%h acc_hit=%b acc_ex=%h",
        " selected_req=%b selected_va=%h selected_store=%b selected_valid=%b selected_ex=%h",
        " scalar_req=%b scalar_va=%h owner_observed=0 selected_pa=%h scalar_pa=%h scalar_rsp_valid=%b",
        " pre_pmp_valid=%b pre_pmp_pa=%h pre_pmp_ex=%h scalar_ex=%h",
        " ctrl_byp=%h ctrl=%h pop_ld=%b pop_st=%b acc_req_packed=%h acc_rsp_packed=%h"},
        cb.enabled, cb.scalar_valid, cb.scalar_ready, cb.scalar_fu, cb.flush,
        cb.acc_req.acc_mmu_req, cb.acc_req.acc_mmu_vaddr, cb.acc_req.acc_mmu_is_store,
        cb.acc_rsp.acc_mmu_valid, cb.acc_rsp.acc_mmu_paddr, cb.acc_rsp.acc_mmu_dtlb_hit,
        cb.acc_rsp.acc_mmu_exception, cb.selected_req, cb.selected_va, cb.selected_store,
        cb.selected_valid, cb.selected_ex, cb.scalar_req, cb.scalar_va,
        cb.selected_pa, cb.scalar_pa, cb.scalar_rsp_valid, cb.pre_pmp_valid, cb.pre_pmp_pa,
        cb.pre_pmp_ex, cb.scalar_ex, cb.ctrl_byp, cb.ctrl, cb.pop_ld, cb.pop_st, cb.acc_req, cb.acc_rsp);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_addrgen_probe #(
  parameter config_pkg::cva6_cfg_t C = config_pkg::cva6_cfg_empty,
  parameter int VLEN = 1024,
  parameter int StateWidth = 1, parameter int AxiStateWidth = 1,
  parameter type pe_t = logic, parameter type addr_t = logic,
  parameter type ex_t = logic, parameter type ar_t = logic, parameter type aw_t = logic
) (
  input logic clk_i, rst_ni, enabled, pe_valid, req_valid, req_ready, idle,
  input pe_t pe, held, held_d,
  input addr_t burst_q, burst_d, burst_req,
  input logic [StateWidth-1:0] state_q, state_d,
  input logic [AxiStateWidth-1:0] axi_state_q, axi_state_d,
  input logic pe_accept, axi_start, last_translation, ex_flush_q,
  input logic [ara_pkg::NrVInsn-1:0] running_q, running_d, running_in,
  input logic mmu_req, mmu_store, mmu_hit, mmu_valid,
  input logic [C.VLEN-1:0] va,
  input logic [C.PLEN-1:0] pa,
  input ex_t mmu_ex, out_ex, mmu_ex_q, mmu_ex_d,
  input logic ack, fof, ex_flush, core_store_pending,
  input logic [$clog2(VLEN+1)-1:0] ex_vstart, ex_vstart_d,
  input logic qfull, qempty, qpush, qpop, queue_valid, load_ready, store_ready,
  input ara_pkg::addrgen_axi_req_t queue_in, queue_out,
  input ar_t ar,
  input aw_t aw,
  input logic ar_valid, ar_ready, aw_valid, aw_ready
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("addrgen")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, enabled, pe_valid, req_valid, req_ready, idle, pe, held;
    input burst_q, burst_d, state_q, state_d, axi_state_q, axi_state_d;
    input held_d, burst_req, pe_accept, axi_start, last_translation, ex_flush_q;
    input running_q, running_d, running_in, mmu_ex_q, mmu_ex_d;
    input mmu_req, mmu_store, mmu_hit, mmu_valid, va, pa, mmu_ex, out_ex;
    input ack, fof, ex_flush, core_store_pending, ex_vstart, ex_vstart_d;
    input qfull, qempty, qpush, qpop, queue_valid, load_ready, store_ready;
    input queue_in, queue_out, ar, aw, ar_valid, ar_ready, aw_valid, aw_ready;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      ((cb.idle !== 1'b1) ||
       ({cb.pe_valid, cb.mmu_req, cb.mmu_valid, cb.out_ex.valid, cb.ex_flush,
         cb.ex_flush_q, cb.ack, cb.qpush, cb.qpop, cb.ar_valid, cb.aw_valid} !== '0) ||
       (cb.state_q !== cb.state_d) || (cb.axi_state_q !== cb.axi_state_d));
    row = "";
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"enabled=%b state=%0d next=%0d axi_state=%0d axi_next=%0d idle=%b",
        " pe_valid=%b pe_id=%h pe_op=%0d pe_base=%h pe_vl=%0d pe_vstart=%0d",
        " held_id=%h held_op=%0d held_vl=%0d held_vstart=%0d req_valid=%b req_ready=%b",
        " burst_va=%h bytes=%0d next_va=%h next_bytes=%0d sew=%0d load=%b",
        " mmu_req=%b store=%b va=%h hit=%b valid=%b pa=%h mmu_ex=%h",
        " ack=%b ex_valid=%b cause=%h tval=%h vstart=%0d vstart_d=%0d fof=%b ex_flush=%b core_st=%b",
        " qfull=%b qempty=%b qpush=%b qpop=%b qvalid=%b ld_ready=%b st_ready=%b qin=%h qout=%h",
        " ar_v=%b ar_r=%b ar_addr=%h ar_len=%0d ar_size=%0d aw_v=%b aw_r=%b aw_addr=%h aw_len=%0d aw_size=%0d",
        " pe_accept=%b axi_start=%b held=%h held_d=%h burst_req=%h burst_q=%h burst_d=%h",
        " running_q=%b running_d=%b running_in=%b mmu_ex_q=%h mmu_ex_d=%h last_translation=%b ex_flush_q=%b"},
        cb.enabled, cb.state_q, cb.state_d, cb.axi_state_q, cb.axi_state_d, cb.idle,
        cb.pe_valid, cb.pe.id, cb.pe.op, cb.pe.scalar_op, cb.pe.vl, cb.pe.vstart,
        cb.held.id, cb.held.op, cb.held.vl, cb.held.vstart, cb.req_valid, cb.req_ready,
        cb.burst_q.addr, cb.burst_q.len, cb.burst_d.addr, cb.burst_d.len, cb.burst_q.vew, cb.burst_q.is_load,
        cb.mmu_req, cb.mmu_store, cb.va, cb.mmu_hit, cb.mmu_valid, cb.pa, cb.mmu_ex,
        cb.ack, cb.out_ex.valid, cb.out_ex.cause, cb.out_ex.tval, cb.ex_vstart, cb.ex_vstart_d,
        cb.fof, cb.ex_flush, cb.core_store_pending, cb.qfull, cb.qempty, cb.qpush, cb.qpop,
        cb.queue_valid, cb.load_ready, cb.store_ready, cb.queue_in, cb.queue_out,
        cb.ar_valid, cb.ar_ready, cb.ar.addr, cb.ar.len, cb.ar.size,
        cb.aw_valid, cb.aw_ready, cb.aw.addr, cb.aw.len, cb.aw.size,
        cb.pe_accept, cb.axi_start, cb.held, cb.held_d, cb.burst_req, cb.burst_q, cb.burst_d,
        cb.running_q, cb.running_d, cb.running_in, cb.mmu_ex_q, cb.mmu_ex_d,
        cb.last_translation, cb.ex_flush_q);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_vlsu_probe #(
  parameter int N = 4,
  parameter type req_t = logic, parameter type rsp_t = logic,
  parameter type vid_t = logic, parameter type vaddr_t = logic,
  parameter type data_t = logic, parameter type be_t = logic, parameter type pe_rsp_t = logic
) (
  input logic clk_i, rst_ni,
  input req_t req,
  input rsp_t rsp,
  input logic [N-1:0] vrf_req, vrf_gnt, vrf_final,
  input vid_t [N-1:0] vrf_id,
  input vaddr_t [N-1:0] vrf_addr,
  input data_t [N-1:0] vrf_data,
  input be_t [N-1:0] vrf_be,
  input logic load_complete, store_complete, store_pending, burst_ex, ex_flush, ex_flush_done,
  input logic [1:0] pe_ready,
  input pe_rsp_t [1:0] pe_rsp
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("vlsu")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, req, rsp, vrf_req, vrf_gnt, vrf_final;
    input vrf_id, vrf_addr, vrf_data, vrf_be;
    input load_complete, store_complete, store_pending, burst_ex, ex_flush, ex_flush_done, pe_ready, pe_rsp;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      ({cb.req.ar_valid, cb.req.aw_valid, cb.req.w_valid, cb.rsp.r_valid, cb.rsp.b_valid,
        cb.vrf_req, cb.vrf_final, cb.load_complete, cb.store_complete, cb.store_pending,
        cb.burst_ex, cb.ex_flush, cb.ex_flush_done, cb.pe_rsp} !== '0);
    row = "";
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"ar_v=%b ar_r=%b ar=%h aw_v=%b aw_r=%b aw=%h",
        " w_v=%b w_r=%b w=%h r_v=%b r_r=%b r=%h b_v=%b b_r=%b b=%h",
        " vrf_req=%b vrf_gnt=%b vrf_final=%b vrf_id=%h vrf_addr=%h vrf_data=%h vrf_be=%h",
        " load_complete=%b store_complete=%b store_pending=%b burst_ex=%b ex_flush=%b ex_flush_done=%b",
        " pe_ready=%b pe_rsp=%h ar_fire=%b aw_fire=%b w_fire=%b r_fire=%b b_fire=%b vrf_accept=%b"},
        cb.req.ar_valid, cb.rsp.ar_ready, cb.req.ar, cb.req.aw_valid, cb.rsp.aw_ready, cb.req.aw,
        cb.req.w_valid, cb.rsp.w_ready, cb.req.w, cb.rsp.r_valid, cb.req.r_ready, cb.rsp.r,
        cb.rsp.b_valid, cb.req.b_ready, cb.rsp.b,
        cb.vrf_req, cb.vrf_gnt, cb.vrf_final, cb.vrf_id, cb.vrf_addr, cb.vrf_data, cb.vrf_be,
        cb.load_complete, cb.store_complete, cb.store_pending, cb.burst_ex, cb.ex_flush, cb.ex_flush_done,
        cb.pe_ready, cb.pe_rsp, cb.req.ar_valid && cb.rsp.ar_ready, cb.req.aw_valid && cb.rsp.aw_ready,
        cb.req.w_valid && cb.rsp.w_ready, cb.rsp.r_valid && cb.req.r_ready,
        cb.rsp.b_valid && cb.req.b_ready, cb.vrf_req & cb.vrf_gnt);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_ptw_probe #(
  parameter config_pkg::cva6_cfg_t C = config_pkg::cva6_cfg_empty,
  parameter int StateWidth = 1, parameter int LevelWidth = 1, parameter int StageWidth = 1,
  parameter type dc_req_t = logic, parameter type dc_rsp_t = logic,
  parameter type pte_t = logic, parameter type update_t = logic
) (
  input logic clk_i, rst_ni, flush, enable_i, enable_d, walk, walk_i, error, access_error,
  input logic shared_access, shared_hit, shared_miss, itlb_req, store, mxr,
  input logic [C.PPNW-1:0] root,
  input logic [C.ASID_WIDTH-1:0] asid, asid_q,
  input logic [C.VLEN-1:0] shared_va, va_q, va_d, update_va,
  input logic [C.PLEN-1:0] ptr_q, ptr_d, bad_pa,
  input logic [StateWidth-1:0] state_q, state_d,
  input logic [LevelWidth-1:0] level_q, level_d,
  input logic [StageWidth-1:0] stage_q, stage_d,
  input logic rvalid_q, tag_q, tag_d,
  input logic [C.XLEN-1:0] rdata_q,
  input pte_t pte,
  input update_t update_shared,
  input dc_req_t req,
  input dc_rsp_t rsp
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("ptw")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, flush, enable_i, enable_d, walk, walk_i, error, access_error;
    input shared_access, shared_hit, shared_miss, itlb_req, store, mxr, root, asid, asid_q;
    input shared_va, va_q, va_d, update_va, ptr_q, ptr_d, bad_pa;
    input state_q, state_d, level_q, level_d, stage_q, stage_d;
    input rvalid_q, rdata_q, tag_q, tag_d, pte, update_shared, req, rsp;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    // stage_q is only maintained when RVH is enabled; it must not trigger rows otherwise.
    active = cb.rst_ni === 1'b1 &&
      (({cb.walk, cb.error, cb.access_error, cb.shared_access, cb.shared_miss,
         cb.req.data_req, cb.rsp.data_rvalid, cb.rvalid_q, cb.update_shared.valid} !== '0) ||
       (cb.state_q !== cb.state_d) ||
       (({cb.enable_i, cb.enable_d} !== '0) && (cb.flush !== 1'b0)));
    row = "";
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"en_i=%b en_d=%b root=%h asid=%h asid_q=%h flush=%b walk=%b walk_i=%b",
        " state=%0d next=%0d level_q=%h level_d=%h stage_used=%b stage_q=%h stage_d=%h",
        " shared_access=%b shared_hit=%b shared_miss=%b itlb_req=%b shared_va=%h store=%b mxr=%b",
        " va_q=%h va_d=%h ptr_q=%h ptr_d=%h tag_q=%b tag_d=%b req=%h rsp=%h",
        " cache_req=%b cache_gnt=%b cache_fire=%b cache_rvalid=%b cache_rdata=%h rvalid_q=%b rdata_q=%h pte=%h",
        " update=%h update_va=%h error=%b access_error=%b bad_pa=%h"},
        cb.enable_i, cb.enable_d, cb.root, cb.asid, cb.asid_q, cb.flush, cb.walk, cb.walk_i,
        cb.state_q, cb.state_d, cb.level_q, cb.level_d, C.RVH, cb.stage_q, cb.stage_d,
        cb.shared_access, cb.shared_hit, cb.shared_miss, cb.itlb_req, cb.shared_va, cb.store, cb.mxr,
        cb.va_q, cb.va_d, cb.ptr_q, cb.ptr_d, cb.tag_q, cb.tag_d, cb.req, cb.rsp,
        cb.req.data_req, cb.rsp.data_gnt, cb.req.data_req && cb.rsp.data_gnt,
        cb.rsp.data_rvalid, cb.rsp.data_rdata, cb.rvalid_q, cb.rdata_q, cb.pte,
        cb.update_shared, cb.update_va, cb.error, cb.access_error, cb.bad_pa);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_seq_probe #(
  parameter int N = 4, parameter int P = N + 4, parameter int StateWidth = 1,
  parameter type req_t = logic, parameter type rsp_t = logic,
  parameter type pe_t = logic, parameter type pe_rsp_t = logic,
  parameter type ex_t = logic, parameter type vlen_t = logic
) (
  input logic clk_i, rst_ni, req_valid, req_ready, rsp_valid, idle,
  input req_t req,
  input rsp_t rsp,
  input logic [StateWidth-1:0] state_q, state_d,
  input logic token_q, token_d, token_event, token_stalled,
  input pe_t pe, pe_d,
  input logic pe_valid, pe_valid_d, broadcast_valid,
  input logic [P-1:0] pe_ready,
  input pe_rsp_t [P-1:0] pe_rsp,
  input logic [P-1:0][ara_pkg::NrVInsn-1:0] pe_running_q, pe_running_d,
  input logic [ara_pkg::NrVInsn-1:0] running_q, running_d, running_prev, retired_q,
  input logic [N-1:0] lane_q, lane_d,
  input logic mask_q, mask_d, ack, ack_q, ack_d, fof, fof_q, fof_d, burst_ex, burst_ex_q,
  input ex_t ex, ex_q, ex_d,
  input vlen_t ex_vstart, vstart_q, vstart_d
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("seq")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, req_valid, req_ready, rsp_valid, idle, req, rsp, state_q, state_d;
    input token_q, token_d, token_event, token_stalled, pe, pe_d, pe_valid, pe_valid_d, broadcast_valid;
    input pe_ready, pe_rsp, pe_running_q, pe_running_d, running_q, running_d, running_prev, retired_q;
    input lane_q, lane_d, mask_q, mask_d, ack, ack_q, ack_d, fof, fof_q, fof_d, burst_ex, burst_ex_q;
    input ex, ex_q, ex_d, ex_vstart, vstart_q, vstart_d;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      ((cb.idle !== 1'b1) ||
       ({cb.req_valid, cb.rsp_valid, cb.pe_valid, cb.pe_valid_d, cb.ack, cb.burst_ex,
         cb.burst_ex_q, cb.token_event, cb.retired_q, cb.pe_rsp} !== '0) ||
       (cb.state_q !== cb.state_d) || (cb.lane_q !== cb.lane_d) ||
       (cb.mask_q !== cb.mask_d) || (cb.ack_q !== cb.ack_d));
    row = "";
    // token_event is the DUT's accepted_insn, not req_valid, retirement, or req_valid && ready.
    // lane/mask acceptance latches may be preset for no-source/unmasked ops or forced by
    // burst_ex_q. Observe broadcast/ready/PE payload too; a set latch alone is not a fire.
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"state=%0d next=%0d idle=%b req_valid=%b req_ready=%b req=%h rsp_valid=%b rsp=%h",
        " token_q=%b token_d=%b token_event=%b token_stalled=%b pe_valid=%b pe_valid_d=%b broadcast_valid=%b",
        " pe=%h pe_d=%h pe_ready=%b pe_rsp=%h pe_running_q=%h pe_running_d=%h",
        " running_q=%b running_d=%b running_prev=%b retired_q=%b lane_q=%b lane_d=%b mask_q=%b mask_d=%b",
        " ack=%b ack_q=%b ack_d=%b ex=%h ex_q=%h ex_d=%h vstart=%0d vstart_q=%0d vstart_d=%0d",
        " fof=%b fof_q=%b fof_d=%b burst_ex=%b burst_ex_q=%b",
        " pe_id=%h pe_op=%0d pe_vl=%0d pe_vstart=%0d resp_ex=%h resp_vstart=%0d"},
        cb.state_q, cb.state_d, cb.idle, cb.req_valid, cb.req_ready, cb.req, cb.rsp_valid, cb.rsp,
        cb.token_q, cb.token_d, cb.token_event, cb.token_stalled, cb.pe_valid, cb.pe_valid_d, cb.broadcast_valid,
        cb.pe, cb.pe_d, cb.pe_ready, cb.pe_rsp, cb.pe_running_q, cb.pe_running_d,
        cb.running_q, cb.running_d, cb.running_prev, cb.retired_q, cb.lane_q, cb.lane_d, cb.mask_q, cb.mask_d,
        cb.ack, cb.ack_q, cb.ack_d, cb.ex, cb.ex_q, cb.ex_d, cb.ex_vstart, cb.vstart_q, cb.vstart_d,
        cb.fof, cb.fof_q, cb.fof_d, cb.burst_ex, cb.burst_ex_q,
        cb.pe.id, cb.pe.op, cb.pe.vl, cb.pe.vstart, cb.rsp.exception, cb.rsp.exception_vstart);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

module sv39_dispatcher_probe #(
  parameter int StateWidth = 1, parameter int FlushWidth = 1,
  parameter type acc_req_t = logic, parameter type acc_rsp_t = logic,
  parameter type req_t = logic, parameter type rsp_t = logic,
  parameter type vlen_t = logic, parameter type vtype_t = logic
) (
  input logic clk_i, rst_ni, busy,
  input logic [StateWidth-1:0] state_q, state_d, state_qq,
  input logic [FlushWidth-1:0] flush_q, flush_d,
  input acc_req_t acc_req,
  input acc_rsp_t acc_rsp,
  input req_t req,
  input rsp_t seq_rsp, arch_rsp,
  input logic req_valid, req_ready, seq_rsp_valid, arch_rsp_valid, ara_idle, slide_idle,
  input vlen_t vstart_q, vstart_d, vl_q, vl_d,
  input vtype_t vtype_q, vtype_d,
  input logic flush_start, flush_out, flush_done_in, flush_done_q, flush_done,
  input logic load_complete, store_complete, store_pending
);
  timeunit 1ns;
  timeprecision 1ps;
  longint unsigned epoch = 0;
  cva6_state_prereq_sink #(.Kind("dispatcher")) log_sink();
  always @(negedge rst_ni) if (rst_ni === 1'b0) epoch++;
  clocking cb @(posedge clk_i);
    default input #1step;
    input rst_ni, epoch, busy, state_q, state_d, state_qq, flush_q, flush_d;
    input acc_req, acc_rsp, req, seq_rsp, arch_rsp, req_valid, req_ready;
    input seq_rsp_valid, arch_rsp_valid, ara_idle, slide_idle, vstart_q, vstart_d, vl_q, vl_d, vtype_q, vtype_d;
    input flush_start, flush_out, flush_done_in, flush_done_q, flush_done, load_complete, store_complete, store_pending;
  endclocking
  always @(cb) begin
    bit active;
    string row;
    active = cb.rst_ni === 1'b1 &&
      (({cb.busy, cb.acc_req.req_valid, cb.acc_rsp.resp_valid, cb.req_valid,
         cb.seq_rsp_valid, cb.arch_rsp_valid, cb.flush_start, cb.flush_out,
         cb.flush_done_in, cb.flush_done_q, cb.flush_done, cb.load_complete, cb.store_complete} !== '0) ||
       (cb.state_q !== cb.state_d) || (cb.flush_q !== cb.flush_d) ||
       (cb.vstart_q !== cb.vstart_d) || (cb.vl_q !== cb.vl_d) || (cb.vtype_q !== cb.vtype_d));
    row = "";
    // seq_rsp precedes the segment sequencer; arch_rsp is what updates architectural vstart.
    // The scalar PC/commit/trap identity comes from the separate CVA6 lifecycle/CSR logs.
    if (log_sink.rows < log_sink.row_limit && log_sink.wants_row(active, cb.rst_ni, cb.epoch))
      row = $sformatf({"state=%0d next=%0d state_qq=%0d busy=%b flush_state=%0d flush_next=%0d",
        " acc_req=%h acc_rsp=%h insn=%h acc_valid=%b acc_ready=%b acc_fire=%b",
        " resp_valid=%b resp_ready=%b resp_fire=%b acc_ex=%h",
        " req_valid=%b req_ready=%b req=%h req_token=%b req_op=%0d req_vl=%0d req_vstart=%0d",
        " seq_rsp_valid=%b seq_rsp=%h arch_rsp_valid=%b arch_rsp=%h arch_ex=%h arch_vstart=%0d",
        " vstart_q=%0d vstart_d=%0d vl_q=%0d vl_d=%0d vtype_q=%h vtype_d=%h ara_idle=%b slide_idle=%b",
        " flush_start=%b flush_out=%b flush_done_in=%b flush_done_q=%b flush_done=%b",
        " load_complete=%b store_complete=%b store_pending=%b"},
        cb.state_q, cb.state_d, cb.state_qq, cb.busy, cb.flush_q, cb.flush_d,
        cb.acc_req, cb.acc_rsp, cb.acc_req.insn, cb.acc_req.req_valid, cb.acc_rsp.req_ready,
        cb.acc_req.req_valid && cb.acc_rsp.req_ready, cb.acc_rsp.resp_valid, cb.acc_req.resp_ready,
        cb.acc_rsp.resp_valid && cb.acc_req.resp_ready, cb.acc_rsp.exception,
        cb.req_valid, cb.req_ready, cb.req, cb.req.token, cb.req.op, cb.req.vl, cb.req.vstart,
        cb.seq_rsp_valid, cb.seq_rsp, cb.arch_rsp_valid, cb.arch_rsp, cb.arch_rsp.exception, cb.arch_rsp.exception_vstart,
        cb.vstart_q, cb.vstart_d, cb.vl_q, cb.vl_d, cb.vtype_q, cb.vtype_d, cb.ara_idle, cb.slide_idle,
        cb.flush_start, cb.flush_out, cb.flush_done_in, cb.flush_done_q, cb.flush_done,
        cb.load_complete, cb.store_complete, cb.store_pending);
    log_sink.record(active, cb.rst_ni, cb.epoch, $realtime, row);
  end
endmodule

// CVA6's icache type names are reversed relative to this MMU port direction:
// icache_arsp_t carries fetch_req/fetch_vaddr into the MMU, icache_areq_t the result.
bind cva6_mmu sv39_mmu_probe #(
  .C(CVA6Cfg), .ex_t(exception_t), .ic_req_t(icache_arsp_t), .ic_rsp_t(icache_areq_t),
  .dc_req_t(dcache_req_i_t), .dc_rsp_t(dcache_req_o_t), .pte_t(pte_cva6_t), .update_t(tlb_update_cva6_t)
) i_sv39_mmu_probe (
  .clk_i, .rst_ni, .enable_i(enable_translation_i), .enable_d(en_ld_st_translation_i),
  .flush(flush_i), .flush_tlb(flush_tlb_i), .root(satp_ppn_i), .asid(asid_i),
  .priv(priv_lvl_i), .data_priv(ld_st_priv_lvl_i), .sum(sum_i), .mxr(mxr_i),
  .req(lsu_req_i), .store(lsu_is_store_i), .hit(lsu_dtlb_hit_o), .valid(lsu_valid_o),
  .va(lsu_vaddr_i), .pa(lsu_paddr_o), .ex(lsu_exception_o),
  .req_q(lsu_req_q), .store_q(lsu_is_store_q), .hit_q(dtlb_hit_q), .va_q(lsu_vaddr_q),
  .pte_q(dtlb_pte_q), .page_q(dtlb_is_page_q), .misaligned_q(misaligned_ex_q),
  .shared_access(shared_tlb_access), .shared_hit(shared_tlb_hit), .shared_miss(shared_tlb_miss),
  .itlb_req, .shared_va(shared_tlb_vaddr), .update_va(update_vaddr),
  .sfence_va(vaddr_to_be_flushed_i), .sfence_asid(asid_to_be_flushed_i),
  .ptw_active, .walking_instr, .ptw_error, .ptw_access_exception,
  .itlb_miss(itlb_miss_o), .dtlb_miss(dtlb_miss_o), .daccess_err, .canonical_addr_check,
  .dtlb_content, .update_itlb, .update_dtlb, .update_shared_tlb,
  .if_req(icache_areq_i), .if_rsp(icache_areq_o), .ptw_req(req_port_o), .ptw_rsp(req_port_i)
);

// mmu_state_q/d live in an anonymous generate. Do not invent a genblk path or
// derive authoritative ownership from equal/idle selected addresses. These are
// route witnesses only (owner_observed=0); an owner assertion needs a TB-confirmed
// elaborated hierarchy and a separately reviewed bind, without changing the DUT.
bind load_store_unit sv39_route_probe #(
  .C(CVA6Cfg), .req_t(acc_mmu_req_t), .rsp_t(acc_mmu_resp_t), .ex_t(exception_t), .fu_t(fu_data_t),
  .ctrl_t(lsu_ctrl_t)
) i_sv39_route_probe (
  .clk_i, .rst_ni, .enabled(en_ld_st_translation_i), .scalar_valid(lsu_valid_i),
  .scalar_ready(lsu_ready_o), .flush(flush_i), .scalar_fu(fu_data_i),
  .acc_req(acc_mmu_req_i), .acc_rsp(acc_mmu_resp_o), .selected_req(translation_req),
  .selected_store(st_translation_req), .selected_valid(translation_valid), .scalar_req(cva6_translation_req),
  .selected_va(mmu_vaddr), .scalar_va(cva6_mmu_vaddr), .selected_ex(mmu_exception),
  .selected_pa(mmu_paddr), .scalar_pa(cva6_mmu_paddr), .scalar_rsp_valid(cva6_translation_valid),
  .pre_pmp_valid(pmp_translation_valid), .pre_pmp_pa(lsu_paddr), .pre_pmp_ex(pmp_exception),
  .scalar_ex(cva6_mmu_exception), .ctrl_byp(lsu_ctrl_byp), .ctrl(lsu_ctrl), .pop_ld, .pop_st
);

// addrgen_req_ready means work completed, NOT acceptance of addrgen_req_valid.
// pe_accept and axi_start below reproduce the two RTL FSM admission predicates.
// qpush/qpop are FIFO commands, not proof of a nonempty pop/nonfull push.
// The legacy "sew" column is the encoded log2(byte width), not an element bit count.
bind addrgen sv39_addrgen_probe #(
  .C(CVA6Cfg), .VLEN(VLEN), .pe_t(pe_req_t), .addr_t(addrgen_req_t),
  .ex_t(exception_t), .ar_t(axi_ar_t), .aw_t(axi_aw_t),
  .StateWidth($bits(state_q)), .AxiStateWidth($bits(axi_addrgen_state_q))
) i_sv39_addrgen_probe (
  .clk_i, .rst_ni, .enabled(en_ld_st_translation_i), .pe_valid(pe_req_valid_i),
  .req_valid(addrgen_req_valid), .req_ready(addrgen_req_ready), .idle(idle_o),
  .pe(pe_req_i), .held(pe_req_q), .held_d(pe_req_d),
  .burst_q(axi_addrgen_q), .burst_d(axi_addrgen_d), .burst_req(addrgen_req),
  .state_q, .state_d, .axi_state_q(axi_addrgen_state_q), .axi_state_d(axi_addrgen_state_d),
  .pe_accept((state_q == IDLE) && pe_req_valid_i &&
             (ara_pkg::is_load(pe_req_i.op) || ara_pkg::is_store(pe_req_i.op)) && !vinsn_running_q[pe_req_i.id]),
  .axi_start((axi_addrgen_state_q == AXI_ADDRGEN_IDLE) && addrgen_req_valid),
  .running_q(vinsn_running_q), .running_d(vinsn_running_d), .running_in(pe_vinsn_running_i),
  .mmu_ex_q(mmu_exception_q), .mmu_ex_d(mmu_exception_d),
  .last_translation(last_translation_completed), .ex_flush_q(lsu_ex_flush_q),
  .mmu_req(mmu_req_o), .mmu_store(mmu_is_store_o), .mmu_hit(mmu_dtlb_hit_i), .mmu_valid(mmu_valid_i),
  .va(mmu_vaddr_o), .pa(mmu_paddr_i), .mmu_ex(mmu_exception_i), .out_ex(addrgen_exception_o),
  .ack(addrgen_ack_o), .fof(addrgen_fof_exception_o), .ex_flush(lsu_ex_flush_i), .core_store_pending(core_st_pending_i),
  .ex_vstart(addrgen_exception_vstart_o), .ex_vstart_d(addrgen_exception_vstart_d),
  .qfull(axi_addrgen_queue_full), .qempty(axi_addrgen_queue_empty),
  .qpush(axi_addrgen_queue_push), .qpop(axi_addrgen_queue_pop),
  .queue_valid(axi_addrgen_req_valid_o), .load_ready(ldu_axi_addrgen_req_ready_i), .store_ready(stu_axi_addrgen_req_ready_i),
  .queue_in(axi_addrgen_queue), .queue_out(axi_addrgen_req_o),
  .ar(axi_ar_o), .aw(axi_aw_o), .ar_valid(axi_ar_valid_o), .ar_ready(axi_ar_ready_i),
  .aw_valid(axi_aw_valid_o), .aw_ready(axi_aw_ready_i)
);

bind vlsu sv39_vlsu_probe #(
  .N(NrLanes), .req_t(axi_req_t), .rsp_t(axi_resp_t), .vid_t(vid_t), .vaddr_t(vaddr_t),
  .data_t(elen_t), .be_t(strb_t), .pe_rsp_t(pe_resp_t)
) i_sv39_vlsu_probe (
  .clk_i, .rst_ni, .req(axi_req_o), .rsp(axi_resp_i),
  .vrf_req(ldu_result_req_o), .vrf_gnt(ldu_result_gnt_i), .vrf_final(ldu_result_final_gnt_i),
  .vrf_id(ldu_result_id_o), .vrf_addr(ldu_result_addr_o), .vrf_data(ldu_result_wdata_o), .vrf_be(ldu_result_be_o),
  .load_complete(load_complete_o), .store_complete(store_complete_o), .store_pending(store_pending_o),
  .burst_ex(lsu_current_burst_exception_o), .ex_flush(lsu_ex_flush_i), .ex_flush_done(lsu_ex_flush_done_o),
  .pe_ready(pe_req_ready_o), .pe_rsp(pe_resp_o)
);

bind cva6_ptw sv39_ptw_probe #(
  .C(CVA6Cfg), .StateWidth($bits(state_q)), .LevelWidth($bits(ptw_lvl_q)), .StageWidth($bits(ptw_stage_q)),
  .dc_req_t(dcache_req_i_t), .dc_rsp_t(dcache_req_o_t), .pte_t(pte_cva6_t), .update_t(tlb_update_cva6_t)
) i_sv39_ptw_probe (
  .clk_i, .rst_ni, .flush(flush_i), .enable_i(enable_translation_i), .enable_d(en_ld_st_translation_i),
  .walk(ptw_active_o), .walk_i(walking_instr_o), .error(ptw_error_o), .access_error(ptw_access_exception_o),
  .shared_access(shared_tlb_access_i), .shared_hit(shared_tlb_hit_i), .shared_miss(shared_tlb_miss_o),
  .itlb_req(itlb_req_i), .store(lsu_is_store_i), .mxr(mxr_i), .root(satp_ppn_i),
  .asid(asid_i), .asid_q(tlb_update_asid_q), .shared_va(shared_tlb_vaddr_i),
  .va_q(vaddr_q), .va_d(vaddr_n), .update_va(update_vaddr_o),
  .ptr_q(ptw_pptr_q), .ptr_d(ptw_pptr_n), .bad_pa(bad_paddr_o),
  .state_q, .state_d, .level_q(ptw_lvl_q), .level_d(ptw_lvl_n), .stage_q(ptw_stage_q), .stage_d(ptw_stage_d),
  .rvalid_q(data_rvalid_q), .rdata_q(data_rdata_q), .tag_q(tag_valid_q), .tag_d(tag_valid_n),
  .pte, .update_shared(shared_tlb_update_o), .req(req_port_o), .rsp(req_port_i)
);

bind ara_sequencer sv39_seq_probe #(
  .N(NrLanes), .P(NrPEs), .StateWidth($bits(state_q)), .req_t(ara_req_t), .rsp_t(ara_resp_t),
  .pe_t(pe_req_t), .pe_rsp_t(pe_resp_t), .ex_t(exception_t), .vlen_t(vlen_t)
) i_sv39_seq_probe (
  .clk_i, .rst_ni, .req_valid(ara_req_valid_i), .req_ready(ara_req_ready_o),
  .rsp_valid(ara_resp_valid_o), .idle(ara_idle_o), .req(ara_req_i), .rsp(ara_resp_o), .state_q, .state_d,
  .token_q(ara_req_token_q), .token_d(ara_req_token_d),
  .token_event(accepted_insn), .token_stalled(accepted_insn_stalled),
  .pe(pe_req_o), .pe_d(pe_req_d), .pe_valid(pe_req_valid_o), .pe_valid_d(pe_req_valid_d),
  .broadcast_valid(pe_req_broadcast_valid), .pe_ready(pe_req_ready_i), .pe_rsp(pe_resp_i),
  .pe_running_q(pe_vinsn_running_q), .pe_running_d(pe_vinsn_running_d),
  .running_q(vinsn_running_q), .running_d(vinsn_running_d),
  .running_prev(vinsn_running_prev_q), .retired_q(vinsn_retired_q),
  .lane_q(memory_lane_accepted_q), .lane_d(memory_lane_accepted_d),
  .mask_q(memory_mask_accepted_q), .mask_d(memory_mask_accepted_d),
  .ack(addrgen_ack_i), .ack_q(addrgen_acked_q), .ack_d(addrgen_acked_d),
  .ex(addrgen_exception_i), .ex_q(addrgen_exception_q), .ex_d(addrgen_exception_d),
  .ex_vstart(addrgen_exception_vstart_i), .vstart_q(addrgen_exception_vstart_q), .vstart_d(addrgen_exception_vstart_d),
  .fof(addrgen_fof_exception_i), .fof_q(addrgen_fof_exception_q), .fof_d(addrgen_fof_exception_d),
  .burst_ex(lsu_current_burst_exception_i), .burst_ex_q(lsu_current_burst_exception_q)
);

bind ara_dispatcher sv39_dispatcher_probe #(
  .StateWidth($bits(state_q)), .FlushWidth($bits(lsu_ex_state_q)),
  .acc_req_t(accelerator_req_t), .acc_rsp_t(accelerator_resp_t), .req_t(ara_req_t), .rsp_t(ara_resp_t),
  .vlen_t(vlen_t), .vtype_t(rvv_pkg::vtype_t)
) i_sv39_dispatcher_probe (
  .clk_i, .rst_ni, .busy((state_q != NORMAL_OPERATION) || (lsu_ex_state_q != LSU_FLUSH_IDLE)),
  .state_q, .state_d, .state_qq, .flush_q(lsu_ex_state_q), .flush_d(lsu_ex_state_d),
  .acc_req(acc_req_i), .acc_rsp(acc_resp_o), .req(ara_req_o), .req_valid(ara_req_valid_o), .req_ready(ara_req_ready_i),
  .seq_rsp(ara_resp_i), .seq_rsp_valid(ara_resp_valid_i), .arch_rsp(ara_resp), .arch_rsp_valid(ara_resp_valid),
  .ara_idle(ara_idle_i), .slide_idle(sldu_idle_i), .vstart_q(csr_vstart_q), .vstart_d(csr_vstart_d),
  .vl_q(csr_vl_q), .vl_d(csr_vl_d), .vtype_q(csr_vtype_q), .vtype_d(csr_vtype_d),
  .flush_start(lsu_ex_flush_start), .flush_out(lsu_ex_flush_o), .flush_done_in(lsu_ex_flush_done_i),
  .flush_done_q(lsu_ex_flush_done_q), .flush_done(lsu_ex_flush_done),
  .load_complete(load_complete_i), .store_complete(store_complete_i), .store_pending(store_pending_i)
);
`endif
