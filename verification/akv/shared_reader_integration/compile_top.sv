// Elaboration-only top: complete VLSU, no CPU, RAM system, firmware or stimulus.
module shared_reader_integration_compile_top;
  import ara_pkg::*;
  localparam int NrLanes = 4;
  localparam int VLEN = 1024;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [$clog2(VLEN/8/NrLanes*32)-1:0] vaddr_t;
  localparam config_pkg::cva6_cfg_t CVA6Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  `include "ara/ara_typedef.svh"
  `include "ara/intf_typedef.svh"
  `include "axi/typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)
  typedef logic [63:0] axi_addr_t;
  typedef logic [127:0] axi_data_t;
  typedef logic [15:0] axi_strb_t;
  typedef logic [1:0] axi_id_t;
  typedef logic [0:0] axi_user_t;
  `AXI_TYPEDEF_ALL(axi, axi_addr_t, axi_id_t, axi_data_t, axi_strb_t, axi_user_t)

  // Variable inputs and full debug elaboration keep the actual engines visible.
  logic clk, rst_n;
  pe_req_t request;
  axi_resp_t response;
  exception_t mmu_exception;
  axi_req_t bus_request;
  vlsu #(
    .NrLanes(NrLanes), .VLEN(VLEN), .vaddr_t(vaddr_t),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .CVA6Cfg(CVA6Cfg),
    .exception_t(exception_t), .AxiDataWidth(128), .AxiAddrWidth(64),
    .axi_ar_t(axi_ar_chan_t), .axi_r_t(axi_r_chan_t),
    .axi_aw_t(axi_aw_chan_t), .axi_w_t(axi_w_chan_t), .axi_b_t(axi_b_chan_t),
    .axi_req_t(axi_req_t), .axi_resp_t(axi_resp_t)
  ) dut (
    .clk_i(clk), .rst_ni(rst_n), .axi_req_o(bus_request), .axi_resp_i(response),
    .core_st_pending_i(1'b0), .load_prepare_valid_i(1'b0), .load_prepare_addr_i('0),
    .load_prepare_safe_i(1'b0), .load_prepare_flush_i(1'b0),
    .pe_req_i(request), .pe_req_valid_i(1'b0), .pe_vinsn_running_i('0),
    .stu_operand_i('0), .stu_operand_valid_i('0),
    .addrgen_operand_i('0), .addrgen_operand_valid_i('0), .lsu_ex_flush_i(1'b0),
    .mask_i('0), .mask_valid_i('0), .mask_target_fu_i(VFU_LoadUnit),
    .mask_owner_id_i('0), .mask_first_element_i('0),
    .en_ld_st_translation_i(1'b0), .mmu_dtlb_hit_i(1'b0), .mmu_dtlb_ppn_i('0),
    .mmu_valid_i(1'b0), .mmu_paddr_i('0), .mmu_exception_i(mmu_exception),
    .ldu_result_gnt_i('0), .ldu_result_final_gnt_i('0)
  );
endmodule
