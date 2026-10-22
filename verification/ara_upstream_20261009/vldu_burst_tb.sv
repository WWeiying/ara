// Real VLDU + mask spill register, driven only through public request interfaces.
`timescale 1ns/1ps
module vldu_burst_tb #(parameter int VLEN = 8192);
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam int NrLanes = 4, AxiDataWidth = 128;
  typedef logic [$clog2(VLEN+1)-1:0] vlen_t;
  typedef logic [15:0] vaddr_t;
  typedef logic [7:0] strb_t;
  `include "ara/ara_typedef.svh"
  typedef struct packed {
    logic [3:0] id;
    logic [127:0] data;
    logic [1:0] resp;
    logic last;
    logic user;
  } axi_r_t;
  logic clk_i = 0, rst_ni = 0;
  always #5 clk_i = ~clk_i;
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
  logic [NrLanes-1:0] ldu_result_req_o, ldu_result_gnt_i, ldu_result_final_gnt_i;
  vid_t [NrLanes-1:0] ldu_result_id_o;
  vaddr_t [NrLanes-1:0] ldu_result_addr_o;
  elen_t [NrLanes-1:0] ldu_result_wdata_o;
  strb_t [NrLanes-1:0] ldu_result_be_o, mask_i, mask_word_o;
  logic [NrLanes-1:0] mask_valid_i, mask_word_valid_o;
  vid_t mask_owner_id_i, mask_owner_id_o;
  vlen_t mask_first_element_i, mask_first_element_o;
  logic mask_ready_o, idle_o;
  vldu #(.NrLanes(NrLanes), .VLEN(VLEN), .vaddr_t(vaddr_t),
         .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .AxiDataWidth(AxiDataWidth),
         .AxiAddrWidth(64), .axi_r_t(axi_r_t)) dut (.*);

  int cycle_no, cases, checked_bytes, r_beats, descriptors, skips, partials, stalls;
  int start_at[8], stop_at[8], dest[8], seen_count[8], done_count[8];
  bit live[8], masked[8], all_masked[8], seen[8][8192];
  int mask_cursor, mask_owner, mask_words;
  bit pressure, pop, raccept, paccept;
  logic [3:0] final_pending;
  typedef struct packed {vid_t id; vaddr_t addr; elen_t data; strb_t be;} held_t;
  held_t held[4];
  bit held_valid[4];
  int peak_owners, stable_checks, mask_checks;

  function automatic byte pattern(int id, int index);
    return byte'((index * 73) ^ (index >> 7) ^ (id * 91) ^ 8'hb6);
  endfunction
  function automatic bit enabled(int id, int index);
    return !all_masked[id] && (!masked[id] || index % 5 != 2);
  endfunction
  // Ara byte-interleaves lanes and bit-reverses the three byte-position bits
  // inside each lane. This independent inverse does not call DUT shuffle helpers.
  function automatic int element_offset(int lane, int byte_position);
    return (((byte_position&1)<<2) | (byte_position&2) | (byte_position>>2))*4+lane;
  endfunction

  task automatic tick;
    for (int l = 0; l < 4; l++)
      ldu_result_gnt_i[l] = !pressure || ((cycle_no+l*3)%11 < 5);
    ldu_result_final_gnt_i = final_pending;
    mask_valid_i = '0;
    mask_i = '0;
    if (mask_words > mask_cursor && (!pressure || cycle_no%7 != 0)) begin
      mask_valid_i = '1;
      mask_owner_id_i = vid_t'(mask_owner);
      mask_first_element_i = vlen_t'(mask_cursor*32);
      for (int l = 0; l < 4; l++)
        for (int b = 0; b < 8; b++)
          mask_i[l][b] = enabled(mask_owner, mask_cursor*32+element_offset(l,b));
    end
    @(posedge clk_i);
    pop = axi_addrgen_req_valid_i && axi_addrgen_req_ready_o;
    raccept = axi_r_valid_i && axi_r_ready_o;
    paccept = pe_req_valid_i && pe_req_ready_o;
    if (rst_ni) begin
      if (dut.vinsn_queue_q.commit_cnt > peak_owners) peak_owners=dut.vinsn_queue_q.commit_cnt;
      if ($isunknown({axi_r_ready_o, axi_addrgen_req_ready_o, ldu_result_req_o, pe_resp_o}))
        $fatal(1, "UNKNOWN_CONTROL cycle=%0d", cycle_no);
      if (mask_ready_o) mask_cursor++;
      if (raccept) r_beats++;
      if (axi_r_valid_i && !axi_r_ready_o) stalls++;
      if (pop) descriptors++;
      if (axi_addrgen_req_valid_i && axi_addrgen_req_i.len == 255 &&
          dut.axi_len_q == 0 && axi_r_valid_i && !axi_r_ready_o) begin
        partials++;
        $display("FIRST_BEAT_PARTIAL cycle=%0d POP=%b RREADY=%b len_q=%0d len_d=%0d rptr_q=%0d rptr_d=%0d vrfptr_q=%0d issue_q=%0d issue_d=%0d",
                 cycle_no,pop,axi_r_ready_o,dut.axi_len_q,dut.axi_len_d,
                 dut.axi_r_byte_pnt_q,dut.axi_r_byte_pnt_d,dut.vrf_word_byte_pnt_q,
                 dut.issue_cnt_bytes_q,dut.issue_cnt_bytes_d);
      end
      if (axi_addrgen_req_valid_i && axi_addrgen_req_i.is_skip && axi_r_ready_o)
        $fatal(1, "SKIP_CONSUMED_R cycle=%0d", cycle_no);
      if (dut.vinsn_issue_valid && !dut.vinsn_issue_q.vm && (|mask_word_valid_o) &&
          axi_addrgen_req_valid_i && (axi_r_valid_i || axi_addrgen_req_i.is_skip)) begin
        if (mask_owner_id_o !== dut.vinsn_issue_q.id ||
            mask_first_element_o != ((dut.vinsn_issue_q.vstart/32)+dut.seq_word_wr_offset_q)*32)
          $fatal(1,"MASK_OWNER_OR_FIRST_ELEMENT");
        mask_checks++;
      end
      for (int l = 0; l < 4; l++) begin
        if (held_valid[l]) begin
          if (!ldu_result_req_o[l] ||
              {ldu_result_id_o[l],ldu_result_addr_o[l],ldu_result_wdata_o[l],ldu_result_be_o[l]} !== held[l])
            $fatal(1,"UNSTABLE_STALLED_RESULT lane=%0d",l);
          stable_checks++;
        end
        held[l]={ldu_result_id_o[l],ldu_result_addr_o[l],ldu_result_wdata_o[l],ldu_result_be_o[l]};
        held_valid[l]=ldu_result_req_o[l] && !ldu_result_gnt_i[l];
        if (ldu_result_req_o[l] && ldu_result_gnt_i[l]) begin
          int id, word_index, index;
          id = ldu_result_id_o[l];
          if (!live[id]) $fatal(1, "WRONG_OWNER lane=%0d id=%0d", l, id);
          word_index = int'(ldu_result_addr_o[l]) - dest[id] * (VLEN/256);
          if (word_index < 0 || word_index >= 256) $fatal(1, "BAD_VRF_ADDR");
          for (int b = 0; b < 8; b++) begin
            bit want;
            index = word_index*32 + element_offset(l,b);
            want = index >= start_at[id] && index < stop_at[id] && enabled(id,index);
            if (ldu_result_be_o[l][b] !== want)
              $fatal(1, "BAD_BE id=%0d index=%0d got=%b want=%b", id,index,ldu_result_be_o[l][b],want);
            if (want) begin
              if (seen[id][index]) $fatal(1, "DUPLICATE_BYTE id=%0d index=%0d",id,index);
              if (ldu_result_wdata_o[l][b*8+:8] !== pattern(id,index))
                $fatal(1, "BAD_BYTE id=%0d index=%0d got=%h want=%h",id,index,
                       ldu_result_wdata_o[l][b*8+:8],pattern(id,index));
              seen[id][index] = 1;
              seen_count[id]++;
              checked_bytes++;
            end
          end
        end
      end
      for (int id = 0; id < 8; id++) begin
        if (pe_resp_o.vinsn_done[id]) begin
          if (!live[id] || done_count[id]) $fatal(1,"BAD_DONE_OWNER id=%0d",id);
          for (int i = start_at[id]; i < stop_at[id]; i++)
            if (seen[id][i] != enabled(id,i)) $fatal(1,"MISSING_BYTE id=%0d index=%0d",id,i);
          done_count[id]++;
          pe_vinsn_running_i[id] = 0;
        end
      end
    end
    final_pending = ldu_result_req_o & ldu_result_gnt_i;
    cycle_no++;
    #1;
    @(negedge clk_i);
  endtask

  task automatic reset_case;
    rst_ni=0; pe_req_i='0; pe_req_valid_i=0; pe_vinsn_running_i='0;
    axi_r_i='0; axi_r_valid_i=0; axi_addrgen_req_i='0; axi_addrgen_req_valid_i=0;
    addrgen_illegal_load_i=0; lsu_ex_flush_i=0; mask_owner_id_i=0; mask_first_element_i=0;
    mask_cursor=0; mask_words=0; mask_owner=0; final_pending=0; peak_owners=0;
    for (int l=0; l<4; l++) held_valid[l]=0;
    for (int id=0; id<8; id++) begin
      live[id]=0; done_count[id]=0; seen_count[id]=0; all_masked[id]=0;
      for (int i=0; i<8192; i++) seen[id][i]=0;
    end
    repeat(3) tick();
    rst_ni=1;
    tick();
  endtask

  task automatic issue(int id, int first, int count, bit use_mask, bit indexed);
    live[id]=1; start_at[id]=first; stop_at[id]=first+count; dest[id]=8+id*8;
    masked[id]=use_mask;
    pe_req_i='0; pe_req_i.id=vid_t'(id); pe_req_i.vfu=VFU_LoadUnit;
    pe_req_i.op=indexed ? VLXE : VLE; pe_req_i.vm=!use_mask;
    pe_req_i.vtype.vsew=EW8; pe_req_i.vtype.vlmul=LMUL_8; pe_req_i.emul=LMUL_8;
    pe_req_i.vd=5'(dest[id]); pe_req_i.vl=vlen_t'(first+count); pe_req_i.vstart=vlen_t'(first);
    pe_req_valid_i=1; pe_vinsn_running_i[id]=1;
    do tick(); while (!paccept);
    pe_req_valid_i=0;
    if (use_mask) begin
      mask_owner=id; mask_cursor=first/32; mask_words=(first+count+31)/32;
    end
  endtask

  // A descriptor is held until its handshake; every AXI beat is held until RREADY.
  // No DUT state is deposited/forced. The byte oracle does not use DUT shuffle_index.
  task automatic burst(int id, int first, int len, int address_offset, int size, bit skip,
                       longint unsigned page=64'h80001000);
    int beat, payload, base, lower, upper, waiting;
    beat=0; payload=0; waiting=0;
    axi_addrgen_req_i='0;
    if (skip) address_offset=0;
    axi_addrgen_req_i.addr=skip ? 0 : page+address_offset;
    axi_addrgen_req_i.vaddr=axi_addrgen_req_i.addr;
    axi_addrgen_req_i.elem_start=first;
    axi_addrgen_req_i.len=axi_pkg::len_t'(len); axi_addrgen_req_i.size=axi_pkg::size_t'(size);
    axi_addrgen_req_i.is_load=1; axi_addrgen_req_i.is_skip=skip;
    axi_addrgen_req_valid_i=1;
    while (beat<=len) begin
      base=(address_offset >> size)*(1<<size)+beat*(1<<size);
      lower=beat==0 ? address_offset%16 : base%16;
      upper=(base%16)+(1<<size)-1;
      axi_r_i='0; axi_r_i.last=(beat==len);
      for(int b=lower; b<=upper; b++) axi_r_i.data[b*8+:8]=pattern(id,first+payload+b-lower);
      axi_r_valid_i=!skip;
      if (pressure && !skip && beat%3==1) begin
        axi_r_valid_i=0; tick();
        if(pop) $fatal(1,"POP_WITHOUT_R beat=%0d",beat);
        axi_r_valid_i=1;
      end
      do begin
        tick(); waiting++;
        if (!skip && pop && (!raccept || beat!=len)) begin
          $display("PREMATURE_DESCRIPTOR cycle=%0d len=%0d beat=%0d RVALID=%b RREADY=%b POP=%b axi_len_q=%0d axi_len_d=%0d rptr_q=%0d vrfptr_q=%0d",
                   cycle_no-1,len,beat,axi_r_valid_i,raccept,pop,dut.axi_len_q,dut.axi_len_d,
                   dut.axi_r_byte_pnt_q,dut.vrf_word_byte_pnt_q);
          $fatal(1,"DESCRIPTOR_BEFORE_LAST_R");
        end
        if (!skip && raccept && ((beat==len) != pop)) $fatal(1,"BAD_LAST_DESCRIPTOR beat=%0d",beat);
        if(waiting>10000) $fatal(1,"BURST_TIMEOUT len=%0d skip=%b",len,skip);
      end while (!(skip ? pop : raccept));
      if(skip) begin
        if (len != 0) $fatal(1,"Fixture skip descriptors must represent one indexed element");
        skips++;
      end
      payload+=upper-lower+1;
      beat++;
    end
    axi_addrgen_req_valid_i=0; axi_r_valid_i=0;
  endtask

  task automatic drain(int owners);
    int waited;
    waited=0;
    while (!done_count[owners-1]) begin
      tick(); waited++;
      if(waited>1000) $fatal(1,"DRAIN_TIMEOUT");
    end
    mask_words=0;
    repeat(5) tick();
    if (!idle_o) $fatal(1,"NOT_IDLE_AFTER_DRAIN");
    for(int id=0; id<owners; id++)
      if(done_count[id]!=1) $fatal(1,"MISSING_DONE id=%0d",id);
  endtask

  task automatic single(int len, int first, int offset, bit bp, bit use_mask);
    int count;
    pressure=bp;
    count=(len+1)*16-offset;
    reset_case(); issue(0,first,count,use_mask,0);
    burst(0,first,len,offset,4,0); drain(1);
    cases++;
    $display("VLDU_CASE_PASS case=%0d len=%0d vstart=%0d offset=%0d bp=%b mask=%b bytes=%0d",
             cases,len,first,offset,bp,use_mask,seen_count[0]);
  endtask

  task automatic page_cross;
    pressure=1; reset_case(); issue(0,0,31+4096+13,0,0);
    burst(0,0,1,1,4,0,64'h80000fe0);
    burst(0,31,255,0,4,0,64'h80001000);
    // Last R beat contains 16 bytes, but only thirteen belong to the instruction.
    burst(0,4127,0,0,4,0,64'h80002000);
    drain(1); cases++; $display("VLDU_NATURAL_PAGE_CROSS_PASS bytes=%0d",seen_count[0]);
  endtask

  initial begin
    int lens[4]='{0,1,254,255};
    cycle_no=0; cases=0; checked_bytes=0; r_beats=0; descriptors=0; skips=0; partials=0; stalls=0;
    stable_checks=0; mask_checks=0;
    @(negedge clk_i);
    if ($test$plusargs("SMALL_ONLY")) begin
      for(int len=0;len<32;len++) begin
        single(len,0,0,0,0);
        single(len,31,0,1,0);
        single(len,3,3,1,1);
      end
      single(63,0,0,1,0);
    end else if ($test$plusargs("SPLIT_FOCUSED")) page_cross();
    else begin
    // First beat has sixteen bytes, but only one byte fits in the first VRF word.
    single(255,31,0,1,0);
    if (!$test$plusargs("FOCUSED")) begin
      foreach(lens[k]) begin
        single(lens[k],0,0,0,0);
        single(lens[k],31,0,1,0);
        single(lens[k],3,3,1,1);
      end
      pressure=1; reset_case(); issue(0,5,4096+32-5,0,0);
      // 4KiB boundary split followed by a separate descriptor for the same owner.
      burst(0,5,255,5,4,0); burst(0,4096,1,0,4,0,64'h80002000); drain(1); cases++;
      $display("VLDU_SPLIT_PASS");
      pressure=1; reset_case(); issue(0,0,64,1,1);
      for(int i=0;i<64;i++) burst(0,i,0,(i*7)%16,0,!enabled(0,i));
      drain(1); cases++; $display("VLDU_INDEX_MASK_SKIP_PASS skips=%0d",skips);
      pressure=1; reset_case(); all_masked[0]=1; issue(0,0,40,1,1);
      for(int i=0;i<40;i++) burst(0,i,0,0,0,1);
      drain(1); cases++; $display("VLDU_ALL_SKIP_PASS noR=40");
      pressure=1; reset_case(); issue(0,0,4096,0,0); issue(1,0,32,0,0);
      burst(0,0,255,0,4,0); burst(1,0,1,0,4,0); drain(2);
      if (peak_owners<2) $fatal(1,"QUEUE_OVERLAP_NOT_EXERCISED");
      cases++; $display("VLDU_QUEUE_OWNER_PASS owners=2 peak=%0d",peak_owners);
      page_cross();
    end
    end
    $display("VLDU_SUITE_PASS cases=%0d bytes=%0d R=%0d desc=%0d skips=%0d stalls=%0d stable=%0d masks=%0d partials=%0d VLEN=%0d",
             cases,checked_bytes,r_beats,descriptors,skips,stalls,stable_checks,mask_checks,partials,VLEN);
    $finish;
  end
  initial begin #2000000; $fatal(1,"WATCHDOG"); end
endmodule
