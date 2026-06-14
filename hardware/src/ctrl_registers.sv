// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description: AXI-LITE accessible control registers, holding
// static information about Ara's SoC.

module ctrl_registers #(
    parameter int   unsigned                 DataWidth       = 32,
    parameter int   unsigned                 AddrWidth       = 32,
    // Parameters
    parameter logic          [DataWidth-1:0] DRAMBaseAddr    = 0,
    parameter logic          [DataWidth-1:0] DRAMLength      = 0,
    // AXI Structs
    parameter type                           axi_lite_req_t  = logic,
    parameter type                           axi_lite_resp_t = logic
  ) (
    input  logic                           clk_i,
    input  logic                           rst_ni,
    // AXI Bus
    input  axi_lite_req_t                  axi_lite_slave_req_i,
    output axi_lite_resp_t                 axi_lite_slave_resp_o,
    // Control registers
    output logic           [DataWidth-1:0] exit_o,
    output logic           [DataWidth-1:0] dram_base_addr_o,
    output logic           [DataWidth-1:0] dram_end_addr_o,
    output logic           [DataWidth-1:0] event_trigger_o,
    output logic           [DataWidth-1:0] hw_cnt_en_o,
    // HDV task CSR bridge.  These CSRs are exposed after the legacy Ara
    // control registers in the same AXI-Lite window.
    output logic                           hdv_csr_valid_o,
    output logic                           hdv_csr_write_o,
    output logic                  [11:0]   hdv_csr_addr_o,
    output logic           [DataWidth-1:0] hdv_csr_wdata_o,
    input  logic                           hdv_csr_ready_i,
    input  logic           [DataWidth-1:0] hdv_csr_rdata_i,
    input  logic                           hdv_csr_error_i,
    input  logic                           hdv_task_busy_i,
    input  logic                           hdv_task_done_i,
    input  logic                           hdv_task_error_i
  );

  `include "common_cells/registers.svh"

  ///////////////////
  //  Definitions  //
  ///////////////////

  localparam int unsigned NumRegs          = 9;
  localparam int unsigned DataWidthInBytes = (DataWidth + 7) / 8;
  localparam int unsigned RegNumBytes      = NumRegs * DataWidthInBytes;
  localparam int unsigned ExitReg          = 0;
  localparam int unsigned DramBaseReg      = 1;
  localparam int unsigned DramEndReg       = 2;
  localparam int unsigned EventTriggerReg  = 3;
  localparam int unsigned HwCntEnReg       = 4;
  localparam int unsigned HdvTaskAddrReg   = 5;
  localparam int unsigned HdvTaskPaddrReg  = 6;
  localparam int unsigned HdvTaskStartReg  = 7;
  localparam int unsigned HdvTaskStatusReg = 8;

  localparam logic [DataWidthInBytes-1:0] ReadOnlyReg  = {DataWidthInBytes{1'b1}};
  localparam logic [DataWidthInBytes-1:0] ReadWriteReg = {DataWidthInBytes{1'b0}};

  // Memory map
  // [71:64]: hdv_task_status (rw1c bits [2:1])
  // [63:56]: hdv_task_start  (rw, write bit 0 to start)
  // [55:48]: hdv_task_paddr  (rw)
  // [47:40]: hdv_task_addr   (rw)
  // [39:32]: hw_cnt_en       (rw)
  // [31:24]: event_trigger   (rw)
  // [23:16]: dram_end_addr   (ro)
  // [15:8]:  dram_base_addr  (ro)
  // [7:0]:   exit            (rw)
  localparam logic [NumRegs-1:0][DataWidth-1:0] RegRstVal = '{
    ExitReg         : 0,
    DramBaseReg     : DRAMBaseAddr,
    DramEndReg      : DRAMBaseAddr + DRAMLength,
    EventTriggerReg : 0,
    HwCntEnReg      : 0,
    HdvTaskAddrReg  : 0,
    HdvTaskPaddrReg : 0,
    HdvTaskStartReg : 0,
    HdvTaskStatusReg: 0,
    default         : 0
  };
  localparam logic [NumRegs-1:0][DataWidthInBytes-1:0] AxiReadOnly = '{
    ExitReg         : ReadWriteReg,
    DramBaseReg     : ReadOnlyReg,
    DramEndReg      : ReadOnlyReg,
    EventTriggerReg : ReadWriteReg,
    HwCntEnReg      : ReadWriteReg,
    HdvTaskAddrReg  : ReadWriteReg,
    HdvTaskPaddrReg : ReadWriteReg,
    HdvTaskStartReg : ReadWriteReg,
    HdvTaskStatusReg: ReadWriteReg,
    default         : ReadWriteReg
  };

  /////////////////
  //  Registers  //
  /////////////////

  logic [RegNumBytes-1:0] wr_active_d, wr_active_q;
  logic [RegNumBytes-1:0] reg_load;
  logic [RegNumBytes-1:0][7:0] reg_d;

  logic [DataWidth-1:0] hw_cnt_en;
  logic [DataWidth-1:0] event_trigger;
  logic [DataWidth-1:0] dram_base_address;
  logic [DataWidth-1:0] dram_end_address;
  logic [DataWidth-1:0] exit;
  logic [DataWidth-1:0] hdv_task_addr;
  logic [DataWidth-1:0] hdv_task_paddr;
  logic [DataWidth-1:0] hdv_task_start;
  logic [DataWidth-1:0] hdv_task_status;
  logic hdv_status_write_req;

  assign hdv_status_write_req = axi_lite_slave_req_i.aw_valid
                              & axi_lite_slave_req_i.w_valid
                              & (axi_lite_slave_req_i.aw.addr >= AddrWidth'(HdvTaskStatusReg * DataWidthInBytes))
                              & (axi_lite_slave_req_i.aw.addr <  AddrWidth'((HdvTaskStatusReg + 1) * DataWidthInBytes));

  always_comb begin
    reg_load = '0;
    reg_d    = '0;

    if (!hdv_status_write_req) begin
      for (int unsigned i = 0; i < DataWidthInBytes; i++) begin
        reg_load[HdvTaskStatusReg * DataWidthInBytes + i] = 1'b1;
        reg_d[HdvTaskStatusReg * DataWidthInBytes + i] =
          (i == 0) ? {5'b0, hdv_task_error_i, hdv_task_done_i, hdv_task_busy_i} : 8'h00;
      end
    end
  end

  axi_lite_regs #(
    .RegNumBytes (RegNumBytes    ),
    .AxiAddrWidth(AddrWidth      ),
    .AxiDataWidth(DataWidth      ),
    .AxiReadOnly (AxiReadOnly    ),
    .RegRstVal   (RegRstVal      ),
    .req_lite_t  (axi_lite_req_t ),
    .resp_lite_t (axi_lite_resp_t)
  ) i_axi_lite_regs (
    .clk_i      (clk_i                                      ),
    .rst_ni     (rst_ni                                     ),
    .axi_req_i  (axi_lite_slave_req_i                       ),
    .axi_resp_o (axi_lite_slave_resp_o                      ),
    .wr_active_o(wr_active_d                                ),
    .rd_active_o(/* Unused */                               ),
    .reg_d_i    (reg_d                                      ),
    .reg_load_i (reg_load                                   ),
    .reg_q_o    ({hdv_task_status, hdv_task_start, hdv_task_paddr, hdv_task_addr,
                  hw_cnt_en, event_trigger, dram_end_address, dram_base_address, exit})
  );

  `FF(wr_active_q, wr_active_d, '0);

  /////////////////
  //   Signals   //
  /////////////////

  assign hw_cnt_en_o      = hw_cnt_en;
  assign event_trigger_o  = event_trigger;
  assign dram_base_addr_o = dram_base_address;
  assign dram_end_addr_o  = dram_end_address;
  assign exit_o           = {exit, logic'(|wr_active_q[7:0])};

  always_comb begin
    hdv_csr_valid_o = 1'b0;
    hdv_csr_write_o = 1'b1;
    hdv_csr_addr_o  = 12'h0;
    hdv_csr_wdata_o = '0;

    if (|wr_active_q[HdvTaskAddrReg * DataWidthInBytes +: DataWidthInBytes]) begin
      hdv_csr_valid_o = 1'b1;
      hdv_csr_addr_o  = 12'h7c0;
      hdv_csr_wdata_o = hdv_task_addr;
    end else if (|wr_active_q[HdvTaskPaddrReg * DataWidthInBytes +: DataWidthInBytes]) begin
      hdv_csr_valid_o = 1'b1;
      hdv_csr_addr_o  = 12'h7c1;
      hdv_csr_wdata_o = hdv_task_paddr;
    end else if (|wr_active_q[HdvTaskStartReg * DataWidthInBytes +: DataWidthInBytes]) begin
      hdv_csr_valid_o = 1'b1;
      hdv_csr_addr_o  = 12'h7c2;
      hdv_csr_wdata_o = hdv_task_start;
    end else if (|wr_active_q[HdvTaskStatusReg * DataWidthInBytes +: DataWidthInBytes]) begin
      hdv_csr_valid_o = 1'b1;
      hdv_csr_addr_o  = 12'h7c3;
      hdv_csr_wdata_o = hdv_task_status;
    end
  end

  if (DataWidth != 64)
    $error("[ctrl_registers] HDV CSR bridge expects 64-bit control registers.");

endmodule : ctrl_registers
