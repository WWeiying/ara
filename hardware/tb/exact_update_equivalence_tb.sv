`timescale 1ns/1ps
module exact_update_equivalence_tb;
  logic clk_i=0; always #5 clk_i=~clk_i;
  logic rst_ni=0, start_i=0, in_valid_i=0, last_i=0, out_ready_i=0;
  logic [2:0] rnd_mode_i=0;
  logic format_fp16_i=0, seed_valid_i=0;
  logic [31:0] seed_i=0;
  logic [63:0] data_i=0;
  logic [3:0] active_i=0;
  typedef struct packed {
    logic ready, valid, busy;
    logic [31:0] result;
    logic [4:0] flags;
    logic [287:0] exact_value;
    logic [3:0] special;
    logic source_seen, finite_seen, pos_zero, neg_zero, seed_valid;
    logic [31:0] seed;
    logic [2:0] rm;
    logic fp16;
  } response_t;
  response_t response[16][9];
  logic [15:0] ready, busy;
  int cycles=0, cases=0;
  int test_cases=300;
  function automatic logic [31:0] population_value(input int n);
    int shift;
    logic sign_bit;
    shift=31;
    sign_bit=1'((n/25)%2);
`ifdef ARA_RED_WIDE_EXACT_SEGMENTS
    // Exercise the largest local shifts in all four exponent windows,
    // including the maximum finite FP32 exponent in the highest window.
    shift=63+64*((n/25)%4);
    if (shift>253) shift=253;
    sign_bit=1'((n/100)%2);
`endif
    return (sign_bit ? 32'h80000000 : 32'h0) |
           (32'(shift+1)<<23) | 32'h007fffff;
  endfunction
  function automatic logic population_cancels(input int n);
`ifdef ARA_RED_WIDE_EXACT_SEGMENTS
    return ((n/200)%3)==2;
