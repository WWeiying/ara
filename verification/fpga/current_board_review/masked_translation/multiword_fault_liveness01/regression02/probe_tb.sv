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
  `AXI_TYPEDEF_R_CHAN_T(r_t, logic[255:0], id_t, user_t)
  `include "sequencer_types.svh"

  bit clk=0;
  always #5 clk=~clk;
  logic rst=0, ara_valid=0, ara_ready, ara_resp_valid, ara_idle;
  ara_req_t ara_req;
  ara_resp_t ara_resp;
  pe_req_t pe_req;
  pe_resp_t [7:0] pe_resp;
  pe_resp_t ld_resp, mask_resp;
  logic pe_valid, broadcast_valid, ld_ready, mask_ready;
  logic [7:0] pe_ready, running;
  logic ack, fof, early_ld, early_st, ld_exception, load_complete;
  exception_t exception_out, mmu_ex;
  vlen_t exception_start;
  logic mmu_req, mmu_valid, mmu_store, ar_valid, aw_valid;
  logic [Cfg.VLEN-1:0] mmu_va;
  ar_t ar;
  aw_t aw;
  addrgen_axi_req_t desc;
  logic desc_valid, desc_ready, addr_idle, ld_idle;
  logic [3:0][7:0] mask_bits, ld_mask_bits;
  logic [3:0] mask_valid, ld_mask_valid;
  vid_t mask_owner, ld_mask_owner;
  vlen_t mask_first, ld_mask_first;
  vfu_e mask_target;
  logic mask_accept;
  elen_t [3:0][NrMaskFUnits+1:0] operands;
  logic [3:0][NrMaskFUnits+1:0] operand_valid, operand_ready;
  logic [3:0] ld_result_req, mask_result_req;
  vid_t [3:0] ld_result_id;
  vaddr_t [3:0] ld_result_addr;
  elen_t [3:0] ld_result_data;
  logic [3:0][7:0] ld_result_be;

  r_t axi_r;
  logic axi_r_valid, axi_r_ready, axi_ar_ready, flush;
  logic [Cfg.PLEN-1:0] mmu_pa;
  logic [3:0] result_gnt, result_final_gnt;

  always_comb begin
    pe_ready='1;
    pe_ready[4+OffsetLoad]=ld_ready;
    pe_ready[4+OffsetMask]=mask_ready;
    pe_resp='0;
    pe_resp[4+OffsetLoad]=ld_resp;
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
    .lsu_current_burst_exception_i(ld_exception),.qbs_fflags_i('0),.qbs_fflags_valid_i(1'b0));

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
    .vldu_mask_ready_i(mask_accept),.vstu_mask_ready_i(1'b0),.sldu_mask_ready_i(1'b0));

  vldu #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(256),.AxiAddrWidth(64),
    .vaddr_t(vaddr_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),.axi_r_t(r_t)) ld (
    .clk_i(clk),.rst_ni(rst),.axi_r_i(axi_r),.axi_r_valid_i(axi_r_valid),.axi_r_ready_o(axi_r_ready),
    .load_complete_o(load_complete),.pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.pe_req_ready_o(ld_ready),.pe_resp_o(ld_resp),
    .ldu_current_burst_exception_o(ld_exception),.axi_addrgen_req_i(desc),
    .axi_addrgen_req_valid_i(desc_valid),.axi_addrgen_req_ready_o(desc_ready),
    .addrgen_illegal_load_i(early_ld),.ldu_result_req_o(ld_result_req),
    .ldu_result_id_o(ld_result_id),.ldu_result_addr_o(ld_result_addr),
    .ldu_result_wdata_o(ld_result_data),.ldu_result_be_o(ld_result_be),
    .ldu_result_gnt_i(result_gnt),.ldu_result_final_gnt_i(result_final_gnt),.lsu_ex_flush_i(flush),
    .mask_i(mask_bits),.mask_valid_i(mask_valid & {4{mask_target==VFU_LoadUnit}}),
    .mask_owner_id_i(mask_owner),.mask_first_element_i(mask_first),.mask_ready_o(mask_accept),
    .mask_word_o(ld_mask_bits),.mask_word_valid_o(ld_mask_valid),
    .mask_owner_id_o(ld_mask_owner),.mask_first_element_o(ld_mask_first),.idle_o(ld_idle));

  addrgen #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(256),.AxiAddrWidth(64),
    .axi_ar_t(ar_t),.axi_aw_t(aw_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg),.exception_t(exception_t)) ag (
    .clk_i(clk),.rst_ni(rst),.axi_ar_o(ar),.axi_ar_valid_o(ar_valid),.axi_ar_ready_i(axi_ar_ready),
    .axi_aw_o(aw),.axi_aw_valid_o(aw_valid),.axi_aw_ready_i(1'b1),
    .en_ld_st_translation_i(1'b1),.mmu_misaligned_ex_o(),.mmu_req_o(mmu_req),
    .mmu_vaddr_o(mmu_va),.mmu_is_store_o(mmu_store),.mmu_dtlb_hit_i(1'b0),
    .mmu_dtlb_ppn_i('0),.mmu_valid_i(mmu_valid),.mmu_paddr_i(mmu_pa),.mmu_exception_i(mmu_ex),
    .core_st_pending_i(1'b0),.pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.addrgen_exception_o(exception_out),.addrgen_ack_o(ack),
    .addrgen_exception_vstart_o(exception_start),.addrgen_fof_exception_o(fof),
    .addrgen_illegal_load_o(early_ld),.addrgen_illegal_store_o(early_st),
    .axi_addrgen_req_o(desc),.axi_addrgen_req_valid_o(desc_valid),
    .ldu_axi_addrgen_req_ready_i(desc_ready),.stu_axi_addrgen_req_ready_i(1'b0),
    .ldu_mask_word_i(ld_mask_bits),.ldu_mask_word_valid_i(ld_mask_valid),
    .ldu_mask_owner_id_i(ld_mask_owner),.ldu_mask_first_element_i(ld_mask_first),
    .stu_mask_word_i('0),.stu_mask_word_valid_i('0),.stu_mask_owner_id_i('0),
    .stu_mask_first_element_i('0),.addrgen_operand_i('0),.addrgen_operand_valid_i('0),
    .addrgen_operand_ready_o(),.lsu_ex_flush_i(flush),.idle_o(addr_idle));


  typedef struct packed {vid_t id; vaddr_t addr; elen_t data; logic[7:0] be;} wb_t;
  wb_t wb_in[4], wb_out[4];
  logic[3:0] bank_valid, bank_ready;
  int cycle_no, release_cycle;
  for(genvar l=0;l<4;l++) begin: request_buffers
    assign wb_in[l]={ld_result_id[l],ld_result_addr[l],ld_result_data[l],ld_result_be[l]};
    stream_register #(.T(wb_t)) buf_i(
      .clk_i(clk),.rst_ni(rst),.clr_i(1'b0),.testmode_i(1'b0),
      .data_i(wb_in[l]),.valid_i(ld_result_req[l]),.ready_o(result_gnt[l]),
      .data_o(wb_out[l]),.valid_o(bank_valid[l]),.ready_i(bank_ready[l]));
    assign bank_ready[l]=cycle_no>=release_cycle;
    assign result_final_gnt[l]=bank_valid[l] && bank_ready[l];
  end
  typedef struct {ar_t ar; int beat; int due;} read_t;
  read_t reads[$], dropped;
  byte vrf[2][512];
  bit seen[2][512];
  int first[2], limits[2], stops[2];
  bit masks[2];
  logic[63:0] predicates[2], bases[2];
  bit active, submitted, mmu_pending, token, baseline;
  int case_id, phase, fd, group_index, vl, start_elem, fault_elem, expected_bytes;
  int accepted, responses, ld_dones, mask_dones, mask_accepts, mask_pops;
  int operand_count[4], mmu_due, mmu_requests, mmu_returns;
  int ar_count, r_count, desc_count, skip_count, exception_desc_count, written;
  int first_result_accept, first_final, last_final, done_cycle, blocked_bank_cycles;
  int ack_count, cycle_start, first_window;
  logic [63:0] mmu_saved_addr;
  bit is_masked, is_fof;
  vid_t owner;

  function automatic byte pattern(logic[63:0] a);
    return byte'(8'ha6 ^ (a[7:0]*37) ^ (case_id*13));
  endfunction

  function automatic bit wanted(int g, int b);
    return b>=first[g]*8 && b<stops[g]*8 &&
           (!masks[g] || predicates[g][b/8]);
  endfunction

  task automatic check_vrf;
    for(int g=0;g<2;g++)
      for(int b=0;b<512;b++) begin
        bit want;
        want=wanted(g,b);
        assert(seen[g][b]==want &&
               vrf[g][b]===(want ? pattern(bases[g]+b) : 8'h5b))
          else $fatal(1,"FULL_VRF case=%0d phase=%0d group=%0d byte=%0d got=%h want=%h",
                      case_id,phase,g,b,vrf[g][b],want ? pattern(bases[g]+b) : 8'h5b);
      end
  endtask

  task automatic tick;
    axi_ar_ready=reads.size()<8;
    axi_r='0; axi_r_valid=0;
    if(reads.size()!=0 && cycle_no>=reads[0].due) begin
      logic[63:0] beat_addr;
      beat_addr=(reads[0].ar.addr & ~64'd31) + reads[0].beat*32;
      axi_r_valid=1; axi_r.id=reads[0].ar.id;
      axi_r.last=(reads[0].beat==reads[0].ar.len);
      for(int b=0;b<32;b++) axi_r.data[b*8+:8]=pattern(beat_addr+b);
    end
    mmu_valid=mmu_pending && cycle_no==mmu_due;
    mmu_pa=mmu_saved_addr;
    mmu_ex='0;
    if(mmu_valid && fault_elem>=0 && mmu_saved_addr>=64'h40001000) begin
      mmu_ex.valid=1; mmu_ex.cause=riscv::LOAD_PAGE_FAULT;
      mmu_ex.tval=mmu_saved_addr;
    end
    operands='0; operand_valid='0;
    for(int b=0;b<32;b++) begin
      int physical_byte;
      physical_byte=shuffle_index(b,4,EW8);
      operands[physical_byte/8][0][(physical_byte%8)*8+:8]=
          byte'(predicates[group_index] >> (b*8));
    end
    for(int l=0;l<4;l++)
      operand_valid[l][0]=active && is_masked && submitted && operand_count[l]==0;
    @(posedge clk);
    if(rst) begin
      if(active && broadcast_valid && ld_ready &&
         !submitted) begin
        assert(pe_req.op==VLE && pe_req.vl==vl && pe_req.vstart==start_elem)
          else $fatal(1,"BAD_REAL_REQUEST");
        submitted=1; accepted++; owner=pe_req.id;
      end
      for(int l=0;l<4;l++)
        if(operand_valid[l][0] && operand_ready[l][0]) operand_count[l]++;
      if(mmu_valid) begin mmu_returns++; mmu_pending=0; end
      else if(mmu_req && !mmu_pending) begin
        int e;
        assert(active && submitted && !mmu_store) else $fatal(1,"UNOWNED_MMU");
        e=(mmu_va-bases[group_index])/8;
        assert(e>=start_elem && e<vl &&
               (!is_masked || predicates[group_index][e]))
          else $fatal(1,"MMU_INACTIVE_OR_OUTSIDE");
        mmu_saved_addr=mmu_va; mmu_due=cycle_no+3;
        mmu_pending=1; mmu_requests++;
      end
      if(axi_r_valid && axi_r_ready) begin
        assert(reads.size()!=0) else $fatal(1,"R_WITHOUT_AR");
        r_count++;
        if(axi_r.last) dropped=reads.pop_front();
        else reads[0].beat++;
      end
      if(ar_valid && axi_ar_ready) begin
        read_t entry;
        assert(active && (fault_elem<0 || ar.addr<64'h40001000))
          else $fatal(1,"AR_ON_FAULT_PAGE");
        entry.ar=ar; entry.beat=0; entry.due=cycle_no+2;
        reads.push_back(entry); ar_count++;
      end
      if(desc_valid && desc_ready) begin
        assert(desc.is_load) else $fatal(1,"STORE_DESCRIPTOR");
        desc_count++;
        if(desc.is_skip) begin skip_count++; assert(!axi_r_ready) else $fatal(1,"SKIP_RREADY"); end
        if(desc.is_exception) exception_desc_count++;
      end
      if(mask_accept) begin
        assert(active && is_masked && mask_owner==owner &&
               mask_first==first_window+mask_accepts*4)
          else $fatal(1,"INPUT_MASK_OWNER_WINDOW");
        mask_accepts++;
      end
      if(ld.mask_ready_d) begin
        assert(active && is_masked && ld_mask_valid!=0 && ld_mask_owner==owner &&
               ld_mask_first==first_window+mask_pops*4)
          else $fatal(1,"POP_MASK_OWNER_WINDOW");
        mask_pops++;
      end
      for(int l=0;l<4;l++) begin
        if(ld_result_req[l] && result_gnt[l]) begin
          assert(active && ld_result_id[l]==owner) else $fatal(1,"REQUEST_OWNER");
          if(first_result_accept<0) first_result_accept=cycle_no;
        end
        if(bank_valid[l] && !bank_ready[l]) blocked_bank_cycles++;
        if(result_final_gnt[l]) begin
          int word_index,index;
          assert(active && wb_out[l].id==owner) else $fatal(1,"FINAL_OWNER");
          word_index=int'(wb_out[l].addr)-int'(vaddr(5'(24+group_index*4),4,1024));
          if(first_final<0) first_final=cycle_no;
          last_final=cycle_no;
          for(int b=0;b<8;b++) if(wb_out[l].be[b]) begin
            index=(word_index*4+l)*8+b;
            assert(word_index>=0 && word_index<16 && wanted(group_index,index) &&
                   !seen[group_index][index] &&
                   wb_out[l].data[b*8+:8]===pattern(bases[group_index]+index))
              else $fatal(1,"WRITE_ORACLE case=%0d phase=%0d lane=%0d word=%0d byte=%0d data=%h",
                          case_id,phase,l,word_index,b,wb_out[l].data[b*8+:8]);
            vrf[group_index][index]=wb_out[l].data[b*8+:8];
            seen[group_index][index]=1; written++;
          end
        end
      end
      if(active && ld_resp.vinsn_done[owner]) begin
        ld_dones++; done_cycle=cycle_no;
        assert(written==expected_bytes && !(|bank_valid))
          else $fatal(1,"LOAD_DONE_BEFORE_FINAL_WRITE");
        if(fault_elem>=0)
          assert(mask_pops==(vl-first_window+3)/4 && ld_mask_valid==0)
            else $fatal(1,"FAULT_DONE_BEFORE_DRAIN");
      end
      if(active && mask_resp.vinsn_done[owner]) mask_dones++;
      if(ack) ack_count++;
      if(ara_resp_valid) begin
        responses++;
        assert(active && ara_resp.exception.valid==(fault_elem>=0))
          else $fatal(1,"RESPONSE_EXCEPTION");
        if(fault_elem>=0)
          assert(ara_resp.exception.cause==13 && ara_resp.exception_vstart==fault_elem &&
                 ara_resp.fof_exception==(is_fof && fault_elem>0) &&
                 ld_dones==1 && written==expected_bytes)
            else $fatal(1,"FAULT_RESPONSE_BEFORE_WRITE_OR_WRONG_QUALIFICATION");
        else assert(!ara_resp.fof_exception) else $fatal(1,"FALSE_FOF");
      end
      assert(!aw_valid && !early_ld && !early_st && mask_result_req==0)
        else $fatal(1,"UNEXPECTED_PATH");
      $fdisplay(fd,"%0d,%0d,%0d,%b,%b,%b,%h,%b,%b,%h,%0d,%0d,%b,%b,%h,%b,%b,%h,%b,%b,%0d,%0d,%b,%0d,%0d,%b,%0d,%b,%h,%h,%h,%h,%b,%b,%b,%b,%b,%0d,%b,%b,%0d,%0d,%0d",
        case_id,phase,cycle_no,broadcast_valid,mmu_req,mmu_valid,mmu_va,mmu_ex.valid,
        ar_valid,ar.addr,ar.len,ar.size,axi_ar_ready,axi_r_valid,axi_r.data,axi_r_ready,
        desc_valid,desc,desc_ready,mask_valid,mask_first,mask_owner,mask_accept,
        ld_mask_first,ld_mask_owner,ld_mask_valid,ld.ldu_ex_state_q,
        ld_result_req,ld_result_id,ld_result_addr,ld_result_data,ld_result_be,
        result_gnt,result_final_gnt,ld_resp.vinsn_done,mask_resp.vinsn_done,
        ara_resp_valid,ara_resp.exception_vstart,ara_resp.fof_exception,
        ara_idle,mu.commit_cnt_q,written,reads.size());
    end
    #1; @(negedge clk); cycle_no++;
  endtask

  task automatic instruction(int g, int n, int start, bit masked,
                             logic[63:0] pred, int fault, bit fof_mode, bit delayed);
    group_index=g; vl=n; start_elem=start; is_masked=masked;
    fault_elem=fault; is_fof=fof_mode; first_window=(start/4)*4;
    first[g]=start; limits[g]=n; stops[g]=(fault<0 ? n : fault);
    masks[g]=masked; predicates[g]=pred;
    bases[g]=(fault<0 ? 64'h40002000 : 64'h40001000-fault*8);
    expected_bytes=0;
    for(int b=0;b<512;b++) if(wanted(g,b)) expected_bytes++;
    accepted=0; responses=0; ld_dones=0; mask_dones=0;
    mask_accepts=0; mask_pops=0; ar_count=0; r_count=0; desc_count=0;
    skip_count=0; exception_desc_count=0; ack_count=0; written=0;
    mmu_requests=0; mmu_returns=0; mmu_pending=0; mmu_saved_addr=0;
    first_result_accept=-1; first_final=-1; last_final=-1; done_cycle=-1;
    blocked_bank_cycles=0;
    for(int l=0;l<4;l++) operand_count[l]=0;
    release_cycle=delayed ? cycle_no+60 : 0;
    active=1; submitted=0; owner=0; token=!token;
    ara_req='0; ara_req.token=token; ara_req.op=VLE; ara_req.vm=!masked;
    ara_req.vd=5'(24+g*4); ara_req.use_vd=1;
    ara_req.scalar_op=bases[g]; ara_req.stride=8; ara_req.vl=vlen_t'(n);
    ara_req.vstart=vlen_t'(start); ara_req.fault_only_first=fof_mode;
    ara_req.vtype.vsew=EW64; ara_req.vtype.vlmul=LMUL_4;
    ara_req.emul=LMUL_4; ara_req.eew_vmask=EW8; ara_valid=1;
    cycle_start=cycle_no;
    while(responses==0 || ld_dones==0 || !ara_idle) begin
      tick();
      if(responses) ara_valid=0;
      assert(cycle_no-cycle_start<200)
        else $fatal(1,"PROGRESS_BOUND case=%0d phase=%0d done=%0d responses=%0d idle=%b ex=%0d",
                    case_id,phase,ld_dones,responses,ara_idle,ld.ldu_ex_state_q);
    end
    repeat(5) tick();
    assert(accepted==1 && responses==1 && ld_dones==1 && mask_dones==int'(masked) &&
           ack_count==1 && exception_desc_count==int'(fault>=0) && reads.size()==0 &&
           mmu_requests==mmu_returns && !mmu_pending &&
           mask_valid==0 && ld_mask_valid==0 && mu.commit_cnt_q==0 &&
           !ld.i_vldu_mask_register.gen_spill_reg.a_full_q &&
           !ld.i_vldu_mask_register.gen_spill_reg.b_full_q)
      else $fatal(1,"TERMINAL_RESIDUE_OR_COUNTS");
    assert(mask_accepts==(masked ? (n-first_window+3)/4 : 0) &&
           mask_pops==mask_accepts) else $fatal(1,"MASK_COUNT");
    for(int l=0;l<4;l++) assert(operand_count[l]==int'(masked)) else $fatal(1,"SOURCE_COUNT");
    if(delayed) assert(first_result_accept<release_cycle && blocked_bank_cycles>0 &&
                        first_final>=release_cycle && done_cycle>last_final)
      else $fatal(1,"FINAL_GRANT_DELAY_NOT_EXERCISED");
    check_vrf();
    $display("INSTRUCTION_PASS case=%0d phase=%0d VL=%0d start=%0d fault=%0d fof=%0b bytes=%0d AR=%0d R=%0d skip=%0d words=%0d pops=%0d firstaccept=%0d firstfinal=%0d lastfinal=%0d done=%0d blocked=%0d",
      case_id,phase,n,start,fault,fof_mode,written,ar_count,r_count,skip_count,
      mask_accepts,mask_pops,first_result_accept,first_final,last_final,done_cycle,blocked_bank_cycles);
    active=0;
    if(fault>=0) begin
      assert(ara_idle) else $fatal(1,"FLUSH_BEFORE_GLOBAL_IDLE");
      flush=1; tick(); flush=0; repeat(3) tick();
    end
  endtask

  initial begin
    baseline=$test$plusargs("BASELINE");
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"case,phase,cycle,broadcast,mmu_req,mmu_response,mmu_addr,mmu_fault,ar_valid,ar_addr,ar_len,ar_size,ar_ready,r_valid,r_data,r_ready,desc_valid,desc,desc_ready,mask_valid,mask_first,mask_owner,mask_accept,ld_mask_first,ld_mask_owner,ld_mask_valid,ex_state,result_req,result_id,result_addr,result_data,result_be,result_gnt,final_gnt,ld_done,mask_done,ara_response,exception_start,fof,global_idle,mask_commit,written,axi_pending");
    for(case_id=0;case_id<(baseline ? 2 : 7);case_id++) begin
      rst=0; ara_valid=0; ara_req='0; token=0; active=0; submitted=0;
      flush=0; cycle_no=0; release_cycle=0; reads.delete();
      mmu_pending=0; mmu_saved_addr=0; fault_elem=-1; group_index=0;
      for(int g=0;g<2;g++) begin
        first[g]=0; limits[g]=0; stops[g]=0; masks[g]=0; predicates[g]=0; bases[g]=0;
        for(int b=0;b<512;b++) begin vrf[g][b]=8'h5b; seen[g][b]=0; end
      end
      repeat(5) tick(); rst=1; phase=0; tick();
      case(case_id)
        0: instruction(0,9,0,1,64'h155,-1,0,0);
        1: instruction(0,9,0,0,'1,-1,0,0);
        2: instruction(0,9,3,1,'1,5,0,1);
        3: instruction(0,13,5,1,'1,7,0,1);
        4: instruction(0,9,0,1,'1,8,0,1);
        5: instruction(0,9,0,1,'1,5,1,1);
        6: instruction(0,9,0,1,'1,0,1,0);
      endcase
      phase=1;
      instruction(1,5,0,1,64'ha,-1,0,0);
      $display("SCENARIO_PASS case=%0d full_group_bytes=1024",case_id);
    end
    $display("JOINT_REGRESSION_PASS scenarios=%0d",baseline ? 2 : 7);
    $fclose(fd); $finish;
  end
  initial begin #40000; $fatal(1,"FIXED_BATCH_WATCHDOG_4000_CLOCKS"); end
endmodule
