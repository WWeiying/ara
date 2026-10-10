// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Date: 21/10/2020
// Description: Top level testbench module for Verilator.

module ara_tb_verilator #(
    parameter int unsigned NrLanes = 0,
    parameter int unsigned VLEN    = 0,
    parameter int unsigned L2SizeBytes = 1 << 20
  )(
    input  logic        clk_i,
    input  logic        rst_ni,
    output logic [63:0] exit_o
  );

  /*****************
   *  Definitions  *
   *****************/

  localparam AxiAddrWidth     = 64;
  localparam AxiWideDataWidth = 64 * NrLanes / 2;
  localparam L2NumWords       = L2SizeBytes / (AxiWideDataWidth / 8);
  logic [63:0] dut_exit;
  logic [63:0] exit_status_q;

  assign exit_o = exit_status_q[0] ? exit_status_q : dut_exit;

  /*********
   *  DUT  *
   *********/

  ara_testharness #(
    .NrLanes     (NrLanes         ),
    .VLEN        (VLEN            ),
    .AxiAddrWidth(AxiAddrWidth    ),
    .AxiDataWidth(AxiWideDataWidth),
    .L2SizeBytes (L2SizeBytes     )
  ) dut (
    .clk_i (clk_i ),
    .rst_ni(rst_ni),
    .exit_o(dut_exit)
  );

  // Load the ELF directly into the uninitialized Verilator SRAM. Keeping
  // tc_sram's init_val alive causes large memories to be expanded into reset
  // assignments, while SimInit="none" deliberately leaves SRAM contents intact.
  export "DPI-C" function simutil_set_mem;
  function automatic int simutil_set_mem(
      input int index,
      input bit [511:0] value
  );
    if (index >= 0 && index < L2NumWords) begin
      dut.i_ara_soc.i_dram.sram[index] = value[AxiWideDataWidth-1:0];
      return 1;
    end
    return 0;
  endfunction

  export "DPI-C" task simutil_memload;
  task automatic simutil_memload(input string file);
    $readmemh(file, dut.i_ara_soc.i_dram.sram);
  endtask

  /*********
   *  EOC  *
   *********/

  always @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      exit_status_q <= '0;
    end else if (dut_exit[0]) begin
      exit_status_q <= dut_exit;
      if (dut_exit >> 1) begin
        $warning("Core Test ", $sformatf("*** FAILED *** (tohost = %0d)", (dut_exit >> 1)));
      end else begin
        // Print vector HW runtime
        $display("[hw-cycles]: %d", int'(dut.runtime_buf_q));
        $info("Core Test ", $sformatf("*** SUCCESS *** (tohost = %0d)", (dut_exit >> 1)));
      end

      $finish(dut_exit >> 1);
    end
  end

endmodule : ara_tb_verilator
