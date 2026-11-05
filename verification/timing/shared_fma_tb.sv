// SPDX-License-Identifier: SHL-0.51
module shared_fma_tb;
  import fpnew_pkg::*;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst = 0, flush = 0, iv = 0, ir, ov, ready = 0, busy;
  logic [2:0][63:0] operands;
  logic [NUM_FP_FORMATS-1:0][2:0] boxed;
  roundmode_e rm;
  operation_e op;
  fp_format_e fmt;
  logic mod, vec;
  logic [3:0] mask;
  logic [31:0] tag, out_tag;
  logic [63:0] result;
  status_t flags;
  logic [2:0][63:0] ref_results;
  status_t [2:0] ref_flags;
  typedef struct packed {logic [63:0] data; status_t flags; logic [31:0] tag;} expected_t;
  expected_t pending[$];
  expected_t expected, want;
  int accepted = 0, checked = 0, aborted = 0, stalls = 0;
  int format_count[3], operation_count[4], rounding_count[5];
  logic held = 0;
  logic input_fired = 0;
  expected_t held_value;

  simd_fma_shared #(.TagType(logic [31:0])) dut (
    .clk_i(clk), .rst_ni(rst), .operands_i(operands), .is_boxed_i(boxed),
    .rnd_mode_i(rm), .op_i(op), .op_mod_i(mod), .fmt_i(fmt),
    .vectorial_op_i(vec), .simd_mask_i(mask), .tag_i(tag),
    .in_valid_i(iv), .in_ready_o(ir), .flush_i(flush),
    .result_o(result), .status_o(flags), .tag_o(out_tag),
    .out_valid_o(ov), .out_ready_i(ready), .busy_o(busy)
  );

  // Old per-format arithmetic is combinational here; the scoreboard is
  // independent of the candidate pipeline latency, packing and mask reduction.
  for (genvar f = 0; f < 3; f++) begin : gen_ref
    localparam fp_format_e Format = fp_format_e'(f);
    localparam int Width = fp_width(Format);
    localparam int Lanes = 64/Width;
    logic [Lanes-1:0][Width-1:0] values;
    status_t [Lanes-1:0] status;
    for (genvar l = 0; l < Lanes; l++) begin : gen_element
      logic [2:0][Width-1:0] ops;
      for (genvar k = 0; k < 3; k++)
        assign ops[k] = operands[k][Width*l+:Width];
      fpnew_fma #(.FpFormat(Format), .NumPipeRegs(0)) reference (
        .clk_i(clk), .rst_ni(rst), .operands_i(ops),
        .is_boxed_i(vec ? 3'b111 : boxed[f]), .rnd_mode_i(rm),
        .op_i(op), .op_mod_i(mod), .tag_i(1'b0), .mask_i(1'b1), .aux_i(1'b0),
        .in_valid_i(1'b1), .in_ready_o(), .flush_i(1'b0),
        .result_o(values[l]), .status_o(status[l]), .extension_bit_o(),
        .tag_o(), .mask_o(), .aux_o(), .out_valid_o(), .out_ready_i(1'b1), .busy_o()
      );
    end
    always_comb begin
      ref_results[f] = '1;
      ref_flags[f] = '0;
      for (int l = 0; l < Lanes; l++) if (l == 0 || vec) begin
        ref_results[f][Width*l+:Width] = values[l];
        if (mask[l*(Width/16)]) ref_flags[f] |= status[l];
      end
    end
  end
  always_comb expected = '{ref_results[fmt], ref_flags[fmt], tag};

  always @(posedge clk) begin
    input_fired = rst && !flush && iv && ir;
    if (!rst || flush) begin
      aborted += pending.size();
      pending.delete();
      held = 0;
    end else begin
      if (held && (!ov || {result, flags, out_tag} !== held_value))
        $fatal(1, "Output changed under backpressure");
      held = ov && !ready;
      held_value = '{result, flags, out_tag};
      if (iv && ir) begin
        // Exact independent anchor: every element computes 1*1+1=2.
        if (tag < 1200) begin
          case (fmt)
            FP16: if (expected.data !== {4{16'h4000}}) $fatal(1,"FP16 exact oracle");
            FP32: if (expected.data !== {2{32'h40000000}}) $fatal(1,"FP32 exact oracle");
            FP64: if (expected.data !== 64'h4000000000000000) $fatal(1,"FP64 exact oracle");
            default: $fatal(1,"Invalid oracle format");
          endcase
          if (expected.flags !== '0) $fatal(1,"Exact FMA raised flags");
        end
        if (tag >= 1200 && tag < 1400) begin
          if (expected.data !== 64'h3f8000007fc00000)
            $fatal(1,"Independent zero-times-infinity oracle");
          if (expected.flags !== (tag[0] ? 5'b00000 : 5'b10000))
            $fatal(1,"FP32 element mask leaked or suppressed invalid flag");
        end
        pending.push_back(expected);
        accepted++;
        format_count[int'(fmt)]++;
        operation_count[int'(op)]++;
        rounding_count[int'(rm)]++;
      end
      if (ov && !ready) stalls++;
      if (ov && ready) begin
        if (!pending.size()) $fatal(1, "Unsolicited output");
        want = pending.pop_front();
        if ({result,flags,out_tag} !== want)
          $fatal(1, "FMA mismatch tag=%d want_tag=%d result=%h want=%h flags=%h want=%h",
                 out_tag,want.tag,result,want.data,flags,want.flags);
        checked++;
      end
    end
  end

  function automatic logic [63:0] special(int width, int selection);
    logic [63:0] one, inf, qnan, snan, sign;
    case (width)
      16: begin one='h3c00; inf='h7c00; qnan='h7e00; snan='h7c01; sign='h8000; end
      32: begin one='h3f800000; inf='h7f800000; qnan='h7fc00000; snan='h7f800001; sign='h80000000; end
      default: begin one='h3ff0000000000000; inf='h7ff0000000000000;
        qnan='h7ff8000000000000; snan='h7ff0000000000001; sign='h8000000000000000; end
    endcase
    case (selection % 10)
      0: return 0;
      1: return sign;
      2: return one;
      3: return one | sign;
      4: return inf;
      5: return inf | sign;
      6: return qnan;
      7: return snan;
      8: return 1;
      default: return inf - 1;
    endcase
  endfunction

  initial begin
    int width;
    int seed;
    seed = 32'h5f4a12;
    seed = $urandom(seed);
    operands='0; boxed='1; fmt=FP16; op=ADD; rm=RNE; mod=0; vec=1; mask='1; tag=0;
    repeat (3) @(negedge clk);
    rst=1;
    // First saturate the pipeline with mixed-format vectors: no bubbles or
    // backpressure. Then exercise stalls, scalar boxing, flush and reset.
    for (int n=0; n<24000; n++) begin
      @(negedge clk);
      ready = n < 1200 ? 1'b1 : ($urandom_range(0,3) != 0 && n%89 > 14);
      flush = n > 1200 && n%607 == 0;
      rst = !(n > 1200 && n%1999 == 0);
      if (!rst || flush || !iv || input_fired) begin
        iv = rst && !flush && (n < 1200 || $urandom_range(0,4) != 0);
        fmt=fp_format_e'(n%3); width=fp_width(fmt);
        op=operation_e'((n/3)%4); rm=roundmode_e'((n/12)%5);
        mod=(n/60)%2; vec=n<1200 || n%7 != 0;
        mask=4'(n/3); boxed=n%11 == 0 ? '0 : '1; tag=32'(n);
        for (int k=0;k<3;k++) begin
          operands[k]={$urandom,$urandom};
          if (n%2 == 0) begin
            operands[k]='0;
            for (int l=0;l<64/width;l++)
              operands[k] |= special(width,(n/2+k*3+l)%10) << (l*width);
          end
        end
        if (n < 1200) begin
          op=FMADD; rm=RNE; mod=0; mask='1; boxed='1;
          for (int k=0;k<3;k++) begin
            operands[k]='0;
            for (int l=0;l<64/width;l++) operands[k] |= special(width,2) << (l*width);
          end
        end
        if (n >= 1200 && n < 1400) begin
          fmt=FP32; vec=1; op=MUL; rm=RNE; mod=0; boxed='1;
          operands[0]=64'h3f80000000000000;
          operands[1]=64'h3f8000007f800000;
          operands[2]='0;
          mask=n%2 ? 4'b0100 : 4'b0001;
        end
      end
      if (n==1200 && accepted != 1200)
        $fatal(1,"Mixed-format pipeline did not sustain one vector command per cycle: %d",accepted);
    end
    @(negedge clk); iv=0; flush=0; rst=1; ready=1;
    repeat (15) @(negedge clk);
    if (pending.size() || busy || checked < 10000 || stalls < 100 || aborted == 0)
      $fatal(1,"Incomplete regression accepted=%d checked=%d aborted=%d stalls=%d pending=%d",
             accepted,checked,aborted,stalls,pending.size());
    foreach (format_count[i]) if (format_count[i]<1000) $fatal(1,"Missing format");
    foreach (operation_count[i]) if (operation_count[i]<1000) $fatal(1,"Missing operation");
    foreach (rounding_count[i]) if (rounding_count[i]<1000) $fatal(1,"Missing rounding mode");
    if (accepted != checked+aborted) $fatal(1,"Transaction accounting mismatch");
    $display("SHARED_FMA_PASS accepted=%0d checked=%0d aborted=%0d stalls=%0d",
             accepted,checked,aborted,stalls);
    $finish;
  end
  initial begin #1000000; $fatal(1,"Watchdog"); end
endmodule
