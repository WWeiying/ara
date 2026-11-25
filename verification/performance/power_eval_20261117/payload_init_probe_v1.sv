module payload_init_probe;
  timeunit 1ns; timeprecision 100fs;
  reg clk=0, d=0;
  wire q, control_q;
  integer seed;
  DFQD2BWP12T40P140HVT payload (.D(d),.CP(clk),.Q(q));
  DFQD2BWP12T40P140HVT untouched_control (.D(d),.CP(clk),.Q(control_q));
  initial begin
    if (!$value$plusargs("SEED=%d",seed)) $fatal(1,"Missing test seed");
    #0.1;
    if(q !== (seed==1)) $fatal(1,"Scoped payload init missing");
    if(!$isunknown(control_q)) $fatal(1,"Control was initialized outside whitelist");
    d=1; #0.1; clk=1; #0.1;
    if(q!==1) $fatal(1,"Normal writes lost");
    clk=0; d=1'bx; #0.1; clk=1; #0.1;
    if(!$isunknown(q)) $fatal(1,"Active data X was masked after time zero");
    $display("PAYLOAD_INIT_PROBE_PASS seed=%0d untouched_control_x=1 active_data_x_preserved=1",seed);
    $finish;
  end
endmodule
