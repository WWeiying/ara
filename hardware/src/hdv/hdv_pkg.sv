// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Common declarations for the standalone Hybrid Decoupled Vector (HDV)
// prototype blocks.  The top-level wrapper instantiates Ara as the vector
// backend shell while the frontend blocks remain reusable standalone units.

package hdv_pkg;

  localparam logic [11:0] HDV_CSR_VTASK_ADDR   = 12'h7c0;
  localparam logic [11:0] HDV_CSR_VTASK_PADDR  = 12'h7c1;
  localparam logic [11:0] HDV_CSR_VTASK_START  = 12'h7c2;
  localparam logic [11:0] HDV_CSR_VTASK_STATUS = 12'h7c3;

  typedef enum logic [1:0] {
    HDV_INST_SCALAR = 2'b00,
    HDV_INST_VECTOR = 2'b01,
    HDV_INST_SYSTEM = 2'b10,
    HDV_INST_BRANCH = 2'b11
  } hdv_inst_class_e;

  typedef struct packed {
    logic busy;
    logic done;
    logic error;
  } hdv_task_status_t;

endpackage : hdv_pkg
