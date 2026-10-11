// SPDX-License-Identifier: SHL-0.51
// Multibeat equivalence and latency check. Arithmetic has a separate Python oracle.
module exact_round_bypass_tb;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic start, valid, ready_out, last, fp16;
  logic [2:0] rm;
  logic [31:0] seed;
  logic [63:0] data;
  logic [3:0] active;
  logic [2:0][1:0] ready, out_valid;
  logic [383:0] payload[3][2];
  integer cycles=0, cases=2000, schedule_seed=32971;
  integer first_valid[3][2];
  integer saved_cycle, latency_checks=0, held_cycles=0;
  logic [383:0] held[3][2];
  always @(posedge clk) cycles <= cycles+1;

  for(genvar m=0;m<3;m++) begin : gen_mode
    for(genvar v=0;v<2;v++) begin : gen_version
      logic [287:0] exact_value;
      logic [3:0] special;
      logic seen, finite_seen, positive_zero, negative_zero, seed_valid, format_fp16;
      logic [31:0] seed_value, result;
      logic [2:0] rounding;
      logic [4:0] status;
      fp32_exact_reduction_accum #(
        .ExponentSegmented(m!=0), .EmitRoundedResult(m==2),
        .DeferSeed(m!=2), .SkipUnroundedRoundStage(v==1)
      ) dut (
        .clk_i(clk), .rst_ni(rst_n), .start_i(start), .rnd_mode_i(rm),
        .format_fp16_i(m==2 ? 1'b0 : fp16), .seed_valid_i(1'b1), .seed_i(seed),
        .data_i(data), .active_i(m==2 ? {2'b0,active[1:0]} : active),
        .last_i(last), .in_valid_i(valid), .in_ready_o(ready[m][v]),
        .result_o(result), .status_o(status), .out_valid_o(out_valid[m][v]),
        .out_ready_i(ready_out), .busy_o(), .exact_value_o(exact_value),
        .special_o(special), .source_seen_o(seen), .finite_nonzero_seen_o(finite_seen),
        .pos_zero_seen_o(positive_zero), .neg_zero_seen_o(negative_zero),
        .seed_valid_o(seed_valid), .seed_o(seed_value), .rnd_mode_o(rounding),
        .format_fp16_o(format_fp16)
      );
      assign payload[m][v]={exact_value,special,seen,finite_seen,positive_zero,
        negative_zero,seed_valid,seed_value,rounding,format_fp16,result,status};
    end
  end

  initial begin
    void'($value$plusargs("CASES=%d",cases));
    void'($value$plusargs("SCHEDULE_SEED=%d",schedule_seed));
    schedule_seed=$urandom(schedule_seed);
    start=0;valid=0;ready_out=0;last=0;fp16=0;rm=0;seed=0;data=0;active=0;
    repeat(4) @(negedge clk);
    rst_n=1;
    for(int n=0;n<cases;n++) begin
      automatic int beats=1+n%17;
      automatic int hold_count=n%33;
      fp16=n%2;rm=3'(n%5);seed=$urandom;
      for(int m=0;m<3;m++) for(int v=0;v<2;v++) first_valid[m][v]=0;
      for(int beat=0;beat<beats;beat++) begin
        repeat($urandom_range(0,3)) @(negedge clk);
        start=beat==0;valid=1;last=beat==beats-1;
        data={$urandom,$urandom};
        if(n%7==0) data=64'h7f800001_80000000;
        if(n%11==0) data=64'h7f800000_ff800000;
        active=4'($urandom_range(0,15));
        if(!fp16) active[3:2]=0;
        if(n%13==0) active=0;
        @(posedge clk);
        if(!(&ready)) $fatal(1,"Unexpected input backpressure before last beat");
        #1;
        @(negedge clk);start=0;valid=0;
      end
      saved_cycle=cycles;
      while(!(&out_valid)) begin
        @(posedge clk);#1;
        for(int m=0;m<3;m++) for(int v=0;v<2;v++)
          if(out_valid[m][v] && first_valid[m][v]==0) first_valid[m][v]=cycles;
        if(cycles-saved_cycle>20) $fatal(1,"Result timeout");
      end
      for(int m=0;m<3;m++) begin
        if(payload[m][0] !== payload[m][1]) $fatal(1,"State mismatch case=%0d mode=%0d",n,m);
        if(first_valid[m][0]-first_valid[m][1] != (m==2 ? 0:1))
          $fatal(1,"Unexpected latency case=%0d mode=%0d old=%0d new=%0d",n,m,first_valid[m][0],first_valid[m][1]);
        latency_checks++;
        for(int v=0;v<2;v++) held[m][v]=payload[m][v];
      end
      repeat(hold_count) begin
        @(posedge clk);#1;
        for(int m=0;m<3;m++) for(int v=0;v<2;v++)
          if(!out_valid[m][v] || payload[m][v] !== held[m][v]) $fatal(1,"Unstable held result");
        held_cycles++;
      end
      @(negedge clk);ready_out=1;
      @(negedge clk);ready_out=0;
    end
    $display("PASS exact round bypass: streams=%0d mode_checks=%0d held_cycles=%0d",cases,latency_checks,held_cycles);
    $finish;
  end
  initial begin #100000000; $fatal(1,"Watchdog"); end
endmodule
