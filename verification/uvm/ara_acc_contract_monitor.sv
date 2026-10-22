// Verification-only monitor for the real CVA6-to-Ara accelerator boundary.
// This module is bound into ara_system; it has no synthesizable datapath.
module ara_acc_contract_monitor #(
  parameter int unsigned XLEN          = 64,
  parameter int unsigned GPLEN         = 41,
  parameter int unsigned TRANS_ID_BITS = 3
) (
  input logic                         clk_i,
  input logic                         rst_ni,
  input logic                         req_valid_i,
  input logic                         req_ready_i,
  input logic                         resp_ready_i,
  input logic [31:0]                  req_insn_i,
  input logic [XLEN-1:0]              req_rs1_i,
  input logic [XLEN-1:0]              req_rs2_i,
  input logic [2:0]                    req_frm_i,
  input logic [TRANS_ID_BITS-1:0]     req_id_i,
  input logic                         req_store_pending_i,
  input logic                         req_acc_cons_en_i,
  input logic                         req_inval_ready_i,
  input logic                         resp_valid_i,
  input logic [XLEN-1:0]              resp_result_i,
  input logic [TRANS_ID_BITS-1:0]     resp_id_i,
  input logic                         resp_exception_valid_i,
  input logic [XLEN-1:0]              resp_exception_cause_i,
  input logic [XLEN-1:0]              resp_exception_tval_i,
  input logic [GPLEN-1:0]             resp_exception_tval2_i,
  input logic [31:0]                  resp_exception_tinst_i,
  input logic                         resp_exception_gva_i,
  input logic                         resp_store_pending_i,
  input logic                         resp_store_complete_i,
  input logic                         resp_load_complete_i,
  input logic                         resp_fflags_valid_i,
  input logic                         resp_inval_valid_i,
  input logic                         mmu_en_i,
  input logic                         mmu_req_i,
  input logic                         mmu_valid_i
);

  localparam int unsigned NrTrans = 1 << TRANS_ID_BITS;

  logic [NrTrans-1:0] outstanding_q;
  logic               req_stalled_q;
  logic               resp_stalled_q;

  // Payloads exclude live memory/completion/invalidation sidebands. They do
  // not belong to the instruction held in the CVA6 request spill register.
  localparam int ReqWidth = 32 + 2*XLEN + 3 + TRANS_ID_BITS;
  localparam int RespWidth = XLEN + TRANS_ID_BITS + 1 + 2*XLEN + GPLEN + 32 + 1;
  logic [ReqWidth-1:0] req_payload_q;
  logic [RespWidth-1:0] resp_payload_q;
  wire [ReqWidth-1:0] req_payload =
      {req_insn_i, req_rs1_i, req_rs2_i, req_frm_i, req_id_i};
  wire [RespWidth-1:0] resp_payload = {
      resp_exception_valid_i ? {XLEN{1'b0}} : resp_result_i,
      resp_id_i, resp_exception_valid_i,
      resp_exception_valid_i ? resp_exception_cause_i : {XLEN{1'b0}},
      resp_exception_valid_i ? resp_exception_tval_i : {XLEN{1'b0}},
      resp_exception_valid_i ? resp_exception_tval2_i : {GPLEN{1'b0}},
      resp_exception_valid_i ? resp_exception_tinst_i : 32'b0,
      resp_exception_valid_i && resp_exception_gva_i};

  // Traffic counters describe the current reset epoch; errors survive reset.
  longint unsigned request_count_q;
  longint unsigned response_count_q;
  longint unsigned exception_count_q;
  longint unsigned mmu_request_cycles_q;
  longint unsigned protocol_error_count_q = 0;
  longint unsigned cycle_q = 0;
  int unsigned trace_limit = 0;
  int unsigned trace_count = 0;
  initial void'($value$plusargs("ARA_CONTRACT_TRACE_LIMIT=%d", trace_limit));

  wire req_fire  = req_valid_i  && req_ready_i;
  wire resp_fire = resp_valid_i && resp_ready_i;
  wire req_drop_error = req_stalled_q && (req_valid_i !== 1'b1);
  wire resp_drop_error = resp_stalled_q && (resp_valid_i !== 1'b1);
  wire req_payload_error = req_stalled_q && (req_valid_i === 1'b1)
                           && (req_payload !== req_payload_q);
  wire resp_payload_error = resp_stalled_q && (resp_valid_i === 1'b1)
                            && (resp_payload !== resp_payload_q);
  wire duplicate_id_error = req_fire && outstanding_q[req_id_i]
                            && !(resp_fire && req_id_i == resp_id_i);
  wire orphan_id_error = resp_fire && !outstanding_q[resp_id_i]
                         && !(req_fire && req_id_i == resp_id_i);
  wire unknown_error = $isunknown({req_valid_i, resp_valid_i})
      || ((req_valid_i === 1'b1) && $isunknown({req_ready_i, req_id_i}))
      || ((resp_valid_i === 1'b1)
          && $isunknown({resp_ready_i, resp_id_i, resp_exception_valid_i}));
  wire [6:0] errors = {unknown_error, resp_payload_error, req_payload_error,
                      orphan_id_error === 1'b1, duplicate_id_error === 1'b1,
                      resp_drop_error, req_drop_error};

  // One accounting owner, including payload failures. Sample the transaction
  // at the accepting edge (before DUT nonblocking updates), not one delta later.
  always @(posedge clk_i) begin
    cycle_q <= cycle_q + 1;
    if (rst_ni === 1'b1) begin
      protocol_error_count_q <= protocol_error_count_q + $countones(errors);
      p_request_stable_until_ready: assert (!(req_drop_error || req_payload_error))
        else $error("[ARA_CONTRACT_ERROR] request changed/dropped under backpressure");
      p_response_stable_until_ready: assert (!(resp_drop_error || resp_payload_error))
        else $error("[ARA_CONTRACT_ERROR] response changed/dropped under backpressure");
      if (duplicate_id_error === 1'b1)
        $error("[ARA_CONTRACT_ERROR] duplicate request ID %0d", req_id_i);
      if (orphan_id_error === 1'b1)
        $error("[ARA_CONTRACT_ERROR] orphan response ID %0d", resp_id_i);
      if (unknown_error)
        $error("[ARA_CONTRACT_ERROR] unknown active handshake/identity");
      if ((req_fire || resp_fire) && trace_count < trace_limit) begin
        trace_count <= trace_count + 1;
        $display("[ARA_CONTRACT_TRACE] sample=pre_edge cycle=%0d req=%b/%b fire=%b id=%h insn=%h resp=%b/%b fire=%b id=%h exc=%b pending=%h stalled=%b%b errors=%b",
            cycle_q, req_valid_i, req_ready_i, req_fire, req_id_i, req_insn_i,
            resp_valid_i, resp_ready_i, resp_fire, resp_id_i,
            resp_exception_valid_i, outstanding_q, req_stalled_q, resp_stalled_q, errors);
      end
    end
  end

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      outstanding_q          <= '0;
      req_stalled_q          <= 1'b0;
      resp_stalled_q         <= 1'b0;
      request_count_q        <= 0;
      response_count_q       <= 0;
      exception_count_q      <= 0;
      mmu_request_cycles_q   <= 0;
      req_payload_q          <= '0;
      resp_payload_q         <= '0;
    end else begin
      req_stalled_q <= req_valid_i && !req_ready_i;
      resp_stalled_q <= resp_valid_i && !resp_ready_i;
      req_payload_q <= req_payload;
      resp_payload_q <= resp_payload;

      if (req_fire) begin
        request_count_q <= request_count_q + 1;
      end

      if (resp_fire) begin
        response_count_q <= response_count_q + 1;
      end

      if (resp_fire && resp_exception_valid_i) begin
        exception_count_q <= exception_count_q + 1;
      end
      if (mmu_en_i && mmu_req_i) begin
        mmu_request_cycles_q <= mmu_request_cycles_q + 1;
      end

      // Same-cycle response/request permits ID reuse; otherwise update the
      // scoreboard with the accepted request and consumed response.
      case ({req_fire, resp_fire})
        2'b10: outstanding_q[req_id_i]  <= 1'b1;
        2'b01: outstanding_q[resp_id_i] <= 1'b0;
        2'b11: begin
          // Existing ID: response retires the old request, the new one stays.
          // Free ID: response completes the newly accepted request immediately.
          if (req_id_i != resp_id_i) begin
            outstanding_q[req_id_i] <= 1'b1;
            outstanding_q[resp_id_i] <= 1'b0;
          end
        end
        default: ;
      endcase
    end
  end

  final begin
    $display("[ARA_CONTRACT] requests=%0d responses=%0d exceptions=%0d mmu_request_cycles=%0d protocol_errors=%0d outstanding=%0d req_stalled=%b resp_stalled=%b",
             request_count_q, response_count_q, exception_count_q,
             mmu_request_cycles_q, protocol_error_count_q, $countones(outstanding_q),
             req_stalled_q, resp_stalled_q);
  end

endmodule

// This bind is intentionally kept in the verification source list.  It uses
// the actual ara_system fields and therefore cannot silently fall back to the
// abstract flat interface used by the contract smoke.
`ifndef ARA_ACC_CONTRACT_STANDALONE
bind ara_system ara_acc_contract_monitor #(
  .XLEN          (CVA6Cfg.XLEN),
  .GPLEN         (CVA6Cfg.GPLEN),
  .TRANS_ID_BITS(CVA6Cfg.TRANS_ID_BITS)
) i_ara_acc_contract_monitor (
  .clk_i                       (clk_i),
  .rst_ni                      (rst_ni),
  .req_valid_i                 (acc_req.acc_req.req_valid),
  .req_ready_i                 (acc_resp.acc_resp.req_ready),
  .resp_ready_i                (acc_req.acc_req.resp_ready),
  .req_insn_i                  (acc_req.acc_req.insn),
  .req_rs1_i                   (acc_req.acc_req.rs1),
  .req_rs2_i                   (acc_req.acc_req.rs2),
  .req_frm_i                   (acc_req.acc_req.frm),
  .req_id_i                    (acc_req.acc_req.trans_id),
  .req_store_pending_i         (acc_req.acc_req.store_pending),
  .req_acc_cons_en_i           (acc_req.acc_req.acc_cons_en),
  .req_inval_ready_i           (acc_req.acc_req.inval_ready),
  .resp_valid_i                (acc_resp.acc_resp.resp_valid),
  .resp_result_i               (acc_resp.acc_resp.result),
  .resp_id_i                   (acc_resp.acc_resp.trans_id),
  .resp_exception_valid_i      (acc_resp.acc_resp.exception.valid),
  .resp_exception_cause_i      (acc_resp.acc_resp.exception.cause),
  .resp_exception_tval_i       (acc_resp.acc_resp.exception.tval),
  .resp_exception_tval2_i      (acc_resp.acc_resp.exception.tval2),
  .resp_exception_tinst_i      (acc_resp.acc_resp.exception.tinst),
  .resp_exception_gva_i        (acc_resp.acc_resp.exception.gva),
  .resp_store_pending_i        (acc_resp.acc_resp.store_pending),
  .resp_store_complete_i       (acc_resp.acc_resp.store_complete),
  .resp_load_complete_i        (acc_resp.acc_resp.load_complete),
  .resp_fflags_valid_i         (acc_resp.acc_resp.fflags_valid),
  .resp_inval_valid_i          (acc_resp.acc_resp.inval_valid),
  .mmu_en_i                    (acc_req.acc_mmu_en),
  .mmu_req_i                   (acc_resp.acc_mmu_req.acc_mmu_req),
  .mmu_valid_i                 (acc_req.acc_mmu_resp.acc_mmu_valid)
);
`endif
