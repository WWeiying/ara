`timescale 1ns/1ps

module mvp_audit_tb;
  logic clk = 0;
  logic rst_n = 0;
  logic div_start = 0;
  logic sqrt_start = 0;
  logic kill = 0;
  logic [63:0] operand_a = 0, operand_b = 0;
  logic [2:0] rm = 0;
  logic [5:0] precision_ctl = 0;
  logic [1:0] fmt = 0;
  wire [63:0] result;
  wire [4:0] flags;
  wire ready, done;
  int case_id = -1;
  int cycle = 0;
  int accepted = 0, completed = 0, pending = 0;
  int trace_fd, results_fd;

  div_sqrt_top_mvp dut (
    .Clk_CI(clk), .Rst_RBI(rst_n),
    .Div_start_SI(div_start), .Sqrt_start_SI(sqrt_start),
    .Operand_a_DI(operand_a), .Operand_b_DI(operand_b),
    .RM_SI(rm), .Precision_ctl_SI(precision_ctl), .Format_sel_SI(fmt),
    .Kill_SI(kill), .Result_DO(result), .Fflags_SO(flags),
    .Ready_SO(ready), .Done_SO(done)
  );

  wire fire = div_start && ready && rst_n;
  wire signed [57:0] raw_remainder = dut.nrbd_nrsc_U0.control_U0.Partial_remainder_DP;
  wire [56:0] quotient = dut.nrbd_nrsc_U0.control_U0.Quotient_DP;
  wire signed [53:0] denominator = dut.nrbd_nrsc_U0.control_U0.Denominator_se_D;
  wire signed [57:0] denominator_scaled = {denominator, 4'b0};
  wire [5:0] count_q = dut.nrbd_nrsc_U0.control_U0.Crtl_cnt_S;
  wire [5:0] count_limit = dut.nrbd_nrsc_U0.control_U0.State_ctl_S;
  wire final_state = dut.nrbd_nrsc_U0.control_U0.Final_state_S;
  wire iteration_enable = dut.nrbd_nrsc_U0.control_U0.Fsm_enable_S;
  wire normal_operation = dut.Special_case_dly_SB;
  wire remainder_nonzero = dut.Remainder_nonzero_S;
  wire [2:0] latched_rm = dut.RM_dly_S;
  wire [1:0] latched_fmt = dut.nrbd_nrsc_U0.control_U0.Format_sel_S;
  wire [52:0] numerator = dut.Mant_a_D;
  wire [52:0] denominator_mant = dut.Mant_b_D;
  wire [11:0] operand_exp_a = dut.Exp_a_D, operand_exp_b = dut.Exp_b_D;
  wire sign_z = dut.Sign_z_D;
  wire full_precision = dut.Full_precision_S;
  wire div_enable = dut.Div_enable_S;
  wire [12:0] prenorm_exp = dut.Exp_z_D;
  wire [56:0] prenorm_mant = dut.Mant_z_D;
  wire [10:0] norm_exp = dut.fpu_norm_U0.Exp_res_norm_D;
  wire [52:0] norm_mant = dut.fpu_norm_U0.Mant_res_norm_D;
  wire [56:0] explicit_round = dut.fpu_norm_U0.Mant_forround_D;
  wire [1:0] lower_bits = dut.fpu_norm_U0.Mant_lower_D;
  wire sticky = dut.fpu_norm_U0.Mant_sticky_bit_D;
  wire round_up = dut.fpu_norm_U0.Mant_roundUp_S;
  wire overflow = dut.fpu_norm_U0.Exp_OF_S;
  wire overflow_to_inf = dut.fpu_norm_U0.Overflow_to_inf_S;
  wire [53:0] rounded_upper = dut.fpu_norm_U0.Mant_upperRounded_D;
  wire [10:0] rounded_exp = dut.fpu_norm_U0.Exp_res_round_D;
  wire [51:0] rounded_mant = dut.fpu_norm_U0.Mant_res_round_D;

  always #5 clk = ~clk;

  task automatic trace_sample(input string phase);
    $fwrite(trace_fd,
      "%0d,%0d,%0t,%s,%b,%b,%b,%b,%b,%0d,%0d,%0d,%h,%h,%h,%h,%h,%0d,%h,%h,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%h,%h,%h,%h,%h,%b,%b,%b,%b,%b,%h,%h,%h,%h,%h\n",
      case_id, cycle, $time, phase, rst_n, div_start, ready, fire, done,
      accepted, completed, pending, operand_a, operand_b, fmt, rm,
      raw_remainder, raw_remainder, quotient, denominator, denominator,
      count_q, final_state, iteration_enable, normal_operation, remainder_nonzero,
      div_enable, full_precision, latched_fmt, latched_rm, prenorm_exp, prenorm_mant,
      norm_exp, norm_mant, lower_bits, sticky, round_up, overflow, overflow_to_inf,
      explicit_round, rounded_exp, rounded_mant, result, flags);
  endtask

  // Pre-edge accounting is distinct from observing updated DUT registers.
  always @(posedge clk) begin
    cycle = cycle + 1;
    trace_sample("pre");
    if (rst_n) begin
      if (fire) begin
        if (pending != 0 || done !== 1'b0)
          $fatal(1, "HARNESS_ERROR overlapping acceptance");
        accepted = accepted + 1;
        pending = 1;
      end
      if (done) begin
        if (pending != 1)
          $fatal(1, "HARNESS_ERROR unsolicited or duplicate Done");
        completed = completed + 1;
        pending = 0;
      end
    end else if (pending != 0) begin
      $fatal(1, "HARNESS_ERROR reset cancelled an unconsumed request");
    end
    #1;
    trace_sample("post_nba");
  end

  task automatic run_case(
    input int id,
    input string name,
    input logic [1:0] format_value,
    input logic [2:0] round_mode,
    input logic [63:0] a, b, oracle_result,
    input logic [4:0] oracle_flags
  );
    logic [63:0] observed_result;
    logic [4:0] observed_flags;
    logic [52:0] expected_mant_a, expected_mant_b;
    logic [11:0] expected_exp_a, expected_exp_b;
    int acceptance_cycle, latency;
    bit result_match;

    @(negedge clk);
    case_id = id;
    rst_n = 0;
    div_start = 0;
    repeat (3) @(negedge clk);
    if (ready !== 1'b1 || done !== 1'b0 || count_q !== 6'b0 ||
        quotient !== 57'b0 || raw_remainder !== 58'b0)
      $fatal(1, "HARNESS_ERROR reset state case=%s", name);
    rst_n = 1;
    @(negedge clk);
    if (ready !== 1'b1 || done !== 1'b0 || accepted != id || completed != id)
      $fatal(1, "HARNESS_ERROR not idle before case=%s", name);
    operand_a = a;
    operand_b = b;
    fmt = format_value;
    rm = round_mode;
    div_start = 1;

    @(posedge clk);
    if (fire !== 1'b1 || done !== 1'b0)
      $fatal(1, "HARNESS_ERROR request not accepted case=%s", name);
    #1;
    acceptance_cycle = cycle;
    if (format_value == 2'b01) begin
      expected_mant_a = {1'b1, a[51:0]};
      expected_mant_b = {1'b1, b[51:0]};
      expected_exp_a = {1'b0, a[62:52]};
      expected_exp_b = {1'b0, b[62:52]};
    end else begin
      expected_mant_a = {1'b1, a[22:0], 29'b0};
      expected_mant_b = {1'b1, b[22:0], 29'b0};
      expected_exp_a = {4'b0, a[30:23]};
      expected_exp_b = {4'b0, b[30:23]};
    end
    if (latched_fmt !== format_value || latched_rm !== round_mode ||
        numerator !== expected_mant_a || denominator_mant !== expected_mant_b ||
        operand_exp_a !== expected_exp_a || operand_exp_b !== expected_exp_b ||
        full_precision !== 1'b1 || normal_operation !== 1'b1 ||
        sign_z !== (format_value == 2'b01 ? (a[63] ^ b[63]) : (a[31] ^ b[31])))
      $fatal(1, "HARNESS_ERROR captured metadata mismatch case=%s", name);
    @(negedge clk);
    div_start = 0;

    latency = 0;
    while (done !== 1'b1 && latency < 64) begin
      @(posedge clk);
      #1;
      latency = cycle - acceptance_cycle;
    end
    if (done !== 1'b1 || latency == 0 || ready !== 1'b1 || div_enable !== 1'b1)
      $fatal(1, "HARNESS_ERROR completion/timeout case=%s latency=%0d", name, latency);
    if ($isunknown({result, flags, raw_remainder, quotient, denominator,
                    norm_exp, norm_mant, lower_bits, sticky, round_up}))
      $fatal(1, "HARNESS_ERROR unknown completion payload case=%s", name);
    observed_result = result;
    observed_flags = flags;
    result_match = (result === oracle_result && flags === oracle_flags);
    $fwrite(results_fd,
      "%0d,%s,%0d,%0d,%h,%h,%h,%h,%h,%h,%0d,%0d,%h,%h,%h,%h,%h,%h,%b,%b,%b,%b,%h,%h,%h,%b\n",
      id, name, format_value == 2'b01 ? 64 : 32, round_mode, a, b,
      oracle_result, oracle_flags, result, flags, latency, result_match,
      raw_remainder, quotient, denominator, norm_exp, norm_mant, explicit_round,
      lower_bits, sticky, round_up, overflow, rounded_exp, rounded_mant,
      denominator_scaled, remainder_nonzero);
    $display("AUDIT_CASE id=%0d name=%s result=%h flags=%h expected=%h/%h oracle_match=%0d latency=%0d",
             id, name, result, flags, oracle_result, oracle_flags, result_match, latency);

    // The next edge is where a wrapper consumes the registered Done indication.
    @(posedge clk);
    if (done !== 1'b1 || result !== observed_result || flags !== observed_flags)
      $fatal(1, "HARNESS_ERROR pre-edge/post-NBA payload disagreement case=%s", name);
    #1;
    if (done !== 1'b0 || accepted != id + 1 || completed != id + 1 || pending != 0)
      $fatal(1, "HARNESS_ERROR completion accounting case=%s", name);
    repeat (2) begin
      @(posedge clk);
      #1;
      if (done !== 1'b0 || ready !== 1'b1)
        $fatal(1, "HARNESS_ERROR drain case=%s", name);
    end
  endtask

  initial begin
    trace_fd = $fopen("trace.csv", "w");
    results_fd = $fopen("results.csv", "w");
    if (!trace_fd || !results_fd) $fatal(1, "HARNESS_ERROR opening evidence files");
    $fwrite(trace_fd, "case_id,cycle,time,phase,reset_n,start,ready,fire,done,accepted,completed,pending,a,b,fmt,rm,remainder,remainder_signed,quotient,denominator,denominator_signed,count,final_state,iteration_enable,normal_operation,remainder_nonzero,div_enable,full_precision,latched_fmt,latched_rm,prenorm_exp,prenorm_mant,norm_exp,norm_mant,lower,sticky,round_up,overflow,overflow_to_inf,explicit_round,rounded_exp,rounded_mant,result,flags\n");
    $fwrite(results_fd, "id,name,format,rm,a,b,expected_result,expected_flags,result,flags,latency,oracle_match,remainder,quotient,denominator,norm_exp,norm_mant,explicit_round,lower,sticky,round_up,overflow,rounded_exp,rounded_mant,denominator_scaled,remainder_nonzero\n");
    $dumpfile("probes.vcd");
    $dumpvars(1, mvp_audit_tb);
    `include "cases.svh"
    if (accepted != 8 || completed != 8 || pending != 0)
      $fatal(1, "HARNESS_ERROR incomplete suite");
    $display("AUDIT_COMPLETE cases=8 accepted=%0d completed=%0d pending=%0d", accepted, completed, pending);
    $fclose(results_fd);
    $fclose(trace_fd);
    $finish;
  end

  initial begin
    #6000;
    $fatal(1, "HARNESS_ERROR global 600-cycle timeout");
  end
endmodule
