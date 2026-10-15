`timescale 1ns/1ps
module probe_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [10:0] vlen_t;
  typedef logic [15:0] vaddr_t;
  typedef logic [63:0] address_t;
  typedef logic [3:0] id_t;
  typedef logic user_t;
  `include "ara/ara_typedef.svh"
  `include "ara/intf_typedef.svh"
  `include "axi/typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cfg)
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, address_t, id_t, user_t)
  `AXI_TYPEDEF_AW_CHAN_T(aw_t, address_t, id_t, user_t)
  `AXI_TYPEDEF_W_CHAN_T(w_t, logic[127:0], logic[15:0], user_t)
  `AXI_TYPEDEF_B_CHAN_T(b_t, id_t, user_t)
  `include "sequencer_types.svh"

  bit clk=0;
  always #5 clk=~clk;
  logic rst=0, ara_valid=0, ara_ready, ara_resp_valid, ara_idle;
  ara_req_t ara_req;
  ara_resp_t ara_resp;
  pe_req_t pe_req;
  pe_resp_t [7:0] pe_resp;
  pe_resp_t st_resp, mask_resp;
  logic pe_valid, broadcast_valid, st_ready, mask_ready;
  logic [7:0] pe_ready, running;
  logic ack, fof, early_ld, early_st, st_exception, store_complete;
  exception_t exception_out, mmu_ex;
  vlen_t exception_start;
  logic mmu_req, mmu_valid, mmu_store, ar_valid, aw_valid;
  logic [Cfg.VLEN-1:0] mmu_va;
  ar_t ar;
  aw_t aw;
  addrgen_axi_req_t desc;
  logic desc_valid, desc_ready, addr_idle, st_idle;
  logic [3:0][7:0] mask_bits, st_mask_bits;
  logic [3:0] mask_valid, st_mask_valid;
  vid_t mask_owner, st_mask_owner;
  vlen_t mask_first, st_mask_first;
  vfu_e mask_target;
  logic mask_accept;
  elen_t [3:0][NrMaskFUnits+1:0] operands;
  logic [3:0][NrMaskFUnits+1:0] operand_valid, operand_ready;
  logic [3:0] mask_result_req;
  elen_t [3:0] st_operands;
  logic [3:0] st_operand_valid, st_operand_ready;
  w_t w;
  logic w_valid, st_pending, w_ready, b_valid, b_ready;
  b_t b;
  elen_t [3:0] indices;
  logic [3:0] index_valid;
  logic index_ready;
  id_t aw_id;

  always_comb begin
    pe_ready='1;
    pe_ready[4+OffsetStore]=st_ready;
    pe_ready[4+OffsetMask]=mask_ready;
    pe_resp='0;
    pe_resp[4+OffsetStore]=st_resp;
    pe_resp[4+OffsetMask]=mask_resp;
  end
  // Same masked-memory broadcast qualification as ara.sv, with ready lane sources.
  assign broadcast_valid=pe_valid && ((pe_req.vm && pe_req.vfu!=VFU_MaskUnit) ||
                                      ((&pe_ready[3:0]) && mask_ready));
  ara_sequencer #(.NrLanes(4),.VLEN(1024),.ara_req_t(ara_req_t),.ara_resp_t(ara_resp_t),
    .pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),.exception_t(exception_t)) seq (
    .clk_i(clk),.rst_ni(rst),.ara_req_i(ara_req),.ara_req_valid_i(ara_valid),
    .ara_req_ready_o(ara_ready),.ara_resp_o(ara_resp),.ara_resp_valid_o(ara_resp_valid),
    .ara_idle_o(ara_idle),.ara_store_accepted_o(),.pe_req_o(pe_req),
    .pe_req_valid_o(pe_valid),.pe_vinsn_running_o(running),.pe_req_ready_i(pe_ready),
    .pe_resp_i(pe_resp),.alu_vinsn_done_i(1'b0),.mfpu_vinsn_done_i(1'b0),
    .global_hazard_table_o(),.pe_scalar_resp_i('0),.pe_scalar_resp_valid_i(1'b0),
    .pe_scalar_resp_ready_o(),.addrgen_ack_i(ack),.addrgen_exception_i(exception_out),
    .addrgen_exception_vstart_i(exception_start),.addrgen_fof_exception_i(fof),
    .lsu_current_burst_exception_i(st_exception),.qbs_fflags_i('0),.qbs_fflags_valid_i(1'b0));

  masku #(.NrLanes(4),.VLEN(1024),.vaddr_t(vaddr_t),.pe_req_t(pe_req_t),
    .pe_resp_t(pe_resp_t)) mu (
    .clk_i(clk),.rst_ni(rst),.pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.pe_req_ready_o(mask_ready),.pe_resp_o(mask_resp),
    .masku_operand_i(operands),.masku_operand_valid_i(operand_valid),
    .masku_operand_ready_o(operand_ready),.masku_result_req_o(mask_result_req),
    .masku_result_gnt_i('0),.masku_result_final_gnt_i('0),
    .masku_vrgat_req_ready_i('1),.mask_o(mask_bits),.mask_valid_o(mask_valid),
    .mask_target_fu_o(mask_target),.mask_owner_id_o(mask_owner),
    .mask_first_element_o(mask_first),.lane_mask_ready_i('0),
    .vldu_mask_ready_i(1'b0),.vstu_mask_ready_i(mask_accept),.sldu_mask_ready_i(1'b0));

  vstu #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(128),.AxiAddrWidth(64),
    .vaddr_t(vaddr_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),
    .exception_t(exception_t),.axi_w_t(w_t),.axi_b_t(b_t)) st (
    .clk_i(clk),.rst_ni(rst),.axi_w_o(w),.axi_w_valid_o(w_valid),.axi_w_ready_i(w_ready),
    .axi_b_i(b),.axi_b_valid_i(b_valid),.axi_b_ready_o(b_ready),
    .store_pending_o(st_pending),.store_complete_o(store_complete),
    .pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.pe_req_ready_o(st_ready),.pe_resp_o(st_resp),
    .stu_current_burst_exception_o(st_exception),.store_b_exception_o(),
    .store_b_exception_vstart_o(),.axi_addrgen_req_i(desc),
    .axi_addrgen_req_valid_i(desc_valid),.axi_addrgen_req_ready_o(desc_ready),
    .addrgen_illegal_store_i(early_st),.stu_operand_i(st_operands),
    .stu_operand_valid_i(st_operand_valid),.stu_operand_ready_o(st_operand_ready),
    .lsu_ex_flush_i(1'b0),
    .mask_i(mask_bits),.mask_valid_i(mask_valid & {4{mask_target==VFU_StoreUnit}}),
    .mask_owner_id_i(mask_owner),.mask_first_element_i(mask_first),.mask_ready_o(mask_accept),
    .mask_word_o(st_mask_bits),.mask_word_valid_o(st_mask_valid),
    .mask_owner_id_o(st_mask_owner),.mask_first_element_o(st_mask_first),.idle_o(st_idle));

  addrgen #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(128),.AxiAddrWidth(64),
    .axi_ar_t(ar_t),.axi_aw_t(aw_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg),.exception_t(exception_t)) ag (
    .clk_i(clk),.rst_ni(rst),.axi_ar_o(ar),.axi_ar_valid_o(ar_valid),.axi_ar_ready_i(1'b1),
    .axi_aw_o(aw),.axi_aw_valid_o(aw_valid),.axi_aw_ready_i(1'b1),
    .en_ld_st_translation_i(1'b0),.mmu_misaligned_ex_o(),.mmu_req_o(mmu_req),
    .mmu_vaddr_o(mmu_va),.mmu_is_store_o(mmu_store),.mmu_dtlb_hit_i(1'b0),
    .mmu_dtlb_ppn_i('0),.mmu_valid_i(mmu_valid),.mmu_paddr_i('0),.mmu_exception_i(mmu_ex),
    .core_st_pending_i(1'b0),.pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.addrgen_exception_o(exception_out),.addrgen_ack_o(ack),
    .addrgen_exception_vstart_o(exception_start),.addrgen_fof_exception_o(fof),
    .addrgen_illegal_load_o(early_ld),.addrgen_illegal_store_o(early_st),
    .axi_addrgen_req_o(desc),.axi_addrgen_req_valid_o(desc_valid),
    .ldu_axi_addrgen_req_ready_i(1'b0),.stu_axi_addrgen_req_ready_i(desc_ready),
    .ldu_mask_word_i('0),.ldu_mask_word_valid_i('0),
    .ldu_mask_owner_id_i('0),.ldu_mask_first_element_i('0),
    .stu_mask_word_i(st_mask_bits),.stu_mask_word_valid_i(st_mask_valid),
    .stu_mask_owner_id_i(st_mask_owner),.stu_mask_first_element_i(st_mask_first),.addrgen_operand_i(indices),.addrgen_operand_valid_i(index_valid),
    .addrgen_operand_ready_o(index_ready),.lsu_ex_flush_i(1'b0),.idle_o(addr_idle));


  localparam logic[63:0] Base=64'h80010000;
  typedef struct {aw_t aw;} write_t;
  typedef struct {id_t id; int due;} response_t;
  write_t writes[$], write_head;
  response_t replies[$], reply_head;
  int fd, case_id, cycle_no, stride_bytes, start_elem, stop_elem;
  int accepted, acks, responses, aws, ws, bs, normal_pops, markers, early_count;
  int completes, dones, done_cycle, last_b, first_w, last_w, blocked_good, protected_cycles;
  int data_count[4];
  bit submitted, baseline, fault;
  vid_t owner;
  logic[63:0] scalar_base;
  byte memory[64];
  bit touched[64];

  function automatic byte source_byte(int byte_index);
    return byte'(8'h41 ^ (byte_index*29));
  endfunction
  function automatic logic[63:0] element_addr(int e);
    return scalar_base+64'(e*stride_bytes);
  endfunction

  task automatic tick;
    w_ready=(case_id!=1 || cycle_no>=40);
    b='0; b_valid=0;
    if(replies.size()!=0 && cycle_no>=replies[0].due) begin
      b_valid=1; b.id=replies[0].id;
    end
    for(int l=0;l<4;l++) begin
      st_operand_valid[l]=submitted && data_count[l]==0;
      for(int byte_index=0;byte_index<8;byte_index++)
        st_operands[l][byte_index*8+:8]=source_byte(l*8+byte_index);
    end
    @(posedge clk);
    if(rst) begin
      $fdisplay(fd,"%0d,%0d,%b,%b,%0d,%b,%0d,%0d,%b,%h,%0d,%0d,%b,%b,%h,%h,%b,%b,%b,%b,%b,%b,%h,%h,%0d,%b,%b,%b,%0d,%h,%0d,%b,%b,%0d,%h,%0d,%b,%0d,%0d,%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b",
        case_id,cycle_no,broadcast_valid,st_ready,pe_req.id,pe_req.vm,pe_req.vl,pe_req.vstart,
        aw_valid,aw.addr,aw.len,aw.size,w_valid,w_ready,w.data,w.strb,w.last,b_valid,b_ready,
        ag.axi_addrgen_queue_push,desc_valid,desc_ready,desc.addr,desc.vaddr,desc.elem_start,
        desc.is_exception,desc.is_skip,ack,exception_out.cause,exception_out.tval,exception_start,
        exception_out.valid,ara_resp_valid,ara_resp.exception.cause,ara_resp.exception.tval,
        ara_resp.exception_vstart,ara_resp.exception.valid,
        st.issue_cnt_bytes_q,st.vrf_cnt_q,st.vrf_pnt_q,st.vinsn_queue_q.commit_cnt,
        st.vinsn_queue_q.pending_b[st.vinsn_queue_q.commit_pnt],
        st_operand_valid,st_operand_ready,st.stu_operand_valid,st.stu_operand_ready,
        st_pending,store_complete,st_resp.vinsn_done,ara_idle,st_idle,early_st,st_exception);
      if(broadcast_valid && st_ready && !submitted) begin
        assert(pe_req.op==VSSE && pe_req.vm && pe_req.vl==2 &&
               pe_req.vstart==start_elem && pe_req.scalar_op==scalar_base &&
               pe_req.stride==64'(stride_bytes) && pe_req.old_eew_vs1==EW64)
          else $fatal(1,"BAD_REQUEST");
        submitted=1; owner=pe_req.id; accepted++;
      end
      for(int l=0;l<4;l++)
        if(st_operand_valid[l] && st_operand_ready[l]) data_count[l]++;
      if(b_valid && b_ready) begin
        assert(replies.size()>0 && b.resp==0) else $fatal(1,"BAD_B");
        reply_head=replies.pop_front(); bs++; last_b=cycle_no;
      end
      if(aw_valid) begin
        write_t entry;
        assert(submitted && aws<stop_elem-start_elem &&
               aw.addr==element_addr(start_elem+aws) && aw.len==0 && aw.size==3 &&
               aw.burst==axi_pkg::BURST_INCR)
          else $fatal(1,"AW_GEOMETRY");
        entry.aw=aw; writes.push_back(entry); aws++;
      end
      if(w_valid && w_ready) begin
        response_t entry;
        int elem, lower;
        assert(writes.size()>0 && w.last) else $fatal(1,"W_WITHOUT_AW");
        write_head=writes.pop_front();
        elem=start_elem+ws; lower=int'(write_head.aw.addr%16);
        assert(w.strb==(16'hff<<lower)) else $fatal(1,"W_STRB");
        for(int byte_index=0;byte_index<16;byte_index++) if(w.strb[byte_index]) begin
          int index;
          logic[63:0] address;
          address=(write_head.aw.addr & ~64'd15)+byte_index;
          index=int'(address-(Base-16));
          assert(index>=0 && index<64 && !touched[index] &&
                 w.data[byte_index*8+:8]===source_byte(elem*8+byte_index-lower))
            else $fatal(1,"W_DATA case=%0d elem=%0d byte=%0d data=%h",case_id,elem,byte_index,w.data);
          memory[index]=w.data[byte_index*8+:8]; touched[index]=1;
        end
        entry.id=write_head.aw.id; entry.due=cycle_no+(case_id==1 ? 10 : 2);
        replies.push_back(entry); ws++; last_w=cycle_no;
        if(first_w<0) first_w=cycle_no;
      end
      if(desc_valid && desc_ready) begin
        assert(!desc.is_load && !desc.is_skip) else $fatal(1,"DESC_TYPE");
        if(desc.is_exception) begin
          assert(case_id==1 && normal_pops==1 && markers==0 &&
                 desc.vaddr==Base+4 && desc.elem_start==1 && bs==1)
            else $fatal(1,"ORDERED_MARKER_BEFORE_PREFIX_B");
          markers++;
        end else begin
          assert(w_valid && w_ready && desc.addr==element_addr(start_elem+normal_pops))
            else $fatal(1,"NORMAL_POP_WITHOUT_W");
          normal_pops++;
        end
      end
      if(case_id==1 && desc_valid && !desc.is_exception && !w_ready) begin
        blocked_good++;
        assert(!desc_ready && !store_complete && !st_resp.vinsn_done[owner])
          else $fatal(1,"PREFIX_DISCARDED_UNDER_W_PRESSURE");
      end
      if(acks && fault && dones==0 && !st_resp.vinsn_done[owner]) begin
        protected_cycles++;
        assert(st_pending && !ara_idle) else $fatal(1,"FAULT_LOST_PENDING_PROTECTION");
      end
      if(ack) begin
        acks++;
        assert(exception_out.valid==fault) else $fatal(1,"ACK_KIND");
        if(fault)
          assert(exception_out.cause==6 && exception_out.tval==Base+4 && exception_start==1 &&
                 early_st==(case_id==3))
            else $fatal(1,"ACK_CONTEXT");
      end
      if(early_st) begin early_count++; assert(case_id==3) else $fatal(1,"DOUBLE_EARLY"); end
      if(ara_resp_valid) begin
        responses++;
        assert(ara_resp.exception.valid==fault) else $fatal(1,"RESP_KIND");
        if(fault)
          assert(ara_resp.exception.cause==6 && ara_resp.exception.tval==Base+4 &&
                 ara_resp.exception_vstart==1 && (dones!=0 || st_pending || st_resp.vinsn_done[owner]))
            else $fatal(1,"RESP_CONTEXT_OR_PENDING");
      end
      if(store_complete) begin
        completes++;
        assert(bs==stop_elem-start_elem && writes.size()==0 && replies.size()==0)
          else $fatal(1,"COMPLETE_BEFORE_B");
      end
      if(submitted && st_resp.vinsn_done[owner]) begin
        dones++; done_cycle=cycle_no;
        assert(bs==stop_elem-start_elem && (bs==0 || cycle_no>last_b))
          else $fatal(1,"DONE_BEFORE_B");
      end
      assert(!ar_valid && !early_ld && !mmu_req && mask_valid==0 && st_mask_valid==0)
        else $fatal(1,"UNEXPECTED_PATH");
    end
    #1; @(negedge clk); cycle_no++;
  endtask

  initial begin
    baseline=$test$plusargs("BASELINE_NORMAL");
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"case,cycle,broadcast,st_ready,owner,vm,vl,vstart,aw_valid,aw_addr,aw_len,aw_size,w_valid,w_ready,w_data,w_strb,w_last,b_valid,b_ready,desc_push,desc_valid,desc_ready,desc_addr,desc_vaddr,desc_elem,desc_exception,desc_skip,ack,cause,tval,exception_start,exception,response,resp_cause,resp_tval,resp_start,resp_exception,issue_bytes,vrf_cnt,vrf_ptr,commit_count,pending_b,operand_valid,operand_ready,buffer_valid,buffer_pop,store_pending,store_complete,done,global_idle,st_idle,early_st,st_exception");
    for(case_id=0;case_id<(baseline ? 1 : 4);case_id++) begin
      rst=0; ara_valid=0; ara_req='0; cycle_no=0;
      operands='0; operand_valid='0; st_operands='0; st_operand_valid='0;
      indices='0; index_valid='0; mmu_valid=0; mmu_ex='0;
      writes.delete(); replies.delete();
      accepted=0; acks=0; responses=0; aws=0; ws=0; bs=0; normal_pops=0; markers=0;
      completes=0; dones=0; done_cycle=-1; early_count=0; last_b=-1;
      first_w=-1; last_w=-1; blocked_good=0; protected_cycles=0;
      submitted=0; owner=0; scalar_base=Base; stride_bytes=8; start_elem=0; stop_elem=2;
      fault=case_id==1 || case_id==3;
      case(case_id)
        1: begin stride_bytes=4; stop_elem=1; end
        2: begin stride_bytes=4; scalar_base=Base-4; start_elem=1; end
        3: begin stride_bytes=4; start_elem=1; stop_elem=1; end
        default: ;
      endcase
      for(int l=0;l<4;l++) data_count[l]=0;
      for(int j=0;j<64;j++) begin memory[j]=8'h5b; touched[j]=0; end
      repeat(5) tick(); rst=1; tick();
      ara_req='0; ara_req.token=1; ara_req.op=VSSE; ara_req.vm=1;
      ara_req.vs1=24; ara_req.use_vs1=1; ara_req.eew_vs1=EW64; ara_req.old_eew_vs1=EW64;
      ara_req.scalar_op=scalar_base; ara_req.stride=64'(stride_bytes);
      ara_req.vl=2; ara_req.vstart=vlen_t'(start_elem);
      ara_req.vtype.vsew=EW64; ara_req.vtype.vlmul=LMUL_1; ara_req.emul=LMUL_1;
      ara_req.eew_vmask=EW8; ara_valid=1;
      repeat(250) begin tick(); if(responses) ara_valid=0; end
      assert(accepted==1 && acks==1 && responses==1 && dones==1 && completes==1 &&
             aws==stop_elem-start_elem && ws==aws && bs==aws && normal_pops==aws &&
             markers==int'(case_id==1) && early_count==int'(case_id==3) &&
             ara_idle && addr_idle && st_idle && !st_pending &&
             writes.size()==0 && replies.size()==0)
        else $fatal(1,"TERMINAL case=%0d AW=%0d W=%0d B=%0d done=%0d idle=%b/%b/%b",
                    case_id,aws,ws,bs,dones,ara_idle,addr_idle,st_idle);
      for(int l=0;l<4;l++) assert(data_count[l]==1) else $fatal(1,"SOURCE_HANDSHAKE");
      for(int j=0;j<64;j++) begin
        bit want;
        byte expected;
        want=0; expected=8'h5b;
        for(int e=start_elem;e<stop_elem;e++)
          for(int k=0;k<8;k++) if(Base-16+j==element_addr(e)+k) begin
            want=1; expected=source_byte(e*8+k);
          end
        assert(touched[j]==want && memory[j]===expected) else $fatal(1,"FULL_MEMORY_GUARD");
      end
      if(case_id==1)
        assert(blocked_good>20 && protected_cycles>30 && first_w==40 &&
               last_b==50 && done_cycle>last_b) else $fatal(1,"PRESSURE_NOT_EXERCISED");
      $display("CASE_PASS case=%0d AW=%0d W=%0d B=%0d marker=%0d early=%0d firstW=%0d lastB=%0d done=%0d blocked=%0d protected=%0d",
               case_id,aws,ws,bs,markers,early_count,first_w,last_b,done_cycle,blocked_good,protected_cycles);
    end
    $display("M9_STORE_ACCEPTANCE_COMPLETE cases=%0d",baseline ? 1 : 4);
    $fclose(fd); $finish;
  end
  initial begin #11000; $fatal(1,"FIXED_BATCH_WATCHDOG_1100_CLOCKS"); end
endmodule
