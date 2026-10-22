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
    .clk_i(clk),.rst_ni(rst),.axi_r_i('0),.axi_r_valid_i(1'b0),.axi_r_ready_o(),
    .load_complete_o(load_complete),.pe_req_i(pe_req),.pe_req_valid_i(broadcast_valid),
    .pe_vinsn_running_i(running),.pe_req_ready_o(ld_ready),.pe_resp_o(ld_resp),
    .ldu_current_burst_exception_o(ld_exception),.axi_addrgen_req_i(desc),
    .axi_addrgen_req_valid_i(desc_valid),.axi_addrgen_req_ready_o(desc_ready),
    .addrgen_illegal_load_i(early_ld),.ldu_result_req_o(ld_result_req),
    .ldu_result_id_o(ld_result_id),.ldu_result_addr_o(ld_result_addr),
    .ldu_result_wdata_o(ld_result_data),.ldu_result_be_o(ld_result_be),
    .ldu_result_gnt_i('0),.ldu_result_final_gnt_i('0),.lsu_ex_flush_i(1'b0),
    .mask_i(mask_bits),.mask_valid_i(mask_valid & {4{mask_target==VFU_LoadUnit}}),
    .mask_owner_id_i(mask_owner),.mask_first_element_i(mask_first),.mask_ready_o(mask_accept),
    .mask_word_o(ld_mask_bits),.mask_word_valid_o(ld_mask_valid),
    .mask_owner_id_o(ld_mask_owner),.mask_first_element_o(ld_mask_first),.idle_o(ld_idle));

  addrgen #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(256),.AxiAddrWidth(64),
    .axi_ar_t(ar_t),.axi_aw_t(aw_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg),.exception_t(exception_t)) ag (
    .clk_i(clk),.rst_ni(rst),.axi_ar_o(ar),.axi_ar_valid_o(ar_valid),.axi_ar_ready_i(1'b1),
    .axi_aw_o(aw),.axi_aw_valid_o(aw_valid),.axi_aw_ready_i(1'b1),
    .en_ld_st_translation_i(1'b1),.mmu_misaligned_ex_o(),.mmu_req_o(mmu_req),
    .mmu_vaddr_o(mmu_va),.mmu_is_store_o(mmu_store),.mmu_dtlb_hit_i(1'b0),
    .mmu_dtlb_ppn_i('0),.mmu_valid_i(mmu_valid),.mmu_paddr_i('0),.mmu_exception_i(mmu_ex),
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
    .addrgen_operand_ready_o(),.lsu_ex_flush_i(1'b0),.idle_o(addr_idle));

  int vl, cycle_no, fd, accepted, req_cycle=-1, mmu_returns, acks, descs;
  int ld_dones, mask_dones, responses, mask_accepts, mask_pops, stable_rows;
  int operand_count[4];
  bit submitted, response_seen;
  vid_t owner;

  always @(negedge clk) if (rst) begin
    mmu_valid=0; mmu_ex='0;
    if(req_cycle>=0 && cycle_no==req_cycle+2 && mmu_returns==0) begin
      mmu_valid=1; mmu_ex.valid=1; mmu_ex.cause=riscv::LOAD_PAGE_FAULT;
      mmu_ex.tval=64'h40001000;
    end
    for(int l=0;l<4;l++) begin
      operand_valid[l][0]=submitted && operand_count[l]==0;
      operands[l][0]='1;
    end
    if(response_seen) ara_valid=0;
  end

  always @(posedge clk) if(rst) begin
    cycle_no++;
    if(broadcast_valid && mask_ready) begin
      accepted++; owner=pe_req.id; submitted=1;
      assert(ld_ready && pe_req.vl==vl && pe_req.op==VLSE && !pe_req.vm && pe_req.stride==0)
        else $fatal(1,"bad real PE acceptance");
    end
    for(int l=0;l<4;l++)
      if(operand_valid[l][0] && operand_ready[l][0]) operand_count[l]++;
    if(mmu_req && req_cycle<0) begin
      req_cycle=cycle_no;
      assert(submitted && !mmu_store && mmu_va==64'h40001000 &&
             ld_mask_owner==owner && ld_mask_first==0 && ld_mask_valid[0] && ld_mask_bits[0][0])
        else $fatal(1,"MMU request without real matching active mask window");
    end
    if(mmu_valid) begin
      mmu_returns++;
      assert(req_cycle>=0 && cycle_no==req_cycle+3) else $fatal(1,"unsolicited MMU response");
    end
    if(ack) begin
      acks++;
      assert(exception_out.valid && exception_out.cause==13 && exception_start==0)
        else $fatal(1,"wrong real AddrGen fault");
    end
    if(desc_valid && desc_ready) begin
      descs++;
      assert(desc.is_load && desc.is_exception && !desc.is_skip) else $fatal(1,"wrong descriptor");
    end
    if(mask_accept) begin
      assert(mask_owner==owner && mask_first==mask_accepts*4) else $fatal(1,"mask ownership/order");
      mask_accepts++;
    end
    if(ld.mask_ready_d) begin
      assert(ld_mask_valid!=0 && ld_mask_owner==owner &&
             ld_mask_first==mask_pops*4 && ld.ldu_ex_state_q==4)
        else $fatal(1,"drain consumed wrong owner/window or wrong state");
      mask_pops++;
    end
    if(ld_resp.vinsn_done[owner]) begin
      assert(mask_pops==(vl+3)/4 && ld_mask_valid==0 &&
             mask_accepts==(vl+3)/4 && mu.commit_cnt_q==0)
        else $fatal(1,"load done before complete predicate drain");
      ld_dones++;
    end
    if(mask_resp.vinsn_done[owner]) mask_dones++;
    if(ara_resp_valid) begin
      responses++; response_seen=1;
      assert(ara_resp.exception.valid && ara_resp.exception.cause==13 &&
             ara_resp.exception_vstart==0 && ld_dones==1)
        else $fatal(1,"premature/wrong sequencer response");
    end
    assert(!ar_valid && !aw_valid && !early_ld && !early_st && !fof &&
           ld_result_req==0 && mask_result_req==0) else $fatal(1,"unexpected data/prefix traffic");
    $fdisplay(fd,"%0d,%0d,%b,%b,%b,%b,%b,%b,%b,%b,%0d,%0d,%b,%b,%0d,%b,%0d,%b,%b,%0d,%b,%b,%b,%b,%b,%0d,%0d,%0d",
      cycle_no,vl,broadcast_valid,mmu_req,mmu_valid,ack,desc_valid,desc_ready,
      mask_valid,mask_accept,mask_first,mask_owner,ld_mask_valid,ld.mask_input_valid,
      ld_mask_first,ld.mask_ready_d,ld.ldu_ex_state_q,ld.vinsn_issue_valid,
      ld_resp.vinsn_done[owner],mu.commit_cnt_q,mask_resp.vinsn_done[owner],
      ara_resp_valid,ara_idle,response_seen && ara_idle,running,
      ld.i_vldu_mask_register.gen_spill_reg.a_full_q,ld.i_vldu_mask_register.gen_spill_reg.b_full_q,mu.mask_queue_cnt_q);
    if(cycle_no>=80) begin
      assert(response_seen && ara_idle && running==0 && mu.commit_cnt_q==0 &&
        !ld.vinsn_issue_valid && ld.ldu_ex_state_q==0 &&
        ld.result_queue_cnt_q==0 && ld.result_final_gnt_q==4'hf &&
        mask_valid==0 && ld_mask_valid==0 &&
        !ld.i_vldu_mask_register.gen_spill_reg.a_full_q &&
        !ld.i_vldu_mask_register.gen_spill_reg.b_full_q)
        else $fatal(1,"fixed fault path did not drain and reach global idle");
      stable_rows++;
    end
    if(cycle_no==100) begin
      assert(accepted==1 && mmu_returns==1 && acks==1 && descs==1 && ld_dones==1 &&
        responses==1 && mask_accepts==(vl+3)/4 && mask_pops==(vl+3)/4 &&
        mask_dones==1 && stable_rows==21)
        else $fatal(1,"incomplete discriminator scope");
      for(int l=0;l<4;l++) assert(operand_count[l]==1) else $fatal(1,"not one genuine packed-mask beat");
      $display("OBSERVATION vl=%0d accepted=%0d mmu=%0d ack=%0d descriptor=%0d ld_done=%0d mask_done=%0d response=%0d mask_accepts=%0d global_idle=%0b mask_commit=%0d stable_rows=%0d",
        vl,accepted,mmu_returns,acks,descs,ld_dones,mask_dones,responses,mask_accepts,ara_idle,mu.commit_cnt_q,stable_rows);
      $display("PREDICATE_DRAIN_IDLE_PASS vl=%0d words=%0d pops=%0d", vl,mask_accepts,mask_pops);
      $fclose(fd); $finish;
    end
  end

  initial begin
    vl=8; void'($value$plusargs("VL=%d",vl));
    assert(vl inside {1,4,5,8,9,12,16}) else $fatal(1,"only authorized seven fault boundaries");
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"cycle,vl,broadcast,mmu_req,mmu_response,addr_ack,desc_valid,desc_ready,mask_valid,mask_accept,mask_first,mask_owner,ld_mask_valid,ld_mask_input_valid,ld_mask_first,ld_mask_pop,ld_ex_state,ld_issue_valid,ld_done,mask_commit,mask_done,ara_response,ara_idle,flush_eligible_model,running,spill_a,spill_b,mask_queue_count");
    ara_req='0; operands='0; operand_valid='0; mmu_valid=0; mmu_ex='0;
    cycle_no=0; accepted=0; mmu_returns=0; acks=0; descs=0;
    ld_dones=0; mask_dones=0; responses=0; mask_accepts=0; mask_pops=0; stable_rows=0;
    for(int l=0;l<4;l++) operand_count[l]=0;
    repeat(5) @(negedge clk);
    rst=1;
    @(negedge clk);
    ara_req.token=1; ara_req.op=VLSE; ara_req.vm=0; ara_req.vd=24; ara_req.use_vd=1;
    ara_req.scalar_op=64'h40001000; ara_req.stride=0; ara_req.vl=vlen_t'(vl);
    ara_req.vtype.vsew=EW64; ara_req.vtype.vlmul=LMUL_4; ara_req.emul=LMUL_4;
    ara_req.eew_vmask=EW8; ara_valid=1;
  end
  initial begin #2000; $fatal(1,"fixed 200-cycle watchdog"); end
endmodule
