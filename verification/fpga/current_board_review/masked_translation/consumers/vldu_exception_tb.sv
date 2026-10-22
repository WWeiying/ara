`timescale 1ns/1ps
module vldu_exception_tb;
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
  logic [3:0] bank_valid, bank_ready;
  int cycle_no, release_cycle, variant, trace_fd;
  for (genvar l=0; l<4; l++) begin: requester_buffers
    assign wb_in[l]={ldu_result_id_o[l],ldu_result_addr_o[l],
                     ldu_result_wdata_o[l],ldu_result_be_o[l]};
    // Same public stream buffer as operand_requester.sv; final grant is bank acceptance.
    stream_register #(.T(wb_t)) buffer_i (
      .clk_i, .rst_ni, .clr_i(1'b0), .testmode_i(1'b0),
      .data_i(wb_in[l]), .valid_i(ldu_result_req_o[l]), .ready_o(ldu_result_gnt_i[l]),
      .data_o(wb_out[l]), .valid_o(bank_valid[l]), .ready_i(bank_ready[l]));
    assign bank_ready[l]=cycle_no>=release_cycle;
    assign ldu_result_final_gnt_i[l]=bank_valid[l] && bank_ready[l];
  end

  byte vrf[2][128];
  bit seen[2][128];
  int first[2], limit[2], stop_at[2], done_count[2], accepted[2], written[2];
  int done_cycle[2], first_accept[2], last_write[2], expected_bytes[2];
  int mask_cursor, mask_words, owner, r_count, skip_count, desc_count;
  bit use_mask[2], active[2], pop, raccept, paccept, early_data_done;
  bit idle_before_flush, idle_after_flush;
  int pending_bytes_at_done;
  int zero_be_finals;

  function automatic int seq_byte(int lane, int offset);
    int slot;
    slot=offset/2;
    slot=((slot&1)<<1)|(slot>>1);
    return (slot*4+lane)*2+(offset%2);
  endfunction
  function automatic byte pattern(int id, int b);
    return byte'(8'ha6 ^ (b*37) ^ (id*91));
  endfunction
  function automatic bit enabled(int id, int elem);
    return !use_mask[id] || (elem%2==1);
  endfunction

  task automatic tick;
    mask_i='0; mask_valid_i='0;
    if (mask_cursor<mask_words) begin
      mask_valid_i='1; mask_owner_id_i=vid_t'(owner);
      mask_first_element_i=vlen_t'(mask_cursor*16);
      for (int l=0;l<4;l++)
        for (int b=0;b<8;b++)
          mask_i[l][b]=enabled(owner,mask_cursor*16+seq_byte(l,b)/2);
    end
    @(posedge clk_i);
    pop=axi_addrgen_req_valid_i && axi_addrgen_req_ready_o;
    raccept=axi_r_valid_i && axi_r_ready_o;
    paccept=pe_req_valid_i && pe_req_ready_o;
    if (rst_ni) begin
      $fdisplay(trace_fd,"%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%0d,%0d,%0d,%0d,%0d,%0d",
        cycle_no,axi_addrgen_req_valid_i,axi_addrgen_req_i.is_skip,
        axi_addrgen_req_i.is_exception,axi_addrgen_req_ready_o,
        axi_r_valid_i,axi_r_ready_o,ldu_result_req_o,ldu_result_gnt_i,
        ldu_result_final_gnt_i,pe_resp_o.vinsn_done,load_complete_o,
        lsu_ex_flush_i,idle_o,accepted[0],written[0],
        dut.issue_cnt_bytes_q,dut.commit_cnt_bytes_q,dut.result_queue_cnt_q,
        unsigned'(mask_word_valid_o));
      if (mask_ready_o) mask_cursor++;
      if (pop) begin
        desc_count++;
        if (axi_addrgen_req_i.is_skip) skip_count++;
      end
      if (raccept) r_count++;
      if (axi_addrgen_req_valid_i && axi_addrgen_req_i.is_skip && axi_r_ready_o)
        $fatal(1,"SKIP_RREADY");
      for (int l=0;l<4;l++) begin
        if (ldu_result_req_o[l] && ldu_result_gnt_i[l]) begin
          int id;
          id=int'(ldu_result_id_o[l]);
          if (id>1 || !active[id]) $fatal(1,"BAD_ACCEPT_OWNER");
          if (first_accept[id]<0) first_accept[id]=cycle_no;
          accepted[id]+=$countones(ldu_result_be_o[l]);
        end
        if (ldu_result_final_gnt_i[l]) begin
          int id, word_index, index;
          id=int'(wb_out[l].id);
          word_index=int'(wb_out[l].addr)-(8+id*8)*4;
          if (id>1) $fatal(1,"BAD_WRITE_OWNER");
          if (|wb_out[l].be) begin
            if (word_index<0 || word_index>=4) $fatal(1,"BAD_WRITE_ADDR");
          end else begin
            zero_be_finals++;
            $display("ZERO_BE_FINAL cycle=%0d lane=%0d id=%0d addr=%h",cycle_no,l,id,wb_out[l].addr);
          end
          last_write[id]=cycle_no;
          for (int b=0;b<8;b++) begin
            index=word_index*32+seq_byte(l,b);
            if (wb_out[l].be[b]) begin
              if (index<first[id]*2 || index>=stop_at[id]*2 ||
                  !enabled(id,index/2) || seen[id][index])
                $fatal(1,"BAD_WRITE_BE id=%0d byte=%0d",id,index);
              if (wb_out[l].data[b*8+:8]!==pattern(id,index))
                $fatal(1,"BAD_WRITE_DATA id=%0d byte=%0d",id,index);
              seen[id][index]=1;
              vrf[id][index]=wb_out[l].data[b*8+:8];
              written[id]++;
            end
          end
        end
      end
      for (int id=0;id<2;id++) if (pe_resp_o.vinsn_done[id]) begin
        done_count[id]++; done_cycle[id]=cycle_no;
        if (done_count[id]>1 || !active[id]) $fatal(1,"DUPLICATE_DONE");
        if (written[id]!=expected_bytes[id]) begin
          early_data_done=1;
          pending_bytes_at_done=expected_bytes[id]-written[id];
        end
        $display("DONE id=%0d cycle=%0d accepted=%0d written=%0d expected=%0d bank_valid=%b",
          id,cycle_no,accepted[id],written[id],expected_bytes[id],bank_valid);
      end
    end
    #1;
    @(negedge clk_i);
    cycle_no++;
    if (cycle_no>400) $fatal(1,"BOUNDED_WATCHDOG");
  endtask

  task automatic issue(int id, int begin_elem, int vl, int end_elem, bit masked, bit fof);
    first[id]=begin_elem; limit[id]=vl; stop_at[id]=end_elem;
    use_mask[id]=masked; active[id]=1; expected_bytes[id]=0;
    for (int i=begin_elem;i<end_elem;i++) if (enabled(id,i)) expected_bytes[id]+=2;
    pe_req_i='0; pe_req_i.id=vid_t'(id); pe_req_i.vfu=VFU_LoadUnit;
    pe_req_i.op=VLE; pe_req_i.vm=!masked; pe_req_i.fault_only_first=fof;
    pe_req_i.vtype.vsew=EW16; pe_req_i.vtype.vlmul=LMUL_1; pe_req_i.emul=LMUL_1;
    pe_req_i.vd=5'(8+id*8); pe_req_i.vl=vlen_t'(vl); pe_req_i.vstart=vlen_t'(begin_elem);
    pe_req_valid_i=1; pe_vinsn_running_i[id]=1;
    do tick(); while (!paccept);
    pe_req_valid_i=0;
    if (masked) begin
      owner=id; mask_cursor=begin_elem/16; mask_words=(vl+15)/16;
    end
  endtask

  task automatic descriptor(int id, int elem, bit fault);
    bit skip;
    int offset;
    skip=!fault && !enabled(id,elem);
    axi_addrgen_req_i='0; axi_addrgen_req_i.is_load=1;
    axi_addrgen_req_i.is_skip=skip; axi_addrgen_req_i.is_exception=fault;
    axi_addrgen_req_i.size=1; axi_addrgen_req_i.elem_start=elem;
    axi_addrgen_req_i.addr=skip ? 0 : 64'h80001000+elem*2;
    axi_addrgen_req_i.vaddr=axi_addrgen_req_i.addr;
    axi_addrgen_req_valid_i=1;
    offset=(elem*2)%32;
    axi_r_i='0; axi_r_i.last=1;
    for (int b=0;b<2;b++) axi_r_i.data[(offset+b)*8+:8]=pattern(id,elem*2+b);
    axi_r_valid_i=!skip && !fault;
    do tick(); while (!pop);
    if (!skip && !fault && !raccept) $fatal(1,"ACTIVE_DESCRIPTOR_WITHOUT_R");
    axi_addrgen_req_valid_i=0; axi_r_valid_i=0;
  endtask

  task automatic settle_and_check(int id);
    int wait_count;
    wait_count=0;
    while (!done_count[id] && wait_count<100) begin tick(); wait_count++; end
    if (!done_count[id]) $fatal(1,"NO_DONE id=%0d",id);
    pe_vinsn_running_i[id]=0;
    repeat(40) tick();
    for (int b=0;b<128;b++) begin
      bit want;
      want=b>=first[id]*2 && b<stop_at[id]*2 && enabled(id,b/2);
      if (seen[id][b]!=want || vrf[id][b] !== (want ? pattern(id,b) : 8'h5b))
        $fatal(1,"FINAL_VRF id=%0d byte=%0d",id,b);
    end
  endtask

  initial begin
    variant=0;
    if ($value$plusargs("CASE=%d",variant)) begin end
    trace_fd=$fopen("cycles.csv","w");
    $fdisplay(trace_fd,"cycle,desc_valid,skip,exception,desc_ready,rvalid,rready,result_req,result_gnt,final_gnt,done,complete,flush,idle,accepted0,written0,issue_bytes,commit_bytes,result_count,mask_valid");
    $dumpfile("window.vcd"); $dumpvars(0,vldu_exception_tb);
    pe_req_i='0; pe_req_valid_i=0; pe_vinsn_running_i='0;
    axi_r_i='0; axi_r_valid_i=0; axi_addrgen_req_i='0; axi_addrgen_req_valid_i=0;
    addrgen_illegal_load_i=0; lsu_ex_flush_i=0; mask_owner_id_i=0; mask_first_element_i=0;
    mask_cursor=0; mask_words=0; release_cycle=35;
    for (int id=0;id<2;id++) begin
      first_accept[id]=-1; last_write[id]=-1; done_cycle[id]=-1;
      for (int b=0;b<128;b++) begin vrf[id][b]=8'h5b; seen[id][b]=0; end
    end
    repeat(3) tick(); rst_ni=1; tick();
    if (variant==0) begin
      issue(0,1,8,8,1,0);
      for (int e=1;e<8;e++) descriptor(0,e,0);
    end else if (variant==2) begin
      issue(0,0,8,0,0,0);
      descriptor(0,0,1);
    end else if (variant==4) begin
      issue(0,1,40,19,1,0);
      for (int e=1;e<19;e++) descriptor(0,e,0);
      descriptor(0,19,1);
    end else if (variant==5) begin
      issue(0,0,24,16,1,0);
      for (int e=0;e<16;e++) descriptor(0,e,0);
      descriptor(0,16,1);
    end else begin
      issue(0,1,8,5,1,variant==3);
      for (int e=1;e<5;e++) descriptor(0,e,0);
      descriptor(0,5,1);
    end
    settle_and_check(0);
    idle_before_flush=idle_o;
    $display("BEFORE_FLUSH cycle=%0d idle=%b issue=%0d commit=%0d result_count=%0d mask=%b",
      cycle_no,idle_o,dut.issue_cnt_bytes_q,dut.commit_cnt_bytes_q,dut.result_queue_cnt_q,mask_word_valid_o);
    // Model the external exception-cleanup handshake after completion, not an internal force.
    if (variant!=0) begin lsu_ex_flush_i=1; tick(); lsu_ex_flush_i=0; repeat(8) tick(); end
    mask_words=mask_cursor;
    idle_after_flush=idle_o;
    $display("AFTER_FLUSH cycle=%0d idle=%b issue=%0d commit=%0d result_count=%0d mask=%b",
      cycle_no,idle_o,dut.issue_cnt_bytes_q,dut.commit_cnt_bytes_q,dut.result_queue_cnt_q,mask_word_valid_o);
    issue(1,0,4,4,0,0);
    for (int e=0;e<4;e++) descriptor(1,e,0);
    settle_and_check(1);
    $display("OBSERVATION case=%0d early_data_done=%0d pending_bytes=%0d first_accept=%0d done0=%0d last_write0=%0d idle_before_flush=%0d idle_after_flush=%0d successor_done=%0d successor_idle=%0d r=%0d skip=%0d descriptors=%0d zero_be_finals=%0d",
      variant,early_data_done,pending_bytes_at_done,first_accept[0],done_cycle[0],last_write[0],
      idle_before_flush,idle_after_flush,done_count[1],idle_o,r_count,skip_count,desc_count,zero_be_finals);
    if (variant==0 && (early_data_done || !idle_before_flush || !idle_o)) $fatal(1,"CONTROL_FAILED");
    $display("PROBE_COMPLETED case=%0d",variant);
    $fclose(trace_fd); $finish;
  end
endmodule