`else
    return ((n/25)%3)==2;
`endif
  endfunction
  `define OUTPUTS(R) .in_ready_o(R.ready), .out_valid_o(R.valid), .busy_o(R.busy), \
    .result_o(R.result), .status_o(R.flags), .exact_value_o(R.exact_value), \
    .special_o(R.special), .source_seen_o(R.source_seen), \
    .finite_nonzero_seen_o(R.finite_seen), .pos_zero_seen_o(R.pos_zero), \
    .neg_zero_seen_o(R.neg_zero), .seed_valid_o(R.seed_valid), .seed_o(R.seed), \
    .rnd_mode_o(R.rm), .format_fp16_o(R.fp16)
  for(genvar c=0;c<16;c++) begin:g
    if (!((c & 2) && (c & 4))) begin:legal
    fp32_exact_reduction_accum_reference #(.ExponentSegmented((c&1)!=0),
      .EmitRoundedResult((c&2)!=0),.DeferSeed((c&4)!=0),
      .SkipUnroundedRoundStage((c&8)!=0)) original (.format_fp16_i((c & 2) ? 1'b0 : format_fp16_i), `OUTPUTS(response[c][0]), .*);
    for(genvar v=0;v<8;v++) begin:versions
      fp32_exact_reduction_accum #(.ExponentSegmented((c&1)!=0),
        .EmitRoundedResult((c&2)!=0),.DeferSeed((c&4)!=0),
        .SkipUnroundedRoundStage((c&8)!=0),.SharedBeatUpdate((v&1)!=0),.SharedNormalize((v&2)!=0),
        .CollisionForwardUpdate((v&4)!=0)) dut
        (.format_fp16_i((c & 2) ? 1'b0 : format_fp16_i), `OUTPUTS(response[c][v+1]), .*);
    end
    assign ready[c]=response[c][0].ready;
    assign busy[c]=response[c][0].busy;
    always @(posedge clk_i) if(rst_ni)
      for(int v=1;v<9;v++) begin
        response_t expected, actual;
        expected=response[c][0]; actual=response[c][v];
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
`ifndef ARA_RED_TEST_STRICT_EXACT_PAYLOAD
        // The transport contract defines exact_value only at out_valid.
        // Different in-place representations need not agree while accumulating.
        // Ready/valid, metadata, flags and the entire valid payload still match.
        if (!expected.valid && !actual.valid) begin
          expected.exact_value='0; actual.exact_value='0;
        end
`endif
`endif
        if(actual !== expected)
          $fatal(1,"update mismatch config=%0d version=%0d case=%0d cycle=%0d got=%h reference=%h",c,v,cases,cycles,response[c][v],response[c][0]);
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
        if (actual.valid && cases%25==0) begin
          // Independent fixed-integer model for the long population cases:
          // Decode the directed finite operand in the 2^-149 domain.
          logic signed [287:0] quantum, model;
          logic [31:0] sample_value;
          int population;
          sample_value=population_value(cases);
          quantum=288'hffffff << (int'(sample_value[30:23])-1);
          if (sample_value[31]) quantum=-quantum;
          population=population_cancels(cases) ? 0 : 256;
          if (!(c&4)) population++;
          model=quantum*population;
          if (actual.exact_value !== model)
            $fatal(1,"population oracle mismatch config=%0d version=%0d case=%0d got=%h expected=%h",c,v,cases,actual.exact_value,model);
        end
`endif
      end
    end else begin:unsupported
      // Deferred seed requires global finalization; local rounding is illegal.
      assign ready[c]=1'b1;
      assign busy[c]=1'b0;
    end
  end
  `undef OUTPUTS
  always @(posedge clk_i) cycles++;
  task automatic random_beat(input int n);
    data_i={$urandom,$urandom};active_i=4'($urandom);
    case(n%16)
      0:data_i='0;
      1:data_i=64'h7f800000ff800000;
      2:data_i=64'h7fc000007f800001;
      3:data_i=64'h7e007c00fc007c01;
      4:data_i=64'h3f8000003f800000;
      5:data_i=64'h3c003c003c003c00;
      6:begin data_i=64'h3c00bc003c00bc00;active_i=4'hf;end // Same bin, cancellation.
      7:begin data_i=64'h3f800000bf800000;active_i=4'hf;end
      8:begin data_i=64'h040084007bfffbff;active_i=4'hf;end // Two distant FP16 bins.
      9:begin data_i=64'h3c01bc023c03bc04;active_i=4'hf;end
      10:begin data_i=64'h3f8000013fffffff;active_i=4'h3;end
      11:begin data_i=64'h7bff7bff7bff7bff;active_i=4'hf;end
      12:begin data_i=64'h0001800100018001;active_i=4'hf;end
      13:begin data_i=64'h3c003c003c003c00;active_i=4'h5;end
      14:begin data_i=64'h7f7fffffff7fffff;active_i=4'h3;end
      15:begin data_i=64'h7e007c00fc007c01;active_i=4'h0;end
    endcase
  endtask
  initial begin
    if ($value$plusargs("TEST_CASES=%d",test_cases) && test_cases<=0)
      $fatal(1,"TEST_CASES must be positive");
    repeat(3) @(negedge clk_i);rst_ni=1;
    for(int n=0;n<test_cases;n++) begin
      int beats;logic concurrent_start;
      beats=1+$urandom_range(0,31);concurrent_start=1'($urandom);
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
      // Population carry near the supported FP32 bound: 256 source elements
      // plus seed. Other cases continue to cover bubbles and random lengths.
      if (n % 25 == 0) beats=128;
`endif
      cases=n;
      @(negedge clk_i);out_ready_i=0;
      format_fp16_i=1'(n);rnd_mode_i=3'(n/2);seed_valid_i=1'($urandom);seed_i=$urandom;
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
      if (n % 25 == 0) begin
        format_fp16_i=0;seed_valid_i=1;seed_i=population_value(n);
      end
`endif
      random_beat(n);start_i=1;in_valid_i=concurrent_start;last_i=(beats==1);
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
      if (n % 25 == 0) begin
        data_i={population_value(n),population_value(n)};active_i=4'h3;
      end
`endif
      @(negedge clk_i);start_i=0;in_valid_i=0;last_i=0;
      for(int b=concurrent_start?1:0;b<beats;b++) begin
        repeat($urandom_range(0,2)) @(negedge clk_i);
        if(!(&ready)) $fatal(1,"Unexpected input stall");
        // Input metadata is not stable after start; registered format must win.
        format_fp16_i=1'($urandom);rnd_mode_i=3'($urandom);seed_i=$urandom;
        random_beat(n+b);in_valid_i=1;last_i=(b==beats-1);
`ifdef ARA_RED_COMPACT_EXACT_SEGMENTS
        if (n % 25 == 0) begin
          data_i={population_value(n),population_value(n)};
          if (population_cancels(n) && b%2) data_i[63:0] ^= 64'h8000000080000000;
          active_i=4'h3;
        end
`endif
        @(negedge clk_i);in_valid_i=0;last_i=0;
      end
      repeat(8) @(negedge clk_i);
      out_ready_i=1;
      repeat(3) @(negedge clk_i);
      if(|busy) $fatal(1,"Failed to drain");
      out_ready_i=0;
    end
    $display("EXACT_UPDATE_EQUIVALENCE_PASS cases=%0d configs=12 cycles=%0d",cases+1,cycles);$finish;
  end
  initial begin #10000000; $fatal(1,"timeout"); end
endmodule
