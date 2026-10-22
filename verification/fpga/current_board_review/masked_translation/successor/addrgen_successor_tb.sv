module addrgen_successor_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [10:0] vlen_t;
  typedef logic [63:0] address_t;
  typedef logic [3:0] id_t;
  typedef logic user_t;
  `include "ara/ara_typedef.svh"
  `include "ara/intf_typedef.svh"
  `include "axi/typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cfg)
  `AXI_TYPEDEF_AR_CHAN_T(ar_t, address_t, id_t, user_t)
  `AXI_TYPEDEF_AW_CHAN_T(aw_t, address_t, id_t, user_t)

  bit clk=0;
  always #5 clk=~clk;
  logic rst, req_valid, translation, axi_ready, desc_ready;
  pe_req_t req;
  logic [7:0] running;
  logic [3:0][7:0] mask_word;
  logic [3:0] mask_valid;
  vid_t mask_owner;
  vlen_t mask_first;
  elen_t [3:0] indices;
  logic [3:0] index_valid, index_ready;
  logic mmu_req, mmu_valid, mmu_store, ack, fof, illegal_load, illegal_store, idle;
  logic [Cfg.VLEN-1:0] mmu_va;
  logic [Cfg.PLEN-1:0] mmu_pa;
  exception_t mmu_ex, ex;
  vlen_t ex_start;
  ar_t ar;
  aw_t aw;
  logic ar_valid, aw_valid, desc_valid;
  addrgen_axi_req_t desc;
  int variant, cycle, pattern, nvl, start, sew, bytes_per_element, window_elements;
  int fault_index, fault_at, fault_cause, expected_desc, expected_bus, expected_mmu;
  int pops, buses, requests, responses, acks, consumed, window_since, window_base;
  int req_cycle, due, ack_cycle, index_pops;
  bit store_op, strided, indexed, burst, delayed_mask, pressure, fault_first;
  bit pending, pending_fault;
  address_t base, step, pending_va;
  address_t exp_addr[128], bus_addr[128], translation_addr[128];
  int exp_kind[128], exp_element[128], exp_size[128], exp_len[128];
  int bus_size[128], bus_len[128], translation_element[128];
  string name;

  addrgen #(.NrLanes(4), .VLEN(1024), .AxiDataWidth(256), .AxiAddrWidth(64),
    .axi_ar_t(ar_t), .axi_aw_t(aw_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .CVA6Cfg(Cfg), .exception_t(exception_t)) dut (
    .clk_i(clk), .rst_ni(rst), .axi_ar_o(ar), .axi_ar_valid_o(ar_valid), .axi_ar_ready_i(axi_ready),
    .axi_aw_o(aw), .axi_aw_valid_o(aw_valid), .axi_aw_ready_i(axi_ready),
    .en_ld_st_translation_i(translation), .mmu_misaligned_ex_o(),
    .mmu_req_o(mmu_req), .mmu_vaddr_o(mmu_va), .mmu_is_store_o(mmu_store),
    .mmu_dtlb_hit_i(1'b0), .mmu_dtlb_ppn_i('0), .mmu_valid_i(mmu_valid),
    .mmu_paddr_i(mmu_pa), .mmu_exception_i(mmu_ex), .core_st_pending_i(1'b0),
    .pe_req_i(req), .pe_req_valid_i(req_valid), .pe_vinsn_running_i(running),
    .addrgen_exception_o(ex), .addrgen_ack_o(ack), .addrgen_exception_vstart_o(ex_start),
    .addrgen_fof_exception_o(fof), .addrgen_illegal_load_o(illegal_load),
    .addrgen_illegal_store_o(illegal_store), .axi_addrgen_req_o(desc),
    .axi_addrgen_req_valid_o(desc_valid),
    .ldu_axi_addrgen_req_ready_i(desc_valid && desc_ready && !store_op),
    .stu_axi_addrgen_req_ready_i(desc_valid && desc_ready && store_op),
    .ldu_mask_word_i(mask_word), .ldu_mask_word_valid_i(mask_valid),
    .ldu_mask_owner_id_i(mask_owner), .ldu_mask_first_element_i(mask_first),
    .stu_mask_word_i(mask_word), .stu_mask_word_valid_i(mask_valid),
    .stu_mask_owner_id_i(mask_owner), .stu_mask_first_element_i(mask_first),
    .addrgen_operand_i(indices), .addrgen_operand_valid_i(index_valid),
    .addrgen_operand_ready_o(index_ready), .lsu_ex_flush_i(1'b0), .idle_o(idle));

  function automatic bit active(int i);
    case(pattern)
      0: return 0;
      1: return 1;
      2: return i%3==1;
      3: return i==0;
      4: return i==3;
      default: return i%2==0;
    endcase
  endfunction
  // Lane-local subelements are bit-reversed (Ara shuffle contract), not linear.
  // Derive that permutation independently rather than using shuffle_index.
  function automatic int physical_byte(int b, int e);
    int slot, reversed;
    slot=b/(4*e); reversed=0;
    for(int width=8/e;width>1;width=width/2) begin
      reversed=(reversed<<1)|(slot&1); slot=slot>>1;
    end
    return ((b/e)%4)*8+reversed*e+(b%e);
  endfunction
  function automatic address_t va_for(int i);
    return base + address_t'(i)*(indexed ? 64'd4 : step);
  endfunction
  function automatic address_t pa_for(address_t va);
    return translation ? va+64'h40000000 : va;
  endfunction

  task automatic configure;
    name="alloff_fault"; pattern=0; translation=1; nvl=8; start=0; sew=1;
    fault_index=0; base=64'h40001000; step=2;
    store_op=0; strided=0; indexed=0; burst=0; delayed_mask=0; pressure=0; fault_first=0;
    case(variant)
      0: ;
      1: begin name="active_fault"; pattern=3; end
      2: begin name="sparse_multiword"; pattern=2; nvl=35; fault_index=-1; end
      3: begin name="vstart15_sparse"; pattern=2; start=15; nvl=35; fault_index=-1; end
      4: begin name="alloff_vm_disabled"; translation=0; end
      5: begin name="sparse_vm_disabled"; translation=0; pattern=2; fault_index=-1; end
      6: begin name="store_sparse"; store_op=1; pattern=2; fault_index=-1; end
      7: begin name="store_alloff"; store_op=1; end
      8: begin name="store_active_fault"; store_op=1; pattern=4; fault_index=3; end
      9: begin name="positive_stride"; strided=1; step=6; pattern=2; fault_index=-1; end
      10: begin name="negative_stride"; strided=1; step=-64'd6; pattern=2; fault_index=-1; end
      11: begin name="zero_stride"; strided=1; step=0; pattern=2; fault_index=-1; end
      12: begin name="odd_alloff"; base++; end
      13: begin name="odd_alloff_vm_disabled"; base++; translation=0; end
      14: begin name="odd_active_after_skips"; base++; pattern=4; fault_index=-1; end
      15: begin name="odd_active_vm_disabled"; base++; pattern=4; fault_index=-1; translation=0; end
      16: begin name="fof_first_fault"; fault_first=1; pattern=3; end
      17: begin name="fof_after_skips"; fault_first=1; pattern=4; fault_index=3; end
      18: begin name="fof_alloff"; fault_first=1; end
      19: begin name="backpressure_allon"; pattern=1; nvl=49; pressure=1; fault_index=-1; end
      20: begin name="delayed_owner_window"; pattern=2; nvl=50; start=17; delayed_mask=1; pressure=1; fault_index=-1; end
      21: begin name="unmasked_burst"; burst=1; pattern=1; fault_index=-1; end
      22: begin name="unmasked_burst_vm_disabled"; burst=1; pattern=1; fault_index=-1; translation=0; end
      23: begin name="indexed_sparse_control"; indexed=1; pattern=2; fault_index=-1; end
      24: begin name="indexed_alloff_control"; indexed=1; end
      25: begin name="indexed_vstart_control"; indexed=1; pattern=2; start=3; fault_index=-1; end
      26: begin name="e8_window_boundary"; sew=0; step=1; pattern=2; start=31; nvl=65; fault_index=-1; end
      27: begin name="e32_window_boundary"; sew=2; step=4; pattern=2; start=7; nvl=25; fault_index=-1; end
      28: begin name="e64_window_boundary"; sew=3; step=8; pattern=2; start=3; nvl=13; fault_index=-1; end
      29: begin name="store_negative_vstart"; store_op=1; strided=1; step=-64'd6; pattern=2; start=3; nvl=19; fault_index=-1; end
      30: begin name="store_odd_after_skips"; store_op=1; base++; pattern=4; fault_index=-1; end
      31: begin name="fof_odd_after_skips"; base++; pattern=4; fault_first=1; fault_index=-1; end
      default: $fatal(1,"unknown CASE");
    endcase
    bytes_per_element=1<<sew; window_elements=32/bytes_per_element;
  endtask

  task automatic make_oracle;
    address_t va;
    int kind;
    expected_desc=0; expected_bus=0; expected_mmu=0; fault_at=-1; fault_cause=0;
    for(int i=start;i<nvl;i++) begin
      va=va_for(i); kind=active(i)?0:1;
      if(active(i) && va%bytes_per_element!=0) begin
        kind=2; fault_at=i; fault_cause=store_op?6:4;
      end else if(active(i) && translation && i==fault_index) begin
        kind=2; fault_at=i; fault_cause=store_op?15:13;
      end
      exp_kind[expected_desc]=kind; exp_element[expected_desc]=i;
      exp_addr[expected_desc]=kind==0?pa_for(va):0;
      exp_size[expected_desc]=burst?5:sew;
      exp_len[expected_desc]=0;
      expected_desc++;
      if(active(i) && translation && va%bytes_per_element==0) begin
        translation_addr[expected_mmu]=va; translation_element[expected_mmu]=i;
        expected_mmu++;
      end
      if(kind==0) begin
        bus_addr[expected_bus]=pa_for(va); bus_size[expected_bus]=burst?5:sew;
        bus_len[expected_bus]=0; expected_bus++;
      end
      if(kind==2 || burst) break;
    end
  endtask

  // MMU and consumer are models. Window advancement follows accepted descriptor
  // bytes, not AddrGen internal counters, and never anticipates a future word.
  always @(negedge clk) if(rst) begin
    mmu_valid=pending && cycle+1==due;
    mmu_ex='0; mmu_pa='0;
    if(mmu_valid) begin
      mmu_pa=pa_for(pending_va);
      if(pending_fault) begin
        mmu_ex.valid=1; mmu_ex.cause=store_op?15:13; mmu_ex.tval=pending_va;
      end
    end
    axi_ready=!pressure || pending || cycle%5!=0;
    desc_ready=!pressure || (cycle>=18 && cycle%4==0);
    mask_first=vlen_t'(window_base); mask_owner=vid_t'(3); mask_valid='0; mask_word='0;
    for(int b=0;b<32;b++) begin
      automatic int p=physical_byte(b,bytes_per_element);
      mask_word[p/8][p%8]=active(window_base+b/bytes_per_element);
    end
    for(int l=0;l<4;l++) mask_valid[l]=(window_base+l<nvl);
    if(delayed_mask && cycle-window_since<3) mask_valid='0;
    if(delayed_mask && cycle-window_since>=3 && cycle-window_since<6) mask_owner=vid_t'(2);
    if(indexed && index_pops!=0) index_valid='0;
    if(acks==1 && pops==expected_desc && !pending) running='0;
  end

  always @(posedge clk) if(rst) begin
    cycle++;
    assert(!$isunknown({mmu_req,ack,ex.valid,ar_valid,aw_valid,desc_valid,idle}))
      else $fatal(1,"unknown public control");
    assert(!illegal_load && !illegal_store) else $fatal(1,"duplicate/early illegal sideband");
    if(mmu_req) begin
      if(!pending) begin
        assert(requests<expected_mmu && mmu_va==translation_addr[requests] && mmu_store==store_op)
          else $fatal(1,"unexpected MMU req n=%0d va=%h expected_n=%0d expected_va=%h",requests,mmu_va,expected_mmu,translation_addr[requests]);
        if(!burst) assert(mask_owner==3 && |mask_valid)
          else $fatal(1,"request before valid owned mask");
        pending=1; pending_va=mmu_va; pending_fault=translation_element[requests]==fault_index;
        req_cycle=cycle; due=cycle+3; requests++;
        $display("MMU cycle=%0d va=%h store=%0b",cycle,mmu_va,mmu_store);
      end else assert(mmu_va==pending_va) else $fatal(1,"MMU address changed in flight");
    end
    if(mmu_valid) begin
      assert(pending && cycle==due) else $fatal(1,"unbound MMU response");
      responses++; pending=0;
    end
    if(ar_valid || aw_valid) begin
      assert(axi_ready && buses<expected_bus && ar_valid==!store_op && aw_valid==store_op)
        else $fatal(1,"unexpected AXI access");
      assert((store_op?aw.addr:ar.addr)==bus_addr[buses] &&
             (store_op?aw.size:ar.size)==bus_size[buses] &&
             (store_op?aw.len:ar.len)==bus_len[buses])
        else $fatal(1,"wrong AXI geometry n=%0d addr=%h expected=%h",buses,store_op?aw.addr:ar.addr,bus_addr[buses]);
      $display("AXI cycle=%0d n=%0d addr=%h size=%0d len=%0d",cycle,buses,store_op?aw.addr:ar.addr,store_op?aw.size:ar.size,store_op?aw.len:ar.len);
      buses++;
    end
    if(desc_valid && desc_ready) begin
      assert(pops<expected_desc && desc.is_load==!store_op &&
        desc.is_skip==(exp_kind[pops]==1) && desc.is_exception==(exp_kind[pops]==2))
        else $fatal(1,"descriptor kind/order n=%0d got_skip=%b got_ex=%b expected_kind=%0d",pops,desc.is_skip,desc.is_exception,exp_kind[pops]);
      assert(desc.size==exp_size[pops] && desc.len==exp_len[pops]) else $fatal(1,"descriptor size/len");
      if(!desc.is_exception) assert(desc.addr==exp_addr[pops]) else $fatal(1,"descriptor address");
      if(!desc.is_exception && !desc.is_skip) assert(desc.vaddr==va_for(exp_element[pops]) && desc.elem_start==exp_element[pops])
        else $fatal(1,"descriptor fault-attribution metadata");
      $display("DESC cycle=%0d n=%0d element=%0d skip=%b ex=%b addr=%h",cycle,pops,exp_element[pops],desc.is_skip,desc.is_exception,desc.addr);
      if(exp_kind[pops]!=2) consumed=burst?nvl:exp_element[pops]+1;
      pops++;
      if(consumed/window_elements*window_elements!=window_base && consumed<nvl) begin
        window_base=consumed/window_elements*window_elements; window_since=cycle;
      end
    end
    if(indexed && |(index_valid & index_ready)) index_pops++;
    if(ack) begin
      acks++; ack_cycle=cycle;
      assert(acks==1 && ex.valid==(fault_at>=0)) else $fatal(1,"ack exception/count mismatch");
      if(fault_at>=0) assert(ex.cause==fault_cause && ex.tval==va_for(fault_at) && ex_start==fault_at)
        else $fatal(1,"fault attribution cause=%0d tval=%h start=%0d expected=%0d/%h/%0d",ex.cause,ex.tval,ex_start,fault_cause,va_for(fault_at),fault_at);
      assert(fof==(fault_first && fault_at>0)) else $fatal(1,"FOF classification");
      $display("ACK cycle=%0d ex=%b cause=%0d start=%0d fof=%b",cycle,ex.valid,ex.cause,ex_start,fof);
    end
    assert(cycle<1500) else $fatal(1,"timeout requests=%0d pops=%0d/%0d ack=%0d idle=%b",requests,pops,expected_desc,acks,idle);
  end

  task automatic run_case(int selected);
    rst=0; req_valid=0; req='0; running='0; mask_word='0; mask_valid='0;
    mask_owner=3; mask_first=0; indices='0; index_valid='0;
    mmu_valid=0; mmu_pa='0; mmu_ex='0; pending=0; axi_ready=1; desc_ready=1;
    cycle=0; pops=0; buses=0; requests=0; responses=0; acks=0; index_pops=0;
    variant=selected;
    configure(); make_oracle(); consumed=start; window_base=start/window_elements*window_elements; window_since=0;
    $display("CONFIG case=%0d name=%s masked=%0b translation=%0b sew=%0d vl=%0d start=%0d base=%h stride=%h expected_desc=%0d bus=%0d mmu=%0d",variant,name,!burst,translation,8<<sew,nvl,start,base,step,expected_desc,expected_bus,expected_mmu);
    repeat(4) @(negedge clk);
    req.id=3; req.vm=burst; req.vl=nvl; req.vstart=start; req.vtype.vsew=vew_e'(sew);
    req.vtype.vlmul=LMUL_1; req.emul=LMUL_1; req.scalar_op=base; req.stride=step;
    req.op=indexed?(store_op?VSXE:VLXE):strided?(store_op?VSSE:VLSE):(store_op?VSE:VLE);
    req.vfu=store_op?VFU_StoreUnit:VFU_LoadUnit; req.vd=24; req.use_vd=!store_op;
    req.vs1=8; req.use_vs1=store_op; req.vs2=16; req.use_vs2=indexed;
    req.eew_vs2=EW16; req.old_eew_vs2=EW16; req.fault_only_first=fault_first;
    if(indexed) begin
      for(int i=0;i<16;i++) begin
        automatic int p=physical_byte(i*2,2);
        indices[p/8][(p%8)*8+:16]=16'(i*4);
      end
      index_valid='1;
    end
    running[3]=1; rst=1;
    @(negedge clk); req_valid=1;
    @(negedge clk); req_valid=0;
    while(acks!=1 || pops!=expected_desc || !idle) @(negedge clk);
    repeat(4) @(negedge clk);
    assert(buses==expected_bus && requests==expected_mmu && responses==expected_mmu && acks==1)
      else $fatal(1,"final counts");
    if(indexed) assert(index_pops==1) else $fatal(1,"index operand consumption");
    $display("LOCAL_PASS case=%0d name=%s descriptors=%0d axi=%0d translations=%0d ack_cycle=%0d cycles=%0d consumer_real=0",variant,name,pops,buses,requests,ack_cycle,cycle);
    rst=0;
  endtask

  initial begin
    int count, selected;
    count=1;
    if($value$plusargs("COUNT=%d",count)) begin
      for(int n=0;n<count;n++) begin
        assert($value$plusargs($sformatf("CASE%0d=%%d",n),selected)) else $fatal(1,"missing case selection");
        run_case(selected);
      end
    end else begin
      selected=0; void'($value$plusargs("CASE=%d",selected));
      run_case(selected);
    end
    $display("SUITE_COMPLETE cases=%0d",count);
    $finish;
  end
endmodule
