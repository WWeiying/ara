`timescale 1ns/1ps
`include "axi/typedef.svh"
`include "cheshire/typedef.svh"
`include "ara/intf_typedef.svh"
`include "rvfi_types.svh"

// Full scalar/vector pipelines, but controlled RAM latency and reset state.
// This is NOT a replay of the board's historical timing or cache contents.
module loader_cpu_chain_tb;
  import cheshire_pkg::*;
  `include "loader_board_cfg.svh"
  localparam cheshire_cfg_t Cfg=board_cfg();
  localparam config_pkg::cva6_cfg_t Cva6Cfg=build_config_pkg::build_config(gen_cva6_cfg(Cfg));
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cva6Cfg)
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, Cva6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, Cva6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_MMU_REQ(acc_mmu_req_t, Cva6Cfg)
  `CVA6_INTF_TYPEDEF_MMU_RESP(acc_mmu_resp_t, Cva6Cfg, exception_t)
  `CVA6_INTF_TYPEDEF_CVA6_TO_ACC(cva6_to_acc_t, accelerator_req_t, acc_mmu_resp_t)
  `CVA6_INTF_TYPEDEF_ACC_TO_CVA6(acc_to_cva6_t, accelerator_resp_t, acc_mmu_req_t)
  typedef logic[Cfg.AddrWidth-1:0] address_t;
  typedef logic[3:0] core_id_t;
  typedef logic[Cfg.AxiMstIdWidth-1:0] vector_id_t;
  typedef logic[63:0] core_data_t;
  typedef logic[7:0] core_strb_t;
  typedef logic[127:0] vector_data_t;
  typedef logic[15:0] vector_strb_t;
  typedef logic[Cfg.AxiUserWidth-1:0] user_t;
  `AXI_TYPEDEF_ALL(core_axi,address_t,core_id_t,core_data_t,core_strb_t,user_t)
  `AXI_TYPEDEF_ALL(vector_axi,address_t,vector_id_t,vector_data_t,vector_strb_t,user_t)
  typedef `RVFI_PROBES_INSTR_T(Cva6Cfg) probe_instr_t;
  typedef `RVFI_PROBES_CSR_T(Cva6Cfg) probe_csr_t;
  typedef struct packed { probe_csr_t csr; probe_instr_t instr; } probe_t;
  logic clk=0,rst=0;
  always #10 clk=~clk;
  cva6_to_acc_t acc_req;
  acc_to_cva6_t acc_resp,acc_pack;
  core_axi_req_t req;
  core_axi_resp_t rsp;
  vector_axi_req_t vreq,vout;
  vector_axi_resp_t vrsp,vdown;
  probe_t probes;
  wire inval,root_last;
  wire [47:0] inval_addr;
  logic [63:0] root_line,target_pc,entry_pc;
  int collision=0,aw_count=0,collisions=0,cycle=0,retired=0;
  logic [63:0] last_pc=0;
  logic armed=0;
  logic overlap_seen=0;
  int trace_start=-1;
  typedef struct packed {
    logic clk,rst,inval,rvalid,rready,rlast,capture,metadata_pop,mshr;
    logic ptw_request,ptw_reply,fetch_request,fetch_valid;
    logic [31:0] cycle;
    logic [63:0] last_pc,rdata,vaw_addr,fetch_va;
  } trace_t;
  trace_t trace;
  always_comb begin
    trace.clk=clk; trace.rst=rst; trace.cycle=cycle; trace.last_pc=last_pc;
    trace.inval=inval; trace.rvalid=rsp.r_valid; trace.rready=req.r_ready;
    trace.rlast=rsp.r.last; trace.rdata=rsp.r.data; trace.vaw_addr=vreq.aw.addr;
    trace.capture=cpu.gen_cache_wt.i_cache_subsystem.i_adapter.dcache_rtrn_rd_en;
    trace.metadata_pop=cpu.gen_cache_wt.i_cache_subsystem.i_adapter.dcache_rd_pop;
    trace.mshr=cpu.gen_cache_wt.i_cache_subsystem.i_wt_dcache.i_wt_dcache_missunit.mshr_vld_q;
    trace.ptw_request=cpu.dcache_req_to_cache[0].data_req;
    trace.ptw_reply=cpu.dcache_req_from_cache[0].data_rvalid;
    trace.fetch_request=cpu.icache_areq_cache_ex.fetch_req;
    trace.fetch_va=cpu.icache_areq_cache_ex.fetch_vaddr;
    trace.fetch_valid=cpu.icache_areq_ex_cache.fetch_valid;
  end
`ifdef LOADER_FSDB
  initial begin
    string wave;
    if(!$value$plusargs("wave=%s",wave)) $fatal(1,"Missing waveform path");
    $fsdbDumpfile(wave);
    $fsdbDumpvars(0,loader_cpu_chain_tb.trace);
    $fsdbDumpoff;
  end
