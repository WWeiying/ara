`timescale 1ns/1ps
module index_tb;
  bit enabled=0;
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
  `AXI_TYPEDEF_W_CHAN_T(w_t, logic[255:0], logic[31:0], user_t)
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

  vstu #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(256),.AxiAddrWidth(64),
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

  addrgen #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(256),.AxiAddrWidth(64),
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

  int cycle_no, fd, accepted, acks, aw_count, w_count, b_count, early_count;
  int mask_accepts, mask_pops, st_dones, mask_dones, responses;
  int first_w_cycle=-1, last_pop_cycle=-1, done_cycle=-1, early_cycle=-1;
  int premature_pops, premature_done, good_head_while_pending0;
  int kept_prefix_cycles, pending_b_cycles, b_cycle=-1;
  int operand_count[4], data_count[4], index_count;
  bit submitted, response_seen;
  vid_t owner;

  always @(negedge clk) if(rst) begin
    w_ready=cycle_no>=40;
    b='0; b.id=aw_id;
    b_valid=first_w_cycle>=0 && cycle_no>=first_w_cycle+10 && b_count==0;
    for(int l=0;l<4;l++) begin
      operand_valid[l][0]=submitted && operand_count[l]==0;
      operands[l][0]='1;
      st_operand_valid[l]=submitted && data_count[l]==0;
      st_operands[l]=64'h123456789abcdef0;
      index_valid[l]=submitted && index_count==0;
    end
    if(response_seen)ara_valid=0;
  end

  always @(posedge clk) if(rst) begin
    cycle_no++;
    if(broadcast_valid && mask_ready) begin
      accepted++;owner=pe_req.id;submitted=1;
      assert(st_ready && pe_req.op==VSXE && pe_req.vl==2 && !pe_req.vm &&
             pe_req.eew_vs2==EW64 && pe_req.old_eew_vs2==EW64)
        else $fatal(1,"bad genuine indexed request");
    end
    for(int l=0;l<4;l++) begin
      if(operand_valid[l][0] && operand_ready[l][0])operand_count[l]++;
      if(st_operand_valid[l] && st_operand_ready[l])data_count[l]++;
    end
    if(index_ready && &index_valid)index_count++;
    if(aw_valid) begin
      aw_count++;aw_id=aw.id;
      assert(aw_count==1 && aw.addr==64'h40001000 && aw.len==0 && aw.size==3)
        else $fatal(1,"not exact aligned idx0 AW");
    end
    if(w_valid && w_ready) begin
      w_count++;first_w_cycle=cycle_no;
      assert(w_count==1 && w.last && w.strb==32'hff &&
             w.data[63:0]==64'h123456789abcdef0)
        else $fatal(1,"wrong real prefix W payload");
    end
    if(b_valid && b_ready) begin b_count++;b_cycle=cycle_no; end
    if(early_count>0 && w_count==0) begin
      assert(desc_valid && !desc.is_exception && !desc.is_skip && st.vinsn_issue_valid &&
             mask_pops==0 && st_dones==0 && !store_complete)
        else $fatal(1,"GOOD prefix lost before delayed W release");
      kept_prefix_cycles++;
    end
    if(st.vinsn_queue_q.pending_b[st.vinsn_queue_q.commit_pnt]!=0 && b_count==0) begin
      assert(mask_pops==0 && st_dones==0 && !store_complete && !st.mask_ready_d)
        else $fatal(1,"drain/done before real prefix B return");
      pending_b_cycles++;
    end
    if(early_st) begin
      early_count++;early_cycle=cycle_no;
      assert(aw_count==1 && w_count==0 && !w_ready && !w_valid &&
             st.vinsn_queue_q.pending_b=='0 && desc_valid &&
             !desc.is_exception && !desc.is_skip && !desc.is_load)
        else $fatal(1,"early illegal not accompanied by genuine pending GOOD descriptor");
      good_head_while_pending0++;
    end
    if(mask_accept) begin
      assert(mask_owner==owner && mask_first==0 && mask_accepts==0)
        else $fatal(1,"wrong genuine two-element mask ownership");
      mask_accepts++;
    end
    if(st.mask_ready_d && st.mask_word_valid) begin
      assert(st.mask_word_q.owner==owner && st_mask_first==0 && mask_pops==0)
        else $fatal(1,"wrong mask drain owner/window");
      mask_pops++;last_pop_cycle=cycle_no;
      assert(w_count==1 && b_count==1) else $fatal(1,"mask pop before original prefix W/B");
      if(w_count==0 && desc_valid && !desc.is_exception)premature_pops++;
    end
    if(submitted && st_resp.vinsn_done[owner]) begin
      st_dones++;done_cycle=cycle_no;
      assert(w_count==1 && b_count==1 && mask_pops==1 && !st.mask_word_valid)
        else $fatal(1,"store done before prefix+full mask drain");
      if(w_count==0 || b_count==0)premature_done++;
    end
    if(submitted && mask_resp.vinsn_done[owner])mask_dones++;
    if(ack) begin
      acks++;
      assert(exception_out.valid && exception_out.cause==6 &&
             exception_out.tval==64'h40001001 && exception_start==1)
        else $fatal(1,"wrong indexed idx1 misalignment architectural context");
    end
    if(ara_resp_valid) begin
      responses++;response_seen=1;
      assert(ara_resp.exception.valid && ara_resp.exception.cause==6 &&
             ara_resp.exception.tval==64'h40001001 && ara_resp.exception_vstart==1)
        else $fatal(1,"wrong sequencer misalignment response");
    end
    assert(!ar_valid && !early_ld && !fof && !mmu_req && mask_result_req==0)
      else $fatal(1,"unexpected indexed alignment-probe traffic");
    $fdisplay(fd,"%0d,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%b,%0d,%0d,%0d,%0d,%0d",
      cycle_no,aw_valid,w_valid,w_ready,b_valid,b_ready,early_st,desc_valid,desc_ready,
      desc.is_exception,desc.is_skip,st.vinsn_issue_valid,st_resp.vinsn_done[owner],
      mask_valid,mask_accept,st.mask_ready_d,ara_resp_valid,ara_idle,
      st.vinsn_queue_q.pending_b[st.vinsn_queue_q.commit_pnt],mask_accepts,mask_pops,
      premature_pops,premature_done);
    if(cycle_no==100) begin
      assert(accepted==1 && aw_count==1 && early_count==1 && acks==1 && responses==1 &&
             good_head_while_pending0==1 && index_count==1 && mask_accepts==1 &&
             mask_pops==1 && mask_dones==1 && st_dones==1)
        else $fatal(1,"incomplete real indexed discriminator");
      for(int l=0;l<4;l++)
        assert(operand_count[l]==1 && data_count[l]==1)
          else $fatal(1,"missing genuine mask/data source beat");
      $display("OBSERVATION indexed_vl2 accepted=%0d AW=%0d W=%0d B=%0d early=%0d early_cycle=%0d good_pendingB0=%0d premature_pops=%0d premature_done=%0d mask_pops=%0d done_cycle=%0d last_pop_cycle=%0d global_idle=%0b",
        accepted,aw_count,w_count,b_count,early_count,early_cycle,good_head_while_pending0,
        premature_pops,premature_done,mask_pops,done_cycle,last_pop_cycle,ara_idle);
      assert(premature_pops==0 && premature_done==0 && w_count==1 && b_count==1 &&
             kept_prefix_cycles>=10 && pending_b_cycles>=5 &&
             done_cycle>=last_pop_cycle && done_cycle>b_cycle &&
             st_idle && ara_idle && running==0 && mu.commit_cnt_q==0 &&
             mu.mask_queue_cnt_q==0 && !st.mask_word_valid &&
             !st.i_vstu_mask_register.gen_spill_reg.a_full_q &&
             !st.i_vstu_mask_register.gen_spill_reg.b_full_q)
        else $fatal(1,"indexed prefix/data/B/mask terminal acceptance incomplete");
      $display("PREFIX_ACCEPTANCE kept_cycles=%0d pendingB_cycles=%0d W_cycle=%0d B_cycle=%0d last_pop=%0d done=%0d local_spill_empty=1",
          kept_prefix_cycles,pending_b_cycles,first_w_cycle,b_cycle,last_pop_cycle,done_cycle);
      $display("GOOD_PREFIX_W_B_PRESERVED_NOT_SOC_ACCEPTANCE");
      $fclose(fd);$finish;
    end
  end

  initial begin: stimulus
    string kind;
    kind="fault"; void'($value$plusargs("KIND=%s",kind));
    if(kind!="index") disable stimulus;
    enabled=1;
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"cycle,aw,w,w_ready,b,b_ready,early_illegal,desc_valid,desc_ready,desc_exception,desc_skip,issue_valid,store_done,mask_valid,mask_accept,mask_pop,ara_response,ara_idle,pending_b,mask_accepts,mask_pops,premature_pops,premature_done");
    ara_req='0;operands='0;operand_valid='0;st_operands='0;st_operand_valid='0;
    indices[0]=0;indices[1]=1;indices[2]=16;indices[3]=24;index_valid='0;
    mmu_valid=0;mmu_ex='0;w_ready=0;b_valid=0;b='0;aw_id='0;owner='0;
    cycle_no=0;accepted=0;acks=0;aw_count=0;w_count=0;b_count=0;early_count=0;
    mask_accepts=0;mask_pops=0;st_dones=0;mask_dones=0;responses=0;index_count=0;
    premature_pops=0;premature_done=0;good_head_while_pending0=0;
    kept_prefix_cycles=0;pending_b_cycles=0;
    for(int l=0;l<4;l++)begin operand_count[l]=0;data_count[l]=0;end
    repeat(5)@(negedge clk);rst=1;@(negedge clk);
    ara_req.token=1;ara_req.op=VSXE;ara_req.vm=0;ara_req.vs1=24;ara_req.use_vs1=1;
    ara_req.old_eew_vs1=EW64;ara_req.vs2=8;ara_req.use_vs2=1;
    ara_req.eew_vs2=EW64;ara_req.old_eew_vs2=EW64;
    ara_req.scalar_op=64'h40001000;ara_req.vl=2;
    ara_req.vtype.vsew=EW64;ara_req.vtype.vlmul=LMUL_4;ara_req.emul=LMUL_4;
    ara_req.eew_vmask=EW8;ara_valid=1;
  end
  initial begin #2000;if(enabled)$fatal(1,"fixed 200-cycle watchdog");end
endmodule
