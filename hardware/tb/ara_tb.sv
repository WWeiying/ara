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
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
`ifdef TARGET_GATESIM
    counters.cycle   = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.cycle_q[63:0];
    counters.instret = ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.instret_q[63:0];
`else
    // HDV RTL mode: no CVA6 present; use wall-clock cycle counter instead
    counters.cycle   = ara_tb.wall_cycle;
    counters.instret = '0;
`endif
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
`ifdef FOR_VERIFY
    counters.seq_raw_hazard_cycle   = ara_tb.seq_raw_hazard_cycle;
    counters.seq_war_hazard_cycle   = ara_tb.seq_war_hazard_cycle;
    counters.seq_waw_hazard_cycle   = ara_tb.seq_waw_hazard_cycle;
    counters.seq_false_hazard_cycle = ara_tb.seq_false_hazard_cycle;
    counters.seq_block_cycle        = ara_tb.seq_block_cycle;
`endif
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
`ifdef FOR_VERIFY
      int total_seq_raw_hazard_cycle;
      int total_seq_war_hazard_cycle;
      int total_seq_waw_hazard_cycle;
      int total_seq_false_hazard_cycle;
      int total_seq_block_cycle;
`endif
      
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
      total_rvv_axi_r_count  = ara_tb.perf_end_n.rvv_axi_r_count  - ara_tb.perf_start_n.rvv_axi_r_count;
`ifdef FOR_VERIFY
      total_seq_raw_hazard_cycle   = ara_tb.perf_end_n.seq_raw_hazard_cycle   - ara_tb.perf_start_n.seq_raw_hazard_cycle;
      total_seq_war_hazard_cycle   = ara_tb.perf_end_n.seq_war_hazard_cycle   - ara_tb.perf_start_n.seq_war_hazard_cycle;
      total_seq_waw_hazard_cycle   = ara_tb.perf_end_n.seq_waw_hazard_cycle   - ara_tb.perf_start_n.seq_waw_hazard_cycle;
      total_seq_false_hazard_cycle = ara_tb.perf_end_n.seq_false_hazard_cycle - ara_tb.perf_start_n.seq_false_hazard_cycle;
      total_seq_block_cycle        = ara_tb.perf_end_n.seq_block_cycle        - ara_tb.perf_start_n.seq_block_cycle;
`endif

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
`ifdef FOR_VERIFY
      $display("[PERF] seq_raw_hazard_cycles      : %0d", total_seq_raw_hazard_cycle  );
      $display("[PERF] seq_war_hazard_cycles      : %0d", total_seq_war_hazard_cycle  );
      $display("[PERF] seq_waw_hazard_cycles      : %0d", total_seq_waw_hazard_cycle  );
      $display("[PERF] seq_false_hazard_cycles    : %0d", total_seq_false_hazard_cycle);
      $display("[PERF] seq_block_cycles           : %0d", total_seq_block_cycle       );
