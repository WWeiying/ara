// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module vldu_restore_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  `include "ara/ara_typedef.svh"
  typedef struct packed { logic [127:0] data; } r_t;
  localparam int Count = 16;
  logic clk_i=0, rst_ni=0;
  pe_req_t request;
  pe_resp_t response;
  addrgen_axi_req_t address;
  r_t r;
  logic req_valid, req_ready, rvalid=0, rready, addrvalid, addrready;
  logic [7:0] running=0;
  logic [3:0] valid, grant=0, final_grant=0, held=0;
  logic [3:0][2:0] ids;
  logic [3:0][9:0] addrs;
  logic [3:0][63:0] data;
  logic [3:0][7:0] be;
  logic [3:0][84:0] held_payload;
  int accepted=0, completed=0, memory_insn=0, beat=0, cycles=0;
  int lane_insn[4]='{default:0}, words[4]='{default:0};
  int pressure=1, seed=1, short_loads=0, maximum_inflight=0, held_cycles=0;
  always #5 clk_i=~clk_i;
  function automatic int bytes_for(int insn);
    if(short_loads && insn%5==0) return insn%2==0 ? 7 : 15;
    return insn%5==0 ? 832 : 1024;
  endfunction
  function automatic int id_for(int insn);
    return (insn*3+seed)%8;
  endfunction
  function automatic int vd_for(int insn);
    return (insn%4)*8;
  endfunction
  function automatic byte pattern(int insn, index);
    return byte'((index*37) ^ (index>>3) ^ (insn*91+seed));
  endfunction
  function automatic int source_index(int word_index, lane, b);
    int reversed;
    reversed=((b&1)<<2)|(b&2)|((b>>2)&1);
    return word_index*32+reversed*4+lane;
  endfunction
  always_comb begin
    request='0;
    request.id=3'(id_for(accepted));
    request.op=VLE;
    request.vfu=VFU_LoadUnit;
    request.vm=1;
    request.vd=5'(vd_for(accepted));
    request.use_vd=1;
    request.vl=11'(bytes_for(accepted));
    request.vtype.vsew=EW8;
    request.vtype.vlmul=LMUL_8;
    request.emul=LMUL_8;
    request.vtype.vta=1;
    request.vtype.vma=1;
    req_valid=rst_ni && accepted<Count && !running[id_for(accepted)];
    address='0;
    address.addr=64'h80000000+memory_insn*4096;
    address.size=4;
    address.len=8'((bytes_for(memory_insn)+15)/16-1);
    address.is_load=1;
    addrvalid=rst_ni && memory_insn<accepted && memory_insn<Count;
    for(int b=0;b<16;b++) r.data[b*8+:8]=pattern(memory_insn,beat*16+b);
  end
`ifdef MAPPED_RESTORE
  `include "vldu_restore_mapped.svh"
