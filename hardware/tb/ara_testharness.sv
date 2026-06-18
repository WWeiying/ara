// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description: Test harness for Ara.
//              This is loosely based on CVA6's test harness.
//              Instantiates an AXI-Bus and memories.

module ara_testharness #(
    // Ara-specific parameters
    parameter int unsigned NrLanes      = 0,
    parameter int unsigned VLEN         = 0,
    // AXI Parameters
    parameter int unsigned AxiUserWidth = 1,
    parameter int unsigned AxiIdWidth   = 5,
    parameter int unsigned AxiAddrWidth = 64,
    parameter int unsigned AxiDataWidth = 64*NrLanes/2,
    parameter int unsigned HdvNumSlots  = 8,
    parameter logic [63:0] HdvInitialRa  = '0,
    parameter logic [63:0] HdvInitialA0  = '0,
    parameter logic [63:0] HdvInitialA1  = '0,
    parameter logic [63:0] HdvInitialA2  = '0,
    parameter logic [63:0] HdvInitialA3  = '0,
    parameter logic [63:0] HdvInitialFa0 = '0,
    // AXI Resp Delay [ps] for gate-level simulation
    parameter int unsigned AxiRespDelay = 200
  ) (
    input  logic        clk_i,
    input  logic        rst_ni,
    output logic [63:0] exit_o,
    input  logic                         hdv_host_csr_valid_i = 1'b0,
    input  logic                         hdv_host_csr_write_i = 1'b0,
    input  logic [11:0]                  hdv_host_csr_addr_i = '0,
    input  logic [63:0]                  hdv_host_csr_wdata_i = '0,
    output logic                         hdv_host_csr_ready_o,
    output logic [63:0]                  hdv_host_csr_rdata_o,
    output logic                         hdv_host_csr_error_o,
    input  logic                         hdv_redirect_valid_i = 1'b0,
    input  logic [63:0]                  hdv_redirect_pc_i = '0,
    input  logic                         hdv_loop_lock_i = 1'b0,
    input  logic [HdvNumSlots-2:0]       hdv_dep_break_i = '0,
    output logic [63:0]                  hdv_active_task_desc_o,
    output logic                         hdv_task_busy_o,
    output logic                         hdv_task_done_o,
    output logic                         hdv_task_error_o,
    input  logic                         hdv_task_complete_i = 1'b0,
    input  logic                         hdv_task_error_i = 1'b0,
    output logic                         hdv_scalar_valid_o,
    input  logic                         hdv_scalar_ready_i = 1'b1,
    output logic [HdvNumSlots-1:0]       hdv_scalar_insn_valid_o,
    output logic [HdvNumSlots-1:0][31:0] hdv_scalar_insn_o,
    output logic [HdvNumSlots-1:0]       hdv_scalar_insn_is_32b_o,
    output logic [HdvNumSlots-1:0][63:0] hdv_scalar_insn_pc_o,
    output logic [63:0]                  hdv_scalar_pc_o,
    input  logic                         hdv_scalar_accepted_i = 1'b0,
    // Vector dispatch is now internal (HEU → hdv_vec_dispatch_unit → Ara)
    input  logic                         hdv_backend_error_i = 1'b0,
    output logic                         hdv_ep_busy_o,
    output logic                         hdv_ep_accepted_o,
    output logic                         hdv_ep_error_o
  );

  `include "axi/typedef.svh"

  /*****************
   *  Definitions  *
   *****************/

  typedef logic [AxiDataWidth-1:0] axi_data_t;
  typedef logic [AxiDataWidth/8-1:0] axi_strb_t;
  typedef logic [AxiAddrWidth-1:0] axi_addr_t;
  typedef logic [AxiUserWidth-1:0] axi_user_t;
  typedef logic [AxiIdWidth-1:0] axi_id_t;

  `AXI_TYPEDEF_AR_CHAN_T(ar_chan_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_chan_t, axi_data_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_AW_CHAN_T(aw_chan_t, axi_addr_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_W_CHAN_T(w_chan_t, axi_data_t, axi_strb_t, axi_user_t)
  `AXI_TYPEDEF_B_CHAN_T(b_chan_t, axi_id_t, axi_user_t)
  `AXI_TYPEDEF_REQ_T(axi_req_t, aw_chan_t, w_chan_t, ar_chan_t)
  `AXI_TYPEDEF_RESP_T(axi_resp_t, b_chan_t, r_chan_t)

  /*************
   *  Signals  *
   *************/

  // UART
  logic        uart_penable;
  logic        uart_pwrite;
  logic [31:0] uart_paddr;
  logic        uart_psel;
  logic [31:0] uart_pwdata;
  logic [31:0] uart_prdata;
  logic        uart_pready;
  logic        uart_pslverr;

  // AXI
  axi_req_t  dram_req;
  axi_resp_t dram_resp;

  /*********
   *  SoC  *
   *********/

  ara_soc #(
    .NrLanes     (NrLanes      ),
    .VLEN        (VLEN         ),
    .AxiAddrWidth(AxiAddrWidth ),
    .AxiDataWidth(AxiDataWidth ),
    .AxiIdWidth  (AxiIdWidth   ),
    .AxiUserWidth(AxiUserWidth ),
    .HdvNumSlots (HdvNumSlots  ),
    .HdvInitialRa(HdvInitialRa  ),
    .HdvInitialA0(HdvInitialA0  ),
    .HdvInitialA1(HdvInitialA1  ),
    .HdvInitialA2(HdvInitialA2  ),
    .HdvInitialA3(HdvInitialA3  ),
    .HdvInitialFa0(HdvInitialFa0),
    .AxiRespDelay(AxiRespDelay )
  ) i_ara_soc (
    .clk_i         (clk_i       ),
    .rst_ni        (rst_ni      ),
    .hw_cnt_en_o   (/* Unused */),
    .exit_o        (exit_o      ),
    .scan_enable_i (1'b0        ),
    .scan_data_i   (1'b0        ),
    .scan_data_o   (/* Unused */),
    // UART
    .uart_penable_o(uart_penable),
    .uart_pwrite_o (uart_pwrite ),
    .uart_paddr_o  (uart_paddr  ),
    .uart_psel_o   (uart_psel   ),
    .uart_pwdata_o (uart_pwdata ),
    .uart_prdata_i (uart_prdata ),
    .uart_pready_i (uart_pready ),
    .uart_pslverr_i(uart_pslverr),
    .hdv_host_csr_valid_i(hdv_host_csr_valid_i),
    .hdv_host_csr_write_i(hdv_host_csr_write_i),
    .hdv_host_csr_addr_i (hdv_host_csr_addr_i ),
    .hdv_host_csr_wdata_i(hdv_host_csr_wdata_i),
    .hdv_host_csr_ready_o(hdv_host_csr_ready_o),
    .hdv_host_csr_rdata_o(hdv_host_csr_rdata_o),
    .hdv_host_csr_error_o(hdv_host_csr_error_o),
    .hdv_redirect_valid_i(hdv_redirect_valid_i),
    .hdv_redirect_pc_i   (hdv_redirect_pc_i   ),
    .hdv_loop_lock_i     (hdv_loop_lock_i     ),
    .hdv_dep_break_i     (hdv_dep_break_i     ),
    .hdv_active_task_desc_o(hdv_active_task_desc_o),
    .hdv_task_busy_o     (hdv_task_busy_o     ),
    .hdv_task_done_o     (hdv_task_done_o     ),
    .hdv_task_error_o    (hdv_task_error_o    ),
    .hdv_task_complete_i (hdv_task_complete_i ),
    .hdv_task_error_i    (hdv_task_error_i    ),
    .hdv_scalar_valid_o  (hdv_scalar_valid_o  ),
    .hdv_scalar_ready_i  (hdv_scalar_ready_i  ),
    .hdv_scalar_insn_valid_o(hdv_scalar_insn_valid_o),
    .hdv_scalar_insn_o   (hdv_scalar_insn_o   ),
    .hdv_scalar_insn_is_32b_o(hdv_scalar_insn_is_32b_o),
    .hdv_scalar_insn_pc_o(hdv_scalar_insn_pc_o),
    .hdv_scalar_pc_o     (hdv_scalar_pc_o     ),
    .hdv_scalar_accepted_i   (hdv_scalar_accepted_i   ),
    // Vector dispatch ports removed — now internal to hdv_top via hdv_vec_dispatch_unit
    .hdv_backend_error_i (hdv_backend_error_i ),
    .hdv_ep_busy_o  (hdv_ep_busy_o  ),
    .hdv_ep_accepted_o  (hdv_ep_accepted_o  ),
    .hdv_ep_error_o (hdv_ep_error_o )
  );

  /**********
   *  UART  *
   **********/

  mock_uart i_mock_uart (
    .clk_i    (clk_i       ),
    .rst_ni   (rst_ni      ),
    .penable_i(uart_penable),
    .pwrite_i (uart_pwrite ),
    .paddr_i  (uart_paddr  ),
    .psel_i   (uart_psel   ),
    .pwdata_i (uart_pwdata ),
    .prdata_o (uart_prdata ),
    .pready_o (uart_pready ),
    .pslverr_o(uart_pslverr)
  );

`ifndef TARGET_GATESIM

  /***************
   *  V_RUNTIME  *
   ***************/

  // Software runtime measurements are not precise since there is some overhead when the vector
  // function starts and when it's over. Moreover, the csr value should be retreived.
  // When the vector function runtime is short, these overhead can compromise the measurement.
  // This is a way to measure the runtime more precisely.
  //
  // The vector runtime counter starts counting up as soon as the first vector instruction is
  // dispatched to Ara. Then, it will count up forever. When there are no more vector instructions
  // dispatched AND Ara is idle again, the csr runtime is updated.
  // If a new vector instruction is dispathced, the runtime will be updated once again as soon as
  // the previous updating conditions applies again.
  //
  // The counter has now a SW enable. This enable allows the hw-counter to start counting when
  // the start conditions happen.
  //
  // This leads to accurate measurements IF:
  //   1) Every program run contains only a single benchmark to be measured
  //   2) The SW reads the runtime value when Ara is idle and all the vector instructions are over!
  // The last point implies that the function should fence() to let all the vector stores finish,
  // and also depend on the scalar returned value if the last vector instruction is of this type.

  logic [63:0] runtime_cnt_d, runtime_cnt_q;
  logic [63:0] runtime_buf_d, runtime_buf_q;
  logic runtime_cnt_en_d, runtime_cnt_en_q;
  logic	runtime_to_be_updated_d, runtime_to_be_updated_q;

  // The counter can start only if it's enabled. When it's disabled, it will go on counting until
  // the last vector instruciton is over.
  logic cnt_en_mask;
`ifndef IDEAL_DISPATCHER
  assign cnt_en_mask = i_ara_soc.hw_cnt_en_o[0];
`else
  assign cnt_en_mask = 1'b1;
`endif
  always_comb begin
    // Keep the previous value
    runtime_cnt_en_d = runtime_cnt_en_q;
    // If disabled
    if (!runtime_cnt_en_q)
      // Start only if the software allowed the enable and we detect the first V instruction
    `ifndef SAIF
      runtime_cnt_en_d = i_ara_soc.i_system.i_ara.acc_req_i.acc_req.req_valid & cnt_en_mask;
    `else
      runtime_cnt_en_d = i_ara_soc.i_system.i_ara.acc_req_i[476] & cnt_en_mask;
    `endif
    // If enabled
    if (runtime_cnt_en_q)
      // Stop counting only if the software disabled the counter and Ara returned idle
      runtime_cnt_en_d = cnt_en_mask | ~i_ara_soc.i_system.i_ara.ara_idle;
  end

  // Vector runtime counter
  always_comb begin
    runtime_cnt_d = runtime_cnt_q;
    if (runtime_cnt_en_q) runtime_cnt_d = runtime_cnt_q + 1;
  end

  // Update logic
  always_comb begin
    // The following lines allows for SW management of the runtime.
    // Disabled since Verilator is not compatible with the `force` statement
    //// Force the internal runtime CSR to the most updated runtime value
    //force i_ara_soc.i_ctrl_registers.i_axi_lite_regs.reg_q[31:24] = runtime_buf_q;

    // Keep the previous value
    runtime_to_be_updated_d = runtime_to_be_updated_q;

    // Assert the update flag upon a new valid vector instruction
    `ifndef SAIF
    if (!runtime_to_be_updated_q && i_ara_soc.i_system.i_ara.acc_req_i.acc_req.req_valid) begin
    `else
    if (!runtime_to_be_updated_q && i_ara_soc.i_system.i_ara.acc_req_i[476]) begin
    `endif
      runtime_to_be_updated_d = 1'b1;
    end

    // Update the internal runtime and reset the update flag
    `ifndef SAIF
    if (runtime_to_be_updated_q           &&
        i_ara_soc.i_system.i_ara.ara_idle &&
        !i_ara_soc.i_system.i_ara.acc_req_i.acc_req.req_valid) begin
    `else
    if (runtime_to_be_updated_q           &&
        i_ara_soc.i_system.i_ara.ara_idle &&
        !i_ara_soc.i_system.i_ara.acc_req_i[476]) begin
    `endif
      runtime_buf_d = runtime_cnt_q;
      runtime_to_be_updated_d = 1'b0;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      runtime_cnt_en_q        <= 1'b0;
      runtime_cnt_q           <= '0;
      runtime_to_be_updated_q <= '0;
      runtime_buf_q           <= '0;
   end else begin
      runtime_cnt_en_q        <= runtime_cnt_en_d;
      runtime_cnt_q           <= runtime_cnt_d;
      runtime_to_be_updated_q <= runtime_to_be_updated_d;
      runtime_buf_q           <= runtime_buf_d;
    end
  end

`ifndef IDEAL_DISPATCHER

  /*******************
   *  CVA6 PERF CNT  *
   *******************/

  // Count the number of I$/D$ stalls, and if the scoreboard is
  // full during the V runtime.
  // i_ara_soc.i_system.i_ariane.i_perf_counters.l1_dcache_miss_i
  // i_ara_soc.i_system.i_ariane.i_perf_counters.l1_icache_miss_i
  // i_ara_soc.i_system.i_ariane.i_perf_counters.sb_full_i

  logic [63:0] dcache_stall_cnt_d, dcache_stall_cnt_q;
  logic [63:0] icache_stall_cnt_d, icache_stall_cnt_q;
  logic [63:0] sb_full_cnt_d, sb_full_cnt_q;
  logic [63:0] dcache_stall_buf_d, dcache_stall_buf_q;
  logic [63:0] icache_stall_buf_d, icache_stall_buf_q;
  logic [63:0] sb_full_buf_d, sb_full_buf_q;

  always_comb begin
    dcache_stall_cnt_d = dcache_stall_cnt_q;
    icache_stall_cnt_d = icache_stall_cnt_q;
    sb_full_cnt_d      = sb_full_cnt_q;
`ifdef TARGET_GATESIM
    // GATESIM mode: CVA6 present, track cache/scoreboard stalls
    `ifndef SAIF
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter.perf_counters_i.l1_dcache_miss_i)
      dcache_stall_cnt_d += 1;
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter.perf_counters_i.l1_icache_miss_i)
      icache_stall_cnt_d += 1;
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter.perf_counters_i.sb_full_i)
      sb_full_cnt_d      += 1;
    `else
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter_perf_counters_i.l1_dcache_miss_i)
      dcache_stall_cnt_d += 1;
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter_perf_counters_i.l1_icache_miss_i)
      icache_stall_cnt_d += 1;
    if (runtime_cnt_en_q && i_ara_soc.i_system.i_ariane.gen_perf_counter_perf_counters_i.sb_full_i)
      sb_full_cnt_d      += 1;
    `endif
`endif
    // HDV RTL mode: no CVA6, cache stall counters not available
  end

  // Update logic
  always_comb begin
    // Update the internal runtime and reset the update flag
    `ifndef SAIF
    if (runtime_to_be_updated_q           &&
        i_ara_soc.i_system.i_ara.ara_idle &&
        !i_ara_soc.i_system.i_ara.acc_req_i.acc_req.req_valid) begin
    `else
    if (runtime_to_be_updated_q           &&
        i_ara_soc.i_system.i_ara.ara_idle &&
        !i_ara_soc.i_system.i_ara.acc_req_i[476]) begin
    `endif
      dcache_stall_buf_d = dcache_stall_cnt_q;
      icache_stall_buf_d = icache_stall_cnt_q;
      sb_full_buf_d      = sb_full_cnt_q;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      dcache_stall_cnt_q <= '0;
      icache_stall_cnt_q <= '0;
      sb_full_cnt_q      <= '0;
      dcache_stall_buf_q <= '0;
      icache_stall_buf_q <= '0;
      sb_full_buf_q      <= '0;
    end else begin
      dcache_stall_cnt_q <= dcache_stall_cnt_d;
      icache_stall_cnt_q <= icache_stall_cnt_d;
      sb_full_cnt_q      <= sb_full_cnt_d;
      dcache_stall_buf_q <= dcache_stall_buf_d;
      icache_stall_buf_q <= icache_stall_buf_d;
      sb_full_buf_q      <= sb_full_buf_d;
    end
  end // always_ff @ (posedge clk_i or negedge rst_ni)

`else

  logic [63:0] dcache_stall_buf_q;
  logic [63:0] icache_stall_buf_q;
  logic [63:0] sb_full_buf_q;

  assign dcache_stall_buf_q = '0;
  assign icache_stall_buf_q = '0;
  assign sb_full_buf_q      = '0;

`endif


`endif
endmodule : ara_testharness
