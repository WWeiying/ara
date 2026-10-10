module fsm_reset_probe_dut (
  input logic clk_i,
  input logic rst_ni,
  input logic go_i,
  output logic [1:0] observed_o
);
  typedef enum logic [1:0] {IDLE, A, B, C} state_e;
  state_e state_q, state_d;
  assign observed_o = state_q;
  always_comb begin
    state_d = state_q;
    case (state_q)
      IDLE: if (go_i) state_d = A;
      A: state_d = B;
      B: state_d = C;
      C: state_d = A;
      default: state_d = state_q;
    endcase
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) state_q <= IDLE;
    else state_q <= state_d;
  end
endmodule

module fsm_reset_probe_tb;
  logic clk_i = 0;
  logic rst_ni = 1;
  logic go_i = 0;
  logic [1:0] observed;
  fsm_reset_probe_dut dut(clk_i, rst_ni, go_i, observed);
  always #5 clk_i = ~clk_i;
  always @(observed) $display("STATE_EVENT t=%0t rst=%0b q=%0d", $time, rst_ni, observed);
  task automatic reset_from(input logic [1:0] expected);
    do @(negedge clk_i); while (observed !== expected);
    #1;
    if (observed !== expected || rst_ni !== 1) $fatal(1, "Wrong pre-reset state");
    $display("RESET_BEFORE t=%0t q=%0d clk=%0b", $time, observed, clk_i);
    rst_ni = 0;
    #1;
    if (observed !== 0) $fatal(1, "Async reset did not restore IDLE");
    $display("RESET_AFTER t=%0t q=%0d clk=%0b", $time, observed, clk_i);
    #12;
    rst_ni = 1;
  endtask
  initial begin
    #1 rst_ni = 0;
    #1;
    if (observed !== 0) $fatal(1, "Initial reset failed");
    #10 rst_ni = 1;
    go_i = 1;
    repeat (7) @(negedge clk_i);
    reset_from(1);
    reset_from(2);
    reset_from(3);
    repeat (5) @(negedge clk_i);
    $display("FSM_RESET_PROBE_FUNCTIONAL_PASS");
    $finish;
  end
  initial begin
    #2000;
    $fatal(1, "Bounded probe timeout");
  end
endmodule