`else
  vldu #(.NrLanes(4), .VLEN(1024), .vaddr_t(logic [9:0]),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .AxiDataWidth(128), .AxiAddrWidth(64), .axi_r_t(r_t)) dut (
    .clk_i, .rst_ni, .axi_r_i(r), .axi_r_valid_i(rvalid), .axi_r_ready_o(rready),
    .pe_req_i(request), .pe_req_valid_i(req_valid), .pe_vinsn_running_i(running),
    .pe_req_ready_o(req_ready), .pe_resp_o(response),
    .axi_addrgen_req_i(address), .axi_addrgen_req_valid_i(addrvalid),
    .axi_addrgen_req_ready_o(addrready), .addrgen_illegal_load_i(1'b0),
    .ldu_result_req_o(valid), .ldu_result_id_o(ids), .ldu_result_addr_o(addrs),
    .ldu_result_wdata_o(data), .ldu_result_be_o(be),
    .ldu_result_gnt_i(grant), .ldu_result_final_gnt_i(final_grant),
    .lsu_ex_flush_i(1'b0), .mask_i('0), .mask_valid_i('0),
    .mask_owner_id_i('0), .mask_first_element_i('0)
  );
`endif
  always @(negedge clk_i) if(rst_ni) begin
    cycles++;
    rvalid=addrvalid;
    final_grant=grant;
    for(int lane=0;lane<4;lane++)
      grant[lane]=valid[lane] && (!pressure ||
        (cycles>20 && (cycles+lane*3)%13<4));
    if(cycles>20000) $fatal(1,"TIMEOUT accepted=%0d completed=%0d memory=%0d beat=%0d",accepted,completed,memory_insn,beat);
  end
  // All stimulus bookkeeping changes after the sampling edge, avoiding DUT races.
  always @(posedge clk_i) if(rst_ni) begin
    for(int lane=0;lane<4;lane++) begin
      if(held[lane]) begin
        held_cycles++;
        if(!valid[lane] || {ids[lane],addrs[lane],data[lane],be[lane]} !== held_payload[lane])
          $fatal(1,"HELD_CHANGED cycle=%0d lane=%0d",cycles,lane);
      end
      held[lane]<=valid[lane]&&!grant[lane];
      held_payload[lane]<={ids[lane],addrs[lane],data[lane],be[lane]};
      if(valid[lane]) begin
        if(lane_insn[lane]>=accepted) $fatal(1,"UNREQUESTED_WRITE");
        if(ids[lane]!==3'(id_for(lane_insn[lane])) ||
`ifdef MAPPED_RESTORE
           // The physical 1024-bit/four-lane VRF uses seven word-address bits.
           // Bits 9:7 are unused outside the extracted cell and have no driver.
           addrs[lane][6:0]!==7'(vd_for(lane_insn[lane])*4+words[lane]))
`else
           addrs[lane]!==10'(vd_for(lane_insn[lane])*4+words[lane]))
`endif
          $fatal(1,"METADATA lane=%0d insn=%0d word=%0d id=%0d addr=%0d be=%h",lane,lane_insn[lane],words[lane],ids[lane],addrs[lane],be[lane]);
        for(int b=0;b<8;b++) begin
          if(be[lane][b] !== (source_index(words[lane],lane,b)<bytes_for(lane_insn[lane])))
            $fatal(1,"BYTE_ENABLE lane=%0d insn=%0d byte=%0d",lane,lane_insn[lane],b);
          if(be[lane][b] && data[lane][b*8+:8]!==pattern(lane_insn[lane],source_index(words[lane],lane,b)))
            $fatal(1,"DATA cycle=%0d lane=%0d insn=%0d word=%0d byte=%0d",cycles,lane,lane_insn[lane],words[lane],b);
        end
      end
      if(valid[lane]&&grant[lane]) begin
        if((words[lane]+1)*32>=bytes_for(lane_insn[lane])) begin
          lane_insn[lane]<=lane_insn[lane]+1;
          words[lane]<=0;
        end else words[lane]<=words[lane]+1;
      end
    end
    running <= (running & ~response.vinsn_done) |
      ((req_valid&&req_ready) ? (8'b1<<request.id) : 8'b0);
    if(req_valid&&req_ready) accepted<=accepted+1;
    if(accepted-completed>maximum_inflight) maximum_inflight=accepted-completed;
    if(rvalid&&rready) begin
      if((beat+1)*16>=bytes_for(memory_insn)) begin
        if(!addrready) $fatal(1,"MISSING_ADDRESS_COMPLETION");
        memory_insn<=memory_insn+1;
        beat<=0;
      end else begin
        if(addrready) $fatal(1,"EARLY_ADDRESS_COMPLETION");
        beat<=beat+1;
      end
    end
    if(|response.vinsn_done) begin
      if(response.vinsn_done !== (8'b1<<id_for(completed))) $fatal(1,"COMPLETION_ID got=%h insn=%0d",response.vinsn_done,completed);
      foreach(lane_insn[lane]) if(lane_insn[lane]<=completed) $fatal(1,"EARLY_COMPLETION");
      completed<=completed+1;
    end
  end
  initial begin
    void'($value$plusargs("PRESSURE=%d",pressure));
    void'($value$plusargs("SEED=%d",seed));
    void'($value$plusargs("SHORT=%d",short_loads));
    repeat(15) @(negedge clk_i);
    rst_ni=1;
    wait(completed==Count);
    repeat(10) @(negedge clk_i);
    if(memory_insn!=Count || maximum_inflight<4 || (pressure&&!held_cycles)) $fatal(1,"COVERAGE_MISSING");
    $display("VLDU_RESTORE_PASS instructions=%0d max_inflight=%0d held=%0d pressure=%0d seed=%0d short=%0d",completed,maximum_inflight,held_cycles,pressure,seed,short_loads);
    $finish;
  end
endmodule