`endif
  wire hold_aw=collision && aw_count==3 && !root_last;
  wire hold_read=collision && aw_count<4 && root_last && !(aw_count==3 && vreq.aw_valid);
  always_comb begin
    acc_pack=acc_resp;
    acc_pack.acc_resp.inval_valid=inval;
    acc_pack.acc_resp.inval_addr=inval_addr;
  end
  cva6 #(.CVA6Cfg(Cva6Cfg),.axi_ar_chan_t(core_axi_ar_chan_t),
    .axi_aw_chan_t(core_axi_aw_chan_t),.axi_w_chan_t(core_axi_w_chan_t),
    .b_chan_t(core_axi_b_chan_t),.r_chan_t(core_axi_r_chan_t),
    .cvxif_req_t(cva6_to_acc_t),.cvxif_resp_t(acc_to_cva6_t),
    .noc_req_t(core_axi_req_t),.noc_resp_t(core_axi_resp_t),
    .accelerator_req_t(accelerator_req_t),.accelerator_resp_t(accelerator_resp_t),
    .acc_mmu_req_t(acc_mmu_req_t),.acc_mmu_resp_t(acc_mmu_resp_t)) cpu (
    .clk_i(clk),.rst_ni(rst),.boot_addr_i(64'h80000000),.hart_id_i(64'b0),
    .irq_i(2'b0),.ipi_i(1'b0),.time_irq_i(1'b0),.debug_req_i(1'b0),
    .clic_irq_valid_i(1'b0),.clic_irq_id_i('0),.clic_irq_level_i('0),
    .clic_irq_priv_i(riscv::PRIV_LVL_M),.clic_irq_v_i(1'b0),.clic_irq_vsid_i('0),
    .clic_irq_shv_i(1'b0),.clic_kill_req_i(1'b0),
    .rvfi_probes_o(probes),.cvxif_req_o(acc_req),.cvxif_resp_i(acc_pack),
    .noc_req_o(req),.noc_resp_i(rsp));
  ara #(.NrLanes(4),.VLEN(1024),.OSSupport(1),.CVA6Cfg(Cva6Cfg),
    .exception_t(exception_t),.accelerator_req_t(accelerator_req_t),
    .accelerator_resp_t(accelerator_resp_t),.acc_mmu_req_t(acc_mmu_req_t),
    .acc_mmu_resp_t(acc_mmu_resp_t),.cva6_to_acc_t(cva6_to_acc_t),.acc_to_cva6_t(acc_to_cva6_t),
    .AxiDataWidth(128),.AxiAddrWidth(48),.axi_ar_t(vector_axi_ar_chan_t),
    .axi_r_t(vector_axi_r_chan_t),.axi_aw_t(vector_axi_aw_chan_t),
    .axi_w_t(vector_axi_w_chan_t),.axi_b_t(vector_axi_b_chan_t),
    .axi_req_t(vector_axi_req_t),.axi_resp_t(vector_axi_resp_t)) vector_cpu (
    .clk_i(clk),.rst_ni(rst),.scan_enable_i(1'b0),.scan_data_i(1'b0),
    .acc_req_i(acc_req),.acc_resp_o(acc_resp),.axi_req_o(vreq),.axi_resp_i(vrsp));
  axi_inval_filter #(.MaxTxns(4),.AddrWidth(48),.L1LineWidth(Cva6Cfg.DCACHE_LINE_WIDTH/8),
    .aw_chan_t(vector_axi_aw_chan_t),.req_t(vector_axi_req_t),.resp_t(vector_axi_resp_t)) filter (
    .clk_i(clk),.rst_ni(rst),.en_i(acc_req.acc_req.acc_cons_en),
    .slv_req_i(vreq),.slv_resp_o(vrsp),.mst_req_o(vout),.mst_resp_i(vdown),
    .inval_addr_o(inval_addr),.inval_valid_o(inval),.inval_ready_i(acc_req.acc_req.inval_ready));
  loader_cpu_memory #(.Width(64),.req_t(core_axi_req_t),.rsp_t(core_axi_resp_t)) core_memory (
    .clk(clk),.rst(rst),.req(req),.rsp(rsp),.hold_aw(1'b0),.hold_read(hold_read),
    .root_line(root_line),.armed(armed),.root_last(root_last));
  loader_cpu_memory #(.Width(128),.req_t(vector_axi_req_t),.rsp_t(vector_axi_resp_t)) vector_memory (
    .clk(clk),.rst(rst),.req(vout),.rsp(vdown),.hold_aw(hold_aw),.hold_read(1'b0),
    .root_line(root_line),.armed(1'b0),.root_last());

  bit[7:0] memory[longint unsigned];
  function automatic bit[7:0] read_byte(input longint unsigned address);
    return memory.exists(address) ? memory[address] : 0;
  endfunction
  task automatic write_byte(input longint unsigned address,input bit[7:0] value);
    memory[address]=value;
  endtask
  initial begin : setup
    string path;
    longint unsigned addr;
    int value,fd,n;
    if(!$value$plusargs("memory=%s",path)) $fatal(1,"Missing memory fixture");
    if(!$value$plusargs("entry=%h",entry_pc)) $fatal(1,"Missing entry");
    if(!$value$plusargs("target=%h",target_pc)) $fatal(1,"Missing target");
    if(!$value$plusargs("root=%h",root_line)) $fatal(1,"Missing root");
    if($value$plusargs("collision=%d",collision)) begin end
    fd=$fopen(path,"r");
    if(!fd) $fatal(1,"Cannot open fixture");
    while(!$feof(fd)) begin
      n=$fscanf(fd,"%h %h\n",addr,value);
      if(n==2) memory[addr]=value[7:0];
      else if(n!=-1) $fatal(1,"Malformed memory fixture");
    end
    $fclose(fd);
    $display("CONTROLLED_INITIAL_STATE cold_caches zero_args collision=%0d entry=%h target=%h",collision,entry_pc,target_pc);
    #220; @(negedge clk); rst=1;
  end
  always @(posedge clk) if(rst) begin
    cycle++;
    if(vreq.aw_valid && vrsp.aw_ready) begin
      armed<=1; aw_count++;
      $display("VECTOR_AW cycle=%0d addr=%h len=%0d size=%0d inval=%b",cycle,vreq.aw.addr,vreq.aw.len,vreq.aw.size,inval);
    end
    if(inval && rsp.r_valid && req.r_ready && rsp.r.id[0]) begin
      collisions++;
      $display("COLLISION cycle=%0d last=%b rdata=%h inval_addr=%h capture=%b pop=%b",
        cycle,rsp.r.last,rsp.r.data,inval_addr,trace.capture,trace.metadata_pop);
    end
    if(collision && root_last && inval && rsp.r_valid) overlap_seen=1;
    for(int p=0;p<Cva6Cfg.NrCommitPorts;p++)
      if(probes.instr.commit_ack[p] && !probes.instr.commit_drop[p]) begin
        retired++; last_pc=64'($signed(probes.instr.commit_instr_pc[p]));
        $display("RETIRE cycle=%0d pc=%h",cycle,last_pc);
        if(last_pc==entry_pc) begin
          trace_start=cycle;
`ifdef LOADER_FSDB
          $fsdbDumpon;
