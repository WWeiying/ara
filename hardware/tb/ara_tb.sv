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
  logic [63:0] tc_executed_ifetch_bytes;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
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
    counters.tc_executed_ifetch_bytes = ara_tb.tc_executed_ifetch_bytes;
    counters.rvv_axi_aw_count = ara_tb.rvv_axi_aw_count;
    counters.rvv_axi_w_count  = ara_tb.rvv_axi_w_count ;
    counters.rvv_axi_b_count  = ara_tb.rvv_axi_b_count ;
    counters.rvv_axi_ar_count = ara_tb.rvv_axi_ar_count;
    counters.rvv_axi_r_count  = ara_tb.rvv_axi_r_count ;
    counters.ara_req_valid_cycles  = ara_tb.ara_req_valid_cycles;
    counters.ara_req_fire_count    = ara_tb.ara_req_fire_count;
    counters.ara_req_blocked_cycles = ara_tb.ara_req_blocked_cycles;
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
      int total_tc_executed_ifetch_bytes;
      int total_rvv_axi_aw_count;
      int total_rvv_axi_w_count ;
      int total_rvv_axi_b_count ;
      int total_rvv_axi_ar_count;
      int total_rvv_axi_r_count ;
      int total_ara_req_valid_cycles;
      int total_ara_req_fire_count;
      int total_ara_req_blocked_cycles;
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
      real main_vector_inst_per_cycle;
      real main_vector_req_per_cycle;
      real main_vector_req_blocked_ratio;
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
      total_tc_executed_ifetch_bytes =
          ara_tb.perf_end_n.tc_executed_ifetch_bytes -
          ara_tb.perf_start_n.tc_executed_ifetch_bytes;
      total_rvv_axi_aw_count = ara_tb.perf_end_n.rvv_axi_aw_count - ara_tb.perf_start_n.rvv_axi_aw_count;
      total_rvv_axi_w_count  = ara_tb.perf_end_n.rvv_axi_w_count  - ara_tb.perf_start_n.rvv_axi_w_count ;
      total_rvv_axi_b_count  = ara_tb.perf_end_n.rvv_axi_b_count  - ara_tb.perf_start_n.rvv_axi_b_count ;
      total_rvv_axi_ar_count = ara_tb.perf_end_n.rvv_axi_ar_count - ara_tb.perf_start_n.rvv_axi_ar_count;
      total_rvv_axi_r_count  = ara_tb.perf_end_n.rvv_axi_r_count  - ara_tb.perf_start_n.rvv_axi_r_count ;
      total_ara_req_valid_cycles  = ara_tb.perf_end_n.ara_req_valid_cycles  - ara_tb.perf_start_n.ara_req_valid_cycles;
      total_ara_req_fire_count    = ara_tb.perf_end_n.ara_req_fire_count    - ara_tb.perf_start_n.ara_req_fire_count;
      total_ara_req_blocked_cycles = ara_tb.perf_end_n.ara_req_blocked_cycles - ara_tb.perf_start_n.ara_req_blocked_cycles;
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
      main_vector_inst_per_cycle = real'(total_vector_insns) / total_cycles;
      main_vector_req_per_cycle = real'(total_ara_req_fire_count) / total_cycles;
      main_vector_req_blocked_ratio = real'(total_ara_req_blocked_cycles) / total_cycles;
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
      $display("[PERF] tc_executed_ifetch_bytes   : %0d", total_tc_executed_ifetch_bytes);
      $display("[PERF] IPC                        : %0.3f", ipc);
      $display("[PERF] lane utilization           : %0.3f", lane_utilization);
      $display("[PERF] vector inst rate           : %0.3f", vecinst_rate);
      $display("[PERF] main_vector_inst_per_cycle : %0.6f", main_vector_inst_per_cycle);
      $display("[PERF] ara_req_valid_cycles       : %0d", total_ara_req_valid_cycles);
      $display("[PERF] ara_req_fire_count         : %0d", total_ara_req_fire_count);
      $display("[PERF] ara_req_blocked_cycles     : %0d", total_ara_req_blocked_cycles);
      $display("[PERF] main_vector_req_per_cycle  : %0.3f", main_vector_req_per_cycle);
      $display("[PERF] main_vector_req_blocked_ratio: %0.3f", main_vector_req_blocked_ratio);
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
      $fwrite(file_handle, "[PERF] tc_executed_ifetch_bytes   : %0d\n", total_tc_executed_ifetch_bytes);
      $fwrite(file_handle, "[PERF] IPC                        : %0.3f\n", ipc);
      $fwrite(file_handle, "[PERF] lane utilization           : %0.3f\n", lane_utilization);
      $fwrite(file_handle, "[PERF] vector inst rate           : %0.3f\n", vecinst_rate);
      $fwrite(file_handle, "[PERF] main_vector_inst_per_cycle : %0.6f\n", main_vector_inst_per_cycle);
      $fwrite(file_handle, "[PERF] ara_req_valid_cycles       : %0d\n", total_ara_req_valid_cycles);
      $fwrite(file_handle, "[PERF] ara_req_fire_count         : %0d\n", total_ara_req_fire_count);
      $fwrite(file_handle, "[PERF] ara_req_blocked_cycles     : %0d\n", total_ara_req_blocked_cycles);
      $fwrite(file_handle, "[PERF] main_vector_req_per_cycle  : %0.3f\n", main_vector_req_per_cycle);
      $fwrite(file_handle, "[PERF] main_vector_req_blocked_ratio: %0.3f\n", main_vector_req_blocked_ratio);
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
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
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
    counters.ara_req_valid_cycles   = ara_tb.ara_req_valid_cycles;
    counters.ara_req_fire_count     = ara_tb.ara_req_fire_count;
    counters.ara_req_blocked_cycles = ara_tb.ara_req_blocked_cycles;
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
      int total_ara_req_valid_cycles;
      int total_ara_req_fire_count;
      int total_ara_req_blocked_cycles;
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
      real main_vector_req_per_cycle;
      real main_vector_req_blocked_ratio;
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
      total_ara_req_valid_cycles  = ara_tb.perf_end_n.ara_req_valid_cycles - ara_tb.perf_start_n.ara_req_valid_cycles;
      total_ara_req_fire_count    = ara_tb.perf_end_n.ara_req_fire_count - ara_tb.perf_start_n.ara_req_fire_count;
      total_ara_req_blocked_cycles = ara_tb.perf_end_n.ara_req_blocked_cycles - ara_tb.perf_start_n.ara_req_blocked_cycles;

