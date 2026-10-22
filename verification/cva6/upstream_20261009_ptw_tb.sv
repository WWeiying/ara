`timescale 1ns/1ps
module upstream_20261009_ptw_tb;
  `include "upstream_20261009_common.svh"
  logic access = 0, instr = 0, store = 0;
  logic active, error, access_error, walking;
  logic [63:0] va = 64'h12345088;
  logic [CVA6Cfg.VLEN-1:0] update_va;
  dcache_req_i_t req;
  dcache_req_o_t resp;
  refill_t update;
  cva6_ptw #(.CVA6Cfg(CVA6Cfg), .HYP_EXT(0), .pte_cva6_t(refill_pte_t),
    .tlb_update_cva6_t(refill_t), .dcache_req_i_t(dcache_req_i_t),
    .dcache_req_o_t(dcache_req_o_t)) dut (
    .clk_i(clk), .rst_ni(rst_n), .flush_i(1'b0), .ptw_active_o(active),
    .walking_instr_o(walking), .ptw_error_o(error), .ptw_error_at_g_st_o(),
    .ptw_err_at_g_int_st_o(), .ptw_access_exception_o(access_error),
    .enable_translation_i(1'b1), .enable_g_translation_i(1'b0),
    .en_ld_st_translation_i(1'b1), .en_ld_st_g_translation_i(1'b0),
    .v_i(1'b0), .ld_st_v_i(1'b0), .hlvx_inst_i(1'b0), .lsu_is_store_i(store),
    .req_port_i(resp), .req_port_o(req), .shared_tlb_update_o(update),
    .update_vaddr_o(update_va), .asid_i(16'h5), .vs_asid_i('0), .vmid_i('0),
    .shared_tlb_access_i(access), .shared_tlb_hit_i(1'b0), .shared_tlb_vaddr_i(va),
    .itlb_req_i(instr), .satp_ppn_i(44'h100), .vsatp_ppn_i('0), .hgatp_ppn_i('0),
    .mxr_i(1'b0), .vmxr_i(1'b0), .shared_tlb_miss_o(),
    .pmpcfg_i('0), .pmpaddr_i('0), .bad_paddr_o(), .bad_gpaddr_o());
  initial begin
    int rc, kind, bad_level, bad_bits, leaf_level, leaf_fault, latency;
    int cycles, pending, requests, updates, errors, pmp_errors, address_errors;
    int level, drain, seen_walking;
    logic [63:0] address, expected_addr, queued_pte, final_ppn, final_va, final_asid, final_page;
    refill_pte_t pte;
    open_files(); resp = '0;
    while (!$feof(input_file)) begin
      rc = $fscanf(input_file, "%d %d %d %d %d %d %d\n",
        id, kind, bad_level, bad_bits, leaf_level, leaf_fault, latency);
      if (rc != 7 || id != completed) $fatal(1, "Bad PTW case");
      access = 0; resp = '0; reset_dut();
      instr = kind == 0; store = kind == 2;
      requests = 0; updates = 0; errors = 0; pmp_errors = 0; address_errors = 0;
      seen_walking = 0; final_ppn = 0; final_va = 0; final_asid = 0; final_page = 0;
      pending = -1; drain = -1; queued_pte = 0;
      access = 1; @(posedge clk); #1;
      for (cycles = 0; cycles < 200; cycles++) begin
        @(negedge clk); access = 0; resp = '0;
        if (pending >= 0) begin
          if (pending == 0) begin
            resp.data_rvalid = 1; resp.data_rdata = queued_pte; pending = -1;
          end else pending--;
        end
        if (req.data_req && pending == -1 && !resp.data_rvalid && drain < 0) begin
          resp.data_gnt = 1;
          address = {req.address_tag, req.address_index};
          level = requests;
          if (level > 2) $fatal(1, "Unexpected fourth page-table read");
          expected_addr = 64'h100000 + 4096 * level +
                          8 * ((va >> (12 + 9 * (2-level))) & 511);
          if (address !== expected_addr) address_errors++;
          pte = '0; pte.v = 1;
          if (level == leaf_level) begin
            pte.ppn = 44'h80000; pte.r = 1; pte.w = 1; pte.x = 1; pte.a = 1; pte.d = 1;
            case (leaf_fault)
              1: pte.a = 0;
              2: pte.d = 0;
              3: begin pte.r = 0; pte.x = 0; end
              4: pte.v = 0;
              5: pte.ppn = 44'h80001;
              default: ;
            endcase
          end else begin
            pte.ppn = CVA6Cfg.PPNW'(64'h101 + level);
            if (level == bad_level) begin
              pte.a = (bad_bits & 1) != 0;
              pte.d = (bad_bits & 2) != 0;
              pte.u = (bad_bits & 4) != 0;
            end
          end
          queued_pte = 64'(pte); pending = latency; requests++;
        end
        #1;
        if (active && walking) seen_walking = 1;
        if (update.valid) begin
          updates++; final_ppn = update.content.ppn; final_va = update_va;
          final_asid = update.asid; final_page = update.is_page;
        end
        if (error) errors++;
        if (access_error) pmp_errors++;
        if (drain < 0 && (update.valid || error || access_error)) drain = 6;
        else if (drain > 0) drain--;
        @(posedge clk); #1;
        if (drain == 0) break;
      end
      observe("terminal", drain == 0);
      observe("requests", requests); observe("updates", updates);
      observe("faults", errors); observe("pmp_faults", pmp_errors);
      observe("address_errors", address_errors); observe("walking_instr", seen_walking);
      observe("update_ppn", final_ppn); observe("update_va", final_va);
      observe("update_asid", final_asid); observe("update_page", final_page);
      observe("idle", !active);
      @(negedge clk); resp = '0;
      completed++;
    end
    finish_test();
  end
endmodule
