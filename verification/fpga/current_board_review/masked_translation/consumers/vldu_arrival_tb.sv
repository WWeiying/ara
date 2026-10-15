`timescale 1ns/1ps
module vldu_arrival_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam int NrLanes=4, VLEN=1024, AxiDataWidth=256;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [15:0] vaddr_t;
  typedef logic [7:0] strb_t;
  `include "ara/ara_typedef.svh"
  typedef struct packed {logic [3:0] id; logic [255:0] data;
    logic [1:0] resp; logic last; logic user;} axi_r_t;
  typedef struct packed {vid_t id; vaddr_t addr; elen_t data; strb_t be;} wb_t;
  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  axi_r_t axi_r_i;
  logic axi_r_valid_i, axi_r_ready_o, load_complete_o;
  pe_req_t pe_req_i;
  logic pe_req_valid_i, pe_req_ready_o;
  logic [NrVInsn-1:0] pe_vinsn_running_i;
  pe_resp_t pe_resp_o;
  logic ldu_current_burst_exception_o;
  addrgen_axi_req_t axi_addrgen_req_i;
  logic axi_addrgen_req_valid_i, axi_addrgen_req_ready_o;
  logic addrgen_illegal_load_i, lsu_ex_flush_i;
  logic [3:0] ldu_result_req_o, ldu_result_gnt_i, ldu_result_final_gnt_i;
  vid_t [3:0] ldu_result_id_o;
  vaddr_t [3:0] ldu_result_addr_o;
  elen_t [3:0] ldu_result_wdata_o;
  strb_t [3:0] ldu_result_be_o, mask_i, mask_word_o;
  logic [3:0] mask_valid_i, mask_word_valid_o;
  vid_t mask_owner_id_i, mask_owner_id_o;
  vlen_t mask_first_element_i, mask_first_element_o;
  logic mask_ready_o, idle_o;
  vldu #(.NrLanes(NrLanes), .VLEN(VLEN), .vaddr_t(vaddr_t),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .AxiDataWidth(AxiDataWidth),
    .AxiAddrWidth(64), .axi_r_t(axi_r_t)) dut (.*);
  wb_t wb_in[4], wb_out[4];
  logic [3:0] bank_valid;
  for (genvar l=0; l<4; l++) begin: requester_buffers
    assign wb_in[l]={ldu_result_id_o[l],ldu_result_addr_o[l],
                     ldu_result_wdata_o[l],ldu_result_be_o[l]};
    stream_register #(.T(wb_t)) buffer_i (
      .clk_i, .rst_ni, .clr_i(1'b0), .testmode_i(1'b0),
      .data_i(wb_in[l]), .valid_i(ldu_result_req_o[l]), .ready_o(ldu_result_gnt_i[l]),
      .data_o(wb_out[l]), .valid_o(bank_valid[l]), .ready_i(1'b1));
    assign ldu_result_final_gnt_i[l]=bank_valid[l];
  end
  int variant, cycle_no, fd, accepts, pops, dones, accept_cycle=-1, done_cycle=-1;
  bit paccept, pop;
  task automatic tick;
    @(posedge clk_i);
    paccept=pe_req_valid_i && pe_req_ready_o;
    pop=axi_addrgen_req_valid_i && axi_addrgen_req_ready_o;
    if (rst_ni) begin
      $fdisplay(fd,"%0d,%b,%b,%b,%b,%b,%b,%b,%b,%0d",
        cycle_no,pe_req_valid_i,pe_req_ready_o,axi_addrgen_req_valid_i,
        axi_addrgen_req_ready_o,addrgen_illegal_load_i,pe_resp_o.vinsn_done,
        idle_o,ldu_result_final_gnt_i,dut.issue_cnt_bytes_q);
      if (paccept) begin accepts++; accept_cycle=cycle_no; end
      if (pop) pops++;
      if (pe_resp_o.vinsn_done[0]) begin dones++; done_cycle=cycle_no; end
      for (int l=0;l<4;l++)
        if (bank_valid[l] && (|wb_out[l].be)) $fatal(1,"FIRST_FAULT_WROTE_DATA");
      if (axi_r_ready_o) $fatal(1,"FAULT_CONSUMED_R");
    end
    #1; @(negedge clk_i); cycle_no++;
    if (paccept) pe_req_valid_i=0;
    if (pop) axi_addrgen_req_valid_i=0;
    if (dones) pe_vinsn_running_i=0;
  endtask
  initial begin
    variant=0;
    if ($value$plusargs("CASE=%d",variant)) begin end
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"cycle,pe_valid,pe_ready,desc_valid,desc_ready,early_illegal,done,idle,final_gnt,issue_bytes");
    $dumpfile("window.vcd"); $dumpvars(0,vldu_arrival_tb);
    pe_req_i='0; pe_req_valid_i=0; pe_vinsn_running_i=0;
    axi_r_i='0; axi_r_valid_i=0; axi_addrgen_req_i='0; axi_addrgen_req_valid_i=0;
    addrgen_illegal_load_i=0; lsu_ex_flush_i=0; mask_i=0; mask_valid_i=0;
    mask_owner_id_i=0; mask_first_element_i=0;
    repeat(3) tick(); rst_ni=1; tick();
    pe_req_i.id=0; pe_req_i.vfu=VFU_LoadUnit; pe_req_i.op=VLE;
    pe_req_i.vm=1; pe_req_i.vtype.vsew=EW16; pe_req_i.vl=8;
    pe_req_i.vd=8; pe_req_i.vtype.vlmul=LMUL_1; pe_req_i.emul=LMUL_1;
    if (variant<2) begin
      axi_addrgen_req_i.is_load=1; axi_addrgen_req_i.is_exception=1;
      axi_addrgen_req_i.size=1; axi_addrgen_req_i.addr=64'h80001000;
      axi_addrgen_req_valid_i=1;
    end else addrgen_illegal_load_i=1;
    if (variant%2==0) begin
      tick(); addrgen_illegal_load_i=0; repeat(2) tick();
    end
    pe_req_valid_i=1; pe_vinsn_running_i[0]=1;
    tick(); addrgen_illegal_load_i=0;
    repeat(40) tick();
    $display("OBSERVATION case=%0d accepts=%0d pops=%0d dones=%0d accept_cycle=%0d done_cycle=%0d idle=%0d",
      variant,accepts,pops,dones,accept_cycle,done_cycle,idle_o);
    $display("PROBE_COMPLETED case=%0d",variant);
    $fclose(fd); $finish;
  end
endmodule