`endif
        end
        if(last_pc==target_pc) begin
          if(collision && !overlap_seen) $fatal(1,"Controlled overlap did not occur");
          $display("LOADER_CPU_REACHED_TARGET cycles=%0d aw=%0d collisions=%0d",cycle,aw_count,collisions);
          $finish;
        end
      end
    if(probes.instr.ex_commit_valid) begin
      $display("CPU_TRAP cycle=%0d cause=%h tval=%h",cycle,probes.instr.ex_commit_cause,probes.instr.tval);
      $fatal(1,"Unexpected exception");
    end
    if(cycle==20000) begin
      $display("LOADER_CPU_BOUNDED_STOP retired=%0d last_pc=%h aw=%0d collisions=%0d root_last=%b vaw=%b",
        retired,last_pc,aw_count,collisions,root_last,vreq.aw_valid);
      if(collision && !overlap_seen) $fatal(1,"Controlled overlap did not occur; not a DUT deadlock finding");
      $fatal(1,"No target retirement within bound");
    end
`ifdef LOADER_FSDB
    if(trace_start>=0 && cycle==trace_start+2000) $fsdbDumpoff;
`endif
  end
endmodule

// Independent legal AXI RAM ports. No invented invalidation or cache ACK.
module loader_cpu_memory #(
  parameter int Width=64,parameter type req_t=logic,parameter type rsp_t=logic
) (input logic clk,rst,input req_t req,output rsp_t rsp,
   input logic hold_aw,hold_read,input logic[63:0] root_line,input logic armed,
   output logic root_last);
  req_t rd_meta,wr_meta;
  bit reading=0,writing=0,bpending=0,root_request=0;
  int rd_beat=0,wr_beat=0;
  longint unsigned rd_address,wr_address;
  always_comb begin
    root_last=reading && root_request && rd_beat==rd_meta.ar.len;
    rd_address=(64'(rd_meta.ar.addr) & ~((64'd1<<rd_meta.ar.size)-1)) + (64'(rd_beat)<<rd_meta.ar.size);
    wr_address=(64'(wr_meta.aw.addr) & ~((64'd1<<wr_meta.aw.size)-1)) + (64'(wr_beat)<<wr_meta.aw.size);
    rsp='0;
    rsp.ar_ready=!reading;
    rsp.r_valid=reading && !hold_read;
    rsp.r.id=rd_meta.ar.id;
    rsp.r.last=rd_beat==rd_meta.ar.len;
    for(int i=0;i<Width/8;i++)
      rsp.r.data[i*8+:8]=loader_cpu_chain_tb.read_byte((rd_address & ~64'(Width/8-1))+i);
    rsp.aw_ready=!writing && !bpending && !hold_aw;
    rsp.w_ready=writing;
    rsp.b_valid=bpending;
    rsp.b.id=wr_meta.aw.id;
  end
  always @(posedge clk) if(rst) begin
    if(req.ar_valid && rsp.ar_ready) begin
      if(req.ar.burst!=axi_pkg::BURST_INCR || req.ar.size>$clog2(Width/8))
        $fatal(1,"Unsupported read");
      rd_meta<=req; reading<=1; rd_beat<=0;
      root_request<=armed && req.ar.addr==root_line;
      $display("READ %m addr=%h len=%0d id=%h armed=%b",req.ar.addr,req.ar.len,req.ar.id,armed);
    end
    if(rsp.r_valid && req.r_ready) begin
      if(rsp.r.last) reading<=0;
      else rd_beat<=rd_beat+1;
    end
    if(req.aw_valid && rsp.aw_ready) begin
      if(req.aw.burst!=axi_pkg::BURST_INCR || req.aw.size>$clog2(Width/8) || req.aw.atop!=0)
        $fatal(1,"Unsupported write");
      wr_meta<=req; writing<=1; wr_beat<=0;
    end
    if(req.w_valid && rsp.w_ready) begin
      if(req.w.last!=(wr_beat==wr_meta.aw.len)) $fatal(1,"Wrong WLAST");
      for(int i=0;i<Width/8;i++) if(req.w.strb[i])
        loader_cpu_chain_tb.write_byte((wr_address & ~64'(Width/8-1))+i,req.w.data[8*i+:8]);
      if(req.w.last) begin writing<=0; bpending<=1; end
      else wr_beat<=wr_beat+1;
    end
    if(rsp.b_valid && req.b_ready) bpending<=0;
  end
endmodule
