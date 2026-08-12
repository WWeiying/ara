// SPDX-License-Identifier: SHL-0.51

module ara_commit_monitor #(
    parameter int unsigned NrCommitPorts = 1,
    parameter int unsigned NrVInsn = 8,
    parameter int unsigned TransIdWidth = 4,
    parameter int unsigned NrLanes = 1,
    parameter int unsigned VLEN = 1024,
    parameter int unsigned VAddrWidth = 8,
    parameter int unsigned VLenWidth = $clog2(VLEN + 1),
    parameter type rvfi_instr_t = logic,
    parameter type accelerator_req_t = logic,
    parameter type accelerator_resp_t = logic
  ) (
    input logic clk_i,
    input logic rst_ni,
    input rvfi_instr_t [NrCommitPorts-1:0] rvfi_instr_i,
    input accelerator_req_t acc_req_i,
    input accelerator_resp_t acc_resp_i,
    input logic backend_alloc_i,
    input logic [$clog2(NrVInsn)-1:0] backend_alloc_id_i,
    input logic [63:0] backend_arch_seq_i,
    input logic [31:0] backend_arch_insn_i,
    input logic [TransIdWidth-1:0] backend_trans_id_i,
    input logic [NrVInsn-1:0] backend_done_i,
    input logic backend_use_vd_i,
    input logic [4:0] backend_vd_i,
    input logic [2:0] backend_eew_i,
    input logic [VLenWidth-1:0] backend_vl_i,
    input logic [VLenWidth-1:0] backend_vstart_i,
    input logic [NrLanes-1:0][4:0] wb_valid_i,
    input logic [NrLanes-1:0][4:0][$clog2(NrVInsn)-1:0] wb_id_i,
    input logic [NrLanes-1:0][4:0][VAddrWidth-1:0] wb_addr_i,
    input logic [NrLanes-1:0][4:0][63:0] wb_wdata_i,
    input logic [NrLanes-1:0][4:0][7:0] wb_be_i
  );

  string trace_path;
  integer trace_fd;
  logic trace_en;
  string vector_trace_path;
  integer vector_trace_fd;
  logic vector_trace_en;
  longint unsigned cycle_q;
  longint unsigned order_q;
  longint unsigned watchdog_limit;
  longint unsigned idle_cycles_q;
  logic watchdog_en;
  logic tohost_en;
  logic [63:0] tohost_addr;
  logic exit_pc_en;
  logic [63:0] exit_pc;
  logic [63:0] last_retire_pc_q;
  logic [31:0] last_retire_insn_q;
  longint unsigned arch_seq_q;
  logic front_active_q;
  longint unsigned front_seq_q;
  logic [31:0] front_insn_q;
  integer front_trans_id_q;
  logic [NrVInsn-1:0] uop_valid_q;
  logic [NrVInsn-1:0] uop_metadata_valid_q;
  longint unsigned uop_arch_seq_q [NrVInsn];
  logic [31:0] uop_insn_q [NrVInsn];
  integer uop_trans_id_q [NrVInsn];
  logic uop_use_vd_q [NrVInsn];
  logic [4:0] uop_vd_q [NrVInsn];
  logic [2:0] uop_eew_q [NrVInsn];
  logic [VLenWidth-1:0] uop_vl_q [NrVInsn];
  logic [VLenWidth-1:0] uop_vstart_q [NrVInsn];

  initial begin
    trace_en = $value$plusargs("COMMIT_TRACE=%s", trace_path);
    vector_trace_en = $value$plusargs("VECTOR_TRACE=%s", vector_trace_path);
    watchdog_limit = '0;
    watchdog_en = $value$plusargs("COMMIT_WATCHDOG=%d", watchdog_limit) &&
                  (watchdog_limit != 0);
    tohost_addr = '0;
    tohost_en = $value$plusargs("COMMIT_TOHOST=%h", tohost_addr);
    exit_pc = '0;
    exit_pc_en = $value$plusargs("COMMIT_EXIT_PC=%h", exit_pc);
    trace_fd = 0;
    vector_trace_fd = 0;
    if (trace_en) begin
      trace_fd = $fopen(trace_path, "w");
      if (trace_fd == 0) begin
        $fatal(1, "cannot open commit trace: %s", trace_path);
      end
      $fdisplay(trace_fd,
          "cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap");
    end
    if (vector_trace_en) begin
      vector_trace_fd = $fopen(vector_trace_path, "w");
      if (vector_trace_fd == 0) begin
        $fatal(1, "cannot open vector trace: %s", vector_trace_path);
      end
      $fdisplay(vector_trace_fd,
          "cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits");
      $fdisplay(vector_trace_fd,
          "0,config,0,0,0,0,00000000,0,0,0,0,0,0,00,0000000000000000,%0d,%0d",
          NrLanes, VLEN);
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    longint unsigned next_order;
    logic progress;
    if (!rst_ni) begin
      cycle_q <= '0;
      order_q <= '0;
      idle_cycles_q <= '0;
      last_retire_pc_q <= '0;
      last_retire_insn_q <= '0;
      arch_seq_q <= '0;
      front_active_q <= 1'b0;
      front_seq_q <= '0;
      front_insn_q <= '0;
      front_trans_id_q <= -1;
      uop_valid_q <= '0;
      uop_metadata_valid_q <= '0;
      for (int unsigned id = 0; id < NrVInsn; id++) begin
        uop_arch_seq_q[id] <= '0;
        uop_insn_q[id] <= '0;
        uop_trans_id_q[id] <= -1;
        uop_use_vd_q[id] <= 1'b0;
        uop_vd_q[id] <= '0;
        uop_eew_q[id] <= '0;
        uop_vl_q[id] <= '0;
        uop_vstart_q[id] <= '0;
      end
    end else begin
      logic start_arch;
      logic finish_front;
      longint unsigned active_seq;

      cycle_q <= cycle_q + 1;
      next_order = order_q;
      progress = (acc_req_i.req_valid && acc_resp_i.req_ready) ||
                 (acc_resp_i.resp_valid && acc_req_i.resp_ready) ||
                 backend_alloc_i || (|backend_done_i);
      start_arch = acc_req_i.req_valid && !front_active_q;
      finish_front = acc_req_i.req_valid && acc_resp_i.req_ready;
      active_seq = start_arch ? arch_seq_q : front_seq_q;

      if (start_arch) begin
        front_active_q <= 1'b1;
        front_seq_q <= arch_seq_q;
        front_insn_q <= acc_req_i.insn;
        front_trans_id_q <= acc_req_i.trans_id;
        if (trace_en) begin
          $fdisplay(trace_fd,
              "%0d,arch_start,%0d,-1,%0d,0000000000000000,%08h,0,0000000000000000,0000000000000000,00,00,0000000000000000,0",
              cycle_q, arch_seq_q, acc_req_i.trans_id, acc_req_i.insn);
        end
      end

      for (int unsigned id = 0; id < NrVInsn; id++) begin
        if (backend_done_i[id]) begin
          if (!uop_valid_q[id]) begin
            $fatal(1, "completion for untracked backend vid %0d", id);
          end
          if (trace_en) begin
            $fdisplay(trace_fd,
                "%0d,uop_done,%0d,%0d,%0d,0000000000000000,%08h,0,0000000000000000,0000000000000000,00,00,0000000000000000,0",
                cycle_q, uop_arch_seq_q[id], id, uop_trans_id_q[id], uop_insn_q[id]);
          end
          if (vector_trace_en) begin
            $fdisplay(vector_trace_fd,
                "%0d,done,%0d,%0d,0,0,%08h,%0d,%0d,%0d,%0d,%0d,0,00,0000000000000000,%0d,%0d",
                cycle_q, uop_arch_seq_q[id], id, uop_insn_q[id],
                uop_use_vd_q[id], uop_vd_q[id], uop_eew_q[id],
                uop_vl_q[id], uop_vstart_q[id], NrLanes, VLEN);
          end
          uop_valid_q[id] <= 1'b0;
        end
      end

      if (backend_alloc_i) begin
        if (uop_valid_q[backend_alloc_id_i] && !backend_done_i[backend_alloc_id_i]) begin
          $fatal(1, "backend vid %0d reused before completion", backend_alloc_id_i);
        end
        uop_valid_q[backend_alloc_id_i] <= 1'b1;
        uop_metadata_valid_q[backend_alloc_id_i] <= 1'b1;
        uop_arch_seq_q[backend_alloc_id_i] <= backend_arch_seq_i;
        uop_insn_q[backend_alloc_id_i] <= backend_arch_insn_i;
        uop_trans_id_q[backend_alloc_id_i] <= backend_trans_id_i;
        uop_use_vd_q[backend_alloc_id_i] <= backend_use_vd_i;
        uop_vd_q[backend_alloc_id_i] <= backend_vd_i;
        uop_eew_q[backend_alloc_id_i] <= backend_eew_i;
        uop_vl_q[backend_alloc_id_i] <= backend_vl_i;
        uop_vstart_q[backend_alloc_id_i] <= backend_vstart_i;
        if (trace_en) begin
          $fdisplay(trace_fd,
              "%0d,uop_alloc,%0d,%0d,%0d,0000000000000000,%08h,0,0000000000000000,0000000000000000,00,00,0000000000000000,0",
              cycle_q, backend_arch_seq_i, backend_alloc_id_i, backend_trans_id_i,
              backend_arch_insn_i);
        end
        if (vector_trace_en) begin
          $fdisplay(vector_trace_fd,
              "%0d,alloc,%0d,%0d,0,0,%08h,%0d,%0d,%0d,%0d,%0d,0,00,0000000000000000,%0d,%0d",
              cycle_q, backend_arch_seq_i, backend_alloc_id_i, backend_arch_insn_i,
              backend_use_vd_i, backend_vd_i, backend_eew_i,
              backend_vl_i, backend_vstart_i, NrLanes, VLEN);
        end
      end

      if (vector_trace_en) begin
        for (int unsigned lane = 0; lane < NrLanes; lane++) begin
          for (int unsigned source = 0; source < 5; source++) begin
            if (wb_valid_i[lane][source]) begin
              automatic int unsigned id = wb_id_i[lane][source];
              if (uop_metadata_valid_q[id]) begin
                $fdisplay(vector_trace_fd,
                    "%0d,write,%0d,%0d,%0d,%0d,%08h,%0d,%0d,%0d,%0d,%0d,%0d,%02h,%016h,%0d,%0d",
                    cycle_q, uop_arch_seq_q[id], id, lane, source,
                    uop_insn_q[id], uop_use_vd_q[id], uop_vd_q[id], uop_eew_q[id],
                    uop_vl_q[id], uop_vstart_q[id], wb_addr_i[lane][source],
                    wb_be_i[lane][source], wb_wdata_i[lane][source], NrLanes, VLEN);
              end else if (backend_alloc_i && backend_alloc_id_i == id) begin
                $fdisplay(vector_trace_fd,
                    "%0d,write,%0d,%0d,%0d,%0d,%08h,%0d,%0d,%0d,%0d,%0d,%0d,%02h,%016h,%0d,%0d",
                    cycle_q, backend_arch_seq_i, id, lane, source,
                    backend_arch_insn_i, backend_use_vd_i, backend_vd_i, backend_eew_i,
                    backend_vl_i, backend_vstart_i, wb_addr_i[lane][source],
                    wb_be_i[lane][source], wb_wdata_i[lane][source], NrLanes, VLEN);
              end else begin
                $fatal(1, "VRF write for untracked backend vid %0d", id);
              end
            end
          end
        end
      end

      if (finish_front) begin
        front_active_q <= 1'b0;
        arch_seq_q <= active_seq + 1;
      end

      for (int unsigned port = 0; port < NrCommitPorts; port++) begin
        if (rvfi_instr_i[port].valid) begin
          progress = 1'b1;
          last_retire_pc_q <= rvfi_instr_i[port].pc_rdata;
          last_retire_insn_q <= rvfi_instr_i[port].insn;
          if (trace_en) begin
            $fdisplay(trace_fd,
                "%0d,retire,%0d,%0d,-1,%016h,%08h,%0d,%016h,%016h,%02h,%02h,%016h,%0d",
                cycle_q, next_order, port,
                rvfi_instr_i[port].pc_rdata,
                rvfi_instr_i[port].insn,
                rvfi_instr_i[port].rd_addr,
                rvfi_instr_i[port].rd_wdata,
                rvfi_instr_i[port].mem_addr,
                rvfi_instr_i[port].mem_rmask,
                rvfi_instr_i[port].mem_wmask,
                rvfi_instr_i[port].mem_wdata,
                rvfi_instr_i[port].trap);
          end
          if (tohost_en && (|rvfi_instr_i[port].mem_wmask) &&
              (rvfi_instr_i[port].mem_addr == tohost_addr)) begin
            if (rvfi_instr_i[port].mem_wdata[31:0] == 32'd1) begin
              $display("Core Test *** SUCCESS ***");
              $finish;
            end else begin
              $fatal(1, "test wrote failure value %016h to tohost", rvfi_instr_i[port].mem_wdata);
            end
          end
          if (exit_pc_en && rvfi_instr_i[port].pc_rdata == exit_pc) begin
            if (rvfi_instr_i[port].insn == 32'h0000_0073 && rvfi_instr_i[port].trap) begin
              $display("Core Test *** SUCCESS ***");
              $finish;
            end else begin
              $fatal(1,
                  "configured exit PC retired without trapped ecall: pc=%016h insn=%08h trap=%0b",
                  rvfi_instr_i[port].pc_rdata, rvfi_instr_i[port].insn,
                  rvfi_instr_i[port].trap);
            end
          end
          next_order++;
        end
      end

      if (trace_en) begin
        if (acc_req_i.req_valid && acc_resp_i.req_ready) begin
          $fdisplay(trace_fd,
              "%0d,cvx_req,-1,-1,%0d,0000000000000000,%08h,0,0000000000000000,0000000000000000,00,00,0000000000000000,0",
              cycle_q, acc_req_i.trans_id, acc_req_i.insn);
        end

        if (acc_resp_i.resp_valid && acc_req_i.resp_ready) begin
          $fdisplay(trace_fd,
              "%0d,cvx_resp,-1,-1,%0d,0000000000000000,00000000,0,%016h,0000000000000000,00,00,0000000000000000,%0d",
              cycle_q, acc_resp_i.trans_id, acc_resp_i.result, acc_resp_i.exception.valid);
        end

        if (progress && watchdog_en) begin
          $fflush(trace_fd);
          if (vector_trace_fd != 0) begin
            $fflush(vector_trace_fd);
          end
        end
      end

      if (watchdog_en) begin
        if (progress) begin
          idle_cycles_q <= '0;
        end else if (idle_cycles_q + 1 >= watchdog_limit) begin
          $fatal(1,
              "commit watchdog: no architectural or backend progress for %0d cycles; last retire pc=%016h insn=%08h at monitor cycle %0d",
              watchdog_limit, last_retire_pc_q, last_retire_insn_q, cycle_q);
        end else begin
          idle_cycles_q <= idle_cycles_q + 1;
        end
      end

      order_q <= next_order;
    end
  end

  final begin
    if (trace_fd != 0) begin
      $fclose(trace_fd);
    end
    if (vector_trace_fd != 0) begin
      $fclose(vector_trace_fd);
    end
  end

endmodule
