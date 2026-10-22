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
  `AXI_TYPEDEF_R_CHAN_T(r_t, logic[127:0], id_t, user_t)
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

  vldu #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(128),.AxiAddrWidth(64),
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

  addrgen #(.NrLanes(4),.VLEN(1024),.AxiDataWidth(128),.AxiAddrWidth(64),
    .axi_ar_t(ar_t),.axi_aw_t(aw_t),.pe_req_t(pe_req_t),.pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg),.exception_t(exception_t)) ag (
    .clk_i(clk),.rst_ni(rst),.axi_ar_o(ar),.axi_ar_valid_o(ar_valid),.axi_ar_ready_i(axi_ar_ready),
    .axi_aw_o(aw),.axi_aw_valid_o(aw_valid),.axi_aw_ready_i(1'b1),
    .en_ld_st_translation_i(1'b0),.mmu_misaligned_ex_o(),.mmu_req_o(mmu_req),
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


  localparam logic[63:0] Base=64'h80010000;
  typedef struct {ar_t ar; int due;} read_t;
  read_t reads[$], dropped;
  int fd, pf, case_id, stride_bytes, start_elem, stop_elem, accepted, responses;
  int acks, ars, rs, pops, markers, dones, completes, written, done_cycle;
  int elapsed, early_count, fault_acks, first_wb, last_wb;
  bit submitted, baseline, expect_fault, unit_op;
  logic[63:0] scalar_base;
  vid_t owner;
  byte vrf[128];
  bit seen[128];

  function automatic byte pattern(logic[63:0] addr);
    return byte'(8'ha6 ^ (addr[7:0]*37));
  endfunction
  function automatic logic[63:0] source_addr(int elem);
    return scalar_base + 64'(elem*stride_bytes);
  endfunction
  function automatic bit wanted(int index);
    return index>=start_elem*8 && index<stop_elem*8;
  endfunction

  task automatic tick;
    axi_ar_ready=reads.size()<2;
    axi_r='0; axi_r_valid=0;
    if(reads.size()!=0 && cycle_no>=reads[0].due) begin
      axi_r_valid=1; axi_r.id=reads[0].ar.id; axi_r.last=1;
      for(int b=0;b<16;b++)
        axi_r.data[b*8+:8]=pattern((reads[0].ar.addr & ~64'd15)+b);
    end
    @(posedge clk);
    if(rst) begin
      $fdisplay(fd,"%0d,%0d,%0d,%b,%b,%0d,%b,%0d,%0d,%0d,%b,%b,%h,%0d,%0d,%b,%b,%b,%h,%b,%b,%b,%h,%0d,%0d,%b,%b,%0d,%b,%b,%b,%b,%0d,%0d,%0d,%0d,%0d,%b,%b,%h,%h,%h,%b,%b,%b,%b,%b,%b,%b,%0d",
        case_id,cycle_no,stride_bytes,broadcast_valid,ld_ready,pe_req.id,pe_req.vm,
        pe_req.vl,pe_req.vstart,pe_req.stride,ar_valid,axi_ar_ready,ar.addr,ar.len,ar.size,
        axi_r_valid,axi_r_ready,axi_r.last,axi_r.data,ag.axi_addrgen_queue_push,desc_valid,desc_ready,
        desc.addr,desc.len,desc.size,desc.is_exception,desc.is_skip,
        ag.axi_addrgen_state_q,addr_idle,ack,exception_out.valid,ara_resp_valid,
        ld.issue_cnt_bytes_q,ld.commit_cnt_bytes_q,ld.vrf_word_byte_cnt_q,
        ld.vrf_word_byte_pnt_q,ld.axi_r_byte_pnt_q,ld_result_req,result_gnt,
        ld_result_addr,ld_result_data,ld_result_be,result_final_gnt,
        load_complete,ld_resp.vinsn_done,ld_idle,ara_idle,early_ld,early_st,written);

      $fdisplay(pf,"%0d,%0d,%0d,%0d,%0d,%b,%b,%0d,%h,%0d,%b,%0d,%h,%0d,%h,%0d,%b,%0d,%b,%0d,%b,%b",
        case_id,cycle_no,ag.state_q,ag.axi_addrgen_q.len,ld.ldu_ex_state_q,
        ack,exception_out.valid,exception_out.cause,exception_out.tval,exception_start,
        ara_resp.exception.valid,ara_resp.exception.cause,ara_resp.exception.tval,
        ara_resp.exception_vstart,desc.vaddr,desc.elem_start,ld.vinsn_issue_valid,
        ld.vinsn_queue_q.commit_cnt,ag.axi_addrgen_queue_empty,
        ld.result_queue_cnt_q,ld_exception,running);
      if(broadcast_valid && ld_ready && !submitted) begin
        assert(pe_req.op==(unit_op ? VLE : VLSE) && pe_req.vm && pe_req.vl==2 &&
               pe_req.vstart==start_elem && pe_req.stride==64'(stride_bytes) &&
               pe_req.scalar_op==scalar_base && pe_req.vtype.vsew==EW64)
          else $fatal(1,"BAD_REQUEST");
        submitted=1; accepted++; owner=pe_req.id;
      end
      if(axi_r_valid && axi_r_ready) begin
        assert(reads.size()>0 && axi_r.last && axi_r.resp==0)
          else $fatal(1,"INVALID_RESPONSE");
        dropped=reads.pop_front(); rs++;
      end
      if(ar_valid && axi_ar_ready) begin
        read_t entry;
        assert(submitted && ars<(unit_op ? 1 : stop_elem-start_elem) &&
               ar.addr==source_addr(start_elem+(unit_op ? 0 : ars)) &&
               ar.len==0 && ar.size==(unit_op ? 4 : 3) && ar.burst==axi_pkg::BURST_INCR)
          else $fatal(1,"AR_GEOMETRY case=%0d addr=%h len=%0d size=%0d",case_id,ar.addr,ar.len,ar.size);
        entry.ar=ar; entry.due=cycle_no+2;
        reads.push_back(entry); ars++;
      end
      if(desc_valid && desc_ready) begin
        assert(desc.is_load && !desc.is_skip) else $fatal(1,"DESC_KIND");
        if(desc.is_exception) begin
          assert(case_id==1 && markers==0 && pops==1 && desc.vaddr==Base+4 &&
                 desc.elem_start==1 && !axi_r_ready)
            else $fatal(1,"ORDERED_MARKER");
          markers++;
        end else begin
          assert(pops<(unit_op ? 1 : stop_elem-start_elem) &&
                 desc.addr==source_addr(start_elem+(unit_op ? 0 : pops)) &&
                 desc.len==0 && desc.size==(unit_op ? 4 : 3) && axi_r_valid && axi_r_ready)
            else $fatal(1,"DESCRIPTOR_POP");
          pops++;
        end
      end
      for(int l=0;l<4;l++) if(result_final_gnt[l]) begin
        int index, word_index;
        assert(wb_out[l].id==owner) else $fatal(1,"WRONG_WRITE_OWNER");
        word_index=int'(wb_out[l].addr)-int'(vaddr(5'd24,4,1024));
        for(int b=0;b<8;b++) if(wb_out[l].be[b]) begin
          index=(word_index*4+l)*8+b;
          assert(index>=0 && index<128 && wanted(index) && !seen[index] &&
                 wb_out[l].data[b*8+:8]===pattern(source_addr(index/8)+index%8))
            else $fatal(1,"WRITE_ORACLE case=%0d lane=%0d byte=%0d index=%0d",case_id,l,b,index);
          vrf[index]=wb_out[l].data[b*8+:8]; seen[index]=1; written++;
          if(first_wb<0) first_wb=cycle_no;
          last_wb=cycle_no;
        end
      end
      if(ack) begin
        acks++;
        assert(exception_out.valid==expect_fault) else $fatal(1,"ACK_FAULT_QUALIFICATION");
        if(expect_fault) begin
          fault_acks++;
          assert(exception_out.cause==4 && exception_out.tval==Base+4 &&
                 exception_start==1 && early_ld==(case_id==3))
            else $fatal(1,"ACK_PRECISE_CONTEXT case=%0d cause=%0d tval=%h start=%0d early=%b",
                        case_id,exception_out.cause,exception_out.tval,exception_start,early_ld);
        end
      end
      if(early_ld) begin
        early_count++;
        assert(case_id==3 && ack && exception_out.valid) else $fatal(1,"DUP_EARLY_ERROR");
      end
      if(ara_resp_valid) begin
        responses++;
        assert(ara_resp.exception.valid==expect_fault) else $fatal(1,"RESP_FAULT_QUALIFICATION");
        if(expect_fault)
          assert(ara_resp.exception.cause==4 && ara_resp.exception.tval==Base+4 &&
                 ara_resp.exception_vstart==1 && written==(stop_elem-start_elem)*8 &&
                 !ara_resp.fof_exception)
            else $fatal(1,"RESP_CONTEXT_OR_PREFIX");
      end
      if(load_complete) completes++;
      if(submitted && ld_resp.vinsn_done[owner]) begin
        dones++; done_cycle=cycle_no;
        assert(written==(stop_elem-start_elem)*8 && !(|bank_valid))
          else $fatal(1,"DONE_BEFORE_WRITE");
      end
      assert(!early_st && !aw_valid && !mmu_req && mask_valid==0 && ld_mask_valid==0)
        else $fatal(1,"UNEXPECTED_PATH");
    end
    #1; @(negedge clk); cycle_no++;
  endtask

  initial begin
    baseline=$test$plusargs("BASELINE_NORMALS");
    fd=$fopen("cycles.csv","w");
    $fdisplay(fd,"case,cycle,stride,broadcast,ld_ready,owner,vm,vl,vstart,pe_stride,ar_valid,ar_ready,ar_addr,ar_len,ar_size,r_valid,r_ready,r_last,r_data,desc_push,desc_valid,desc_pop,desc_addr,desc_len,desc_size,desc_exception,desc_skip,ag_axi_state,ag_idle,ack,exception,response,issue_bytes,commit_bytes,vrf_count,vrf_ptr,r_ptr,result_req,result_gnt,result_addr,result_data,result_be,final_gnt,load_complete,done,ld_idle,global_idle,early_ld,early_st,written");
    pf=$fopen("context.csv","w");
    $fdisplay(pf,"case,cycle,ag_state,ag_len,ld_ex_state,ack,exception,cause,tval,exception_start,resp_exception,resp_cause,resp_tval,resp_start,desc_vaddr,desc_elem,issue_valid,commit_count,desc_empty,result_count,ld_exception,running");
    for(case_id=(baseline ? 4 : 0);case_id<7;case_id++) begin
      rst=0; ara_valid=0; ara_req='0; cycle_no=0; release_cycle=0;
      flush=0; operands='0; operand_valid='0; mmu_valid=0; mmu_pa=0; mmu_ex='0;
      reads.delete(); accepted=0; responses=0; acks=0; ars=0; rs=0; pops=0; markers=0;
      dones=0; completes=0; written=0; submitted=0; owner=0; done_cycle=-1;
      early_count=0; fault_acks=0; first_wb=-1; last_wb=-1;
      scalar_base=Base; stride_bytes=8; start_elem=0; stop_elem=2;
      expect_fault=(case_id==1 || case_id==3); unit_op=(case_id==4);
      case(case_id)
        1: begin stride_bytes=4; stop_elem=1; end
        2: begin stride_bytes=4; start_elem=1; scalar_base=Base-4; end
        3: begin stride_bytes=4; start_elem=1; stop_elem=1; end
        5: stride_bytes=0;
        6: begin stride_bytes=-8; scalar_base=Base+8; end
        default: ;
      endcase
      for(int b=0;b<128;b++) begin vrf[b]=8'h5b; seen[b]=0; end
      repeat(5) tick(); rst=1; tick();
      ara_req='0; ara_req.token=1; ara_req.op=unit_op ? VLE : VLSE; ara_req.vm=1;
      ara_req.vd=24; ara_req.use_vd=1; ara_req.scalar_op=scalar_base;
      ara_req.stride=64'(stride_bytes); ara_req.vl=2; ara_req.vstart=vlen_t'(start_elem);
      ara_req.vtype.vsew=EW64; ara_req.vtype.vlmul=LMUL_1;
      ara_req.emul=LMUL_1; ara_req.eew_vmask=EW8; ara_valid=1;
      for(elapsed=0;elapsed<250;elapsed++) begin
        tick();
        if(responses) ara_valid=0;
      end
      assert(accepted==1 && responses==1 && acks==1 && reads.size()==0 &&
             ars==(unit_op ? 1 : stop_elem-start_elem) && rs==ars && pops==ars &&
             markers==int'(case_id==1) && early_count==int'(case_id==3) &&
             fault_acks==int'(expect_fault))
        else $fatal(1,"COUNTS case=%0d accepted=%0d resp=%0d ack=%0d AR=%0d R=%0d pop=%0d marker=%0d early=%0d",
                    case_id,accepted,responses,acks,ars,rs,pops,markers,early_count);
      assert(dones==1 && completes==1 && ara_idle && ld_idle && addr_idle &&
             written==(stop_elem-start_elem)*8 &&
             ld.issue_cnt_bytes_q==0 && ld.commit_cnt_bytes_q==0 &&
             ld.vrf_word_byte_cnt_q==0 && ld_result_req==0 && bank_valid==0)
        else $fatal(1,"TERMINAL_NOT_COMPLETE case=%0d done=%0d idle=%b/%b/%b issue=%0d commit=%0d",
                    case_id,dones,ara_idle,ld_idle,addr_idle,ld.issue_cnt_bytes_q,ld.commit_cnt_bytes_q);
      for(int b=0;b<128;b++)
        assert(seen[b]==wanted(b) &&
               vrf[b]===(wanted(b) ? pattern(source_addr(b/8)+b%8) : 8'h5b))
          else $fatal(1,"FULL_DEST_ORACLE case=%0d byte=%0d",case_id,b);
      $display("CASE_PASS case=%0d stride=%0d start=%0d fault=%b AR=%0d R=%0d normal_pop=%0d marker=%0d bytes=%0d first_wb=%0d last_wb=%0d done=%0d idle=1",
        case_id,stride_bytes,start_elem,expect_fault,ars,rs,pops,markers,written,first_wb,last_wb,done_cycle);
    end
    $display("M9_LOCAL_ACCEPTANCE_COMPLETE cases=%0d",baseline ? 3 : 7);
    $fclose(fd); $fclose(pf); $finish;
  end
  initial begin #20000; $fatal(1,"FIXED_BATCH_WATCHDOG_2000_CLOCKS"); end
endmodule