`endif
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
`ifdef FOR_VERIFY
      $fwrite(file_handle, "[PERF] seq_raw_hazard_cycles      : %0d\n", total_seq_raw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_war_hazard_cycles      : %0d\n", total_seq_war_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_waw_hazard_cycles      : %0d\n", total_seq_waw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_false_hazard_cycles    : %0d\n", total_seq_false_hazard_cycle);
      $fwrite(file_handle, "[PERF] seq_block_cycles           : %0d\n", total_seq_block_cycle       );
`endif
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
  logic [63:0] rvv_lane_compute_cycle[4];
  logic [63:0] rvv_mem_only_cycle;
  logic [63:0] rvv_mem_lane_cycle;
  logic [63:0] rvv_load_only_cycle;
  logic [63:0] rvv_load_lane_cycle;
  logic [63:0] rvv_store_only_cycle;
  logic [63:0] rvv_store_lane_cycle;
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif
} perf_t;

function automatic perf_t get_perf_counters();
    perf_t counters;
    counters.timestamp = $realtime;
    counters.rvv_cycle              = ara_tb.rvv_cycle;
    counters.rvv_lane_cycle         = ara_tb.rvv_lane_cycle;
    counters.rvv_lane_compute_cycle[0] = ara_tb.lane_compute_add[0];
    counters.rvv_lane_compute_cycle[1] = ara_tb.lane_compute_add[1];
    counters.rvv_lane_compute_cycle[2] = ara_tb.lane_compute_add[2];
    counters.rvv_lane_compute_cycle[3] = ara_tb.lane_compute_add[3];
    counters.rvv_mem_only_cycle     = ara_tb.rvv_mem_only_cycle ;
    counters.rvv_mem_lane_cycle     = ara_tb.rvv_mem_lane_cycle ;
    counters.rvv_load_only_cycle    = ara_tb.rvv_load_only_cycle ;
    counters.rvv_load_lane_cycle    = ara_tb.rvv_load_lane_cycle ;
    counters.rvv_store_only_cycle   = ara_tb.rvv_store_only_cycle;
    counters.rvv_store_lane_cycle   = ara_tb.rvv_store_lane_cycle;
`ifdef FOR_VERIFY
    counters.seq_raw_hazard_cycle   = ara_tb.seq_raw_hazard_cycle;
    counters.seq_war_hazard_cycle   = ara_tb.seq_war_hazard_cycle;
    counters.seq_waw_hazard_cycle   = ara_tb.seq_waw_hazard_cycle;
    counters.seq_false_hazard_cycle = ara_tb.seq_false_hazard_cycle;
    counters.seq_block_cycle        = ara_tb.seq_block_cycle;
`endif
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
`ifdef FOR_VERIFY
      int total_seq_raw_hazard_cycle;
      int total_seq_war_hazard_cycle;
      int total_seq_waw_hazard_cycle;
      int total_seq_false_hazard_cycle;
      int total_seq_block_cycle;
`endif
       
      int total_rvv_store_lane_cycles;
      
      real lane_utilization;
      real lane_compute_utilization;
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

`ifdef FOR_VERIFY
      total_seq_raw_hazard_cycle   = ara_tb.perf_end_n.seq_raw_hazard_cycle   - ara_tb.perf_start_n.seq_raw_hazard_cycle;
      total_seq_war_hazard_cycle   = ara_tb.perf_end_n.seq_war_hazard_cycle   - ara_tb.perf_start_n.seq_war_hazard_cycle;
      total_seq_waw_hazard_cycle   = ara_tb.perf_end_n.seq_waw_hazard_cycle   - ara_tb.perf_start_n.seq_waw_hazard_cycle;
      total_seq_false_hazard_cycle = ara_tb.perf_end_n.seq_false_hazard_cycle - ara_tb.perf_start_n.seq_false_hazard_cycle;
      total_seq_block_cycle        = ara_tb.perf_end_n.seq_block_cycle        - ara_tb.perf_start_n.seq_block_cycle;
`endif

      lane_utilization = real'(total_rvv_lane_cycles) / total_rvv_cycles;
      file_handle = $fopen($sformatf("perf_report_%s_ideal.log", testcase), "a");
      
      $display("\n[PERF] ==== Performance Report Start ====");
      $display("[PERF] duration                       : %0t x100fs", duration);
      $display("[PERF] total_rvv_cycles               : %0d", total_rvv_cycles           );
      $display("[PERF] total_rvv_lane_cycles          : %0d", total_rvv_lane_cycles      );
      $display("[PERF] total_rvv_lane0_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[0] - ara_tb.perf_start_n.rvv_lane_compute_cycle[0]);
      $display("[PERF] total_rvv_lane1_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[1] - ara_tb.perf_start_n.rvv_lane_compute_cycle[1]);
      $display("[PERF] total_rvv_lane2_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[2] - ara_tb.perf_start_n.rvv_lane_compute_cycle[2]);
      $display("[PERF] total_rvv_lane3_compute_cycles : %0d", ara_tb.perf_end_n.rvv_lane_compute_cycle[3] - ara_tb.perf_start_n.rvv_lane_compute_cycle[3]);
      $display("[PERF] total_rvv_mem_only_cycles      : %0d", total_rvv_mem_only_cycles );
      $display("[PERF] total_rvv_mem_lane_cycles      : %0d", total_rvv_mem_lane_cycles );
      $display("[PERF] total_rvv_load_only_cycles     : %0d", total_rvv_load_only_cycles );
      $display("[PERF] total_rvv_load_lane_cycles     : %0d", total_rvv_load_lane_cycles );
      $display("[PERF] total_rvv_store_only_cycles    : %0d", total_rvv_store_only_cycles);
      $display("[PERF] total_rvv_store_lane_cycles    : %0d", total_rvv_store_lane_cycles);
`ifdef FOR_VERIFY
      $display("[PERF] seq_raw_hazard_cycles          : %0d", total_seq_raw_hazard_cycle  );
      $display("[PERF] seq_war_hazard_cycles          : %0d", total_seq_war_hazard_cycle  );
      $display("[PERF] seq_waw_hazard_cycles          : %0d", total_seq_waw_hazard_cycle  );
      $display("[PERF] seq_false_hazard_cycles        : %0d", total_seq_false_hazard_cycle);
      $display("[PERF] seq_block_cycles               : %0d", total_seq_block_cycle       );
`endif
      $display("[PERF] lane utilization               : %0.3f", lane_utilization);
      $display("[PERF] lane0 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[0] - ara_tb.perf_start_n.rvv_lane_compute_cycle[0]) / total_rvv_cycles);
      $display("[PERF] lane1 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[1] - ara_tb.perf_start_n.rvv_lane_compute_cycle[1]) / total_rvv_cycles);
      $display("[PERF] lane2 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[2] - ara_tb.perf_start_n.rvv_lane_compute_cycle[2]) / total_rvv_cycles);
      $display("[PERF] lane3 compute utilization      : %0.3f", real'(ara_tb.perf_end_n.rvv_lane_compute_cycle[3] - ara_tb.perf_start_n.rvv_lane_compute_cycle[3]) / total_rvv_cycles);
      $display("[PERF] ==== VRF Perf lane0 ====");
      $display("[PERF] lane0 total_bank_requests      : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests    );
      $display("[PERF] lane0 total_bank_conflicts     : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts   );
      $display("[PERF] lane0 total_hp_bank_requests   : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_requests );
      $display("[PERF] lane0 total_hp_bank_conflicts  : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_hp_bank_conflicts);
      $display("[PERF] lane0 total_lp_bank_requests   : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_requests );
      $display("[PERF] lane0 total_lp_bank_conflicts  : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_lp_bank_conflicts);
      $display("[PERF] lane0 hp_block_lp              : %0d",   ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.hp_block_lp            );
      $display("[PERF] lane0 conflict_ratio           : %0.3f", real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_conflicts) / real'(ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor.lane_stats.total_bank_requests));
      $display("[PERF] ==== Performance Report End ====\n");

      $fwrite(file_handle, "[PERF] ==== Performance Report Start ====\n");
      $fwrite(file_handle, "[PERF] duration                   : %0t x100fs\n", duration);
      $fwrite(file_handle, "[PERF] total_rvv_cycles           : %0d\n", total_rvv_cycles           );
      $fwrite(file_handle, "[PERF] total_rvv_lane_cycles      : %0d\n", total_rvv_lane_cycles      );
      $fwrite(file_handle, "[PERF] total_rvv_mem_only_cycles  : %0d\n", total_rvv_mem_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_mem_lane_cycles  : %0d\n", total_rvv_mem_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_only_cycles : %0d\n", total_rvv_load_only_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_load_lane_cycles : %0d\n", total_rvv_load_lane_cycles );
      $fwrite(file_handle, "[PERF] total_rvv_store_only_cycles: %0d\n", total_rvv_store_only_cycles);
      $fwrite(file_handle, "[PERF] total_rvv_store_lane_cycles: %0d\n", total_rvv_store_lane_cycles);
`ifdef FOR_VERIFY
      $fwrite(file_handle, "[PERF] seq_raw_hazard_cycles      : %0d\n", total_seq_raw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_war_hazard_cycles      : %0d\n", total_seq_war_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_waw_hazard_cycles      : %0d\n", total_seq_waw_hazard_cycle  );
      $fwrite(file_handle, "[PERF] seq_false_hazard_cycles    : %0d\n", total_seq_false_hazard_cycle);
      $fwrite(file_handle, "[PERF] seq_block_cycles           : %0d\n", total_seq_block_cycle       );
`endif
      $fwrite(file_handle, "[PERF] lane utilization           : %0.3f\n", lane_utilization);
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
      $fclose(file_handle);
endfunction


function void print_perf_csv();
    string testcase;
    int csv_handle;

    int cycle_count;

    void'($value$plusargs("TESTCASE=%s", testcase));
    csv_handle = $fopen($sformatf("perf_report_%s_ideal.csv", testcase), "w");

    cycle_count = ara_tb.wall_cycle;


    $fwrite(csv_handle, "wall_cycle");
    for (int i = 0; i < cycle_count; i++) begin
        $fwrite(csv_handle, ",%0d", ara_tb.wall_cycle_history[i]);
    end
    $fwrite(csv_handle, "\n");
    
    for (int j = 0; j < 4; j++) begin
      $fwrite(csv_handle, "lane%0d_compute", j);
      for (int i = 0; i < cycle_count; i++) begin
          $fwrite(csv_handle, ",%0d", ara_tb.lane_compute_history[j][i]);
      end
      $fwrite(csv_handle, "\n");
    end

    $fclose(csv_handle);
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
  localparam AxiWideDataWidth  = 64 * NrLanes/2;
  localparam AxiWideBeWidth    = AxiWideDataWidth / 8;
  localparam AxiWideByteOffset = $clog2(AxiWideBeWidth);

  localparam DRAMAddrBase = 64'h8000_0000;
  localparam DRAMLength   = 64'h4000_0000; // 1GByte of DDR (split between two chips on Genesys2)
  localparam HdvNumSlots  = 8;
  `ifdef HDV_TASK_ENTRY
  // Pass as a plain DECIMAL (e.g. hdv_task_entry=2147516416 for 0x80008000):
  // SV `'h` literals lose their apostrophe through make->bender->VCS, and a
  // bare decimal >2^31 sign-extends under 64'(...), so zero-extend the low 32b.
  localparam HdvTaskEntry = {32'h0, 32'(`HDV_TASK_ENTRY)};
  `else
  localparam HdvTaskEntry = 64'h8000_1000;
  `endif
  `ifdef HDV_VSAXPY_ELEMENTS
  localparam int unsigned HdvVsaxpyElements = `HDV_VSAXPY_ELEMENTS;
  `else
  localparam int unsigned HdvVsaxpyElements = 1024;
  `endif
  localparam int unsigned HdvVsaxpyVl = VLEN / 32; // vsetvli ..., e32, m1
  localparam int unsigned HdvVsaxpyIters =
      (HdvVsaxpyElements + HdvVsaxpyVl - 1) / HdvVsaxpyVl;
  // Cross-fetch-packet VLIW packing carries packet-tail non-control EPs into
  // the next fetch packet.  With HdvNumSlots=8, current vsaxpy_hdv dispatch
  // accepts 4 EPs per loop iteration; the loop-end packet terminates the task.
  `ifdef HDV_EXPECTED_EP
  localparam int unsigned HdvVsaxpyExpectedEpAcknowledges = `HDV_EXPECTED_EP;
  `else
  localparam int unsigned HdvVsaxpyExpectedEpAcknowledges =
      (HdvVsaxpyIters == 0) ? 0 : (HdvVsaxpyIters * 4);
  `endif
  // The HDV_INITIAL_A* overrides arrive as plain (unbased) decimal defines from
  // the Makefile.  A bare decimal > 2^31 (e.g. an 0x8000_xxxx address) would be
  // taken as a negative 32-bit int and sign-extended by a 64-bit cast, corrupting
  // the pointer.  Zero-extend the low 32 bits explicitly so any 32-bit address or
  // count passes through unchanged.
  `ifdef HDV_INITIAL_A0
  localparam logic [63:0] HdvVsaxpyN    = {32'h0, 32'(`HDV_INITIAL_A0)};
  `else
  localparam logic [63:0] HdvVsaxpyN    = 64'(HdvVsaxpyElements);
  `endif
  `ifdef HDV_INITIAL_A1
  localparam HdvVsaxpySrc1 = {32'h0, 32'(`HDV_INITIAL_A1)};
  `else
  localparam HdvVsaxpySrc1 = 64'h8000_1040;
  `endif
  `ifdef HDV_INITIAL_A2
  localparam HdvVsaxpySrc2 = {32'h0, 32'(`HDV_INITIAL_A2)};
  `else
  localparam HdvVsaxpySrc2 = 64'h8000_5050;
  `endif
  `ifdef HDV_INITIAL_A3
  localparam HdvVsaxpySrc3 = {32'h0, 32'(`HDV_INITIAL_A3)};
  `else
  localparam HdvVsaxpySrc3 = 64'h0;
  `endif
  `ifdef HDV_INITIAL_A4
  localparam HdvVsaxpyA4   = {32'h0, 32'(`HDV_INITIAL_A4)};
  `else
  localparam HdvVsaxpyA4   = 64'h0;
  `endif
  `ifdef HDV_INITIAL_A5
  localparam HdvVsaxpyA5   = {32'h0, 32'(`HDV_INITIAL_A5)};
  `else
  localparam HdvVsaxpyA5   = 64'h0;
  `endif
  `ifdef HDV_INITIAL_A6
  localparam HdvVsaxpyA6   = {32'h0, 32'(`HDV_INITIAL_A6)};
  `else
  localparam HdvVsaxpyA6   = 64'h0;
  `endif
  `ifdef HDV_INITIAL_A7
  localparam HdvVsaxpyA7   = {32'h0, 32'(`HDV_INITIAL_A7)};
  `else
  localparam HdvVsaxpyA7   = 64'h0;
  `endif
  `ifdef HDV_INITIAL_FA0
  localparam HdvVsaxpyA    = 64'(`HDV_INITIAL_FA0);
  `else
  localparam HdvVsaxpyA    = 64'hffff_ffff_40d5_1eb8;
  `endif

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

  logic [63:0] wall_cycle;
  logic        lane_compute[NrLanes];
  logic [63:0] lane_compute_add[NrLanes];
  logic [63:0] wall_cycle_history[100000];
  logic lane_compute_history[NrLanes][100000];

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      wall_cycle <= '0;
    end
    else begin
      wall_cycle <= wall_cycle + 1;
    end

    wall_cycle_history[wall_cycle] <= wall_cycle;
  end

  for (genvar i = 0; i < NrLanes; i++) begin
    assign lane_compute[i] = (|(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.mfpu_operand_valid_i[2:0] & ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.mfpu_operand_ready_o[2:0])) || (|(ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.alu_operand_valid_i[1:0] & ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[i].i_lane.i_vfus.alu_operand_ready_o[1:0]));

    always_ff @(posedge clk, negedge rst_n) begin
      lane_compute_history[i][wall_cycle] <= lane_compute[i];
    end

    always_ff @(posedge clk, negedge rst_n) begin
      if(!rst_n) begin
        lane_compute_add[i] <= '0;
      end
      else begin
        lane_compute_add[i] <= lane_compute_add[i] + lane_compute[i];
      end
    end

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
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif

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
`ifdef FOR_VERIFY
  logic [63:0] seq_raw_hazard_cycle;
  logic [63:0] seq_war_hazard_cycle;
  logic [63:0] seq_waw_hazard_cycle;
  logic [63:0] seq_false_hazard_cycle;
  logic [63:0] seq_block_cycle;
`endif

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
  logic                         hdv_host_csr_valid;
  logic                         hdv_host_csr_write;
  logic [11:0]                  hdv_host_csr_addr;
  logic [63:0]                  hdv_host_csr_wdata;
  logic                         hdv_host_csr_ready;
  logic [63:0]                  hdv_host_csr_rdata;
  logic                         hdv_host_csr_error;
  logic                         hdv_redirect_valid;
  logic [63:0]                  hdv_redirect_pc;
  logic                         hdv_loop_lock;
  logic                         unused_hdv_mock_loop_lock;
  logic [HdvNumSlots-2:0]       hdv_dep_break;
  logic                         hdv_task_busy;
  logic                         hdv_task_done;
  logic                         hdv_task_error;
  logic                         hdv_task_complete;
  logic                         hdv_host_task_error;
  logic                         hdv_scalar_valid;
  logic                         hdv_scalar_ready;
  logic                         hdv_scalar_ep_done;
  logic [HdvNumSlots-1:0]       hdv_scalar_insn_valid;
  logic [HdvNumSlots-1:0][31:0] hdv_scalar_insn;
  logic [HdvNumSlots-1:0]       hdv_scalar_insn_is_32b;
  logic [HdvNumSlots-1:0][63:0] hdv_scalar_insn_pc;
  // hdv_vector_* signals removed — vector dispatch is now internal to hdv_top
  logic                         hdv_backend_error;
  logic                         hdv_ep_acknowledged;
  logic                         hdv_ep_error;

  assign hdv_dep_break      = '0;
  assign hdv_loop_lock      = 1'b0;

  // This TB must be implemented in C for integration with Verilator.
  // In order to Verilator to understand that the ara_testharness module is the top-level,
  // we do not instantiate it when Verilating this module.
  `ifndef VERILATOR
  ara_testharness #(
    .NrLanes     (NrLanes         ),
    .VLEN        (VLEN            ),
    .AxiAddrWidth(AxiAddrWidth    ),
    .AxiDataWidth(AxiWideDataWidth),
    .HdvNumSlots (HdvNumSlots     ),
    .HdvInitialA0(HdvVsaxpyN       ),
    .HdvInitialA1(HdvVsaxpySrc1    ),
    .HdvInitialA2(HdvVsaxpySrc2    ),
    .HdvInitialA3(HdvVsaxpySrc3    ),
    .HdvInitialA4(HdvVsaxpyA4      ),
    .HdvInitialA5(HdvVsaxpyA5      ),
    .HdvInitialA6(HdvVsaxpyA6      ),
    .HdvInitialA7(HdvVsaxpyA7      ),
    .HdvInitialFa0(HdvVsaxpyA      ),
    .AxiRespDelay(AxiRespDelay    )
  ) dut (
    .clk_i (clk  ),
    .rst_ni(rst_n),
    .exit_o(exit ),
    .hdv_host_csr_valid_i(hdv_host_csr_valid),
    .hdv_host_csr_write_i(hdv_host_csr_write),
    .hdv_host_csr_addr_i (hdv_host_csr_addr ),
    .hdv_host_csr_wdata_i(hdv_host_csr_wdata),
    .hdv_host_csr_ready_o(hdv_host_csr_ready),
    .hdv_host_csr_rdata_o(hdv_host_csr_rdata),
    .hdv_host_csr_error_o(hdv_host_csr_error),
    .hdv_redirect_valid_i(hdv_redirect_valid),
    .hdv_redirect_pc_i   (hdv_redirect_pc   ),
    .hdv_loop_lock_i     (hdv_loop_lock     ),
    .hdv_dep_break_i     (hdv_dep_break     ),
    .hdv_active_task_desc_o(),
    .hdv_task_busy_o     (hdv_task_busy     ),
    .hdv_task_done_o     (hdv_task_done     ),
    .hdv_task_error_o    (hdv_task_error    ),
    .hdv_task_complete_i (hdv_task_complete ),
    .hdv_task_error_i    (hdv_host_task_error),
    .hdv_scalar_valid_o  (hdv_scalar_valid  ),
    .hdv_scalar_ready_i  (hdv_scalar_ready  ),
    .hdv_scalar_insn_valid_o(hdv_scalar_insn_valid),
    .hdv_scalar_insn_o   (hdv_scalar_insn),
    .hdv_scalar_insn_is_32b_o(hdv_scalar_insn_is_32b),
    .hdv_scalar_insn_pc_o(hdv_scalar_insn_pc),
    .hdv_scalar_pc_o     (),
    .hdv_scalar_ep_done_i   (hdv_scalar_ep_done   ),
    // Vector dispatch ports removed — internal to hdv_top
    .hdv_backend_error_i (hdv_backend_error ),
    .hdv_ep_busy_o  (),
    .hdv_ep_acknowledged_o  (hdv_ep_acknowledged  ),
    .hdv_ep_error_o (hdv_ep_error )
  );

  hdv_mock_host_core #(
    .XLEN                       (64),
    .NumSlots                   (HdvNumSlots),
    .ScalarLatency              (1),
    .VectorLatency              (1),
    .AutoStart                  (1'b1),
    .AutoStartDelay             (64),
    .AutoTaskEntry              (HdvTaskEntry),
    .AutoTaskDesc               (DRAMAddrBase + 64'h1000),
    // Real scalar backend controls the loop.  VLIWPU may pack non-control
    // packet tails across fetch-packet boundaries, so vsaxpy_hdv uses the
    // formula above rather than a fixed packet count.
    .AutoExpectedEpAcknowledges  (32'(HdvVsaxpyExpectedEpAcknowledges)),
    .EnableMockBranch           (1'b0),
    .MockLoopIterations         (0),
    .TaskWatchdogCycles         (65536),
    .PacketWatchdogCycles       (1024),
    .addr_t                     (logic [63:0])
  ) i_hdv_mock_host_core (
    .clk_i                     (clk),
    .rst_ni                    (rst_n),
    .flush_i                   (1'b0),
    .mock_hdv_csr_valid_o      (hdv_host_csr_valid),
    .mock_hdv_csr_write_o      (hdv_host_csr_write),
    .mock_hdv_csr_addr_o       (hdv_host_csr_addr),
    .mock_hdv_csr_wdata_o      (hdv_host_csr_wdata),
    .hdv_mock_csr_ready_i      (hdv_host_csr_ready),
    .hdv_mock_csr_rdata_i      (hdv_host_csr_rdata),
    .hdv_mock_csr_error_i      (hdv_host_csr_error),
    .hdv_mock_task_busy_i      (hdv_task_busy),
    .hdv_mock_task_done_i      (hdv_task_done),
    .hdv_mock_task_error_i     (hdv_task_error),
    .mock_hdv_task_complete_o  (hdv_task_complete),
    .mock_hdv_task_error_o     (hdv_host_task_error),
    .hdv_mock_scalar_valid_i   (hdv_scalar_valid),
    .mock_hdv_scalar_ready_o   (hdv_scalar_ready),
    .mock_hdv_scalar_ep_done_o    (hdv_scalar_ep_done),
    .hdv_mock_scalar_insn_valid_i(hdv_scalar_insn_valid),
    .hdv_mock_scalar_insn_i    (hdv_scalar_insn),
    .hdv_mock_scalar_insn_is_32b_i(hdv_scalar_insn_is_32b),
    .hdv_mock_scalar_insn_pc_i (hdv_scalar_insn_pc),
    .mock_hdv_redirect_valid_o (hdv_redirect_valid),
    .mock_hdv_redirect_pc_o    (hdv_redirect_pc),
    .mock_hdv_loop_lock_o      (unused_hdv_mock_loop_lock),
    .hdv_mock_vector_valid_i   (1'b0),  // vector now handled internally by hdv_top
    .mock_hdv_vector_ready_o   (),
    .mock_hdv_vector_ep_acknowledged_o (),
    .hdv_mock_ep_acknowledged_i  (hdv_ep_acknowledged),
    .hdv_mock_ep_error_i  (hdv_ep_error),
    .mock_hdv_backend_error_o  (hdv_backend_error)
  );

  // HDV pipeline observation: print every execute-packet backend-accept event
  // and final state (once on entry) so the HDV IPU→VLIWPU→HEU flow is visible.
  logic [3:0] hdv_mock_state_prev_q;
  logic [31:0] hdv_acknowledged_visible;
  logic        hdv_task_cycle_active_q;
  logic [63:0] hdv_task_cycle_base_q;
  logic        hdv_task_start_fire;
  logic        hdv_task_cycle_valid;
  logic [63:0] hdv_task_cycle_base_visible;
  logic [63:0] hdv_task_cycle;
  logic [63:0] hdv_last_task_cycle_q;
  logic        hdv_task_done_prev_q;
  localparam int unsigned HdvEpTraceDepth = 128;
  int unsigned hdv_ep_trace_fd;
  int unsigned hdv_ep_trace_head_q;
  int unsigned hdv_ep_trace_tail_q;
  int unsigned hdv_ep_trace_count_q;
  bit          hdv_csr_verbose;
  logic [63:0] hdv_ep_trace_enqueued_q;
  logic [63:0] hdv_ep_trace_enqueue_wall_q [HdvEpTraceDepth];
  logic [63:0] hdv_ep_trace_enqueue_task_q [HdvEpTraceDepth];
  logic [63:0] hdv_ep_trace_ep_pc_q        [HdvEpTraceDepth];
  logic [HdvNumSlots-1:0] hdv_ep_trace_insn_valid_q [HdvEpTraceDepth];
  logic [HdvNumSlots-1:0] hdv_ep_trace_insn_is_32b_q[HdvEpTraceDepth];
  logic [HdvNumSlots-1:0][31:0] hdv_ep_trace_insn_q [HdvEpTraceDepth];
  logic [HdvNumSlots-1:0][63:0] hdv_ep_trace_insn_pc_q [HdvEpTraceDepth];
  logic [HdvNumSlots-1:0][1:0]  hdv_ep_trace_class_q [HdvEpTraceDepth];
  logic        hdv_ep_trace_enqueue;
  logic        hdv_ep_trace_flush;

  function automatic string hdv_ep_class_name(input logic [1:0] cls);
    unique case (cls)
      hdv_pkg::HDV_INST_SCALAR: hdv_ep_class_name = "S";
      hdv_pkg::HDV_INST_VECTOR: hdv_ep_class_name = "V";
      hdv_pkg::HDV_INST_SYSTEM: hdv_ep_class_name = "SYS";
      hdv_pkg::HDV_INST_BRANCH: hdv_ep_class_name = "BR";
      default:                  hdv_ep_class_name = "UNK";
    endcase
  endfunction

  initial begin : hdv_ep_trace_open
    string testcase;
    hdv_csr_verbose = $test$plusargs("HDV_CSR_VERBOSE");
    if (!$value$plusargs("TESTCASE=%s", testcase)) begin
      testcase = "default";
    end
    hdv_ep_trace_fd = $fopen($sformatf("hdv_ep_trace_%s.log", testcase), "w");
    if (hdv_ep_trace_fd == 0) begin
      $display("[HDV-TRACE] failed to open hdv_ep_trace_%s.log", testcase);
    end else begin
      $fwrite(hdv_ep_trace_fd, "# HDV execute-packet trace for TESTCASE=%s\n", testcase);
      $fwrite(hdv_ep_trace_fd, "# One EP is captured when VLIWPU hands it to HEU and printed when backend accepted fires.\n");
      $fwrite(hdv_ep_trace_fd, "# class: S=scalar, V=vector, SYS=system, BR=branch/control-flow\n");
    end
  end

  assign hdv_acknowledged_visible = i_hdv_mock_host_core.acknowledged_eps_q +
                                (hdv_ep_acknowledged ? 32'd1 : 32'd0);
  assign hdv_ep_trace_enqueue =
      dut.i_ara_soc.i_system.vliwpu_heu_execute_valid &
      dut.i_ara_soc.i_system.i_hybrid_execution_unit.heu_vliwpu_execute_ready_o;
  assign hdv_ep_trace_flush = dut.i_ara_soc.i_system.dispatch_flush;
  assign hdv_task_start_fire = hdv_host_csr_valid && hdv_host_csr_ready &&
                               hdv_host_csr_write &&
                               (hdv_host_csr_addr == hdv_pkg::HDV_CSR_VTASK_START);
  assign hdv_task_cycle_valid = hdv_task_cycle_active_q || hdv_task_start_fire;
  assign hdv_task_cycle_base_visible = hdv_task_start_fire ? wall_cycle :
                                       hdv_task_cycle_base_q;
  assign hdv_task_cycle = hdv_task_cycle_valid ?
                          (wall_cycle - hdv_task_cycle_base_visible) :
                          64'd0;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      hdv_mock_state_prev_q <= '0;
      hdv_task_cycle_active_q <= 1'b0;
      hdv_task_cycle_base_q <= '0;
      hdv_last_task_cycle_q <= '0;
      hdv_task_done_prev_q <= 1'b0;
      hdv_ep_trace_head_q <= 0;
      hdv_ep_trace_tail_q <= 0;
      hdv_ep_trace_count_q <= 0;
      hdv_ep_trace_enqueued_q <= '0;
      for (int unsigned q = 0; q < HdvEpTraceDepth; q++) begin
        hdv_ep_trace_enqueue_wall_q[q] <= '0;
        hdv_ep_trace_enqueue_task_q[q] <= '0;
        hdv_ep_trace_ep_pc_q[q] <= '0;
        hdv_ep_trace_insn_valid_q[q] <= '0;
        hdv_ep_trace_insn_is_32b_q[q] <= '0;
        hdv_ep_trace_insn_q[q] <= '0;
        hdv_ep_trace_insn_pc_q[q] <= '0;
        hdv_ep_trace_class_q[q] <= '0;
      end
    end else begin
      int unsigned trace_head_next;
      int unsigned trace_tail_next;
      int unsigned trace_count_next;

      trace_head_next = hdv_ep_trace_head_q;
      trace_tail_next = hdv_ep_trace_tail_q;
      trace_count_next = hdv_ep_trace_count_q;

      hdv_mock_state_prev_q <= i_hdv_mock_host_core.state_q;
      hdv_task_done_prev_q <= hdv_task_done;
      if (hdv_task_start_fire) begin
        hdv_task_cycle_active_q <= 1'b1;
        hdv_task_cycle_base_q <= wall_cycle;
        hdv_last_task_cycle_q <= '0;
        $display("[HDV-CSR] @%0t wall_cycle=%0d task_cycle=0 START entry=0x%016h desc=0x%016h expected_ep=%0d",
                 $time, wall_cycle,
                 i_hdv_mock_host_core.task_entry_q,
                 i_hdv_mock_host_core.task_desc_q,
                 i_hdv_mock_host_core.expected_ep_acknowledges_q);
        if (hdv_csr_verbose) begin
          $display("[HDV-CSR]   status busy=%0b done=%0b error=%0b mock_state=%0d tiu_valid=%0b tiu_done=%0b tiu_error=%0b tsu_active=%0b tsu_done=%0b tsu_error=%0b",
                   hdv_task_busy,
                   hdv_task_done,
                   hdv_task_error,
                   i_hdv_mock_host_core.state_q,
                   dut.i_ara_soc.i_system.i_task_interface_unit.task_valid_q,
                   dut.i_ara_soc.i_system.i_task_interface_unit.done_q,
                   dut.i_ara_soc.i_system.i_task_interface_unit.error_q,
                   dut.i_ara_soc.i_system.i_task_schedule_unit.active_q,
                   dut.i_ara_soc.i_system.i_task_schedule_unit.done_q,
                   dut.i_ara_soc.i_system.i_task_schedule_unit.error_q);
          $display("[HDV-CSR]   frontend ipu_state=%0d ipu_busy=%0b exec_base=0x%016h fetch_base=0x%016h exec_idx=%0d fill_req=%0d fill_rsp=%0d buf_a=0x%0h buf_b=0x%0h loop_auto=%0b loop_build=%0b loop_locked=%0b imem_outstanding=%0d trace_q=%0d",
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.state_q,
                   dut.i_ara_soc.i_system.ipu_top_busy,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_base_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fetch_base_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fill_req_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fill_rsp_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.buffer_a_valid_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.buffer_b_valid_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.auto_loop_lock_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.loop_build_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.loop_locked_q,
                   dut.i_ara_soc.i_system.imem_outstanding_q,
                   trace_count_next);
          $display("[HDV-CSR]   backends heu_busy=%0b heu_outstanding=%0b heu_buf=%0b scalar_pending=%0b vector_pending=%0b buf_vec_sent=%0b buf_vec_pending=%0b scalar_state=%0d scalar_insn_valid=0x%0h vec_busy=%0b vec_state=%0d vec_pending=%0b vq0=%0b vq1=%0b resp_meta=%0d",
                   dut.i_ara_soc.i_system.heu_top_busy,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_valid_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.scalar_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.vector_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_vector_sent_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_vector_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.state_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.insn_valid_q,
                   dut.i_ara_soc.i_system.vec_dispatch_busy,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.state_q,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.pending_valid_q,
                   (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q != '0),
                   (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q > 1),
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.resp_meta_count_q);
        end
        if (hdv_ep_trace_fd != 0) begin
          $fwrite(hdv_ep_trace_fd,
                  "[HDV-CSR] time=%0t wall_cycle=%0d task_cycle=0 VTASK_START[0] set wdata=0x%016h entry=0x%016h desc=0x%016h expected_ep=%0d mock_state=%0d ipu_state=%0d ipu_exec_base=0x%016h ipu_fetch_base=0x%016h imem_outstanding=%0d heu_outstanding=%0b heu_buf=%0b scalar_state=%0d vec_state=%0d vec_busy=%0b trace_q=%0d\n",
                  $time, wall_cycle,
                  hdv_host_csr_wdata,
                  i_hdv_mock_host_core.task_entry_q,
                  i_hdv_mock_host_core.task_desc_q,
                  i_hdv_mock_host_core.expected_ep_acknowledges_q,
                  i_hdv_mock_host_core.state_q,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.state_q,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_base_q,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fetch_base_q,
                  dut.i_ara_soc.i_system.imem_outstanding_q,
                  dut.i_ara_soc.i_system.i_hybrid_execution_unit.outstanding_q,
                  dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_valid_q,
                  dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.state_q,
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.state_q,
                  dut.i_ara_soc.i_system.vec_dispatch_busy,
                  trace_count_next);
        end
      end
      if (hdv_task_done && !hdv_task_done_prev_q) begin
        $display("[HDV-CSR] @%0t wall_cycle=%0d task_cycle=%0d DONE accepted=%0d expected=%0d vec_busy=%0b imem_outstanding=%0d",
                 $time, wall_cycle, hdv_task_cycle,
                 i_hdv_mock_host_core.acknowledged_eps_q,
                 i_hdv_mock_host_core.expected_ep_acknowledges_q,
                 dut.i_ara_soc.i_system.vec_dispatch_busy,
                 dut.i_ara_soc.i_system.imem_outstanding_q);
        if (hdv_csr_verbose) begin
          $display("[HDV-CSR]   completion request=%0b host_seen=%0b done_to_tsu=%0b scalar_task_complete=%0b task_busy=%0b task_done=%0b task_error=%0b vec_busy=%0b",
                   dut.i_ara_soc.i_system.task_complete_request,
                   dut.i_ara_soc.i_system.host_task_complete_seen_q,
                   dut.i_ara_soc.i_system.task_done_to_tsu,
                   dut.i_ara_soc.i_system.scalar_backend_task_complete,
                   hdv_task_busy,
                   hdv_task_done,
                   hdv_task_error,
                   dut.i_ara_soc.i_system.vec_dispatch_busy);
          $display("[HDV-CSR]   frontend ipu_state=%0d exec_base=0x%016h fetch_base=0x%016h exec_idx=%0d fill_req=%0d fill_rsp=%0d buf_a=0x%0h buf_b=0x%0h loop_auto=%0b loop_build=%0b loop_locked=%0b loop_exit_seen=%0b imem_outstanding=%0d redirect=%0b redirect_pc=0x%016h",
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.state_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_base_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fetch_base_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fill_req_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fill_rsp_idx_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.buffer_a_valid_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.buffer_b_valid_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.auto_loop_lock_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.loop_build_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.loop_locked_q,
                   dut.i_ara_soc.i_system.i_instruction_prefetch_unit.loop_exit_seen_q,
                   dut.i_ara_soc.i_system.imem_outstanding_q,
                   dut.i_ara_soc.i_system.hdv_ctrl_redirect_valid,
                   dut.i_ara_soc.i_system.hdv_ctrl_redirect_pc);
          $display("[HDV-CSR]   backends heu_outstanding=%0b heu_buf=%0b scalar_pending=%0b vector_pending=%0b buf_vec_sent=%0b buf_vec_pending=%0b scalar_state=%0d scalar_insn_valid=0x%0h scalar_redirect_pending=%0b scalar_task_complete_pending=%0b vec_state=%0d vec_pending=%0b real_wait=0x%0h vset_wait=%0d vq0=%0b vq1=%0b resp_meta=%0d",
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_valid_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.scalar_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.vector_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_vector_sent_q,
                   dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_vector_slice_outstanding_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.state_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.insn_valid_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.redirect_pending_q,
                   dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.task_complete_pending_q,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.state_q,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.pending_valid_q,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.real_wait_valid_q,
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.vset_accept_wait_q,
                   (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q != '0),
                   (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q > 1),
                   dut.i_ara_soc.i_system.i_vec_dispatch_unit.resp_meta_count_q);
        end
        if (hdv_ep_trace_fd != 0) begin
          $fwrite(hdv_ep_trace_fd,
                  "[HDV-CSR] time=%0t wall_cycle=%0d task_cycle=%0d VTASK_STATUS.DONE set accepted=%0d expected=%0d queued=%0d request=%0b host_seen=%0b done_to_tsu=%0b scalar_task_complete=%0b vec_busy=%0b ipu_state=%0d ipu_exec_base=0x%016h ipu_fetch_base=0x%016h imem_outstanding=%0d redirect=%0b redirect_pc=0x%016h heu_outstanding=%0b heu_buf=%0b scalar_state=%0d scalar_pending=0x%0h scalar_redirect_pending=%0b scalar_task_complete_pending=%0b vec_state=%0d vec_pending=%0b real_wait=0x%0h vset_wait=%0d vq0=%0b vq1=%0b resp_meta=%0d\n",
                  $time, wall_cycle, hdv_task_cycle,
                  i_hdv_mock_host_core.acknowledged_eps_q,
                  i_hdv_mock_host_core.expected_ep_acknowledges_q,
                  trace_count_next,
                  dut.i_ara_soc.i_system.task_complete_request,
                  dut.i_ara_soc.i_system.host_task_complete_seen_q,
                  dut.i_ara_soc.i_system.task_done_to_tsu,
                  dut.i_ara_soc.i_system.scalar_backend_task_complete,
                  dut.i_ara_soc.i_system.vec_dispatch_busy,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.state_q,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.exec_base_q,
                  dut.i_ara_soc.i_system.i_instruction_prefetch_unit.fetch_base_q,
                  dut.i_ara_soc.i_system.imem_outstanding_q,
                  dut.i_ara_soc.i_system.hdv_ctrl_redirect_valid,
                  dut.i_ara_soc.i_system.hdv_ctrl_redirect_pc,
                  dut.i_ara_soc.i_system.i_hybrid_execution_unit.outstanding_q,
                  dut.i_ara_soc.i_system.i_hybrid_execution_unit.buffer_valid_q,
                  dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.state_q,
                  dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.insn_valid_q,
                  dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.redirect_pending_q,
                  dut.i_ara_soc.i_system.i_cva6_hdv_scalar_backend.task_complete_pending_q,
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.state_q,
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.pending_valid_q,
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.real_wait_valid_q,
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.vset_accept_wait_q,
                  (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q != '0),
                  (dut.i_ara_soc.i_system.i_vec_dispatch_unit.vq_count_q > 1),
                  dut.i_ara_soc.i_system.i_vec_dispatch_unit.resp_meta_count_q);
          $fflush(hdv_ep_trace_fd);
        end
        hdv_last_task_cycle_q <= hdv_task_cycle;
        hdv_task_cycle_active_q <= 1'b0;
      end

      if (hdv_ep_acknowledged) begin
        if (trace_count_next != 0) begin
          int unsigned trace_idx;
          logic [HdvNumSlots-1:0] scalar_mask;
          logic [HdvNumSlots-1:0] vector_mask;
          logic [HdvNumSlots-1:0] branch_mask;
          logic [HdvNumSlots-1:0] system_mask;

          trace_idx = trace_head_next;
          scalar_mask = '0;
          vector_mask = '0;
          branch_mask = '0;
          system_mask = '0;
          for (int unsigned i = 0; i < HdvNumSlots; i++) begin
            if (hdv_ep_trace_insn_valid_q[trace_idx][i]) begin
              unique case (hdv_ep_trace_class_q[trace_idx][i])
                hdv_pkg::HDV_INST_SCALAR: scalar_mask[i] = 1'b1;
                hdv_pkg::HDV_INST_VECTOR: vector_mask[i] = 1'b1;
                hdv_pkg::HDV_INST_BRANCH: branch_mask[i] = 1'b1;
                hdv_pkg::HDV_INST_SYSTEM: system_mask[i] = 1'b1;
                default: begin
                end
              endcase
            end
          end

          if (hdv_ep_trace_fd != 0) begin
            $fwrite(hdv_ep_trace_fd,
                    "[EP %0d] accept_time=%0t accept_wall=%0d accept_task_cycle=%0d accepted_so_far=%0d enqueue_wall=%0d enqueue_task_cycle=%0d front_latency=%0d ep_pc=0x%016h valid=0x%0h scalar=0x%0h vector=0x%0h branch=0x%0h system=0x%0h scalar_ready=%0b scalar_accepted=%0b vec_busy=%0b task_busy=%0b\n",
                    hdv_acknowledged_visible,
                    $time,
                    wall_cycle,
                    hdv_task_cycle,
                    hdv_acknowledged_visible,
                    hdv_ep_trace_enqueue_wall_q[trace_idx],
                    hdv_ep_trace_enqueue_task_q[trace_idx],
                    wall_cycle - hdv_ep_trace_enqueue_wall_q[trace_idx],
                    hdv_ep_trace_ep_pc_q[trace_idx],
                    hdv_ep_trace_insn_valid_q[trace_idx],
                    scalar_mask,
                    vector_mask,
                    branch_mask,
                    system_mask,
                    hdv_scalar_ready,
                    hdv_scalar_ep_done,
                    dut.i_ara_soc.i_system.vec_dispatch_busy,
                    hdv_task_busy);
            for (int unsigned i = 0; i < HdvNumSlots; i++) begin
              if (hdv_ep_trace_insn_valid_q[trace_idx][i]) begin
                $fwrite(hdv_ep_trace_fd,
                        "  slot%0d class=%s pc=0x%016h insn=0x%08h is32=%0b\n",
                        i,
                        hdv_ep_class_name(hdv_ep_trace_class_q[trace_idx][i]),
                        hdv_ep_trace_insn_pc_q[trace_idx][i],
                        hdv_ep_trace_insn_q[trace_idx][i],
                        hdv_ep_trace_insn_is_32b_q[trace_idx][i]);
              end
            end
            $fflush(hdv_ep_trace_fd);
          end

          trace_head_next = (trace_head_next + 1) % HdvEpTraceDepth;
          trace_count_next--;
        end else if (hdv_ep_trace_fd != 0) begin
          $fwrite(hdv_ep_trace_fd,
                  "[EP %0d] accept_time=%0t accept_wall=%0d accept_task_cycle=%0d accepted_so_far=%0d WARNING=no queued EP snapshot\n",
                  hdv_acknowledged_visible,
                  $time,
                  wall_cycle,
                  hdv_task_cycle,
                  hdv_acknowledged_visible);
          $fflush(hdv_ep_trace_fd);
        end
      end

      if (hdv_ep_trace_flush) begin
        if ((trace_count_next != 0) && (hdv_ep_trace_fd != 0)) begin
          $fwrite(hdv_ep_trace_fd,
                  "[HDV-TRACE] time=%0t wall_cycle=%0d task_cycle=%0d flush drops queued_ep_snapshots=%0d\n",
                  $time, wall_cycle, hdv_task_cycle, trace_count_next);
          $fflush(hdv_ep_trace_fd);
        end
        trace_head_next = 0;
        trace_tail_next = 0;
        trace_count_next = 0;
      end

      if (hdv_ep_trace_enqueue && !hdv_ep_trace_flush) begin
        if (trace_count_next < HdvEpTraceDepth) begin
          int unsigned trace_idx;

          trace_idx = trace_tail_next;
          hdv_ep_trace_enqueue_wall_q[trace_idx] <= wall_cycle;
          hdv_ep_trace_enqueue_task_q[trace_idx] <= hdv_task_cycle;
          hdv_ep_trace_ep_pc_q[trace_idx] <= dut.i_ara_soc.i_system.vliwpu_heu_execute_pc;
          hdv_ep_trace_insn_valid_q[trace_idx] <= '0;
          hdv_ep_trace_insn_is_32b_q[trace_idx] <= '0;
          hdv_ep_trace_insn_q[trace_idx] <= '0;
          hdv_ep_trace_insn_pc_q[trace_idx] <= '0;
          hdv_ep_trace_class_q[trace_idx] <= '0;
          for (int unsigned i = 0; i < HdvNumSlots; i++) begin
            logic is_continuation;

            is_continuation = (i > 0) &&
                              dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_valid[i-1] &&
                              dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_is_32b[i-1];
            if (dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_valid[i] && !is_continuation) begin
              hdv_ep_trace_insn_valid_q[trace_idx][i] <= 1'b1;
              hdv_ep_trace_insn_is_32b_q[trace_idx][i] <=
                  dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_is_32b[i];
              hdv_ep_trace_insn_pc_q[trace_idx][i] <=
                  dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_pc[i];
              hdv_ep_trace_class_q[trace_idx][i] <=
                  dut.i_ara_soc.i_system.vliwpu_heu_execute_class[i];
              if (dut.i_ara_soc.i_system.vliwpu_heu_execute_slot_is_32b[i] &&
                  (i < HdvNumSlots-1)) begin
                hdv_ep_trace_insn_q[trace_idx][i] <= {
                    dut.i_ara_soc.i_system.vliwpu_heu_execute_slot[i+1],
                    dut.i_ara_soc.i_system.vliwpu_heu_execute_slot[i]
                };
              end else begin
                hdv_ep_trace_insn_q[trace_idx][i] <= {
                    16'b0,
                    dut.i_ara_soc.i_system.vliwpu_heu_execute_slot[i]
                };
              end
            end
          end
          trace_tail_next = (trace_tail_next + 1) % HdvEpTraceDepth;
          trace_count_next++;
          hdv_ep_trace_enqueued_q <= hdv_ep_trace_enqueued_q + 1'b1;
        end else if (hdv_ep_trace_fd != 0) begin
          $fwrite(hdv_ep_trace_fd,
                  "[HDV-TRACE] time=%0t wall_cycle=%0d task_cycle=%0d WARNING=EP snapshot queue overflow\n",
                  $time, wall_cycle, hdv_task_cycle);
          $fflush(hdv_ep_trace_fd);
        end
      end

      hdv_ep_trace_head_q <= trace_head_next;
      hdv_ep_trace_tail_q <= trace_tail_next;
      hdv_ep_trace_count_q <= trace_count_next;

      // Only print once on the cycle the state first enters FINISH/FAIL, then stop.
      if (i_hdv_mock_host_core.state_q == 4'd9 && hdv_mock_state_prev_q != 4'd9) begin
        $display("[HDV] @%0t cycle=%0d mock host FINISH — HDV pipeline test PASSED (expected %0d EPs, got %0d, total_task_cycles=%0d)",
                 $time, hdv_last_task_cycle_q,
                 i_hdv_mock_host_core.expected_ep_acknowledges_q,
                 hdv_acknowledged_visible,
                 hdv_last_task_cycle_q);
        // ── Dump vector-command-path performance counters ──────────
        $display("[HDV-PERF] ── vector command path counters ──");
        $display("[HDV-PERF]   dispatch_slots        = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_dispatch_slot);
        $display("[HDV-PERF]   vq_push               = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_vq_push);
        $display("[HDV-PERF]   vq_bypass             = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_vq_bypass);
        $display("[HDV-PERF]   vq_pop                = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_vq_pop);
        $display("[HDV-PERF]   vq_full_stall         = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_vq_full_stall);
        $display("[HDV-PERF]   ara_backpressure      = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_ara_backpressure);
        $display("[HDV-PERF]   fsm_could_bypass      = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_fsm_idle_could_dispatch);
        $display("[HDV-PERF]   ep_acknowledged       = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_ep_acknowledged);
        $display("[HDV-PERF]   ep_vset_acknowledged = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_ep_vset_acknowledged);
        $display("[HDV-PERF]   operand_wait_cycles   = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_operand_wait);
        $display("[HDV-PERF]   resp_meta_full_stall  = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_resp_meta_full_stall);
        $display("[HDV-PERF]   real_wait_full_stall  = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_real_wait_full_stall);
        $display("[HDV-PERF]   vq_max_occupancy      = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_vq_max_occupancy);
        $display("[HDV-PERF]   resp_meta_max         = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_resp_meta_max);
        $display("[HDV-PERF]   dispatch_total_cycles = %0d", dut.i_ara_soc.i_system.i_vec_dispatch_unit.cnt_dispatch_total_cycles);
        // Let outstanding vector stores drain to L2 before ending (perf counters
        // are already captured above; this only affects the L2 write monitor).
        fork begin : drain_finish
          repeat (400) @(posedge clk);
          $finish;
        end join_none
      end
      if (i_hdv_mock_host_core.state_q == 4'd10 && hdv_mock_state_prev_q != 4'd10) begin
        $display("[HDV] @%0t cycle=%0d mock host FAIL — HDV pipeline test FAILED (expected %0d EPs, got %0d, total_task_cycles=%0d)",
                 $time, hdv_task_cycle,
                 i_hdv_mock_host_core.expected_ep_acknowledges_q,
                 i_hdv_mock_host_core.acknowledged_eps_q,
                 hdv_task_cycle);
        $display("[HDV]   fail_reason task_error=%0b ep_error=%0b packet_timeout=%0b task_timeout=%0b task_busy=%0b task_done=%0b vec_busy=%0b imem_outstanding=%0d",
                 hdv_task_error,
                 hdv_ep_error,
                 i_hdv_mock_host_core.packet_timeout,
                 i_hdv_mock_host_core.task_timeout,
                 hdv_task_busy,
                 hdv_task_done,
                 dut.i_ara_soc.i_system.vec_dispatch_busy,
                 dut.i_ara_soc.i_system.imem_outstanding_q);
        $finish;
      end
    end
  end
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
`else
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

`ifdef FOR_VERIFY
  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      seq_raw_hazard_cycle   <= '0;
      seq_war_hazard_cycle   <= '0;
      seq_waw_hazard_cycle   <= '0;
      seq_false_hazard_cycle <= '0;
      seq_block_cycle        <= '0;
    end
    else begin
      seq_raw_hazard_cycle   <= seq_raw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard;
      seq_war_hazard_cycle   <= seq_war_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard;
      seq_waw_hazard_cycle   <= seq_waw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard;
      seq_false_hazard_cycle <= seq_false_hazard_cycle + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.false_hazard;
      seq_block_cycle        <= seq_block_cycle        + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block;
    end
  end
`endif

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
`ifdef TARGET_GATESIM
      // GATESIM mode: CVA6 present, track RVV commits from commit stage
      if (|ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1:0]) begin
        rvv_instret  <= rvv_instret + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].fu == 4'b1010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].fu == 4'b1010));
        rvv_op       <= rvv_op       + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110110)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110110));
        rvv_op_fs1   <= rvv_op_fs1   + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10110111)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10110111));
        rvv_op_fd    <= rvv_op_fd    + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111000)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111000));
        rvv_op_load  <= rvv_op_load  + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111001)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111001));
        rvv_op_store <= rvv_op_store + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].op[7:0] == 8'b10111010)) + (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] && (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].op[7:0] == 8'b10111010));
      end else begin
        rvv_instret  <= rvv_instret;
        rvv_op       <= rvv_op      ;
        rvv_op_fs1   <= rvv_op_fs1  ;
        rvv_op_fd    <= rvv_op_fd   ;
        rvv_op_load  <= rvv_op_load ;
        rvv_op_store <= rvv_op_store;
      end
`else
      // HDV RTL mode: no CVA6, RVV commit counters not available
      rvv_instret  <= rvv_instret;
      rvv_op       <= rvv_op;
      rvv_op_fs1   <= rvv_op_fs1;
      rvv_op_fd    <= rvv_op_fd;
      rvv_op_load  <= rvv_op_load;
      rvv_op_store <= rvv_op_store;
`endif
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
`ifdef TARGET_GATESIM
    // GATESIM mode: CVA6 present, detect rdcycle CSR read to toggle perf window
    if(ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_csr_o &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.csr_regfile_i.csr_addr_i[11:0] == 12'hc00 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.csr_op_o[7:0] == 8'b100010 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.waddr_o[0][4:0] == 5'h0 &&
            ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.we_gpr_o[0]) begin
      perf_time_n = !perf_time_q;
    end
`endif
    // HDV RTL mode: no CVA6, perf window never toggled automatically
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

`ifdef FOR_VERIFY
  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      seq_raw_hazard_cycle   <= '0;
      seq_war_hazard_cycle   <= '0;
      seq_waw_hazard_cycle   <= '0;
      seq_false_hazard_cycle <= '0;
      seq_block_cycle        <= '0;
    end
    else begin
      seq_raw_hazard_cycle   <= seq_raw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.raw_hazard;
      seq_war_hazard_cycle   <= seq_war_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.war_hazard;
      seq_waw_hazard_cycle   <= seq_waw_hazard_cycle   + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.waw_hazard;
      seq_false_hazard_cycle <= seq_false_hazard_cycle + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.false_hazard;
      seq_block_cycle        <= seq_block_cycle        + ara_tb.dut.i_ara_soc.i_system.i_ara.i_sequencer.sequencer_block;
    end
  end
`endif

  initial begin
    #15.5;
    perf_start_n = get_perf_counters();
    perf_monitor = 1'b1;
  end

  final begin
    perf_end_n = get_perf_counters();
    print_perf_report();
    print_perf_csv();
  end

`endif
`endif

endmodule : ara_tb