`ifdef FOR_VERIFY
      total_seq_raw_hazard_cycle   = ara_tb.perf_end_n.seq_raw_hazard_cycle   - ara_tb.perf_start_n.seq_raw_hazard_cycle;
      total_seq_war_hazard_cycle   = ara_tb.perf_end_n.seq_war_hazard_cycle   - ara_tb.perf_start_n.seq_war_hazard_cycle;
      total_seq_waw_hazard_cycle   = ara_tb.perf_end_n.seq_waw_hazard_cycle   - ara_tb.perf_start_n.seq_waw_hazard_cycle;
      total_seq_false_hazard_cycle = ara_tb.perf_end_n.seq_false_hazard_cycle - ara_tb.perf_start_n.seq_false_hazard_cycle;
      total_seq_block_cycle        = ara_tb.perf_end_n.seq_block_cycle        - ara_tb.perf_start_n.seq_block_cycle;
`endif

      lane_utilization = real'(total_rvv_lane_cycles) / total_rvv_cycles;
      main_vector_req_per_cycle = real'(total_ara_req_fire_count) / total_rvv_cycles;
      main_vector_req_blocked_ratio = real'(total_ara_req_blocked_cycles) / total_rvv_cycles;
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
      $display("[PERF] ara_req_valid_cycles           : %0d", total_ara_req_valid_cycles);
      $display("[PERF] ara_req_fire_count             : %0d", total_ara_req_fire_count);
      $display("[PERF] ara_req_blocked_cycles         : %0d", total_ara_req_blocked_cycles);
      $display("[PERF] main_vector_req_per_cycle      : %0.3f", main_vector_req_per_cycle);
      $display("[PERF] main_vector_req_blocked_ratio  : %0.3f", main_vector_req_blocked_ratio);
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
      $fwrite(file_handle, "[PERF] ara_req_valid_cycles       : %0d\n", total_ara_req_valid_cycles);
      $fwrite(file_handle, "[PERF] ara_req_fire_count         : %0d\n", total_ara_req_fire_count);
      $fwrite(file_handle, "[PERF] ara_req_blocked_cycles     : %0d\n", total_ara_req_blocked_cycles);
      $fwrite(file_handle, "[PERF] main_vector_req_per_cycle  : %0.3f\n", main_vector_req_per_cycle);
      $fwrite(file_handle, "[PERF] main_vector_req_blocked_ratio: %0.3f\n", main_vector_req_blocked_ratio);
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

  `ifdef SIM_L2_SIZE_BYTES
  localparam int unsigned L2SizeBytes = `SIM_L2_SIZE_BYTES;
  `else
  localparam int unsigned L2SizeBytes = 1 << 20;
  `endif

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
  logic [63:0] tc_executed_ifetch_bytes;
  logic [63:0] rvv_axi_aw_count;
  logic [63:0] rvv_axi_w_count;
  logic [63:0] rvv_axi_b_count;
  logic [63:0] rvv_axi_ar_count;
  logic [63:0] rvv_axi_r_count;
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
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
  logic [63:0] ara_req_valid_cycles;
  logic [63:0] ara_req_fire_count;
  logic [63:0] ara_req_blocked_cycles;
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
`ifndef ARA_NO_FSDB
    if (!$test$plusargs("NO_FSDB")) begin
      $fsdbDumpfile("ara_tb.fsdb");
      $fsdbDumpvars(0, ara_tb);
      $fsdbDumpMDA(0, ara_tb);
      $fsdbDumpvars("+all");
    end
`endif

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
    .L2SizeBytes (L2SizeBytes     ),
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
    addr_t word_addr;
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
          word_addr = address + (w << AxiWideByteOffset);
          if (word_addr >= DRAMAddrBase &&
              word_addr < DRAMAddrBase + L2SizeBytes) begin
            // Sections must be aligned to AxiWideByteOffset.
            dut.i_ara_soc.i_dram.init_val[
                (word_addr - DRAMAddrBase) >> AxiWideByteOffset] = mem_row;
          end else begin
            $fatal(1,
                   "ELF address 0x%016h exceeds the %0d-byte simulation L2; rebuild the app and simulator with the same sim_l2_mb",
                   word_addr, L2SizeBytes);
          end
        end
      end
    end else begin
      $error("Expecting a firmware to run, none was provided!");
      $finish;
    end
  end : dram_init
  `endif

`ifndef TARGET_GATESIM
  // ara_soc decodes a larger architectural DRAM window than the behavioral
  // simulation SRAM implements. The runtime deliberately places the stack in
  // an equally sized window at the top of architectural DRAM; reject only the
  // unmapped middle so an undersized simulation SRAM cannot silently alias it.
  always_ff @(posedge clk) begin
    if (rst_n) begin
      if (dut.i_ara_soc.system_axi_req.ar_valid &&
          dut.i_ara_soc.system_axi_resp.ar_ready &&
          dut.i_ara_soc.system_axi_req.ar.addr >= DRAMAddrBase + L2SizeBytes &&
          dut.i_ara_soc.system_axi_req.ar.addr <
              DRAMAddrBase + DRAMLength - L2SizeBytes)
        $fatal(1,
               "AXI read address 0x%016h exceeds the %0d-byte simulation L2",
               dut.i_ara_soc.system_axi_req.ar.addr, L2SizeBytes);

      if (dut.i_ara_soc.system_axi_req.aw_valid &&
          dut.i_ara_soc.system_axi_resp.aw_ready &&
          dut.i_ara_soc.system_axi_req.aw.addr >= DRAMAddrBase + L2SizeBytes &&
          dut.i_ara_soc.system_axi_req.aw.addr <
              DRAMAddrBase + DRAMLength - L2SizeBytes)
        $fatal(1,
               "AXI write address 0x%016h exceeds the %0d-byte simulation L2",
               dut.i_ara_soc.system_axi_req.aw.addr, L2SizeBytes);
    end
  end
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

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      ara_req_valid_cycles   <= '0;
      ara_req_fire_count     <= '0;
      ara_req_blocked_cycles <= '0;
    end
    else begin
      ara_req_valid_cycles   <= ara_req_valid_cycles +
        ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid;
      ara_req_fire_count     <= ara_req_fire_count +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
      ara_req_blocked_cycles <= ara_req_blocked_cycles +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         !ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
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
      tc_executed_ifetch_bytes <= '0;
    end
    else begin
      tc_executed_ifetch_bytes <= tc_executed_ifetch_bytes +
        (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_macro_ack_o[0] ?
          (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].is_compressed ?
            64'd2 : 64'd4) : 64'd0) +
        (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_macro_ack_o[1] ?
          (ara_tb.dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].is_compressed ?
            64'd2 : 64'd4) : 64'd0);
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

  always_ff @(posedge clk, negedge rst_n) begin
    if(!rst_n) begin
      ara_req_valid_cycles   <= '0;
      ara_req_fire_count     <= '0;
      ara_req_blocked_cycles <= '0;
    end
    else begin
      ara_req_valid_cycles   <= ara_req_valid_cycles +
        ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid;
      ara_req_fire_count     <= ara_req_fire_count +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
      ara_req_blocked_cycles <= ara_req_blocked_cycles +
        (ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
         !ara_tb.dut.i_ara_soc.i_system.i_ara.ara_req_ready);
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

