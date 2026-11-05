// SPDX-License-Identifier: SHL-0.51
module shared_fma_softfloat_tb;
  import fpnew_pkg::*;
  logic clk=0;
  always #5 clk=~clk;
  logic rst=0, iv=0, ir, ov, ready=0, busy;
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
  typedef struct packed {logic [63:0] data; status_t flags; logic [31:0] tag;} row_t;
  row_t expected, want, pending[$], held_value;
  int sent=0, checked=0, cycle=0;
  logic held=0;
  simd_fma_shared #(.TagType(logic [31:0])) dut (
    .clk_i(clk), .rst_ni(rst), .operands_i(operands), .is_boxed_i(boxed),
    .rnd_mode_i(rm), .op_i(op), .op_mod_i(mod), .fmt_i(fmt),
    .vectorial_op_i(vec), .simd_mask_i(mask), .tag_i(tag),
    .in_valid_i(iv), .in_ready_o(ir), .flush_i(1'b0),
    .result_o(result), .status_o(flags), .tag_o(out_tag),
    .out_valid_o(ov), .out_ready_i(ready), .busy_o(busy)
  );
  always @(negedge clk) begin
    cycle++;
    ready = cycle%47 >= 11 && cycle%7 != 0;
  end
  always @(posedge clk) if (rst) begin
    if (held && (!ov || {result,flags,out_tag} !== held_value))
      $fatal(1,"SoftFloat stream output changed while stalled");
    held = ov && !ready;
    held_value = '{result,flags,out_tag};
    if (iv && ir) begin pending.push_back(expected); sent++; end
    if (ov && ready) begin
      if (!pending.size()) $fatal(1,"Unexpected output");
      want=pending.pop_front();
      if ({result,flags,out_tag} !== want)
        $fatal(1,"SOFTFLOAT_MISMATCH tag=%0d want_tag=%0d result=%h expected=%h flags=%h expected=%h",
               out_tag,want.tag,result,want.data,flags,want.flags);
      checked++;
    end
  end
  initial begin
    int fd, count, f, o, r, m, v, sm;
    logic [17:0] bx;
    logic [63:0] a,b,c,y;
    logic [4:0] ex;
    string path;
    if (!$value$plusargs("VECTORS=%s",path)) $fatal(1,"Missing vectors");
    fd=$fopen(path,"r");
    if (!fd) $fatal(1,"Cannot open vectors");
    operands='0; boxed='1; rm=RNE; op=ADD; fmt=FP16; mod=0; vec=1; mask='1; tag=0;
    repeat (3) @(negedge clk);
    rst=1;
    while (!$feof(fd)) begin
      count=$fscanf(fd,"%d %d %d %d %d %h %h %h %h %h %h %h\n",f,o,r,m,v,sm,bx,a,b,c,y,ex);
      if (count != 12) $fatal(1,"Malformed vector row %0d",sent);
      @(negedge clk);
      fmt=fp_format_e'(f); op=operation_e'(o); rm=roundmode_e'(r);
      mod=1'(m); vec=1'(v); mask=4'(sm); boxed=bx;
      operands[0]=a; operands[1]=b; operands[2]=c;
      expected='{y,status_t'(ex),tag}; iv=1;
      do @(posedge clk); while (!ir);
      @(negedge clk); iv=0; tag++;
    end
    $fclose(fd);
    repeat (100) @(negedge clk);
    if (busy || pending.size() || checked!=sent || checked<1000)
      $fatal(1,"Incomplete SoftFloat stream sent=%d checked=%d",sent,checked);
    $display("SHARED_FMA_SOFTFLOAT_PASS checked=%0d",checked);
    $finish;
  end
  initial begin #5000000; $fatal(1,"Watchdog"); end
endmodule
