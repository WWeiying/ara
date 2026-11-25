module sram_env_probe;
  timeunit 1ns; timeprecision 1ps;
  reg clk=0, ceb=0, web=0;
  reg [3:0] address=0;
  reg [63:0] data=64'h123456789abcdef0, mask=0;
  wire [63:0] q;
  bit observe=0;
  integer pulses=0;
  TS1N28HPCPUHDSVTB16X64M1SWBSO dut (
    .SLP(1'b0),.SD(1'b0),.CLK(clk),.CEB(ceb),.WEB(web),
    .CEBM(1'b1),.WEBM(1'b1),.A(address),.D(data),.BWEB(mask),
    .AM(4'b0),.DM(64'b0),.BWEBM(64'hffffffffffffffff),
    .BIST(1'b0),.RTSEL(2'b01),.WTSEL(2'b00),.Q(q));
  always @(q) if (observe && $isunknown(q)) pulses=pulses+1;
  task tick;
    #0.2 clk=1;
    #0.2 clk=0;
    #0.1;
  endtask
  initial begin
    #1; tick();
    web=1; tick();
    if(q !== 64'h123456789abcdef0) $fatal(1,"Known read failed");
    observe=1; tick(); observe=0;
`ifdef UNIT_DELAY
    if(pulses!=0) $fatal(1,"Artificial read X pulse remains");
`else
    if(pulses==0) $fatal(1,"Nominal read X pulse not reproduced");
`endif
    // Actual enabled unknown writes must remain unknown, never sanitized.
    web=0; address=1; data=64'hxxxxxxxxxxxxxxxx; tick();
    web=1; tick();
    if(!$isunknown(q)) $fatal(1,"True active data X was hidden");
    // Actual unknown clock must still poison previously known memory.
    address=0; clk=1'bx; #0.05; clk=0; #0.2; tick();
    if(!$isunknown(q)) $fatal(1,"True clock X was hidden");
    $display("SRAM_ENV_PROBE_PASS artificial_read_x_pulses=%0d real_data_x_preserved=1 real_clock_x_preserved=1",pulses);
    $finish;
  end
endmodule
