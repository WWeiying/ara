// Copyright 2021 ETH Zurich and University of Bologna.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Author: Matheus Cavalcante <matheusd@iis.ee.ethz.ch>
// Description:
// Top level testbench module.

import "DPI-C" function void read_elf (input string filename);
import "DPI-C" function byte get_section (output longint address, output longint len);
import "DPI-C" context function byte read_section(input longint address, inout byte buffer[]);
import ara_pkg::*;

`define STRINGIFY(x) `"x`"

`ifndef SAIF
`ifndef IDEAL_DISPATCHER
typedef struct {
  realtime timestamp;
  logic [63:0] cycle;
  logic [63:0] instret;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] rvv_instret;
  logic [63:0] rvv_op;
  logic [63:0] rvv_op_fs1;
  logic [63:0] rvv_op_fd;
  logic [63:0] rvv_op_load;
  logic [63:0] rvv_op_store;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
    counters.cycle = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.cycle_q[63:0];
    counters.instret = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.instret_q[63:0];
    counters.rvv_cycle            = ara_tb.rvv_cycle           ;
    counters.rvv_lane_cycle       = ara_tb.rvv_lane_cycle      ;
    counters.rvv_mem_only_cycle  = ara_tb.rvv_mem_only_cycle ;
    counters.rvv_mem_lane_cycle  = ara_tb.rvv_mem_lane_cycle ;
    counters.rvv_load_only_cycle  = ara_tb.rvv_load_only_cycle ;
    counters.rvv_load_lane_cycle  = ara_tb.rvv_load_lane_cycle ;
    counters.rvv_store_only_cycle = ara_tb.rvv_store_only_cycle;
    counters.rvv_store_lane_cycle = ara_tb.rvv_store_lane_cycle;
    counters.rvv_instret = ara_tb.rvv_instret;
    counters.rvv_op       = ara_tb.rvv_op      ;
    counters.rvv_op_fs1   = ara_tb.rvv_op_fs1  ;
    counters.rvv_op_fd    = ara_tb.rvv_op_fd   ;
    counters.rvv_op_load  = ara_tb.rvv_op_load ;
    counters.rvv_op_store = ara_tb.rvv_op_store;
    counters.rvv_axi_aw_count = ara_tb.rvv_axi_aw_count;
    counters.rvv_axi_w_count  = ara_tb.rvv_axi_w_count ;
    counters.rvv_axi_b_count  = ara_tb.rvv_axi_b_count ;
    counters.rvv_axi_ar_count = ara_tb.rvv_axi_ar_count;
    counters.rvv_axi_r_count  = ara_tb.rvv_axi_r_count ;
    return counters;
endfunction

