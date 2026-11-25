`timescale 1ns/1ps
module cast_equiv_port #(parameter int Kind = 0)(input logic clk, output bit done);
  import fpnew_pkg::*;
  localparam fmt_logic_t FM = Kind == 2 ? 6'b001000 : Kind == 3 ? 6'b100000 : 6'b111000;
  localparam ifmt_logic_t IM = Kind == 0 ? 4'b0011 : Kind == 2 ? 4'b1100 :
                               Kind == 3 ? 4'b0010 : 4'b1111;
  localparam int W = maximum(max_fp_width(FM), max_int_width(IM));
  localparam int Depth = Kind == 0 ? 2 : Kind == 3 ? 1 : 3;
  logic rst_ni, in_valid_i, flush_i, out_ready_i, mask_i, op_mod_i;
  logic [W-1:0] operands_i;
  logic [NUM_FP_FORMATS-1:0] is_boxed_i;
  logic [7:0] tag_i, aux_i;
  roundmode_e rnd_mode_i;
  operation_e op_i;
  fp_format_e src_fmt_i, dst_fmt_i;
  int_format_e int_fmt_i;
  wire clk_i = clk;
  typedef struct packed {logic ready, valid, busy;} controls_t;
  typedef struct packed {
    logic [W-1:0] data;
    status_t flags;
    logic ext, mask;
    logic [7:0] tag, aux;
  } payload_t;
  controls_t ctl[2];
  payload_t data[2];
`define CAST_PARAMS .FpFmtConfig(FM), .IntFmtConfig(IM), .NumPipeRegs(Depth), \
    .PipeConfig(DISTRIBUTED), .TagType(logic [7:0]), .AuxType(logic [7:0])
`define CAST_PORTS(i) .in_ready_o(ctl[i].ready), .out_valid_o(ctl[i].valid), \
    .busy_o(ctl[i].busy), .result_o(data[i].data), .status_o(data[i].flags), \
    .extension_bit_o(data[i].ext), .mask_o(data[i].mask), \
    .tag_o(data[i].tag), .aux_o(data[i].aux), .*
  fpnew_cast_multi_ref #(`CAST_PARAMS) old_cast (`CAST_PORTS(0));
  fpnew_cast_multi     #(`CAST_PARAMS) new_cast (`CAST_PORTS(1));
`undef CAST_PORTS
`undef CAST_PARAMS

  int unsigned rng = 32'h2566613a + Kind;
  function automatic int unsigned draw();
    rng ^= rng << 13; rng ^= rng >> 17; rng ^= rng << 5;
    return rng;
  endfunction

  bit accepted;
  int retired, blocked, cancelled;
  always @(posedge clk) begin
    accepted = rst_ni && in_valid_i && ctl[0].ready;
    if (rst_ni) begin
      if ($isunknown(ctl[0]) || ctl[0] !== ctl[1])
        $fatal(1, "control mismatch kind=%0d old=%b new=%b", Kind, ctl[0], ctl[1]);
      if (ctl[0].valid) begin
        if ($isunknown(data[0]) || data[0] !== data[1])
          $fatal(1, "payload mismatch kind=%0d old=%h new=%h", Kind, data[0], data[1]);
        if (out_ready_i && !flush_i) retired++;
        if (!out_ready_i) blocked++;
      end
      if (ctl[0].busy && flush_i) cancelled++;
    end
  end

  initial begin
    rst_ni = 0; flush_i = 0; in_valid_i = 0; out_ready_i = 1;
    repeat (3) @(negedge clk);
    for (int n = 0; n < 24000; n++) begin
      rst_ni = n != 12000;
      flush_i = n % 97 == 45;
      out_ready_i = n < 200 || draw() % 5 != 0;
      if (!in_valid_i || accepted || flush_i || !rst_ni) begin
        in_valid_i = n < 200 || draw() % 7 != 0;
        case (Kind == 3 ? 2 : draw() % 3)
          0: op_i = F2F;
          1: op_i = F2I;
          2: op_i = I2F;
        endcase
        src_fmt_i = Kind == 2 ? FP16 : Kind == 3 ? FP32 : fp_format_e'(draw()%3);
        dst_fmt_i = Kind == 2 ? FP16 : Kind == 3 ? FP32 : fp_format_e'(draw()%3);
        case (Kind)
          0: int_fmt_i = int_format_e'(2 + draw()%2);
          2: int_fmt_i = int_format_e'(draw()%2);
          3: int_fmt_i = INT32;
          default: int_fmt_i = int_format_e'(draw()%4);
        endcase
        op_mod_i = Kind == 3 ? 0 : 1'(draw());
        rnd_mode_i = Kind == 3 ? RNE : roundmode_e'(draw()%6);
        tag_i = n; aux_i = draw(); mask_i = 1'(draw());
        is_boxed_i = draw()%8 ? '1 : draw();
        operands_i = {draw(), draw()};
        case (n % 16)
          0: operands_i = '0;
          1: operands_i = '1;
          2: operands_i = W'(1) << (draw()%W);
          3: operands_i = (W'(1) << (draw()%W)) - 1'b1;
        endcase
      end
      @(negedge clk);
    end
    flush_i = 0; in_valid_i = 0; out_ready_i = 1;
    repeat (Depth+2) @(negedge clk);
    if (ctl[0].busy || retired < 10000 || blocked < 100 || cancelled < 50)
      $fatal(1, "incomplete kind=%0d",Kind);
    $display("CAST_PORT_PASS kind=%0d retired=%0d blocked=%0d cancelled=%0d",
             Kind,retired,blocked,cancelled);
    done = 1;
  end
endmodule

module cast_fused_equiv_tb;
  logic clk = 0;
  always #5 clk = ~clk;
  wire [3:0] done;
  for (genvar i=0; i<4; i++) cast_equiv_port #(i) port(clk,done[i]);
  initial begin wait (&done); $display("CAST_FUSED_EQUIV_PASS"); $finish; end
  initial begin #250000; $fatal(1,"timeout"); end
endmodule
