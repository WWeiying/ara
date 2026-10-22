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
#include <stdexcept>
#include <string>

#include "Vara_tb_verilator___024root.h"
#include "verilated_cov.h"
#include "verilated_toplevel.h"
#include "verilator_memutil.h"
#include "verilator_sim_ctrl.h"

#ifndef L2_SIZE_BYTES
#define L2_SIZE_BYTES 0x00100000
#endif

class TohostMonitor : public SimCtrlExtension {
 public:
  TohostMonitor(ara_tb_verilator &tb, VerilatorSimCtrl &simctrl)
      : tb_(tb), simctrl_(simctrl) {}

  bool ParseCLIArguments(int argc, char **argv, bool &exit_app) override {
    constexpr char kPrefix[] = "+COMMIT_TOHOST=";
    for (int i = 1; i < argc; ++i) {
      const std::string arg(argv[i]);
      if (arg.compare(0, sizeof(kPrefix) - 1, kPrefix) != 0) continue;
      try {
        const std::string hex = arg.substr(sizeof(kPrefix) - 1);
        size_t consumed = 0;
        const uint64_t address = std::stoull(hex, &consumed, 16);
        if (consumed != hex.size() || address < kRamBase ||
            address - kRamBase > L2_SIZE_BYTES - sizeof(uint64_t) ||
            (address & (sizeof(uint64_t) - 1)) != 0 || enabled_) {
          throw std::invalid_argument("invalid tohost address");
        }
        address_ = address;
        enabled_ = true;
      } catch (const std::exception &) {
        std::cerr << "ERROR: invalid +COMMIT_TOHOST address: " << arg << std::endl;
        exit_app = true;
        return false;
      }
    }
    return true;
  }

  void PreExec() override {
    if (enabled_ && ReadTohost() != 0) {
      std::cerr << "ERROR: tohost is not zero before execution" << std::endl;
      simctrl_.RequestStop(false);
    }
  }

  void OnClock(unsigned long) override {
    if (!enabled_ || finished_) return;
    value_ = ReadTohost();
    if (value_ == 0) return;
    finished_ = true;
    simctrl_.RequestStop(value_ == 1);
  }

  bool finished() const { return finished_; }
  uint64_t value() const { return value_; }

 private:
  static constexpr uint64_t kRamBase = 0x80000000ULL;
  static constexpr uint64_t kBytesPerWord = 4 * NR_LANES;

  uint64_t ReadTohost() const {
    const uint64_t offset = address_ - kRamBase;
    const auto &word = tb_.rootp->ara_tb_verilator__DOT__dut__DOT__i_ara_soc__DOT__i_dram__DOT__sram[
        offset / kBytesPerWord];
    const unsigned lane = (offset % kBytesPerWord) / sizeof(uint32_t);
    return static_cast<uint64_t>(word[lane]) |
           (static_cast<uint64_t>(word[lane + 1]) << 32);
  }

  ara_tb_verilator &tb_;
  VerilatorSimCtrl &simctrl_;
  uint64_t address_ = 0;
  uint64_t value_ = 0;
  bool enabled_ = false;
  bool finished_ = false;
};

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
  TohostMonitor tohost_monitor(*tb, simctrl);
  simctrl.RegisterExtension(&tohost_monitor);

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

#if VM_COVERAGE
  tb->contextp()->coveragep()->write();
#endif

  const uint64_t exit = tb->exit_o;
  if (tohost_monitor.finished()) {
    if (tohost_monitor.value() == 1 && simctrl.WasSimulationSuccessful()) {
      std::cout << "Core Test *** SUCCESS *** (tohost = 0)" << std::endl;
      return 0;
    }
    std::cerr << "Core Test *** FAILED *** (tohost = "
              << (tohost_monitor.value() >> 1) << ")" << std::endl;
    return 1;
  }
  if (!simctrl.WasSimulationSuccessful() || !(exit & 1)) {
    std::cerr << "ERROR: simulation stopped before a tohost completion value was observed"
              << std::endl;
    return 1;
  }

  return exit >> 1;
}
