`timescale 1ns/1ps
module fma_lzc_width_case #(parameter integer WIDTH=25)(output reg done);
  localparam integer CW=$clog2(WIDTH);
  reg [WIDTH-1:0] value;
  wire [CW-1:0] count;
  wire empty;
  integer checks, i, j;
  reg [WIDTH-1:0] pattern;
  lzc #(.WIDTH(WIDTH), .MODE(1)) dut(.in_i(value),.cnt_o(count),.empty_o(empty));
  task automatic check(input reg [WIDTH-1:0] stimulus);
    integer expected, bit_index;
    reg found;
    begin
      value=stimulus;
      #1;
      if (empty !== (stimulus == 0)) $fatal(1,"empty mismatch WIDTH=%0d",WIDTH);
      expected=0;found=0;
      for (bit_index=WIDTH-1;bit_index>=0;bit_index=bit_index-1) begin
        if (!found) begin
          if (stimulus[bit_index]) found=1;
          else expected=expected+1;
        end
      end
      if (found && count !== expected[CW-1:0])
        $fatal(1,"count mismatch WIDTH=%0d value=%h count=%0d expected=%0d",WIDTH,stimulus,count,expected);
      checks=checks+1;
    end
  endtask
  initial begin
    done=0;checks=0;
    check(0);
    $display("LZC_ZERO WIDTH=%0d EMPTY=%0d COUNT=%0d COUNT_NOT_ASSERTED",WIDTH,empty,count);
    check({WIDTH{1'b1}});
    pattern=0;
    for(i=0;i<WIDTH;i=i+1) pattern[i]=i%2;
    check(pattern);check(~pattern);
    for(i=0;i<WIDTH;i=i+1) begin
      pattern=0;pattern[i]=1;check(pattern);
      for(j=i+1;j<WIDTH;j=j+1) begin
        pattern=0;pattern[i]=1;pattern[j]=1;check(pattern);
      end
    end
    value={WIDTH{1'bx}};#1;
    if (empty !== 1'bx) $fatal(1,"all-X empty must remain X WIDTH=%0d",WIDTH);
    check(0);
    if(checks != WIDTH+WIDTH*(WIDTH-1)/2+5) $fatal(1,"Incomplete pattern set");
    $display("LZC_WIDTH_PASS WIDTH=%0d MODE=1 CHECKS=%0d",WIDTH,checks);
    done=1;
  end
endmodule
module fma_lzc_width_calibration;
  wire a,b,c;
  fma_lzc_width_case #(.WIDTH(25)) w25(a);
  fma_lzc_width_case #(.WIDTH(51)) w51(b);
  fma_lzc_width_case #(.WIDTH(109)) w109(c);
  initial begin
    wait(a && b && c);
    $display("FMA_LZC_THREE_WIDTHS_PASS");$finish;
  end
  initial begin #10000;$fatal(1,"Bounded standalone calibration timeout");end
endmodule