`ifndef SAIF
`ifndef IDEAL_DISPATCHER
  logic [NrLanes-1:0][1:0] llm_alu_operand_fire;
  logic [NrLanes-1:0][2:0] llm_mfpu_operand_fire;
  logic [NrLanes-1:0] llm_lane_inflight;
  logic [NrLanes-1:0] llm_alu_exec_fire;
  logic [NrLanes-1:0] llm_int_mul_exec_fire;
  logic [NrLanes-1:0] llm_int_mac_exec_fire;
  logic [NrLanes-1:0][3:0] llm_int_mul_exec_elements;
  rvv_pkg::vew_e [NrLanes-1:0] llm_int_mul_exec_vsew;
  logic [NrLanes-1:0] llm_int_div_exec_fire;
  logic [NrLanes-1:0] llm_fp_exec_fire;
  logic [NrLanes-1:0] llm_fp_reduction_active;
  logic [NrLanes-1:0] llm_alu_result_fire;
  logic [NrLanes-1:0] llm_mfpu_result_fire;
  logic [NrLanes-1:0][7:0] llm_alu_result_be;
  logic [NrLanes-1:0][7:0] llm_mfpu_result_be;

  for (genvar lane = 0; lane < NrLanes; lane++) begin : gen_llm_lane_activity
    assign llm_lane_inflight[lane] =
      |dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_vinsn_running_q[lane];
    assign llm_alu_operand_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.alu_operand_valid_i &
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.alu_operand_ready_o;
    assign llm_mfpu_operand_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.mfpu_operand_valid_i &
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.mfpu_operand_ready_o;
    assign llm_alu_exec_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_valu.valu_valid;
    assign llm_int_mul_exec_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vmul_in_valid &&
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vmul_in_ready;
    assign llm_int_mac_exec_fire[lane] = llm_int_mul_exec_fire[lane] &&
      (dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.op
       inside {VMACC, VNMSAC, VMADD, VNMSUB});
    assign llm_int_mul_exec_elements[lane] = llm_int_mul_exec_fire[lane] ?
      ($countones(dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.issue_be) >>
       unsigned'(dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew)) : '0;
    assign llm_int_mul_exec_vsew[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vinsn_issue_q.vtype.vsew;
    assign llm_int_div_exec_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vdiv_in_valid &&
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vdiv_in_ready;
    assign llm_fp_exec_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vfpu_in_valid &&
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.vfpu_in_ready;
    assign llm_fp_reduction_active[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.i_vfus.i_vmfpu.mfpu_state_q != 3'd0;
    assign llm_alu_result_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.alu_result_req &&
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.alu_result_gnt;
    assign llm_mfpu_result_fire[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.mfpu_result_req &&
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.mfpu_result_gnt;
    assign llm_alu_result_be[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.alu_result_be;
    assign llm_mfpu_result_be[lane] =
      dut.i_ara_soc.i_system.i_ara.gen_lanes[lane].i_lane.mfpu_result_be;
  end

  llm_perf_monitor #(
    .NrLanes       (NrLanes),
    .NrVFUs        (ara_pkg::NrVFUs),
    .NrVInsn       (ara_pkg::NrVInsn),
    .VLenWidth     ($clog2(VLEN + 1)),
    .AxiDataWidth  (AxiWideDataWidth),
    .QueueCountWidth(cf_math_pkg::idx_width(ara_pkg::MaxVInsnQueueDepth + 1))
  ) i_llm_perf_monitor (
    .clk_i          (clk),
    .rst_ni         (rst_n),
    .active_i       (perf_time_q),
    .phase_i        (dut.i_ara_soc.hw_cnt_en_o[15:8]),
    .retired_inst_count_i($countones(
      dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1:0])),
    .retired_vector_inst_count_i($countones({
      dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[1] &&
        dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[1].fu ==
          ariane_pkg::ACCEL,
      dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_ack_o[0] &&
        dut.i_ara_soc.i_system.i_ariane.commit_stage_i.commit_instr_i[0].fu ==
          ariane_pkg::ACCEL})),
    .req_valid_i    (dut.i_ara_soc.i_system.i_ara.ara_req_valid),
    .req_ready_i    (dut.i_ara_soc.i_system.i_ara.ara_req_ready),
    .req_op_i       (dut.i_ara_soc.i_system.i_ara.ara_req.op),
    .req_vl_i       (dut.i_ara_soc.i_system.i_ara.ara_req.vl),
    .req_vsew_i     (dut.i_ara_soc.i_system.i_ara.ara_req.vtype.vsew),
    .req_cvt_resize_i(dut.i_ara_soc.i_system.i_ara.ara_req.cvt_resize),
    .req_vm_i       (dut.i_ara_soc.i_system.i_ara.ara_req.vm),
    .req_nf_i       (dut.i_ara_soc.i_system.i_ara.ara_req.nf),
    .ara_idle_i     (dut.i_ara_soc.i_system.i_ara.ara_idle),
    .lane_active_i  (rvv_lane_en),
    .lane_inflight_i(llm_lane_inflight),
    .lane_alu_operand_fire_i (llm_alu_operand_fire),
    .lane_mfpu_operand_fire_i(llm_mfpu_operand_fire),
    .alu_exec_fire_i         (llm_alu_exec_fire),
    .int_mul_exec_fire_i     (llm_int_mul_exec_fire),
    .int_mac_exec_fire_i     (llm_int_mac_exec_fire),
    .int_mul_exec_elements_i (llm_int_mul_exec_elements),
    .int_mul_exec_vsew_i     (llm_int_mul_exec_vsew),
    .int_div_exec_fire_i     (llm_int_div_exec_fire),
    .fp_exec_fire_i          (llm_fp_exec_fire),
    .fp_reduction_active_i    (|llm_fp_reduction_active),
    .alu_result_fire_i       (llm_alu_result_fire),
    .mfpu_result_fire_i      (llm_mfpu_result_fire),
    .alu_result_be_i         (llm_alu_result_be),
    .mfpu_result_be_i        (llm_mfpu_result_be),
    .queue_occ_i    (dut.i_ara_soc.i_system.i_ara.i_sequencer.insn_queue_cnt_q),
    .queue_ready_i  (dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_ready),
    .vinsn_running_i(dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_q),
    .queue_resource_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      !(&dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_queue_issue)),
    .no_vid_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      dut.i_ara_soc.i_system.i_ara.i_sequencer.vinsn_running_full),
    .lane_desync_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      dut.i_ara_soc.i_system.i_ara.i_sequencer.stall_lanes_desynch),
    .operand_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      !(&dut.i_ara_soc.i_system.i_ara.i_sequencer.operand_requester_ready)),
    .mask_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      !dut.i_ara_soc.i_system.i_ara.i_sequencer.mask_requester_ready),
    .slide_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      !dut.i_ara_soc.i_system.i_ara.i_sequencer.slide_requester_ready),
    .hazard_block_i(
      dut.i_ara_soc.i_system.i_ara.ara_req_valid &&
      !dut.i_ara_soc.i_system.i_ara.ara_req_ready &&
      dut.i_ara_soc.i_system.i_ara.i_sequencer.multi_reader_war),
    .scalar_result_wait_i(
      dut.i_ara_soc.i_system.i_ara.i_sequencer.state_q == 1'b1 &&
      dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_req_o.op inside
        {VMVXS, VFMVFS, VCPOP, VFIRST} &&
      !dut.i_ara_soc.i_system.i_ara.i_sequencer.pe_scalar_resp_valid_i),
    .axi_ar_valid_i(dut.i_ara_soc.i_system.i_ara.axi_req_o.ar_valid),
    .axi_ar_ready_i(dut.i_ara_soc.i_system.i_ara.axi_resp_i.ar_ready),
    .axi_ar_len_i  (dut.i_ara_soc.i_system.i_ara.axi_req_o.ar.len),
    .axi_ar_size_i (dut.i_ara_soc.i_system.i_ara.axi_req_o.ar.size),
    .axi_r_valid_i (dut.i_ara_soc.i_system.i_ara.axi_resp_i.r_valid),
    .axi_r_ready_i (dut.i_ara_soc.i_system.i_ara.axi_req_o.r_ready),
    .axi_r_last_i  (dut.i_ara_soc.i_system.i_ara.axi_resp_i.r.last),
    .axi_aw_valid_i(dut.i_ara_soc.i_system.i_ara.axi_req_o.aw_valid),
    .axi_aw_ready_i(dut.i_ara_soc.i_system.i_ara.axi_resp_i.aw_ready),
    .axi_aw_len_i  (dut.i_ara_soc.i_system.i_ara.axi_req_o.aw.len),
    .axi_aw_size_i (dut.i_ara_soc.i_system.i_ara.axi_req_o.aw.size),
    .axi_w_valid_i (dut.i_ara_soc.i_system.i_ara.axi_req_o.w_valid),
    .axi_w_ready_i (dut.i_ara_soc.i_system.i_ara.axi_resp_i.w_ready),
    .axi_w_strb_i  (dut.i_ara_soc.i_system.i_ara.axi_req_o.w.strb),
    .axi_b_valid_i (dut.i_ara_soc.i_system.i_ara.axi_resp_i.b_valid),
    .axi_b_ready_i (dut.i_ara_soc.i_system.i_ara.axi_req_o.b_ready)
  );
`endif
`endif

endmodule : ara_tb
