// Copyright 2026 Institute of Automation, Chinese Academy of Sciences.
// Solderpad Hardware License, Version 0.51, see LICENSE for details.
// SPDX-License-Identifier: SHL-0.51
//
// Description:
// Task Interface Unit (TIU) for the HDV prototype.  The module exposes the
// four paper-level task CSRs through a minimal CSR-like ready/valid port and
// emits task descriptors to the Task Schedule Unit.

module hdv_task_interface_unit import hdv_pkg::*; #(
  parameter int unsigned XLEN = 64,
  parameter type addr_t = logic [XLEN-1:0]
) (
  input  logic         clk_i,
  input  logic         rst_ni,

  input  logic         csr_valid_i,
  input  logic         csr_write_i,
  input  logic [11:0]  csr_addr_i,
  input  logic [XLEN-1:0] csr_wdata_i,
  output logic         csr_ready_o,
  output logic [XLEN-1:0] csr_rdata_o,
  output logic         csr_error_o,

  output logic         task_valid_o,
  input  logic         task_ready_i,
  output addr_t        task_entry_o,
  output addr_t        task_desc_o,

  input  logic         task_busy_i,
  input  logic         task_done_i,
  input  logic         task_error_i,
  output logic         task_status_clear_o
);

  addr_t vtask_addr_d,  vtask_addr_q;
  addr_t vtask_paddr_d, vtask_paddr_q;
  logic  task_valid_d,  task_valid_q;
  logic  done_d,        done_q;
  logic  error_d,       error_q;
  logic  start_pulse;

  assign csr_ready_o = 1'b1;
  assign csr_error_o = csr_valid_i
                     & (csr_addr_i != HDV_CSR_VTASK_ADDR)
                     & (csr_addr_i != HDV_CSR_VTASK_PADDR)
                     & (csr_addr_i != HDV_CSR_VTASK_START)
                     & (csr_addr_i != HDV_CSR_VTASK_STATUS);

  assign task_valid_o = task_valid_q;
  assign task_entry_o = vtask_addr_q;
  assign task_desc_o  = vtask_paddr_q;

  assign start_pulse = csr_valid_i & csr_write_i
                     & (csr_addr_i == HDV_CSR_VTASK_START)
                     & csr_wdata_i[0];

  always_comb begin : p_read_mux
    csr_rdata_o = '0;
    unique case (csr_addr_i)
      HDV_CSR_VTASK_ADDR: begin
        csr_rdata_o = vtask_addr_q;
      end
      HDV_CSR_VTASK_PADDR: begin
        csr_rdata_o = vtask_paddr_q;
      end
      HDV_CSR_VTASK_START: begin
        csr_rdata_o[0] = task_valid_q;
      end
      HDV_CSR_VTASK_STATUS: begin
        csr_rdata_o[0] = task_busy_i | task_valid_q;
        csr_rdata_o[1] = done_q;
        csr_rdata_o[2] = error_q;
      end
      default: begin
        csr_rdata_o = '0;
      end
    endcase
  end

  always_comb begin : p_next
    vtask_addr_d         = vtask_addr_q;
    vtask_paddr_d        = vtask_paddr_q;
    task_valid_d         = task_valid_q;
    done_d               = done_q;
    error_d              = error_q;
    task_status_clear_o  = 1'b0;

    if (csr_valid_i && csr_write_i) begin
      unique case (csr_addr_i)
        HDV_CSR_VTASK_ADDR: begin
          vtask_addr_d = addr_t'(csr_wdata_i);
        end
        HDV_CSR_VTASK_PADDR: begin
          vtask_paddr_d = addr_t'(csr_wdata_i);
        end
        HDV_CSR_VTASK_STATUS: begin
          if (csr_wdata_i[1]) begin
            done_d = 1'b0;
          end
          if (csr_wdata_i[2]) begin
            error_d = 1'b0;
          end
          task_status_clear_o = |csr_wdata_i[2:1];
        end
        default: begin
        end
      endcase
    end

    if (task_valid_q && task_ready_i) begin
      task_valid_d = 1'b0;
    end

    if (start_pulse) begin
      if (!task_valid_q || task_ready_i) begin
        task_valid_d = 1'b1;
        done_d       = 1'b0;
        error_d      = 1'b0;
      end else begin
        error_d      = 1'b1;
      end
    end

    if (task_done_i) begin
      done_d = 1'b1;
    end
    if (task_error_i) begin
      error_d = 1'b1;
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin : p_regs
    if (!rst_ni) begin
      vtask_addr_q  <= '0;
      vtask_paddr_q <= '0;
      task_valid_q  <= 1'b0;
      done_q        <= 1'b0;
      error_q       <= 1'b0;
    end else begin
      vtask_addr_q  <= vtask_addr_d;
      vtask_paddr_q <= vtask_paddr_d;
      task_valid_q  <= task_valid_d;
      done_q        <= done_d;
      error_q       <= error_d;
    end
  end

endmodule : hdv_task_interface_unit
