`timescale 1ns/1ps
module upstream_tb;
  import fpnew_pkg::*;
  localparam fmt_logic_t Formats = 6'b111000;
  logic clk = 0, rst_n = 0;
  always #5 clk = ~clk;
  logic [2:0][63:0] operands;
  operation_e op;
  roundmode_e rm;
  fp_format_e sf, df;
  int_format_e infmt;
  logic umod, flush, vectorial, sync_done;
  logic [5:0] iv, ir, ov, ordy;
  logic [5:0][63:0] result;
  logic [5:0][31:0] tags;
  status_t flags [6];
  logic [31:0] tag;
  logic div_done, div_ready;
  integer count = 0, bad = 0, fd, trace;
  integer probes;

  always @(posedge clk) begin
    if (rst_n && multi_dut.mid_pipe_valid_q[1] && multi_dut.out_pipe_ready[0] &&
        multi_dut.uf_before_round) begin
      $fdisplay(probes, "%0t,%0d,%0d,%0d,%h,%h,%b,%h,%h,%b",
        $time, multi_dut.mid_pipe_tag_q[1], multi_dut.dst_fmt_q2, multi_dut.rnd_mode_q,
        multi_dut.pre_round_abs, multi_dut.rounded_abs, multi_dut.round_sticky_bits,
        multi_dut.final_mantissa, multi_dut.sum_sticky_bits, multi_dut.uf_after_round);
    end
  end

  fpnew_cast_multi #(.FpFmtConfig(Formats), .IntFmtConfig(4'b1111),
    .NumPipeRegs(3), .PipeConfig(DISTRIBUTED), .TagType(logic [31:0])) cast_dut (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(operands[0]), .is_boxed_i('1),
    .rnd_mode_i(rm), .op_i(op), .op_mod_i(umod), .src_fmt_i(sf), .dst_fmt_i(df),
    .int_fmt_i(infmt), .tag_i(tag), .mask_i(1'b1), .aux_i(1'b0),
    .in_valid_i(iv[0]), .in_ready_o(ir[0]), .flush_i(flush),
    .result_o(result[0]), .status_o(flags[0]), .extension_bit_o(), .tag_o(tags[0]),
    .mask_o(), .aux_o(), .out_valid_o(ov[0]), .out_ready_i(ordy[0]), .busy_o());

  fpnew_fma_multi #(.FpFmtConfig(Formats), .NumPipeRegs(3),
    .PipeConfig(DISTRIBUTED), .TagType(logic [31:0])) multi_dut (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(operands), .is_boxed_i('1),
    .rnd_mode_i(rm), .op_i(op), .op_mod_i(umod), .src_fmt_i(sf), .dst_fmt_i(df),
    .tag_i(tag), .mask_i(1'b1), .aux_i(1'b0), .in_valid_i(iv[1]), .in_ready_o(ir[1]),
    .flush_i(flush), .result_o(result[1]), .status_o(flags[1]), .extension_bit_o(),
    .tag_o(tags[1]), .mask_o(), .aux_o(), .out_valid_o(ov[1]),
    .out_ready_i(ordy[1]), .busy_o());

  for (genvar i = 2; i < 5; i++) begin : fixed_fma
    localparam fp_format_e F = i == 2 ? FP32 : (i == 3 ? FP64 : FP16);
    localparam int W = fp_width(F);
    logic [2:0][W-1:0] args;
    logic [W-1:0] res;
    for (genvar j = 0; j < 3; j++) assign args[j] = operands[j][W-1:0];
    assign result[i] = {{(64-W){1'b1}}, res};
    fpnew_fma #(.FpFormat(F), .NumPipeRegs(3), .PipeConfig(DISTRIBUTED),
      .TagType(logic [31:0])) dut (
      .clk_i(clk), .rst_ni(rst_n), .operands_i(args), .is_boxed_i('1),
      .rnd_mode_i(rm), .op_i(op), .op_mod_i(umod), .tag_i(tag), .mask_i(1'b1),
      .aux_i(1'b0), .in_valid_i(iv[i]), .in_ready_o(ir[i]), .flush_i(flush),
      .result_o(res), .status_o(flags[i]), .extension_bit_o(), .tag_o(tags[i]),
      .mask_o(), .aux_o(), .out_valid_o(ov[i]), .out_ready_i(ordy[i]), .busy_o());
  end

  fpnew_divsqrt_th_64_multi #(.FpFmtConfig(Formats), .NumPipeRegs(0),
    .TagType(logic [31:0])) div_dut (
    .clk_i(clk), .rst_ni(rst_n), .operands_i(operands[1:0]), .is_boxed_i('1),
    .rnd_mode_i(rm), .op_i(op), .dst_fmt_i(df), .tag_i(tag), .mask_i(1'b1),
    .aux_i(1'b0), .vectorial_op_i(vectorial), .in_valid_i(iv[5]), .in_ready_o(ir[5]),
    .divsqrt_done_o(div_done), .simd_synch_done_i(sync_done),
    .divsqrt_ready_o(div_ready), .simd_synch_rdy_i(div_ready), .flush_i(flush),
    .result_o(result[5]), .status_o(flags[5]), .extension_bit_o(), .tag_o(tags[5]),
    .mask_o(), .aux_o(), .out_valid_o(ov[5]), .out_ready_i(ordy[5]), .busy_o());

  task automatic reset_units;
    @(negedge clk);
    rst_n = 0; iv = '0; ordy = '0; flush = 0; vectorial = 0; sync_done = 0;
    repeat (3) @(negedge clk);
    rst_n = 1;
  endtask

  task automatic run_case(input int id, u, opcode, srcfmt, dstfmt, intfmt, unsignedop,
      rounding, input logic [63:0] a, b, c, expected, result_mask,
      input logic [4:0] expected_flags);
    int waited;
    bit mismatch;
    logic [63:0] held;
    logic [4:0] held_flags;
    @(negedge clk);
    operands = {c, b, a}; op = operation_e'(opcode); sf = fp_format_e'(srcfmt);
    df = fp_format_e'(dstfmt); infmt = int_format_e'(intfmt); umod = unsignedop;
    rm = roundmode_e'(rounding); tag = id; iv[u] = 1;
    waited = 0;
    do begin
      @(posedge clk);
      waited++;
      if (waited > 200) $fatal(1, "INPUT_TIMEOUT id=%0d", id);
    end while (!ir[u]);
    @(negedge clk);
    iv[u] = 0;
    // Deliberately different live RM during the stored transaction's rounding.
    rm = roundmode_e'((rounding + 2) % 5);
    waited = 0;
    while (!ov[u]) begin
      @(negedge clk);
      waited++;
      if (waited > 200) $fatal(1, "OUTPUT_TIMEOUT id=%0d", id);
    end
    held = result[u]; held_flags = flags[u];
    repeat (3) begin
      @(negedge clk);
      if (!ov[u] || result[u] !== held || flags[u] !== held_flags || tags[u] !== 32'(id))
        $fatal(1, "BACKPRESSURE_UNSTABLE id=%0d", id);
    end
    mismatch = ((result[u] & result_mask) !== expected) ||
               (flags[u] !== expected_flags) || (tags[u] !== 32'(id));
    $fdisplay(trace, "%0d,%0d,%016h,%02h,%0d,%0d,%0d", id, u, result[u],
              flags[u], tags[u], waited, mismatch);
    if (mismatch) begin
      if (bad < 15) $display("MISMATCH id=%0d unit=%0d got=%016h flags=%02h expected=%016h flags=%02h",
                             id, u, result[u], flags[u], expected, expected_flags);
      bad++;
    end
    count++;
    ordy[u] = 1;
    @(posedge clk);
    @(negedge clk);
    ordy[u] = 0;
  endtask

  task automatic stream_cases(input int unit_id);
    int ids[1024], opc[1024], srcf[1024], dstf[1024], intf[1024], uns[1024], rnd[1024];
    logic [63:0] aa[1024], bb[1024], cc[1024], exp[1024], masks[1024];
    logic [4:0] ef[1024];
    int file_in, n, rc, id0, u0, op0, sf0, df0, if0, um0, rm0;
    logic [63:0] a0, b0, c0, e0, m0, held_result;
    logic [4:0] fl0, held_status;
    logic [31:0] held_tag;
    int sent, received, cycles, max_inflight, blocked;
    bit was_stalled, mismatch;
    reset_units();
    file_in = $fopen("cases.txt", "r"); n = 0;
    while (!$feof(file_in)) begin
      rc = $fscanf(file_in, "%d %d %d %d %d %d %d %d %h %h %h %h %h %h\n",
        id0, u0, op0, sf0, df0, if0, um0, rm0, a0, b0, c0, e0, m0, fl0);
      if (rc != 14) $fatal(1, "BAD_STREAM_INPUT");
      if (u0 == unit_id && id0 % 7 == 0) begin
        if (n >= 1024) $fatal(1, "STREAM_CAPACITY");
        ids[n] = 200000 + id0 + 10000*unit_id; opc[n] = op0; srcf[n] = sf0;
        dstf[n] = df0; intf[n] = if0; uns[n] = um0; rnd[n] = rm0;
        aa[n] = a0; bb[n] = b0; cc[n] = c0; exp[n] = e0; masks[n] = m0; ef[n] = fl0;
        n++;
      end
    end
    $fclose(file_in);
    if (n == 0) return;
    sent = 0; received = 0; cycles = 0; max_inflight = 0; blocked = 0; was_stalled = 0;
    while (received < n) begin
      @(negedge clk);
      ordy[unit_id] = (cycles % 5 >= 2);
      iv[unit_id] = sent < n;
      if (sent < n) begin
        operands = {cc[sent], bb[sent], aa[sent]}; tag = ids[sent];
        op = operation_e'(opc[sent]); sf = fp_format_e'(srcf[sent]);
        df = fp_format_e'(dstf[sent]); infmt = int_format_e'(intf[sent]);
        umod = uns[sent]; rm = roundmode_e'(rnd[sent]);
      end else rm = roundmode_e'(cycles % 5);
      @(posedge clk);
      if (was_stalled && (!ov[unit_id] || result[unit_id] !== held_result ||
          flags[unit_id] !== held_status || tags[unit_id] !== held_tag))
        $fatal(1, "STREAM_STABILITY unit=%0d", unit_id);
      was_stalled = ov[unit_id] && !ordy[unit_id];
      held_result = result[unit_id]; held_status = flags[unit_id]; held_tag = tags[unit_id];
      if (was_stalled) blocked++;
      if (iv[unit_id] && ir[unit_id]) sent++;
      if (ov[unit_id] && ordy[unit_id]) begin
        if (received >= sent) $fatal(1, "UNISSUED_RESULT");
        mismatch = (tags[unit_id] !== 32'(ids[received])) ||
            ((result[unit_id] & masks[received]) !== exp[received]) || (flags[unit_id] !== ef[received]);
        $fdisplay(trace, "%0d,%0d,%016h,%02h,%0d,%0d,%0d", ids[received], unit_id,
          result[unit_id], flags[unit_id], tags[unit_id], cycles, mismatch);
        if (mismatch) bad++;
        received++; count++;
      end
      if (sent-received > max_inflight) max_inflight = sent-received;
      if (++cycles > 20*n+100) $fatal(1, "STREAM_TIMEOUT");
    end
    @(negedge clk); iv = '0; ordy = '0;
    if (max_inflight < 2 || blocked == 0) $fatal(1, "INSUFFICIENT_PIPE_PRESSURE");
    $display("STREAM unit=%0d sent=%0d received=%0d max_inflight=%0d blocked=%0d", unit_id,
      sent, received, max_inflight, blocked);
    repeat (5) begin
      @(negedge clk);
      if (ov != 0) $fatal(1, "STREAM_EXTRA_RESULT");
    end
  endtask

  task automatic reset_case(input int u);
    logic [63:0] one;
    fp_format_e f;
    f = u == 2 ? FP32 : (u == 4 ? FP16 : FP64);
    one = f == FP32 ? 64'hffffffff3f800000 :
          (f == FP16 ? 64'hffffffffffff3c00 : 64'h3ff0000000000000);
    reset_units();
    @(negedge clk);
    operands = {64'b0, one, u == 0 ? 64'd1 : one};
    op = u == 0 ? I2F : (u == 5 ? DIV : MUL);
    sf = f; df = f; infmt = INT32; rm = RNE; umod = 0; tag = 32'hfffe0000 + u;
    iv[u] = 1;
    do @(posedge clk); while (!ir[u]);
    // Reset with accepted work still resident in pipeline/launch state.
    reset_units();
    repeat (5) begin
      @(negedge clk);
      if (ov != 0) $fatal(1, "RESET_GHOST unit=%0d", u);
    end
    $display("RESET unit=%0d canceled=1 ghost=0", u);
    run_case(300000 + u, u, u == 0 ? int'(I2F) : (u == 5 ? int'(DIV) : int'(MUL)),
             int'(f), int'(f), int'(INT32), 0, int'(RNE),
             u == 0 ? 64'd1 : one, one, 0, one, '1, 0);
  endtask

  // Cancellation is tested at each of the C910 launch phases. No DUT force.
  task automatic flush_case(input int delay_cycles, input bit is_vector);
    int waited;
    bit bad_clear;
    reset_units();
    @(negedge clk);
    operands[0] = 64'h3ff0000000000000;
    operands[1] = 64'h4008000000000000;
    op = DIV; df = FP64; rm = RNE; tag = 32'hffff0000 + delay_cycles;
    vectorial = is_vector; iv[5] = 1;
    do @(posedge clk); while (!ir[5]);
    @(negedge clk);
    iv[5] = 0;
    if (delay_cycles == 99) begin
      waited = 0;
      while (!div_done) begin
        @(negedge clk);
        if (++waited > 200) $fatal(1, "VECTOR_DONE_TIMEOUT");
      end
      repeat (2) @(negedge clk);
    end else repeat (delay_cycles) @(negedge clk);
    flush = 1;
    @(posedge clk);
    @(negedge clk);
    bad_clear = (div_dut.func_sel !== 0 || div_dut.op_sel !== 0 || div_dut.unit_done_q !== 0);
    $display("FLUSH delay=%0d vector=%0d func=%b op=%b done=%b bad=%0d", delay_cycles,
             is_vector, div_dut.func_sel, div_dut.op_sel, div_dut.unit_done_q, bad_clear);
    if (bad_clear) bad++;
    flush = 0; vectorial = 0;
    // A new request immediately follows cancellation; all arithmetic is oracle checked.
    run_case(100000 + delay_cycles + 1000*int'(is_vector), 5, int'(DIV), int'(FP64),
             int'(FP64), int'(INT64), 0, int'(RNE), 64'h4022000000000000,
             64'h4008000000000000, 0, 64'h4008000000000000, '1, 0);
    repeat (8) begin
      @(negedge clk);
      if (ov != 0) $fatal(1, "GHOST_AFTER_FLUSH");
    end
  endtask

  initial begin
    int rc, id, u, opcode, srcfmt, dstfmt, intfmt, unsignedop, rounding;
    logic [63:0] a, b, c, expected, result_mask;
    logic [4:0] expected_flags;
    operands = '0; op = F2F; rm = RNE; sf = FP64; df = FP64;
    infmt = INT32; umod = 0; tag = 0;
    trace = $fopen("trace.csv", "w");
    probes = $fopen("fma_probes.csv", "w");
    $fdisplay(probes, "time,tag,format,rm,pre,rounded,rs,mantissa,tail,uf");
    fd = $fopen("cases.txt", "r");
    if (!fd || !trace) $fatal(1, "FILES_MISSING");
    $fdisplay(trace, "id,unit,result,flags,tag,wait_cycles,mismatch");
    reset_units();
    while (!$feof(fd)) begin
      rc = $fscanf(fd, "%d %d %d %d %d %d %d %d %h %h %h %h %h %h\n",
                   id, u, opcode, srcfmt, dstfmt, intfmt, unsignedop, rounding,
                   a, b, c, expected, result_mask, expected_flags);
      if (rc != 14) $fatal(1, "BAD_CASE_INPUT fields=%0d", rc);
      run_case(id, u, opcode, srcfmt, dstfmt, intfmt, unsignedop, rounding,
               a, b, c, expected, result_mask, expected_flags);
    end
    if (!$test$plusargs("ARITH_ONLY")) begin
      for (int d = 0; d < 4; d++) flush_case(d, 0);
      flush_case(99, 1);
    end
    if ($test$plusargs("STRESS")) begin
      for (int u = 0; u < 5; u++) stream_cases(u);
      for (int u = 0; u < 6; u++) reset_case(u);
    end
    $fclose(fd); $fclose(trace);
    $display("COMPLETE cases=%0d bad=%0d", count, bad);
    $finish;
  end

  initial begin
    #100000000;
    $fatal(1, "GLOBAL_TIMEOUT");
  end
endmodule