function void print_perf_report();
      realtime duration;
      int total_cycles;
      int total_insns;
      int total_rvv_cycles          ;
      int total_rvv_lane_cycles     ;
      int total_rvv_mem_only_cycles;
      int total_rvv_mem_lane_cycles;
      int total_rvv_load_only_cycles;
      int total_rvv_load_lane_cycles;
      int total_rvv_store_only_cycles;
      int total_rvv_store_lane_cycles;
      int total_vector_insns;
      int total_rvv_op      ;
      int total_rvv_op_fs1  ;
      int total_rvv_op_fd   ;
      int total_rvv_op_load ;
      int total_rvv_op_store;
      int total_rvv_axi_aw_count;
      int total_rvv_axi_w_count ;
      int total_rvv_axi_b_count ;
      int total_rvv_axi_ar_count;
      int total_rvv_axi_r_count ;
      
      real ipc;
      real lane_utilization;
      real vecinst_rate;
      int file_handle;

      string testcase;
      void'($value$plusargs("TESTCASE=%s", testcase));

      duration = ara_tb.perf_end_n.timestamp - ara_tb.perf_start_n.timestamp;
      total_cycles = ara_tb.perf_end_n.cycle - ara_tb.perf_start_n.cycle;
      total_insns = ara_tb.perf_end_n.instret - ara_tb.perf_start_n.instret;
      total_rvv_cycles            = ara_tb.perf_end_n.rvv_cycle            - ara_tb.perf_start_n.rvv_cycle           ;
      total_rvv_lane_cycles       = ara_tb.perf_end_n.rvv_lane_cycle       - ara_tb.perf_start_n.rvv_lane_cycle      ;
      total_rvv_mem_only_cycles  = ara_tb.perf_end_n.rvv_mem_only_cycle  - ara_tb.perf_start_n.rvv_mem_only_cycle ;
      total_rvv_mem_lane_cycles  = ara_tb.perf_end_n.rvv_mem_lane_cycle  - ara_tb.perf_start_n.rvv_mem_lane_cycle ;
      total_rvv_load_only_cycles  = ara_tb.perf_end_n.rvv_load_only_cycle  - ara_tb.perf_start_n.rvv_load_only_cycle ;
      total_rvv_load_lane_cycles  = ara_tb.perf_end_n.rvv_load_lane_cycle  - ara_tb.perf_start_n.rvv_load_lane_cycle ;
      total_rvv_store_only_cycles = ara_tb.perf_end_n.rvv_store_only_cycle - ara_tb.perf_start_n.rvv_store_only_cycle;
      total_rvv_store_lane_cycles = ara_tb.perf_end_n.rvv_store_lane_cycle - ara_tb.perf_start_n.rvv_store_lane_cycle;
      total_vector_insns = ara_tb.perf_end_n.rvv_instret - ara_tb.perf_start_n.rvv_instret;
      total_rvv_op       = ara_tb.perf_end_n.rvv_op       - ara_tb.perf_start_n.rvv_op      ;
      total_rvv_op_fs1   = ara_tb.perf_end_n.rvv_op_fs1   - ara_tb.perf_start_n.rvv_op_fs1  ;
      total_rvv_op_fd    = ara_tb.perf_end_n.rvv_op_fd    - ara_tb.perf_start_n.rvv_op_fd   ;
      total_rvv_op_load  = ara_tb.perf_end_n.rvv_op_load  - ara_tb.perf_start_n.rvv_op_load ;
      total_rvv_op_store = ara_tb.perf_end_n.rvv_op_store - ara_tb.perf_start_n.rvv_op_store;
      total_rvv_axi_aw_count = ara_tb.perf_end_n.rvv_axi_aw_count - ara_tb.perf_start_n.rvv_axi_aw_count;
      total_rvv_axi_w_count  = ara_tb.perf_end_n.rvv_axi_w_count  - ara_tb.perf_start_n.rvv_axi_w_count ;
      total_rvv_axi_b_count  = ara_tb.perf_end_n.rvv_axi_b_count  - ara_tb.perf_start_n.rvv_axi_b_count ;
      total_rvv_axi_ar_count = ara_tb.perf_end_n.rvv_axi_ar_count - ara_tb.perf_start_n.rvv_axi_ar_count;
      total_rvv_axi_r_count  = ara_tb.perf_end_n.rvv_axi_r_count  - ara_tb.perf_start_n.rvv_axi_r_count ;
      ipc = real'(total_insns) / total_cycles;
      lane_utilization = real'(total_rvv_lane_cycles) / total_cycles;
      vecinst_rate = real'(total_vector_insns) / total_insns;
      file_handle = $fopen($sformatf("perf_report_%s.log", testcase), "a");
      
      $display("\n[PERF] ==== Performance Report Start ====");
      $display("[PERF] duration                   : %0t x100fs", duration);
      $display("[PERF] total_cycles               : %0d", total_cycles);
      $display("[PERF] total_insns                : %0d", total_insns);
      $display("[PERF] total_rvv_cycles           : %0d", total_rvv_cycles           );
      $display("[PERF] total_rvv_lane_cycles      : %0d", total_rvv_lane_cycles      );
      $display("[PERF] total_rvv_mem_only_cycles  : %0d", total_rvv_mem_only_cycles );
      $display("[PERF] total_rvv_mem_lane_cycles  : %0d", total_rvv_mem_lane_cycles );
      $display("[PERF] total_rvv_load_only_cycles : %0d", total_rvv_load_only_cycles );
      $display("[PERF] total_rvv_load_lane_cycles : %0d", total_rvv_load_lane_cycles );
      $display("[PERF] total_rvv_store_only_cycles: %0d", total_rvv_store_only_cycles);
      $display("[PERF] total_rvv_store_lane_cycles: %0d", total_rvv_store_lane_cycles);
      $display("[PERF] total_vector_insns         : %0d", total_vector_insns);
      $display("[PERF] IPC                        : %0.3f", ipc);
      $display("[PERF] lane utilization           : %0.3f", lane_utilization);
      $display("[PERF] vector inst rate           : %0.3f", vecinst_rate);
      $display("[PERF] rvv_op                     : %0d", total_rvv_op      );
      $display("[PERF] rvv_op_fs1                 : %0d", total_rvv_op_fs1  );
      $display("[PERF] rvv_op_fd                  : %0d", total_rvv_op_fd   );
      $display("[PERF] rvv_op_load                : %0d", total_rvv_op_load );
      $display("[PERF] rvv_op_store               : %0d", total_rvv_op_store);
      $display("[PERF] ==== Performance Report End ====\n");


      $fwrite(file_handle, "[PERF] ==== Performance Report Start ====\n");
      $fwrite(file_handle, "[PERF] duration                   : %0t x100fs\n", duration);
      $fwrite(file_handle, "[PERF] total_cycles               : %0d\n", total_cycles);
      $fwrite(file_handle, "[PERF] total_insns                : %0d\n", total_insns);
      $fwrite(file_handle, "[PERF] total_rvv_cycles           : %0d\n", total_rvv_cycles           );
      $fwrite(file_handle, "[PERF] total_rvv_lane_cycles      : %0d\n", total_rvv_lane_cycles      );
      $fwrite(file_handle, "[PERF] total_rvv_mem_only_cycles  : %0d\n", total_rvv_mem_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_mem_lane_cycles  : %0d\n", total_rvv_mem_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_only_cycles : %0d\n", total_rvv_load_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_lane_cycles : %0d\n", total_rvv_load_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_store_only_cycles: %0d\n", total_rvv_store_only_cycles);
      $fwrite(file_handle, "[PERF] total_rvv_store_lane_cycles: %0d\n", total_rvv_store_lane_cycles);
      $fwrite(file_handle, "[PERF] total_vector_insns         : %0d\n", total_vector_insns);
      $fwrite(file_handle, "[PERF] IPC                        : %0.3f\n", ipc);
      $fwrite(file_handle, "[PERF] lane utilization           : %0.3f\n", lane_utilization);
      $fwrite(file_handle, "[PERF] vector inst rate           : %0.3f\n", vecinst_rate);
      $fwrite(file_handle, "[PERF] rvv_op                     : %0d\n", total_rvv_op      );
      $fwrite(file_handle, "[PERF] rvv_op_fs1                 : %0d\n", total_rvv_op_fs1  );
      $fwrite(file_handle, "[PERF] rvv_op_fd                  : %0d\n", total_rvv_op_fd   );
      $fwrite(file_handle, "[PERF] rvv_op_load                : %0d\n", total_rvv_op_load );
      $fwrite(file_handle, "[PERF] rvv_op_store               : %0d\n", total_rvv_op_store);
      $fwrite(file_handle, "[PERF] ==== AXI Transaction ====\n");
      $fwrite(file_handle, "[PERF] rvv_axi_aw_count           : %0d\n", total_rvv_axi_aw_count);
      $fwrite(file_handle, "[PERF] rvv_axi_w_count            : %0d\n", total_rvv_axi_w_count );
      $fwrite(file_handle, "[PERF] rvv_axi_b_count            : %0d\n", total_rvv_axi_b_count );
      $fwrite(file_handle, "[PERF] rvv_axi_ar_count           : %0d\n", total_rvv_axi_ar_count);
      $fwrite(file_handle, "[PERF] rvv_axi_r_count            : %0d\n", total_rvv_axi_r_count );
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane0 ====\n");
      $fwrite(file_handle, "[PERF] lane0 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane0 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane0 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane0 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane0 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane0 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane0 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane0 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane0 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane0 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane0 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane0 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane0 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane0 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane0 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane0 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane0 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane0 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane0 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane0 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane0 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane0 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane0 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane0 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane0 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane0 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane0 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane1 ====\n");
      $fwrite(file_handle, "[PERF] lane1 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane1 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane1 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane1 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane1 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane1 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane1 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane1 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane1 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane1 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane1 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane1 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane1 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane1 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane1 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane1 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane1 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane1 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane1 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane1 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane1 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane1 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane1 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane1 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane1 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane1 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane1 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane2 ====\n");
      $fwrite(file_handle, "[PERF] lane2 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane2 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane2 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane2 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane2 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane2 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane2 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane2 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane2 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane2 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane2 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane2 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane2 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane2 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane2 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane2 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane2 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane2 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane2 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane2 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane2 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane2 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane2 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane2 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane2 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane2 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane2 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== VRF Perf lane3 ====\n");
      $fwrite(file_handle, "[PERF] lane3 total_bank_requests     : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_requests  : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $fwrite(file_handle, "[PERF] lane3 total_bank_conflicts    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $fwrite(file_handle, "[PERF] lane3 total_hp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 total_lp_bank_conflicts : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $fwrite(file_handle, "[PERF] lane3 hp_block_lp             : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] );
      $fwrite(file_handle, "[PERF] lane3 bank0_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]);
      $fwrite(file_handle, "[PERF] lane3 bank0_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[0]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[0] ));
      $fwrite(file_handle, "[PERF] lane3 bank1_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] );
      $fwrite(file_handle, "[PERF] lane3 bank1_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]);
      $fwrite(file_handle, "[PERF] lane3 bank1_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[1]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[1] ));
      $fwrite(file_handle, "[PERF] lane3 bank2_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] );
      $fwrite(file_handle, "[PERF] lane3 bank2_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]);
      $fwrite(file_handle, "[PERF] lane3 bank2_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[2]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[2] ));
      $fwrite(file_handle, "[PERF] lane3 bank3_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] );
      $fwrite(file_handle, "[PERF] lane3 bank3_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]);
      $fwrite(file_handle, "[PERF] lane3 bank3_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[3]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[3] ));
      $fwrite(file_handle, "[PERF] lane3 bank4_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] );
      $fwrite(file_handle, "[PERF] lane3 bank4_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]);
      $fwrite(file_handle, "[PERF] lane3 bank4_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[4]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[4] ));
      $fwrite(file_handle, "[PERF] lane3 bank5_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] );
      $fwrite(file_handle, "[PERF] lane3 bank5_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]);
      $fwrite(file_handle, "[PERF] lane3 bank5_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[5]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[5] ));
      $fwrite(file_handle, "[PERF] lane3 bank6_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] );
      $fwrite(file_handle, "[PERF] lane3 bank6_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]);
      $fwrite(file_handle, "[PERF] lane3 bank6_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[6]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[6] ));
      $fwrite(file_handle, "[PERF] lane3 bank7_total_requests    : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] );
      $fwrite(file_handle, "[PERF] lane3 bank7_total_conflicts   : %0d\n",   ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]);
      $fwrite(file_handle, "[PERF] lane3 bank7_conflict_ratio    : %0.3f\n", real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_conflicts[7]) / real'(ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor.lane_stats.bank_total_requests[7] ));
      $fwrite(file_handle, "[PERF] ==== Performance Report End ====\n");

      $fclose(file_handle);
endfunction
`else
typedef struct {
  realtime timestamp;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
    counters.rvv_cycle            = ara_tb.rvv_cycle;
    counters.rvv_lane_cycle       = ara_tb.rvv_lane_cycle;
    counters.rvv_mem_only_cycle  = ara_tb.rvv_mem_only_cycle ;
    counters.rvv_mem_lane_cycle  = ara_tb.rvv_mem_lane_cycle ;
    counters.rvv_load_only_cycle  = ara_tb.rvv_load_only_cycle ;
    counters.rvv_load_lane_cycle  = ara_tb.rvv_load_lane_cycle ;
    counters.rvv_store_only_cycle = ara_tb.rvv_store_only_cycle;
    counters.rvv_store_lane_cycle = ara_tb.rvv_store_lane_cycle;
    return counters;
endfunction

function void print_perf_report();
      realtime duration;
      int total_rvv_cycles          ;
      int total_rvv_lane_cycles     ;
      int total_rvv_mem_only_cycles;
      int total_rvv_mem_lane_cycles;
      int total_rvv_load_only_cycles;
      int total_rvv_load_lane_cycles;
      int total_rvv_store_only_cycles;
      int total_rvv_store_lane_cycles;
      
      real utilization_rate;
      int file_handle;

      string testcase;
      void'($value$plusargs("TESTCASE=%s", testcase));

      duration = ara_tb.perf_end_n.timestamp - ara_tb.perf_start_n.timestamp;
      total_rvv_cycles            = ara_tb.perf_end_n.rvv_cycle            - ara_tb.perf_start_n.rvv_cycle           ;
      total_rvv_lane_cycles       = ara_tb.perf_end_n.rvv_lane_cycle       - ara_tb.perf_start_n.rvv_lane_cycle      ;
      total_rvv_mem_only_cycles  = ara_tb.perf_end_n.rvv_mem_only_cycle  - ara_tb.perf_start_n.rvv_mem_only_cycle ;
      total_rvv_mem_lane_cycles  = ara_tb.perf_end_n.rvv_mem_lane_cycle  - ara_tb.perf_start_n.rvv_mem_lane_cycle ;
      total_rvv_load_only_cycles  = ara_tb.perf_end_n.rvv_load_only_cycle  - ara_tb.perf_start_n.rvv_load_only_cycle ;
      total_rvv_load_lane_cycles  = ara_tb.perf_end_n.rvv_load_lane_cycle  - ara_tb.perf_start_n.rvv_load_lane_cycle ;
      total_rvv_store_only_cycles = ara_tb.perf_end_n.rvv_store_only_cycle - ara_tb.perf_start_n.rvv_store_only_cycle;
      total_rvv_store_lane_cycles = ara_tb.perf_end_n.rvv_store_lane_cycle - ara_tb.perf_start_n.rvv_store_lane_cycle;
      utilization_rate = real'(total_rvv_lane_cycles) / total_rvv_cycles;
      file_handle = $fopen($sformatf("perf_report_%s_ideal.log", testcase), "a");
      
      $display("\n[PERF] ==== Performance Report Start ====");
      $display("[PERF] duration                   : %0t x100fs", duration);
      $display("[PERF] total_rvv_cycles           : %0d", total_rvv_cycles           );
      $display("[PERF] total_rvv_lane_cycles      : %0d", total_rvv_lane_cycles      );
      $display("[PERF] total_rvv_mem_only_cycles  : %0d", total_rvv_mem_only_cycles );
      $display("[PERF] total_rvv_mem_lane_cycles  : %0d", total_rvv_mem_lane_cycles );
      $display("[PERF] total_rvv_load_only_cycles : %0d", total_rvv_load_only_cycles );
      $display("[PERF] total_rvv_load_lane_cycles : %0d", total_rvv_load_lane_cycles );
      $display("[PERF] total_rvv_store_only_cycles: %0d", total_rvv_store_only_cycles);
      $display("[PERF] total_rvv_store_lane_cycles: %0d", total_rvv_store_lane_cycles);
      $display("[PERF] utilization rate           : %0.3f", utilization_rate);
      $display("[PERF] ==== Performance Report End ====\n");

      $fclose(file_handle);
endfunction

`endif
`endif

module ara_tb;
  /*****************
   *  Definitions  *
   *****************/

  `ifdef NR_LANES
  localparam NrLanes = `NR_LANES;
  `else
  localparam NrLanes = 8;
  `endif

  `ifdef VLEN
  localparam VLEN = `VLEN;
  `else
  localparam VLEN = 256;
  `endif

  localparam ClockPeriod  = 1ns;
  // Axi response delay [ps]
  localparam int unsigned AxiRespDelay = 200;

  localparam AxiAddrWidth      = 64;
  localparam AxiWideDataWidth  = 64 * NrLanes / 2;
  localparam AxiWideBeWidth    = AxiWideDataWidth / 8;
  localparam AxiWideByteOffset = $clog2(AxiWideBeWidth);

  localparam DRAMAddrBase = 64'h8000_0000;
  localparam DRAMLength   = 64'h4000_0000; // 1GByte of DDR (split between two chips on Genesys2)

  /********************************
   *  Clock and Reset Generation  *
   ********************************/

  logic clk;
  logic rst_n;

  // Controlling the reset
  initial begin
    clk   = 1'b0;
    rst_n = 1'b0;

    // Synch reset for TB memories
    repeat (10) #(ClockPeriod/2) clk = ~clk;
    clk = 1'b0;

    // Asynch reset for main system
    repeat (5) #(ClockPeriod);
    rst_n = 1'b1;
    repeat (5) #(ClockPeriod);

    // Start the clock
    forever #(ClockPeriod/2) clk = ~clk;
  end

  /*********
   *  DUT  *
   *********/

  `ifndef SAIF
  `ifndef IDEAL_DISPATCHER
  logic        perf_time_q;
  logic        perf_time_n;
  perf_t       perf_start_q, perf_end_q;
  perf_t       perf_start_n, perf_end_n;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
  logic [63:0] rvv_instret;
  logic [63:0] rvv_op      ;
  logic [63:0] rvv_op_fs1  ;
  logic [63:0] rvv_op_fd   ;
  logic [63:0] rvv_op_load ;
  logic [63:0] rvv_op_store;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;

  `else
  logic        perf_monitor;
  perf_t       perf_start_n, perf_end_n;
  logic [63:0] rvv_cycle;
  logic [63:0] rvv_lane_cycle;
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;

  `endif
  `endif

  initial begin
    string testcase;
    $fsdbDumpfile("ara_tb.fsdb");
    $fsdbDumpvars(0, ara_tb);
    $fsdbDumpMDA(0, ara_tb);
    $fsdbDumpvars("+all");

    void'($value$plusargs("TESTCASE=%s", testcase));
    
    `ifdef SAIF
    if(testcase != "") begin
        $dumpfile($sformatf("../vcd/%s.vcd", testcase));
    end else begin
        $dumpfile("../vcd/default.vcd");
    end
    $dumpvars(0, dut.i_ara_soc);
    `endif
  end

  logic [63:0] exit;

  // This TB must be implemented in C for integration with Verilator.
  // In order to Verilator to understand that the ara_testharness module is the top-level,
  // we do not instantiate it when Verilating this module.
  `ifndef VERILATOR
  ara_testharness #(
    .NrLanes     (NrLanes         ),
    .VLEN        (VLEN            ),
    .AxiAddrWidth(AxiAddrWidth    ),
    .AxiDataWidth(AxiWideDataWidth),
    .AxiRespDelay(AxiRespDelay    )
  ) dut (
    .clk_i (clk  ),
    .rst_ni(rst_n),
    .exit_o(exit )
  );
  `endif

  `ifdef TARGET_SRAM_MC 
  //`ifdef SAIF
  //localparam DRAMNumBanks=16;
  //localparam DRAMWordsPerBank=8192;
  //localparam DRAMBankSizeBytes=8192*AxiWideBeWidth;

  ///*************************
  // *  DRAM Initialization  *
  // *************************/
  //typedef logic [AxiAddrWidth-1:0] addr_t;
  //typedef logic [AxiWideDataWidth-1:0] data_t;

  //initial begin : dram_init
  //  automatic data_t mem_row;
  //  byte buffer [];
  //  addr_t address;
  //  addr_t length;
  //  string binary;
  //  addr_t word_addr;
  //  int bank_index;
  //  addr_t bank_offset;
  //  int word_index;
  //  data_t bank_data [DRAMNumBanks][DRAMWordsPerBank];

  //  for (int i = 0; i < DRAMNumBanks; i++) begin
  //      for (int j = 0; j < DRAMWordsPerBank; j++) begin
  //          bank_data[i][j] = '0;
  //      end
  //  end

  //  // tc_sram is initialized with zeros. We need to overwrite this value.
  //  repeat (2)
  //    #ClockPeriod;

  //  // Initialize memories
  //  void'($value$plusargs("PRELOAD=%s", binary));
  //  if (binary != "") begin
  //    // Read ELF
  //    read_elf(binary);
  //    $display("Loading ELF file %s", binary);
  //    while (get_section(address, length)) begin
  //      // Read sections
  //      automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
  //      $display("Loading section %x of length %x", address, length);
  //      buffer = new[nwords * AxiWideBeWidth];
  //      void'(read_section(address, buffer));

  //      // Initializing memories
  //      for (int w = 0; w < nwords; w++) begin
  //        mem_row = '0;
  //        for (int b = 0; b < AxiWideBeWidth; b++) begin
  //          mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
  //        end

  //        word_addr = address + (w << AxiWideByteOffset);
  //        
  //        if (word_addr >= DRAMAddrBase && word_addr < DRAMAddrBase + (DRAMNumBanks * DRAMBankSizeBytes)) begin
  //          bank_index = (word_addr - DRAMAddrBase) / DRAMBankSizeBytes;
  //          bank_offset = (word_addr - DRAMAddrBase) % DRAMBankSizeBytes;
  //          word_index = bank_offset >> AxiWideByteOffset;
  //          
  //          if (bank_index < DRAMNumBanks && word_index < DRAMWordsPerBank) begin
  //            bank_data[bank_index][word_index] = mem_row;
  //          end else begin
  //            $display("Error: Address %x maps to invalid bank(%0d) or word(%0d)", 
  //                     word_addr, bank_index, word_index);
  //          end
  //        end else begin
  //              $display("Cannot initialize address %x, which doesn't fall into the L2 region.", word_addr);
  //        end
  //      end
  //    end

  //    for (int i = 0; i < DRAMNumBanks; i++) begin
  //      automatic string temp_file = $sformatf("temp_bank_%0d.dat", i);
  //      automatic int fd = $fopen(temp_file, "w");
  //      
  //      if (!fd) begin
  //        $error("Failed to open temporary file for bank %0d: %s", i, temp_file);
  //        $finish;
  //      end

  //      for (int w = 0; w < DRAMWordsPerBank; w++) begin
  //        $fdisplay(fd,  "%032h", bank_data[i][w]);
  //      end

  //      $fclose(fd);

  //      $display("Initializing bank %0d with file %s", i, temp_file);
  //      case (i)
  //        0:  dut.i_ara_soc.gen_dram_0__i_dram.preloadData(temp_file);
  //        1:  dut.i_ara_soc.gen_dram_1__i_dram.preloadData(temp_file);
  //        2:  dut.i_ara_soc.gen_dram_2__i_dram.preloadData(temp_file);
  //        3:  dut.i_ara_soc.gen_dram_3__i_dram.preloadData(temp_file);
  //        4:  dut.i_ara_soc.gen_dram_4__i_dram.preloadData(temp_file);
  //        5:  dut.i_ara_soc.gen_dram_5__i_dram.preloadData(temp_file);
  //        6:  dut.i_ara_soc.gen_dram_6__i_dram.preloadData(temp_file);
  //        7:  dut.i_ara_soc.gen_dram_7__i_dram.preloadData(temp_file);
  //        8:  dut.i_ara_soc.gen_dram_8__i_dram.preloadData(temp_file);
  //        9:  dut.i_ara_soc.gen_dram_9__i_dram.preloadData(temp_file);
  //        10: dut.i_ara_soc.gen_dram_10__i_dram.preloadData(temp_file);
  //        11: dut.i_ara_soc.gen_dram_11__i_dram.preloadData(temp_file);
  //        12: dut.i_ara_soc.gen_dram_12__i_dram.preloadData(temp_file);
  //        13: dut.i_ara_soc.gen_dram_13__i_dram.preloadData(temp_file);
  //        14: dut.i_ara_soc.gen_dram_14__i_dram.preloadData(temp_file);
  //        15: dut.i_ara_soc.gen_dram_15__i_dram.preloadData(temp_file);
  //        default: $display("Invalid bank index: %0d", bank_index);
  //      endcase
  //      //$system($sformatf("rm -f %s", temp_file));
  //    end

  //  end else begin
  //    $error("Expecting a firmware to run, none was provided!");
  //    $finish;
  //  end
  //end : dram_init

  //`else
  localparam DRAMNumBanks=8;
  localparam DRAMWordsPerBank=8192;
  localparam DRAMBankSizeBytes=8192*AxiWideBeWidth;

  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;
    addr_t word_addr;
    int bank_index;
    addr_t bank_offset;
    int word_index;
    data_t bank_data [DRAMNumBanks][DRAMWordsPerBank];

    for (int i = 0; i < DRAMNumBanks; i++) begin
        for (int j = 0; j < DRAMWordsPerBank; j++) begin
            bank_data[i][j] = '0;
        end
    end

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));

        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end

          word_addr = address + (w << AxiWideByteOffset);
          
          if (word_addr >= DRAMAddrBase && word_addr < DRAMAddrBase + (DRAMNumBanks * DRAMBankSizeBytes)) begin
            bank_index = (word_addr - DRAMAddrBase) / DRAMBankSizeBytes;
            bank_offset = (word_addr - DRAMAddrBase) % DRAMBankSizeBytes;
            word_index = bank_offset >> AxiWideByteOffset;
            
            if (bank_index < DRAMNumBanks && word_index < DRAMWordsPerBank) begin
              bank_data[bank_index][word_index] = mem_row;
            end else begin
              $display("Error: Address %x maps to invalid bank(%0d) or word(%0d)", 
                       word_addr, bank_index, word_index);
            end
          end else begin
                $display("Cannot initialize address %x, which doesn't fall into the L2 region.", word_addr);
          end
        end
      end

      for (int i = 0; i < DRAMNumBanks; i++) begin
        automatic string temp_file = $sformatf("temp_bank_%0d.dat", i);
        automatic int fd = $fopen(temp_file, "w");
        
        if (!fd) begin
          $error("Failed to open temporary file for bank %0d: %s", i, temp_file);
          $finish;
        end

        for (int w = 0; w < DRAMWordsPerBank; w++) begin
          $fdisplay(fd,  "%032h", bank_data[i][w]);
        end

        $fclose(fd);

        $display("Initializing bank %0d with file %s", i, temp_file);
        case (i)
          0:  dut.i_ara_soc.gen_dram[0 ].i_dram.preloadData(temp_file);
          1:  dut.i_ara_soc.gen_dram[1 ].i_dram.preloadData(temp_file);
          2:  dut.i_ara_soc.gen_dram[2 ].i_dram.preloadData(temp_file);
          3:  dut.i_ara_soc.gen_dram[3 ].i_dram.preloadData(temp_file);
          4:  dut.i_ara_soc.gen_dram[4 ].i_dram.preloadData(temp_file);
          5:  dut.i_ara_soc.gen_dram[5 ].i_dram.preloadData(temp_file);
          6:  dut.i_ara_soc.gen_dram[6 ].i_dram.preloadData(temp_file);
          7:  dut.i_ara_soc.gen_dram[7 ].i_dram.preloadData(temp_file);
          //8:  dut.i_ara_soc.gen_dram[8 ].i_dram.preloadData(temp_file);
          //9:  dut.i_ara_soc.gen_dram[9 ].i_dram.preloadData(temp_file);
          //10: dut.i_ara_soc.gen_dram[10].i_dram.preloadData(temp_file);
          //11: dut.i_ara_soc.gen_dram[11].i_dram.preloadData(temp_file);
          //12: dut.i_ara_soc.gen_dram[12].i_dram.preloadData(temp_file);
          //13: dut.i_ara_soc.gen_dram[13].i_dram.preloadData(temp_file);
          //14: dut.i_ara_soc.gen_dram[14].i_dram.preloadData(temp_file);
          //15: dut.i_ara_soc.gen_dram[15].i_dram.preloadData(temp_file);
          default: $display("Invalid bank index: %0d", bank_index);
        endcase
        //$system($sformatf("rm -f %s", temp_file));
      end

    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init

  //`endif
  `else
  /*************************
   *  DRAM Initialization  *
   *************************/
  typedef logic [AxiAddrWidth-1:0] addr_t;
  typedef logic [AxiWideDataWidth-1:0] data_t;

  initial begin : dram_init
    automatic data_t mem_row;
    byte buffer [];
    addr_t address;
    addr_t length;
    string binary;

    // tc_sram is initialized with zeros. We need to overwrite this value.
    repeat (2)
      #ClockPeriod;

    // Initialize memories
    void'($value$plusargs("PRELOAD=%s", binary));
    if (binary != "") begin
      // Read ELF
      read_elf(binary);
      $display("Loading ELF file %s", binary);
      while (get_section(address, length)) begin
        // Read sections
        automatic int nwords = (length + AxiWideBeWidth - 1)/AxiWideBeWidth;
        $display("Loading section %x of length %x", address, length);
        buffer = new[nwords * AxiWideBeWidth];
        void'(read_section(address, buffer));
        // Initializing memories
        for (int w = 0; w < nwords; w++) begin
          mem_row = '0;
          for (int b = 0; b < AxiWideBeWidth; b++) begin
            mem_row[8 * b +: 8] = buffer[w * AxiWideBeWidth + b];
          end
          if (address >= DRAMAddrBase && address < DRAMAddrBase + DRAMLength)
            // This requires the sections to be aligned to AxiWideByteOffset,
            // otherwise, they can be over-written.
              dut.i_ara_soc.i_dram.init_val[(address - DRAMAddrBase + (w << AxiWideByteOffset)) >> AxiWideByteOffset] = mem_row;
          else
            $display("Cannot initialize address %x, which doesn't fall into the L2 region.", address);
        end
      end
    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init
  `endif


`ifndef TARGET_GATESIM

  /*************************
   *  PRINT STORED VALUES  *
   *************************/

  // This is useful to check that the ideal dispatcher simulation was correct

`ifndef IDEAL_DISPATCHER
  localparam OutResultFile = "../gold_results.txt";
`else
  localparam OutResultFile = "../id_results.txt";
`endif

  int fd;

  data_t                     ara_w;
  logic [AxiWideBeWidth-1:0] ara_w_strb;
  logic                      ara_w_valid;
  logic                      ara_w_ready;

  // Avoid dumping what it's not measured, e.g. cache warming
  logic dump_en_mask;

  initial begin
    fd = $fopen(OutResultFile, "w");
    $display("Dump results on %s", OutResultFile);
  end

  `ifdef SAIF 
  assign ara_w       = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_o[145:18];
  assign ara_w_strb  = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_o[17:2];
  assign ara_w_valid = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_valid_o;
  assign ara_w_ready = dut.i_ara_soc.i_system.i_ara.i_vlsu.i_vstu.axi_w_ready_i;
  `else
  assign ara_w       = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.data;
  assign ara_w_strb  = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w.strb;
  assign ara_w_valid = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_req.w_valid;
  assign ara_w_ready = dut.i_ara_soc.i_system.i_ara.i_vlsu.axi_resp.w_ready;
  `endif

`ifndef IDEAL_DISPATCHER
  assign dump_en_mask = dut.i_ara_soc.hw_cnt_en_o[0];
`else
  // Ideal-Dispatcher system does not warm the scalar cache
  assign dump_en_mask = 1'b1;
`endif
  always_ff @(posedge clk)
    if (dump_en_mask)
      if (ara_w_valid && ara_w_ready)
        for (int b = 0; b < AxiWideBeWidth; b++)
          if (ara_w_strb[b])
            $fdisplay(fd, "%0x", ara_w[b*8 +: 8]);

`endif

  /*********
   *  EOC  *
   *********/

  always @(posedge clk) begin
    if (exit[0]) begin
      if (exit >> 1) begin
        $warning("Core Test ", $sformatf("*** FAILED *** (tohost = %0d)", (exit >> 1)));
      end else begin
        // Print vector HW runtime
`ifndef TARGET_GATESIM
        $display("[hw-cycles]: %d", int'(dut.runtime_buf_q));
        $display("[cva6-d$-stalls]: %d", int'(dut.dcache_stall_buf_q));
        $display("[cva6-i$-stalls]: %d", int'(dut.icache_stall_buf_q));
        $display("[cva6-sb-full]: %d", int'(dut.sb_full_buf_q));
`endif
        $info("Core Test ", $sformatf("*** SUCCESS *** (tohost = %0d)", (exit >> 1)));
      end

`ifndef TARGET_GATESIM
      $fclose(fd);
`endif

`ifdef SAIF
   $dumpoff;
   $dumpflush;
`endif
      $finish(exit >> 1);
    end
  end

// Dump VCD with a SW trigger
`ifdef VCD_DUMP

  /****************
  *  VCD DUMPING  *
  ****************/

`ifdef VCD_PATH
  string vcd_path = `STRINGIFY(`VCD_PATH);
`else
  string vcd_path = "../vcd/last_sim.vcd";
`endif

  localparam logic [63:0] VCD_TRIGGER_ON  = 64'h0000_0000_0000_0001;
  localparam logic [63:0] VCD_TRIGGER_OFF = 64'hFFFF_FFFF_FFFF_FFFF;

  event start_dump_event;
  event stop_dump_event;

  logic [63:0] event_trigger_reg;
  logic        dumping = 1'b0;

  assign event_trigger_reg =
           dut.i_ara_soc.i_ctrl_registers.event_trigger_o;

  initial begin
    $display("VCD_DUMP successfully defined\n");
  end

  always_ff @(posedge clk) begin
    if(event_trigger_reg == VCD_TRIGGER_ON && !dumping) begin
       $display("[TB - VCD] START DUMPING\n");
       -> start_dump_event;
       dumping = 1'b1;
    end
    if(event_trigger_reg == VCD_TRIGGER_OFF) begin
       -> stop_dump_event;
       $display("[TB - VCD] STOP DUMPING\n");
    end
  end

  initial begin
    @(start_dump_event);
    $vcdplusfile(vcd_path);
    $vcdpluson(0, dut.i_ara_soc);

    #1 $display("[TB - VCD] DUMPING...\n");

    @(stop_dump_event)
    $vcdplusclose;
    $finish;
  end

`endif


`ifndef SAIF
`ifndef IDEAL_DISPATCHER
 /***************************
  *  VRF PERFMENCE MONITOR  *
  ***************************/
  for(genvar i = 0; i < NrLanes; i++) begin: vrf_perf_monitor
    vrf_perf_monitor u_vrf_perf_monitor(
      .clk_i           (clk),
      .rst_ni          (rst_n),
      .lane_operand_req(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.lane_operand_req),
      .ext_operand_req (ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_operand_requester.ext_operand_req)
    );
  end

`endif
`endif


`ifndef SAIF
`ifndef IDEAL_DISPATCHER
 /**********************
  *  PERFMENCE MONITOR  *
  ***********************/
  logic rvv_lane_en,rvv_load_en,rvv_store_en;

  always_comb begin
    rvv_lane_en = (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[0]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[1]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[2]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[3]);
    rvv_load_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[4];
    rvv_store_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[5];
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_cycle <= '0;
    end
    else if(!ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.ara_idle_o) begin
      rvv_cycle <= rvv_cycle + 1;
    end
    else begin
      rvv_cycle <= rvv_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_lane_cycle <= '0;
    end
    else if(rvv_lane_en) begin
      rvv_lane_cycle <= rvv_lane_cycle + 1;
    end
    else begin
      rvv_lane_cycle <= rvv_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_only_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && !rvv_lane_en) begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle + 1;
    end
    else begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_lane_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && rvv_lane_en) begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle + 1;
    end
    else begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_only_cycle <= '0;
    end
    else if(rvv_load_en && !rvv_lane_en) begin
      rvv_load_only_cycle <= rvv_load_only_cycle + 1;
    end
    else begin
      rvv_load_only_cycle <= rvv_load_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_lane_cycle <= '0;
    end
    else if(rvv_load_en && rvv_lane_en) begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle + 1;
    end
    else begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_only_cycle <= '0;
    end
    else if(rvv_store_en && !rvv_lane_en) begin
      rvv_store_only_cycle <= rvv_store_only_cycle + 1;
    end
    else begin
      rvv_store_only_cycle <= rvv_store_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_lane_cycle <= '0;
    end
    else if(rvv_store_en && rvv_lane_en) begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle + 1;
    end
    else begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_instret  <= '0;
      rvv_op       <= '0;
      rvv_op_fs1   <= '0;
      rvv_op_fd    <= '0;
      rvv_op_load  <= '0;
      rvv_op_store <= '0;
    end
    else begin
      if (|ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1:0]) begin
        rvv_instret  <= rvv_instret + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].fu == 4'b1010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].fu == 4'b1010));
        rvv_op       <= rvv_op       + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110110)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110110));
        rvv_op_fs1   <= rvv_op_fs1   + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110111)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110111));
        rvv_op_fd    <= rvv_op_fd    + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111000)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111000));
        rvv_op_load  <= rvv_op_load  + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111001)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111001));
        rvv_op_store <= rvv_op_store + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111010));
      end
      else begin
        rvv_instret  <= rvv_instret;
        rvv_op       <= rvv_op      ;
        rvv_op_fs1   <= rvv_op_fs1  ;
        rvv_op_fd    <= rvv_op_fd   ;
        rvv_op_load  <= rvv_op_load ;
        rvv_op_store <= rvv_op_store;
      end
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_axi_aw_count <= '0;
      rvv_axi_w_count  <= '0;
      rvv_axi_b_count  <= '0;
      rvv_axi_ar_count <= '0;
      rvv_axi_r_count  <= '0;
    end
    else begin
      rvv_axi_aw_count <= rvv_axi_aw_count + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.aw_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.aw_ready);
      rvv_axi_w_count  <= rvv_axi_w_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.w_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.w_ready);
      rvv_axi_b_count  <= rvv_axi_b_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.b_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.b_ready);
      rvv_axi_ar_count <= rvv_axi_ar_count + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.ar_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.ar_ready);
      rvv_axi_r_count  <= rvv_axi_r_count  + (ara_tb.dut.i_ara_soc.i_system.i_ara.axi_resp_i.r_valid && ara_tb.dut.i_ara_soc.i_system.i_ara.axi_req_o.r_ready);
    end
  end

  always_comb begin
    perf_time_n = perf_time_q;
    if(ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_csr_o &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.csr_addr_i[11:0] == 12'hc00 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.csr_op_o[7:0] == 8'b100010 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.waddr_o[0][4:0] == 5'h0 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.we_gpr_o[0]) begin
      perf_time_n = !perf_time_q;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      perf_time_q  <= '0;
      perf_start_q <= '{default: '0};
      perf_end_q   <= '{default: '0};
    end
    else begin
      perf_time_q  <= perf_time_n ;
      perf_start_q <= perf_start_n;
      perf_end_q   <= perf_end_n  ;
    end
  end

  always_comb begin
    perf_start_n = perf_start_q;
    perf_end_n = perf_end_q;

    if(!perf_time_q && perf_time_n) begin
      perf_start_n = get_perf_counters();
    end
    if(perf_time_q && !perf_time_n) begin
      perf_end_n = get_perf_counters();
    end
  end

  always_ff @(posedge clk) begin
    if(perf_time_q && !perf_time_n) begin
      print_perf_report();
    end
  end

