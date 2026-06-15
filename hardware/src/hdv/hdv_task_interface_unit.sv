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

  input  logic         host_tiu_csr_valid_i,
  input  logic         host_tiu_csr_write_i,
  input  logic [11:0]  host_tiu_csr_addr_i,
  input  logic [XLEN-1:0] host_tiu_csr_wdata_i,
  output logic         tiu_host_csr_ready_o,
  output logic [XLEN-1:0] tiu_host_csr_rdata_o,
  output logic         tiu_host_csr_error_o,

  output logic         tiu_tsu_task_valid_o,
  input  logic         tsu_tiu_task_ready_i,
  output addr_t        tiu_tsu_task_entry_o,
  output addr_t        tiu_tsu_task_desc_o,

  input  logic         top_tiu_task_busy_i,
  input  logic         tsu_tiu_task_done_i,
  input  logic         tsu_tiu_task_error_i,
  output logic         tiu_tsu_status_clear_o
);

  addr_t vtask_addr_d,  vtask_addr_q;
  addr_t vtask_paddr_d, vtask_paddr_q;
  logic  task_valid_d,  task_valid_q;
  logic  done_d,        done_q;
  logic  error_d,       error_q;
  logic  start_pulse;

  assign tiu_host_csr_ready_o = 1'b1;
  assign tiu_host_csr_error_o = host_tiu_csr_valid_i
                              & (host_tiu_csr_addr_i != HDV_CSR_VTASK_ADDR)
                              & (host_tiu_csr_addr_i != HDV_CSR_VTASK_PADDR)
                              & (host_tiu_csr_addr_i != HDV_CSR_VTASK_START)
                              & (host_tiu_csr_addr_i != HDV_CSR_VTASK_STATUS);

  assign tiu_tsu_task_valid_o = task_valid_q;
  assign tiu_tsu_task_entry_o = vtask_addr_q;
  assign tiu_tsu_task_desc_o  = vtask_paddr_q;

  assign start_pulse = host_tiu_csr_valid_i & host_tiu_csr_write_i
                     & (host_tiu_csr_addr_i == HDV_CSR_VTASK_START)
                     & host_tiu_csr_wdata_i[0];

  always_comb begin : p_read_mux
    tiu_host_csr_rdata_o = '0;
    unique case (host_tiu_csr_addr_i)
      HDV_CSR_VTASK_ADDR: begin
        tiu_host_csr_rdata_o = vtask_addr_q;
      end
      HDV_CSR_VTASK_PADDR: begin
        tiu_host_csr_rdata_o = vtask_paddr_q;
      end
      HDV_CSR_VTASK_START: begin
        tiu_host_csr_rdata_o[0] = task_valid_q;
      end
      HDV_CSR_VTASK_STATUS: begin
        tiu_host_csr_rdata_o[0] = top_tiu_task_busy_i | task_valid_q;
        tiu_host_csr_rdata_o[1] = done_q;
        tiu_host_csr_rdata_o[2] = error_q;
      end
      default: begin
        tiu_host_csr_rdata_o = '0;
      end
    endcase
  end

  always_comb begin : p_next
    vtask_addr_d         = vtask_addr_q;
    vtask_paddr_d        = vtask_paddr_q;
    task_valid_d         = task_valid_q;
    done_d               = done_q;
    error_d              = error_q;
    tiu_tsu_status_clear_o  = 1'b0;

    // Hardware status inputs (lowest priority for done/error): set when the
    // backend reports a result.  tsu_tiu_task_done_i persists until the host clears it,
    // so these must come before the CSR-write block so the host can override.
    if (tsu_tiu_task_done_i) begin
      done_d = 1'b1;
    end
    if (tsu_tiu_task_error_i) begin
      error_d = 1'b1;
    end

    if (task_valid_q && tsu_tiu_task_ready_i) begin
      task_valid_d = 1'b0;
    end

    // New-task submission clears stale done/error from the previous task.
    if (start_pulse) begin
      if (!task_valid_q || tsu_tiu_task_ready_i) begin
        task_valid_d = 1'b1;
        done_d       = 1'b0;
        error_d      = 1'b0;
      end else begin
        error_d      = 1'b1;
      end
    end

    // CSR writes (highest priority for done/error): the host can always clear
    // the done/error bits even while tsu_tiu_task_done_i/tsu_tiu_task_error_i are still high.
    if (host_tiu_csr_valid_i && host_tiu_csr_write_i) begin
      unique case (host_tiu_csr_addr_i)
        HDV_CSR_VTASK_ADDR: begin
          vtask_addr_d = addr_t'(host_tiu_csr_wdata_i);
        end
        HDV_CSR_VTASK_PADDR: begin
          vtask_paddr_d = addr_t'(host_tiu_csr_wdata_i);
        end
        HDV_CSR_VTASK_STATUS: begin
          if (host_tiu_csr_wdata_i[1]) begin
            done_d = 1'b0;
          end
          if (host_tiu_csr_wdata_i[2]) begin
            error_d = 1'b0;
          end
          tiu_tsu_status_clear_o = |host_tiu_csr_wdata_i[2:1];
        end
        default: begin
        end
      endcase
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
