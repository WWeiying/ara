// Actual MASKU + SLDU; vectors and architectural byte-write oracle come from Python.
module mask_slide_matrix_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  localparam logic [63:0] Scalar = 64'hfedcba9876543210;
  bit clk = 0;
  always #5 clk = ~clk;
  logic rst, valid, mr, sr, mask_ready, feeding, active;
  pe_req_t req;
  pe_resp_t mresp, sresp;
  vfu_e target;
  logic [3:0][7:0] mask, be;
  logic [3:0] mv, sv, opvalid, opready, grant, final_grant;
  logic [3:0][9:0] addr;
  vid_t [3:0] result_id;
  elen_t [3:0] source_data, result_data;
  elen_t [3:0][NrMaskFUnits+1:0] mask_data;
  logic [3:0][NrMaskFUnits+1:0] mask_valid, mask_opready;
  logic [255:0] predicates;
  logic [7:0] source_bytes [128], expected_bytes [128];
  int expected_write [128], seen [128];
  int sent [4];
  logic [3:0] mask_sent, stalled;
  logic [3:0][84:0] held_payload;
  int case_id, sew, start, vl, down, scalar, offset, backpressure, vm;
  int cycles, slide_done_cycle, mask_done_cycle, mask_beats, written, blocked;
  int source_base, source_words, passed, trace_case;
  string history [16];

  // Four interleaved lanes; subwords within each lane have bit-reversed indices.
  // This is a local layout adapter, not a call to ara_pkg shuffle/deshuffle helpers.
  function automatic int sequential_byte(int lane, int b, int ew);
    int slot, reversed;
    slot = b >> ew;
    reversed = 0;
    for (int k = 0; k < 3-ew; k++) reversed = (reversed << 1) | ((slot >> k) & 1);
    return ((reversed * 4 + lane) << ew) + (b & ((1 << ew)-1));
  endfunction

  masku #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) m (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_req_ready_o(mr), .pe_resp_o(mresp),
    .masku_operand_i(mask_data), .masku_operand_valid_i(mask_valid),
    .masku_operand_ready_o(mask_opready), .masku_result_gnt_i('1),
    .masku_result_final_gnt_i('1), .masku_vrgat_req_ready_i('1),
    .mask_o(mask), .mask_valid_o(mv), .mask_target_fu_o(target),
    .lane_mask_ready_i('0), .vldu_mask_ready_i(1'b0),
    .vstu_mask_ready_i(1'b0), .sldu_mask_ready_i(mask_ready));
  sldu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic[9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t)) s (
    .clk_i(clk), .rst_ni(rst), .pe_req_i(req), .pe_req_valid_i(valid),
    .pe_vinsn_running_i('1), .pe_req_ready_o(sr), .pe_resp_o(sresp),
    .maintenance_drain_i(1'b0), .sldu_operand_i(source_data),
    .sldu_operand_valid_i(opvalid), .sldu_operand_reduction_i('0),
    .sldu_operand_ready_o(opready), .sldu_result_req_o(sv),
    .sldu_result_addr_o(addr), .sldu_result_wdata_o(result_data),
    .sldu_result_be_o(be), .sldu_result_id_o(result_id),
    .sldu_result_gnt_i(grant), .sldu_result_final_gnt_i(final_grant),
    .mask_i(mask), .mask_valid_i(target == VFU_SlideUnit ? mv : 4'b0),
    .mask_ready_o(mask_ready));

  always_comb begin
    source_data = '0; opvalid = '0; mask_data = '0; mask_valid = '0; grant = '0;
    for (int lane = 0; lane < 4; lane++) begin
      opvalid[lane] = feeding && sent[lane] < source_words;
      mask_valid[lane][0] = feeding && !vm && !mask_sent[lane];
      for (int b = 0; b < 8; b++) begin
        automatic int index;
        index = (source_base + sent[lane])*32 + sequential_byte(lane, b, sew);
        // Nonzero poison beyond VLMAX verifies DOWN zero-fill, not zero input.
        source_data[lane][8*b +: 8] = index < 128 ? source_bytes[index] : 8'ha7;
        mask_data[lane][0][8*b +: 8] = predicates[8*sequential_byte(lane,b,0) +: 8];
      end
      // Initial queue-filling stall, followed by independently phased lane stalls.
      grant[lane] = sv[lane] && (!backpressure ||
          (cycles >= 12 && ((cycles + lane*2) % 7) < 3));
    end
  end

  task automatic fail(string reason);
    $display("MATRIX_FAIL id=%0d sew=%0d start=%0d vl=%0d down=%0d scalar=%0d offset=%0d bp=%0d vm=%0d cycle=%0d reason=%s",
      case_id, sew, start, vl, down, scalar, offset, backpressure, vm, cycles, reason);
    for (int k = 0; k < 16; k++)
      if (cycles >= 16-k) $display("TRACE %s", history[(cycles+k)%16]);
    $fatal(1, "%s", reason);
  endtask

  always @(posedge clk) begin
    if (!rst) begin
      final_grant <= '0;
      mask_sent <= '0;
      for (int lane = 0; lane < 4; lane++) sent[lane] <= 0;
      stalled = '0;
    end else begin
      // The lane stream-register accepts on grant, then writes one cycle later.
      final_grant <= grant;
      for (int lane = 0; lane < 4; lane++) begin
        if (opvalid[lane] && opready[lane]) sent[lane] <= sent[lane]+1;
        if (mask_valid[lane][0] && mask_opready[lane][0]) mask_sent[lane] <= 1;
      end
      if (active) begin
        history[cycles%16] = $sformatf("cycle=%0d mr=%b sr=%b mask_read_elements=%0d mask_commit_elements=%0d mask_queue=%0d mask_pnt=%0d mask_v=%b mask_r=%b slide_issue_bytes=%0d slide_commit_bytes=%0d state=%0d buffered_mask=%b operand_v=%b operand_r=%b result_v=%b grant=%b final=%b result_full=%b",
          cycles, mr, sr, m.read_cnt_q, m.commit_cnt_q, m.mask_queue_cnt_q,
          m.mask_pnt_q, mv, mask_ready, s.issue_cnt_q, s.commit_cnt_q,
          s.state_q, s.mask_valid_q, s.sldu_operand_valid, s.sldu_operand_ready,
          sv, grant, final_grant, s.result_queue_full);
        if (case_id == trace_case) $display("TRACE %s", history[cycles%16]);
        cycles++;
        if (valid && !(mr && sr)) fail("request not jointly accepted");
        if (mask_ready && |mv) mask_beats++;
        if (sresp.vinsn_done[3]) begin
          if (slide_done_cycle) fail("duplicate SLDU completion");
          slide_done_cycle = cycles;
        end
        if (mresp.vinsn_done[3]) begin
          if (mask_done_cycle) fail("duplicate MASKU completion");
          mask_done_cycle = cycles;
        end
        for (int lane = 0; lane < 4; lane++) begin
          if (stalled[lane] && (!sv[lane] ||
              {result_id[lane], addr[lane], be[lane], result_data[lane]} !== held_payload[lane]))
            fail($sformatf("unstable stalled payload lane=%0d", lane));
          stalled[lane] = sv[lane] && !grant[lane];
          held_payload[lane] = {result_id[lane], addr[lane], be[lane], result_data[lane]};
          if (stalled[lane]) blocked++;
          if (grant[lane]) begin
            if (result_id[lane] !== 3 || $isunknown({addr[lane], be[lane]}))
              fail("unknown write address/BE or incorrect instruction id");
            if (addr[lane] < 96 || addr[lane] >= 100) fail("write outside vd register");
            for (int b = 0; b < 8; b++) if (be[lane][b]) begin
              automatic int index;
              index = (int'(addr[lane])-96)*32 + sequential_byte(lane,b,sew);
              if (!expected_write[index]) fail($sformatf("forbidden BE byte=%0d (prefix/tail/predicate)", index));
              if (seen[index]) fail($sformatf("duplicate byte write=%0d", index));
              if (result_data[lane][8*b +: 8] !== expected_bytes[index])
                fail($sformatf("data byte=%0d got=%02h expected=%02h lane=%0d slot=%0d",
                  index, result_data[lane][8*b +: 8], expected_bytes[index], lane, b));
              seen[index]++;
              written++;
            end
          end
        end
      end
    end
  end

  initial begin : matrix
    int fd, count, scanned;
    string vectors;
    rst = 0; valid = 0; feeding = 0; active = 0; req = '0;
    sew = 0; cycles = 0; source_base = 0; source_words = 0; passed = 0;
    trace_case = -1;
    void'($value$plusargs("TRACE_CASE=%d", trace_case));
    if (!$value$plusargs("VECTORS=%s", vectors)) $fatal(1, "Missing VECTORS");
    fd = $fopen(vectors, "r");
    if (!fd || $fscanf(fd, "%d", count) != 1) $fatal(1, "Invalid vector file");
    repeat (count) begin
      @(negedge clk);
      rst = 0; valid = 0; feeding = 0; active = 0;
      repeat (3) @(negedge clk);
      scanned = $fscanf(fd, "%d %d %d %d %d %d %d %d %d %h",
        case_id, sew, start, vl, down, scalar, offset, backpressure, vm, predicates);
      if (scanned != 10) $fatal(1, "Malformed case header");
      for (int b = 0; b < 128; b++) begin
        if ($fscanf(fd, "%h %h %d", source_bytes[b], expected_bytes[b], expected_write[b]) != 3)
          $fatal(1, "Malformed oracle");
        seen[b] = 0;
      end
      if (start >= vl || (!down && !scalar && offset >= vl))
        $fatal(1, "Illegal backend no-op case");
      source_base = down ? (offset << sew)/32 : 0;
      if (!down) source_words = (((vl-offset) << sew)+31)/32;
      else if (scalar) source_words = vl == 1 ? 0 : ((vl << sew)+31)/32;
      else source_words = offset >= (128 >> sew) ? 0 :
          ((vl << sew) + ((offset << sew)%32) + 31)/32;
      req = '0;
      req.id = 3; req.op = down ? VSLIDEDOWN : VSLIDEUP;
      req.vfu = VFU_SlideUnit; req.vm = vm; req.vd = 24; req.use_vd = 1;
      req.vs2 = 8; req.use_vs2 = 1; req.vl = vl; req.vstart = start;
      req.stride = offset; req.use_scalar_op = scalar; req.scalar_op = Scalar;
      req.vtype.vsew = vew_e'(sew); req.eew_vs2 = vew_e'(sew); req.eew_vmask = EW8;
      req.vtype.vlmul = LMUL_1; req.emul = LMUL_1;
      req.is_stride_np2 = $countones((offset << sew) & 31) > 1;
      cycles = 0; slide_done_cycle = 0; mask_done_cycle = 0;
      mask_beats = 0; written = 0; blocked = 0;
      $display("MATRIX_BEGIN id=%0d sew=%0d start=%0d vl=%0d down=%0d scalar=%0d offset=%0d bp=%0d vm=%0d",
        case_id, sew, start, vl, down, scalar, offset, backpressure, vm);
      rst = 1;
      @(negedge clk);
      if (!(mr && sr)) fail("not ready after reset");
      active = 1; valid = 1;
      @(negedge clk);
      valid = 0; feeding = 1;
      while ((!slide_done_cycle || (!vm && !mask_done_cycle)) && cycles < 256) @(negedge clk);
      if (!slide_done_cycle || (!vm && !mask_done_cycle)) fail("bounded completion timeout");
      // Observe late writes and final grants before resetting the next case.
      repeat (5) @(negedge clk);
      for (int b = 0; b < 128; b++)
        if (seen[b] != expected_write[b]) fail($sformatf("missing expected byte=%0d", b));
      if (backpressure && blocked == 0) fail("backpressure was not exercised");
      if (vm && (mask_beats || mask_done_cycle)) fail("unmasked instruction used MASKU");
      if (|sv || |final_grant || |mv) fail("residual result/mask after completion");
      $display("MATRIX_RESULT id=%0d slide_cycles=%0d mask_cycles=%0d mask_beats=%0d bytes=%0d blocked=%0d",
        case_id, slide_done_cycle, mask_done_cycle, mask_beats, written, blocked);
      active = 0; feeding = 0; passed++;
    end
    $fclose(fd);
    $display("MASK_SLIDE_MATRIX_PASS cases=%0d", passed);
    $finish;
  end
endmodule
