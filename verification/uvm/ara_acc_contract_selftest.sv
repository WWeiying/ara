`timescale 1ns/1ps
// Test the checker itself; negative cases are intentionally invalid traffic.
module ara_acc_contract_selftest;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst = 0;
  logic req_valid = 0, req_ready = 1, resp_ready = 1, resp_valid = 0;
  logic [31:0] insn = 32'h02000057;
  logic [63:0] rs1 = 1, rs2 = 2, result = 3;
  logic [2:0] req_id = 0, resp_id = 0, frm = 0;
  logic exc = 0;
  logic [63:0] cause = 0, tval = 0;
  logic [40:0] tval2 = 0;
  logic [31:0] tinst = 0;
  logic gva = 0, sideband = 0, mmu = 0;
  string scenario;
  int expected_errors = 0;

  ara_acc_contract_monitor dut (
    .clk_i(clk), .rst_ni(rst),
    .req_valid_i(req_valid), .req_ready_i(req_ready), .resp_ready_i(resp_ready),
    .req_insn_i(insn), .req_rs1_i(rs1), .req_rs2_i(rs2), .req_frm_i(frm),
    .req_id_i(req_id), .req_store_pending_i(sideband), .req_acc_cons_en_i(sideband),
    .req_inval_ready_i(sideband), .resp_valid_i(resp_valid), .resp_result_i(result),
    .resp_id_i(resp_id), .resp_exception_valid_i(exc),
    .resp_exception_cause_i(cause), .resp_exception_tval_i(tval),
    .resp_exception_tval2_i(tval2), .resp_exception_tinst_i(tinst),
    .resp_exception_gva_i(gva), .resp_store_pending_i(sideband),
    .resp_store_complete_i(sideband), .resp_load_complete_i(sideband),
    .resp_fflags_valid_i(sideband), .resp_inval_valid_i(sideband),
    .mmu_en_i(1'b1), .mmu_req_i(mmu), .mmu_valid_i(sideband)
  );

  task automatic tick;
    @(posedge clk);
    #1;
  endtask

  task automatic request(input logic [2:0] id);
    req_id = id;
    req_valid = 1;
    tick();
    req_valid = 0;
  endtask

  task automatic response(input logic [2:0] id);
    resp_id = id;
    resp_valid = 1;
    tick();
    resp_valid = 0;
  endtask

  task automatic check_pending(input logic [7:0] expected);
    if (dut.outstanding_q !== expected)
      $fatal(1, "SELFTEST scoreboard expected=%h actual=%h", expected, dut.outstanding_q);
  endtask

  initial begin
    if (!$value$plusargs("CASE=%s", scenario)) $fatal(1, "missing CASE");
    repeat (2) tick();
    rst = 1;
    tick();
    case (scenario)
      "legal": begin
        request(1);
        response(1);
        check_pending(0);
        // Immediate response to a free ID.
        req_valid = 1; req_id = 2; resp_valid = 1; resp_id = 2;
        tick();
        req_valid = 0; resp_valid = 0;
        check_pending(0);
        // Retire an old ID and replace it with a new request on the same edge.
        request(3);
        req_valid = 1; resp_valid = 1; resp_id = 3;
        tick();
        req_valid = 0; resp_valid = 0;
        check_pending(8'h08);
        response(3);
        check_pending(0);
        // Concurrent completion and acceptance with distinct IDs.
        request(4);
        req_valid = 1; req_id = 5; resp_valid = 1; resp_id = 4;
        tick();
        req_valid = 0; resp_valid = 0;
        check_pending(8'h20);
        response(5);
        // Memory-status/fflags pulses are independent of held payloads.
        req_valid = 1; req_ready = 0; req_id = 6;
        repeat (3) begin sideband = ~sideband; tick(); end
        req_ready = 1; tick(); req_valid = 0;
        resp_valid = 1; resp_ready = 0; resp_id = 6;
        repeat (3) begin
          sideband = ~sideband;
          cause = cause + 1; tval = tval + 1; // invalid exception: don't care
          tick();
        end
        resp_ready = 1; tick(); resp_valid = 0;
        check_pending(0);
        // Valid exception metadata is part of the held response.
        request(7);
        exc = 1; resp_valid = 1; resp_ready = 0; resp_id = 7;
        tick(); result = result + 1; tick();
        resp_ready = 1; tick(); resp_valid = 0; exc = 0;
        mmu = 1; repeat (3) tick(); mmu = 0;
        if (dut.mmu_request_cycles_q != 3) $fatal(1, "SELFTEST MMU cycle count");
        if (dut.request_count_q != 8 || dut.response_count_q != 8)
          $fatal(1, "SELFTEST traffic count");
      end
      "reset": begin
        request(0);
        rst = 0; tick(); rst = 1; tick();
        check_pending(0);
        request(1); response(1);
      end
      "duplicate": begin
        request(0); request(0); response(0); expected_errors = 1;
      end
      "orphan": begin
        request(0); response(0); response(0); expected_errors = 1;
      end
      "request_drop": begin
        req_valid = 1; req_ready = 0; tick();
        req_valid = 0; tick(); req_ready = 1;
        request(0); response(0); expected_errors = 1;
      end
      "response_drop": begin
        request(0); resp_valid = 1; resp_ready = 0; tick();
        resp_valid = 0; tick(); resp_ready = 1;
        response(0); expected_errors = 1;
      end
      "request_payload", "request_frm": begin
        req_valid = 1; req_ready = 0; tick();
        if (scenario == "request_frm") frm = 3;
        else rs1 = rs1 + 1;
        req_ready = 1; tick(); req_valid = 0;
        response(0); expected_errors = 1;
      end
      "response_payload", "exception_payload": begin
        request(0); resp_valid = 1; resp_ready = 0;
        exc = scenario == "exception_payload";
        tick();
        if (exc) tval2 = 1; else result = result + 1;
        resp_ready = 1; tick(); resp_valid = 0; expected_errors = 1;
      end
      "unknown": begin
        request(0); response(0);
        req_valid = 1'bx; tick(); req_valid = 0; expected_errors = 1;
      end
      "error_then_reset": begin
        response(0); expected_errors = 1;
        rst = 0; tick(); rst = 1; tick();
        request(0); response(0);
      end
      "incomplete": request(0);
      default: $fatal(1, "unknown CASE %s", scenario);
    endcase
    tick();
    if (dut.protocol_error_count_q != expected_errors)
      $fatal(1, "SELFTEST errors expected=%0d actual=%0d", expected_errors,
          dut.protocol_error_count_q);
    $display("[SELFTEST_PASS] case=%s expected_errors=%0d", scenario, expected_errors);
    $finish;
  end
  initial begin
    #5000;
    $fatal(1, "SELFTEST timeout");
  end
endmodule
