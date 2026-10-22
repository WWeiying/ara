module verilator_coverage_smoke_dut (
  input  logic       clk_i,
  input  logic       rst_ni,
  input  logic       enable_i,
  input  logic [1:0] mode_i,
  output logic [3:0] count_o
);
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      count_o <= '0;
    end else if (enable_i) begin
      case (mode_i)
        2'd0: count_o <= count_o + 4'd1;
        2'd1: count_o <= count_o + 4'd2;
        default: count_o <= count_o - 4'd1;
      endcase
    end
  end
endmodule

module verilator_coverage_smoke;
  logic clk;
  logic rst_n;
  logic enable;
  logic [1:0] mode;
  logic [3:0] count;

  verilator_coverage_smoke_dut dut (
    .clk_i(clk),
    .rst_ni(rst_n),
    .enable_i(enable),
    .mode_i(mode),
    .count_o(count)
  );

  initial begin
    clk = 1'b0;
    forever #5 clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    enable = 1'b0;
    mode = 2'd0;
    repeat (2) @(negedge clk);
    rst_n = 1'b1;
    enable = 1'b1;
    repeat (3) @(negedge clk);
    mode = 2'd1;
    repeat (2) @(negedge clk);
    mode = 2'd2;
    repeat (2) @(negedge clk);
    enable = 1'b0;
    @(negedge clk);
    if (count !== 4'd5) $fatal(1, "count=%0d", count);
    $display("VERILATOR_COVERAGE_SMOKE_PASS count=%0d", count);
    $finish;
  end
endmodule
