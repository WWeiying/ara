// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Top-level Verilator test-bench for Ara.

#include <cstdint>
#include <fstream>
#include <iostream>

#include "verilated_toplevel.h"
#include "verilator_memutil.h"
#include "verilator_sim_ctrl.h"

#ifndef L2_SIZE_BYTES
#define L2_SIZE_BYTES 0x00100000
#endif

int main(int argc, char **argv) {
  // Create an instance of the DUT
  ara_tb_verilator *tb = new ara_tb_verilator;

  // Initialize lowRISC's verilator utilities
  VerilatorMemUtil memutil;
  VerilatorSimCtrl &simctrl = VerilatorSimCtrl::GetInstance();
  simctrl.SetTop(tb, &tb->clk_i, &tb->rst_ni,
                 VerilatorSimCtrlFlags::ResetPolarityNegative);

  // Initialize the DRAM
  MemAreaLoc l2_mem = {.base=0x80000000, .size=L2_SIZE_BYTES};
  memutil.RegisterMemoryArea(
                             "ram", "TOP.ara_tb_verilator", 64*NR_LANES/2, &l2_mem);
  simctrl.RegisterExtension(&memutil);

  simctrl.SetInitialResetDelay(5);
  simctrl.SetResetDuration(5);

  // Evaluate once so the exported DPI memory functions are registered before
  // the memutil extension loads the ELF directly into the SRAM array.
  Verilated::commandArgs(argc, argv);
  tb->eval();

  bool exit_app = false;
  const bool args_ok = simctrl.ParseCommandArgs(argc, argv, exit_app);
  if (exit_app) {
    return args_ok ? 0 : 1;
  }

  std::cout << "Simulation of Ara" << std::endl
            << "=================" << std::endl
            << std::endl;

  simctrl.RunSimulation();

  const uint64_t exit = tb->dut().exit_o;
  if (!simctrl.WasSimulationSuccessful() || !(exit & 1)) {
    std::cerr << "ERROR: simulation stopped before a tohost completion value was observed"
              << std::endl;
    return 1;
  }

  return exit >> 1;
}
