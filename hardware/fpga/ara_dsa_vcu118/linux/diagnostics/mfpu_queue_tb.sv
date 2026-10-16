`timescale 1ns/1ps
module mfpu_queue_tb;
  logic clk = 0, rst = 0, valid, ready, req, grant;
  logic operand_valid, operand_ready;
  logic [2:0] id, result_id;
  logic [4:0] vd;
  logic [10:0] vl;
  logic [63:0] operand, data;
  logic [9:0] addr;
  logic [7:0] be, done;
  int cycles=0, accepted=0, consumed=0, written=0, completed=0, blocked=0;
  int length=32, pressure=1;
  logic [7:0] live=0;
  logic held=0;
  logic [84:0] held_payload;
  function automatic logic [63:0] source_word(input int n);
    return 64'h89abcdef13579bdf ^ (64'(n)*64'h102030405060709);
  endfunction
  always #5 clk = ~clk;
  assign valid = rst && accepted < 32 && !live[accepted%8];
  assign id = 3'(accepted%8);
  assign vd = 5'((accepted%4)*8);
  assign vl = 11'(length);
  assign operand = source_word(consumed);
  assign operand_valid = rst && consumed < accepted*length;
  assign grant = req && (!pressure || cycles%23 >= 17);
  mfpu_queue_probe dut (
    .clk_i(clk), .rst_ni(rst), .id_i(id), .vd_i(vd), .vl_i(vl),
    .valid_i(valid), .ready_o(ready), .operand_i(operand),
    .operand_valid_i(operand_valid), .operand_ready_o(operand_ready),
    .req_o(req), .grant_i(grant), .id_o(result_id), .addr_o(addr),
    .data_o(data), .be_o(be), .done_o(done)
  );
  always @(posedge clk) if (rst) begin
    cycles <= cycles+1;
    if (valid && ready) begin
      live[id] <= 1;
      accepted <= accepted+1;
    end
    if (operand_valid && operand_ready) consumed <= consumed+1;
    if (held && (!req || {result_id,addr,data,be} !== held_payload))
      $fatal(1,"blocked result changed cycle=%0d",cycles);
    held <= req && !grant;
    held_payload <= {result_id,addr,data,be};
    if (req && !grant) blocked <= blocked+1;
    if (req && grant) begin
      if (written >= 32*length || result_id !== 3'((written/length)%8) ||
          addr !== 10'(((written/length)%4)*32+written%length) ||
          be !== 8'hff || data !== source_word(written)*64'd3)
        $fatal(1,"payload mismatch n=%0d id=%d addr=%h be=%h data=%h expected=%h",
               written,result_id,addr,be,data,source_word(written)*64'd3);
      written = written+1;
    end
    for (int i=0;i<8;i++) if (done[i]) begin
      if (!live[i] || i != completed%8 || written != (completed+1)*length)
        $fatal(1,"invalid completion id=%0d completed=%0d written=%0d",i,completed,written);
      live[i] <= 0;
      completed = completed+1;
    end
    if (completed==32) begin
      if (consumed != 32*length || (pressure && blocked==0))
        $fatal(1,"missing input or backpressure coverage");
      $display("MFPU_QUEUE_PASS vl=%0d pressure=%0d words=%0d blocked=%0d cycles=%0d",
               length,pressure,written,blocked,cycles);
      $finish;
    end
    if (cycles>30000) $fatal(1,"timeout accepted=%0d consumed=%0d written=%0d completed=%0d",
                            accepted,consumed,written,completed);
  end
  initial begin
    void'($value$plusargs("VL=%d",length));
    void'($value$plusargs("PRESSURE=%d",pressure));
    if (length<1 || length>32) $fatal(1,"bad VL");
    repeat(20) @(negedge clk);
    rst=1;
  end
endmodule