`else
 /**********************
  *  PERFMENCE MONITOR  *
  ***********************/
  logic rvv_lane_en,rvv_load_en,rvv_store_en;

  always_comb begin
    rvv_lane_en = (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[0]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[1]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[2]) ||
                  (|ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[3]);
    rvv_load_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[4];
    rvv_store_en = |ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_d[5];
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_cycle <= '0;
    end
    else if(perf_monitor) begin
      rvv_cycle <= rvv_cycle + 1;
    end
    else begin
      rvv_cycle <= rvv_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_lane_cycle <= '0;
    end
    else if(rvv_lane_en) begin
      rvv_lane_cycle <= rvv_lane_cycle + 1;
    end
    else begin
      rvv_lane_cycle <= rvv_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_only_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && !rvv_lane_en) begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle + 1;
    end
    else begin
      rvv_mem_only_cycle <= rvv_mem_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_mem_lane_cycle <= '0;
    end
    else if((rvv_load_en || rvv_store_en) && rvv_lane_en) begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle + 1;
    end
    else begin
      rvv_mem_lane_cycle <= rvv_mem_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_only_cycle <= '0;
    end
    else if(rvv_load_en && !rvv_lane_en) begin
      rvv_load_only_cycle <= rvv_load_only_cycle + 1;
    end
    else begin
      rvv_load_only_cycle <= rvv_load_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_load_lane_cycle <= '0;
    end
    else if(rvv_load_en && rvv_lane_en) begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle + 1;
    end
    else begin
      rvv_load_lane_cycle <= rvv_load_lane_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_only_cycle <= '0;
    end
    else if(rvv_store_en && !rvv_lane_en) begin
      rvv_store_only_cycle <= rvv_store_only_cycle + 1;
    end
    else begin
      rvv_store_only_cycle <= rvv_store_only_cycle;
    end
  end

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      rvv_store_lane_cycle <= '0;
    end
    else if(rvv_store_en && rvv_lane_en) begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle + 1;
    end
    else begin
      rvv_store_lane_cycle <= rvv_store_lane_cycle;
    end
  end

  initial begin
    #15.5;
    perf_start_n = get_perf_counters();
    perf_monitor = 1'b1;
  end

  final begin
    perf_end_n = get_perf_counters();
    print_perf_report();
  end

`endif
`endif

endmodule : ara_tb
