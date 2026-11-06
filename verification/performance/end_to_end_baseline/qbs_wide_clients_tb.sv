`timescale 1ns/1ps

module wide_clients_fixture #(parameter int Width=128, parameter bit PerRange=0)
    (input logic go, output bit done=0);
  import axi_pkg::*;
  import qbs_pkg::*;
  `include "axi/typedef.svh"
  `include "shared_reader_types.svh"
  typedef logic [63:0] addr_t;
  typedef logic [Width-1:0] data_t;
  typedef logic [0:0] id_t, user_t;
  typedef struct packed {logic [63:0] cause,tval; logic valid;} exception_t;
  `AXI_TYPEDEF_AR_CHAN_T(ar_t,addr_t,id_t,user_t)
  `AXI_TYPEDEF_R_CHAN_T(r_t,data_t,id_t,user_t)
  `QBS_AKV_SHARED_READER_TYPEDEF_REQ_T(req_t,64)
  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(rsp_t,Width,64,exception_t)
  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(narrow_t,128,64,exception_t)
  logic clk=0;
  always #5 clk=~clk;
  logic rst_n=0;
  logic [1:0] owner=0,command_fire=0;
  req_t request[2];
  rsp_t response[2];
  narrow_t akv;
  ar_t ar;
  r_t r;
  logic av,ardy,rv,rr,pv,allowed,mmu_req;
  addr_t pa,mva;
  logic [12:0] pb;
  logic translate=0,mmu_fail=0,deny=0,hold_r=0,hold_ar=0,inject=0;
  exception_t exc;
  int client=0,ticks=0;
  bit normal=0,fault_mode=0;
  addr_t base[2],queue_addr[2];
  int length[2],size[2],queue_size[2],queue_len[2];
  int received[2],completed[2],ar_offset[2],permission_offset[2];
  bit qrd=0,qwr=0;
  int qcount=0,qbeat=0,ar_seen=0,r_seen=0,payload_seen=0,footprints=0;
  int normal_cases=0,fault_cases=0,commands=0;
  int lower_half=0,upper_half=0,full32=0,data_stalls=0,completion_stalls=0;
  int stalled_faults=0,inactive_checks=0,normal_bytes=0,normal_ars=0,normal_beats=0;
  int mixed_pairs=0,akv_upper=0;
  bit error_seen=0,ar_stalled=0,data_stalled=0;
  ar_t saved_ar;
  logic [Width+Width/8+31:0] saved_data;
  rsp_t active_rsp;
  assign active_rsp=response[client];
  assign exc='{cause:64'h1122334455667788,tval:64'h8877665544332211,valid:1'b1};
  assign allowed=!deny;
  assign ardy=qcount<2 && ticks%5!=1 && !(hold_ar && ar_seen!=0);
  assign rv=qcount!=0 && !hold_r;

  qbs_akv_shared_reader #(.AxiDataWidth(Width),.AxiAddrWidth(64),.VAddrWidth(64),
      .PAddrWidth(64),.PerRangeTransferSize(PerRange),.req_t(req_t),.rsp_t(rsp_t),
      .axi_ar_t(ar_t),.axi_r_t(r_t),.exception_t(exception_t)) dut (
    .clk_i(clk),.rst_ni(rst_n),.owner_i(owner),.command_fire_i(command_fire),
    .client_req_i(request),.client_rsp_o(response),.core_st_pending_i(1'b0),
    .en_ld_st_translation_i(translate),.mmu_req_o(mmu_req),.mmu_vaddr_o(mva),
    .mmu_is_store_o(),.mmu_valid_i(1'b0),.mmu_paddr_i(64'b0),
    .mmu_exception_valid_i(mmu_req && mmu_fail),.mmu_exception_i(exc),
    .physical_check_valid_o(pv),.physical_check_addr_o(pa),.physical_check_bytes_o(pb),
    .physical_range_allowed_i(allowed),.axi_ar_o(ar),.axi_ar_valid_o(av),
    .axi_ar_ready_i(ardy),.axi_r_i(r),.axi_r_valid_i(rv),.axi_r_ready_o(rr));
  qbs_reader_narrow_view #(.wide_rsp_t(rsp_t),.narrow_rsp_t(narrow_t)) view (
    .clk_i(clk),.rst_ni(rst_n),.wide_i(response[1]),.narrow_o(akv));

  function automatic byte memory_byte(input addr_t a);
    return a[7:0]^a[15:8]^a[23:16]^8'h5a;
  endfunction
  function automatic int index_of(input logic [15:0] tag);
    if(tag==16'h1101) return 0;
    if(tag==16'h2202) return 1;
    $fatal(1,"WC_UNEXPECTED_TAG");return 0;
  endfunction
  task automatic geometry(input addr_t start,input int bytes,sz,
                          output int ars,beats);
    int todo,take,head,span;
    addr_t cursor;
    todo=bytes;cursor=start;ars=0;beats=0;
    while(todo>0) begin
      head=int'(cursor%addr_t'(1<<sz));
      take=todo;
      if(take>4096-int'(cursor[11:0])) take=4096-int'(cursor[11:0]);
      if(take>256*(1<<sz)-head) take=256*(1<<sz)-head;
      span=(head+take+(1<<sz)-1)>>sz;
      ars++;beats+=span;cursor+=addr_t'(take);todo-=take;
    end
  endtask

  always_comb begin
    addr_t cursor,word;
    cursor=queue_addr[qrd]+addr_t'(qbeat<<queue_size[qrd]);
    word=cursor & ~addr_t'(Width/8-1);
    r='0;
    for(int b=0;b<Width/8;b++)
      r.data[8*b+:8]=(word+b>=cursor && word+b<cursor+(1<<queue_size[qrd]))
          ?memory_byte(word+b):8'hc7;
    r.last=qbeat==queue_len[qrd];
    r.resp=inject && qbeat==0 ? RESP_SLVERR:RESP_OKAY;
  end

  // One owner for the target queue and all sampled traffic statistics.
  always @(posedge clk) begin : observe
    int idx,n,take,head,count;
    addr_t cursor;
    ticks++;
    if(!rst_n) begin
      qcount<=0;qrd<=0;qwr<=0;qbeat<=0;
      ar_seen=0;r_seen=0;payload_seen=0;footprints=0;error_seen=0;
      ar_stalled=0;data_stalled=0;
      for(int i=0;i<2;i++) begin received[i]=0;completed[i]=0;ar_offset[i]=0;permission_offset[i]=0;end
    end else begin
      if(|command_fire) begin
        if(qcount!=0 || av || dut.reader_rsp.busy) $fatal(1,"WC_COMMAND_BEFORE_DRAIN");
        ar_seen=0;r_seen=0;payload_seen=0;footprints=0;error_seen=0;
        for(int i=0;i<2;i++) begin received[i]=0;completed[i]=0;ar_offset[i]=0;permission_offset[i]=0;end
      end
      case({av && ardy,rv && rr && r.last})
        2'b10:qcount<=qcount+1;
        2'b01:qcount<=qcount-1;
        default:;
      endcase
      if(ar_stalled && (!av || ar!==saved_ar)) $fatal(1,"WC_STALLED_AR_CHANGED");
      ar_stalled=av && !ardy;saved_ar=ar;
      if(av && ardy) begin
        if(qcount>=2 || int'(ar.addr[11:0])+((int'(ar.len)+1)<<ar.size)>4096)
          $fatal(1,"WC_AR_QUEUE_OR_PAGE");
        if(normal) begin
          idx=index_of(dut.i_read_engine.ar_tag_q);
          if(int'(ar.size)!=size[idx] || ar.cache!==cache_t'(3+idx) ||
             ar.prot!==prot_t'(5+idx)) $fatal(1,"WC_AR_METADATA");
          cursor=base[idx]+addr_t'(ar_offset[idx]);head=int'(cursor%addr_t'(1<<size[idx]));
          take=length[idx]-ar_offset[idx];
          if(take>4096-int'(cursor[11:0])) take=4096-int'(cursor[11:0]);
          if(take>256*(1<<size[idx])-head) take=256*(1<<size[idx])-head;
          count=(head+take+(1<<size[idx])-1)>>size[idx];
          if(take<=0 || ar.addr!==(cursor & ~addr_t'((1<<size[idx])-1)) ||
             int'(ar.len)+1!=count) $fatal(1,"WC_AR_GEOMETRY");
          ar_offset[idx]+=take;
        end
        queue_addr[qwr]<=ar.addr;queue_size[qwr]<=int'(ar.size);
        queue_len[qwr]<=int'(ar.len);qwr<=!qwr;ar_seen++;
      end
      if(rv && rr) begin
        r_seen++;
        if(r.resp!=RESP_OKAY) error_seen=1;
        if(normal && queue_size[qrd]==4) begin
          if(Width==256 && (queue_addr[qrd]+addr_t'(qbeat<<4))%32==16) begin
            upper_half++;if(client==1) akv_upper++;
          end
          else lower_half++;
        end
        if(r.last) begin qrd<=!qrd;qbeat<=0;end else qbeat<=qbeat+1;
      end
      if(pv) begin
        if(pb==0 || int'(pa[11:0])+int'(pb)>4096 || pa%addr_t'(1<<dut.i_read_engine.planner_size_q)!=0)
          $fatal(1,"WC_PERMISSION_FOOTPRINT");
        footprints++;
        if(normal) begin
          idx=index_of(dut.i_read_engine.planner_tag_q);
          cursor=base[idx]+addr_t'(permission_offset[idx]);head=int'(cursor%addr_t'(1<<size[idx]));
          take=length[idx]-permission_offset[idx];
          if(take>4096-int'(cursor[11:0])) take=4096-int'(cursor[11:0]);
          if(take>256*(1<<size[idx])-head) take=256*(1<<size[idx])-head;
          count=(head+take+(1<<size[idx])-1)>>size[idx];
          if(take<=0 || pa!==(cursor & ~addr_t'((1<<size[idx])-1)) || int'(pb)!=(count<<size[idx]))
            $fatal(1,"WC_EXACT_PERMISSION_FOOTPRINT");
          permission_offset[idx]+=take;
        end
      end
      if(normal && qcount==2 && queue_size[0]!=queue_size[1]) mixed_pairs++;
      if(|owner) begin
        if(response[1-client] !== rsp_t'('0)) $fatal(1,"WC_INACTIVE_RESPONSE");
        inactive_checks++;
        if($isunknown({active_rsp.range_ready,active_rsp.data_valid,active_rsp.completion_valid,
                       active_rsp.fault_valid,active_rsp.busy,active_rsp.range_count,
                       active_rsp.ar_count,active_rsp.r_beat_count,active_rsp.payload_byte_count}))
          $fatal(1,"WC_UNKNOWN_CONTROL");
        if(data_stalled && (!active_rsp.data_valid ||
            {active_rsp.data,active_rsp.data_strb,active_rsp.data_offset,active_rsp.data_tag}!==saved_data))
          $fatal(1,"WC_STALLED_DATA_CHANGED");
        data_stalled=active_rsp.data_valid && !request[client].data_ready;
        saved_data={active_rsp.data,active_rsp.data_strb,active_rsp.data_offset,active_rsp.data_tag};
        if(data_stalled) data_stalls++;
        if(active_rsp.completion_valid && !request[client].completion_ready) completion_stalls++;
        if(fault_mode && error_seen && (active_rsp.data_valid || active_rsp.completion_valid))
          $fatal(1,"WC_FAULT_LEAK");
        if(normal) begin
          if(active_rsp.fault_valid) $fatal(1,"WC_NORMAL_FAULT");
          if(active_rsp.data_valid) begin
            if($isunknown({active_rsp.data_strb,active_rsp.data_offset,active_rsp.data_tag}))
              $fatal(1,"WC_UNKNOWN_DATA_CONTROL");
            idx=index_of(active_rsp.data_tag);n=$countones(active_rsp.data_strb);
            if(n<1 || n>(1<<size[idx]) ||
               (active_rsp.data_strb & (active_rsp.data_strb+1))!=0 ||
               int'(active_rsp.data_offset)!=received[idx]) $fatal(1,"WC_DATA_GEOMETRY");
            for(int b=0;b<n;b++)
              if(active_rsp.data[8*b+:8]!==memory_byte(base[idx]+received[idx]+b))
                $fatal(1,"WC_DATA_BYTE");
            if(client==1 && (akv.data_valid!==active_rsp.data_valid ||
                akv.data!==active_rsp.data[127:0] || akv.data_strb!==active_rsp.data_strb[15:0] ||
                akv.data_offset!==active_rsp.data_offset || akv.data_tag!==active_rsp.data_tag))
              $fatal(1,"WC_AKV_VIEW");
            if(request[client].data_ready) begin
              received[idx]+=n;payload_seen+=n;
              if(n==32) full32++;
            end
          end
          if(active_rsp.completion_valid && request[client].completion_ready) begin
            idx=index_of(active_rsp.completion_tag);
            if(received[idx]!=length[idx] || completed[idx]!=0) $fatal(1,"WC_COMPLETION");
            completed[idx]++;
          end
        end
      end else begin
        if(response[0]!==rsp_t'('0) || response[1]!==rsp_t'('0)) $fatal(1,"WC_IDLE_RESPONSE");
        data_stalled=0;
      end
    end
  end

  always @(negedge clk) if(rst_n && |owner) begin
    request[client].data_ready=ticks%7!=2 && ticks%7!=3;
    request[client].completion_ready=ticks%11!=6;
  end

  task automatic start_command(input int who);
    @(negedge clk);
    client=who;request[0]='0;request[1]='0;
    command_fire=2'(1<<who);
    @(negedge clk);command_fire=0;owner=2'(1<<who);
    // An inactive client's poison request must not reach the reader.
    request[1-who].range_valid=1;request[1-who].range_size=7;
    request[1-who].range_vaddr=64'hdead0000;request[1-who].range_bytes=0;
    commands++;
  endtask
  task automatic end_command;
    int bound;
    bound=0;
    while(active_rsp.busy || av || qcount!=0 || dut.i_read_engine.ar_stalled_q ||
          dut.i_read_engine.response_drain_q) begin
      @(negedge clk);bound++;if(bound>1000) $fatal(1,"WC_RELEASE_TIMEOUT");
    end
    @(negedge clk);owner=0;normal=0;fault_mode=0;
    hold_r=0;hold_ar=0;inject=0;translate=0;mmu_fail=0;deny=0;
    @(negedge clk);
  endtask
  task automatic send_range(input int index,input int supplied_size);
    int bound;
    @(negedge clk);
    request[client].range_vaddr=base[index];request[client].range_bytes=16'(length[index]);
    request[client].range_tag=index==0?16'h1101:16'h2202;
    request[client].range_cache=cache_t'(3+index);request[client].range_prot=prot_t'(5+index);
    request[client].range_size=size_t'(supplied_size);request[client].range_valid=1;
    bound=0;
    do begin @(posedge clk);bound++;if(bound>200) $fatal(1,"WC_RANGE_TIMEOUT");end
    while(!active_rsp.range_ready);
    @(negedge clk);request[client].range_valid=0;
  endtask
  task automatic normal_pair(input int who,phase);
    int bound,a,b,c,d;
    start_command(who);
    base[0]=64'h10000+addr_t'(phase);base[1]=64'h21ff0+addr_t'(phase);
    length[0]=who==0?(phase%2==0?16:292):64;
    length[1]=who==0?840:83+phase;
    size[0]=4;size[1]=PerRange && who==0?5:4;
    normal=1;hold_r=1;
    if(phase%4<2) begin
      send_range(0,PerRange?4:7);send_range(1,PerRange?size[1]:7);
    end else begin
      send_range(1,PerRange?size[1]:7);send_range(0,PerRange?4:7);
    end
    bound=0;
    while(ar_seen<2) begin @(negedge clk);bound++;if(bound>200) $fatal(1,"WC_TWO_OUTSTANDING_SETUP");end
    hold_r=0;bound=0;
    while(completed[0]!=1 || completed[1]!=1 || active_rsp.busy || qcount!=0) begin
      @(negedge clk);bound++;if(bound>4000) $fatal(1,"WC_NORMAL_TIMEOUT");
    end
    geometry(base[0],length[0],size[0],a,b);geometry(base[1],length[1],size[1],c,d);
    if(active_rsp.range_count!==32'd2 || active_rsp.ar_count!==32'(a+c) ||
       active_rsp.translation_count!==32'd0 || active_rsp.r_beat_count!==32'(b+d) ||
       active_rsp.payload_byte_count!==32'(length[0]+length[1]) ||
       ar_seen!=a+c || r_seen!=b+d || footprints!=a+c || payload_seen!=length[0]+length[1] ||
       active_rsp.outstanding_max!==2 || active_rsp.outstanding_full_cycles==0)
      $fatal(1,"WC_NORMAL_COUNTERS");
    for(int i=0;i<2;i++) if(ar_offset[i]!=length[i] || permission_offset[i]!=length[i])
      $fatal(1,"WC_INCOMPLETE_AR_OR_PERMISSION_CHECK");
    $display("WIDE_CLIENTS_CASE width=%0d owner=%0d phase=%0d ars=%0d beats=%0d payload=%0d max_outstanding=2",
      Width,who,phase,a+c,b+d,length[0]+length[1]);
    normal_cases++;normal_bytes+=length[0]+length[1];normal_ars+=a+c;normal_beats+=b+d;
    end_command();
  endtask
  task automatic consume_fault(input int mode,input qbs_read_fault_e kind);
    int bound;
    rsp_t held;
    bound=0;
    while(!active_rsp.fault_valid) begin @(negedge clk);bound++;if(bound>1000) $fatal(1,"WC_FAULT_TIMEOUT");end
    if(active_rsp.fault_kind!==kind || active_rsp.fault_tag!==16'h1101 ||
       active_rsp.fault_vaddr!==base[0] || qcount!=0 || av ||
       active_rsp.payload_byte_count!=0 || active_rsp.data_valid || active_rsp.completion_valid)
      $fatal(1,"WC_FAULT_IDENTITY_OR_DRAIN");
    if(active_rsp.fault_mmu_exception !== (mode==3?exc:exception_t'('0)))
      $fatal(1,"WC_FAULT_EXCEPTION_COPY");
    held=active_rsp;
    repeat(3) begin
      @(negedge clk);
      if(!active_rsp.busy || !active_rsp.fault_valid ||
         {active_rsp.fault_kind,active_rsp.fault_tag,active_rsp.fault_vaddr,active_rsp.fault_mmu_exception} !==
         {held.fault_kind,held.fault_tag,held.fault_vaddr,held.fault_mmu_exception})
        $fatal(1,"WC_STALLED_FAULT_CHANGED");
    end
    $display("WIDE_CLIENTS_FAULT width=%0d owner=%0d mode=%0d kind=%0d ars=%0d beats=%0d payload=0",
      Width,client,mode,kind,ar_seen,r_seen);
    request[client].fault_ready=1;
    @(negedge clk);request[client].fault_ready=0;fault_cases++;
    end_command();
  endtask
  task automatic axi_fault(input int who,stalled);
    int bound,a,b,c,d;
    start_command(who);fault_mode=1;hold_r=1;hold_ar=1'(stalled);
    base[0]=64'h8003;base[1]=64'h9007;length[0]=61;length[1]=65;
    size[0]=4;size[1]=PerRange && who==0?5:4;
    send_range(0,PerRange?4:7);send_range(1,PerRange?size[1]:7);
    bound=0;
    while(!(stalled?(av && ar_seen==1):(ar_seen==2))) begin
      @(negedge clk);bound++;if(bound>200) $fatal(1,"WC_FAULT_FIXTURE_TIMEOUT");
    end
    if(stalled) begin
      // Sample the blocked offer before injecting the older R error.
      @(posedge clk);if(!av || ardy) $fatal(1,"WC_AR_NOT_SAMPLED_STALLED");
      @(negedge clk);if(!dut.i_read_engine.ar_stalled_q) $fatal(1,"WC_NO_STALLED_AR_WITNESS");
      stalled_faults++;
    end
    inject=1;hold_r=0;
    repeat(5) @(negedge clk);
    if(stalled && !av) $fatal(1,"WC_FAULT_DROPPED_STALLED_AR");
    hold_ar=0;
    consume_fault(stalled,QBS_READ_FAULT_AXI_RESPONSE);
    geometry(base[0],length[0],size[0],a,b);geometry(base[1],length[1],size[1],c,d);
    if(ar_seen!=a+c || r_seen!=b+d) $fatal(1,"WC_FAULT_DRAIN_COUNTS");
  endtask

  initial begin
    request[0]='0;request[1]='0;
    wait(go);repeat(3) @(negedge clk);rst_n=1;
    for(int phase=0;phase<32;phase++) for(int who=0;who<2;who++) normal_pair(who,phase);
    for(int who=0;who<2;who++) for(int stalled=0;stalled<2;stalled++) axi_fault(who,stalled);
    start_command(0);fault_mode=1;deny=1;base[0]=64'h3013;length[0]=16;
    send_range(0,PerRange?4:7);consume_fault(2,QBS_READ_FAULT_PMA);
    if(ar_seen!=0 || r_seen!=0) $fatal(1,"WC_DENIED_MEMORY_WORK");
    start_command(1);fault_mode=1;translate=1;mmu_fail=1;base[0]=64'h4017;length[0]=16;
    send_range(0,PerRange?4:7);consume_fault(3,QBS_READ_FAULT_MMU);
    if(ar_seen!=0 || r_seen!=0) $fatal(1,"WC_MMU_FAULT_MEMORY_WORK");
    if(normal_cases!=64 || fault_cases!=6 || commands!=70 || stalled_faults!=2 ||
       inactive_checks==0 || lower_half==0 || data_stalls==0 || completion_stalls==0 ||
       (Width==256 && (upper_half<=akv_upper || akv_upper==0 || full32==0 || mixed_pairs==0)) ||
       (Width==128 && (full32!=0 || mixed_pairs!=0 || akv_upper!=0)))
      $fatal(1,"WC_MISSING_COVERAGE");
    $display("WIDE_CLIENTS_FIXTURE_PASS width=%0d per_range=%0d normal=64 faults=6 commands=70 payload=%0d ars=%0d beats=%0d lower_half=%0d upper_half=%0d full32=%0d data_stalls=%0d completion_stalls=%0d stalled_faults=2 inactive_checks=%0d mixed_pairs=%0d akv_upper=%0d",
      Width,PerRange,normal_bytes,normal_ars,normal_beats,lower_half,upper_half,full32,
      data_stalls,completion_stalls,inactive_checks,mixed_pairs,akv_upper);
    done=1;
  end
endmodule

module wide_clients_copy #(parameter int Width=128)(input logic go,negative,output bit done=0);
  import qbs_pkg::*;
  `include "shared_reader_types.svh"
  typedef struct packed {logic [63:0] cause,tval;logic valid;} exception_t;
  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(wide_t,Width,64,exception_t)
  `QBS_AKV_SHARED_READER_TYPEDEF_RSP_T(narrow_t,128,64,exception_t)
  logic clk=0,rst_n=0;
  always #5 clk=~clk;
  wide_t wide='0;
  narrow_t narrow,expected;
  logic [31:0] rng=32'h198ab37d;
  qbs_reader_narrow_view #(.wide_rsp_t(wide_t),.narrow_rsp_t(narrow_t)) dut (
    .clk_i(clk),.rst_ni(rst_n),.wide_i(wide),.narrow_o(narrow));
  // Packed oracle follows the response typedef's field order, not a cast
  // between differently sized packed structs (which would shift metadata).
  always_comb expected={wide.range_ready,wide.data_valid,wide.data[127:0],wide.data_strb[15:0],
    wide.data_offset,wide.data_tag,wide.completion_valid,wide.completion_tag,wide.fault_valid,
    wide.fault_kind,wide.fault_vaddr,wide.fault_tag,wide.fault_mmu_exception,wide.range_count,
    wide.translation_count,wide.ar_count,wide.r_beat_count,wide.payload_byte_count,
    wide.store_wait_cycles,wide.r_backpressure_cycles,wide.outstanding_occupancy_sum,
    wide.outstanding_max,wide.outstanding_full_cycles,wide.busy};
  initial begin
    wait(go);repeat(2) @(negedge clk);rst_n=1;
    if(negative) begin
      if(Width==256) begin
        @(negedge clk);wide.data_valid=1;wide.data_strb=32'h00010000;
        $display("WIDE_CLIENTS_NEGATIVE_ARMED upper_mask=1");
        repeat(3) @(negedge clk);
        $fatal(1,"WC_UPPER_MASK_NOT_REJECTED");
      end
    end else begin
      for(int i=0;i<64;i++) begin
        @(negedge clk);
        for(int b=0;b<$bits(wide_t);b++) begin
          rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};wide[b]=rng[0];
        end
        wide.data_valid=i[0];
        if(wide.data_valid) wide.data_strb=(wide.data_strb << (Width/8-16)) >> (Width/8-16);
        @(posedge clk);#1;
        if(narrow!==expected) $fatal(1,"WC_DIRECT_FIELD_COPY");
      end
      $display("WIDE_CLIENTS_COPY_PASS width=%0d vectors=64 fields=24",Width);done=1;
    end
  end
endmodule

module qbs_wide_clients_tb;
  bit go=0,negative=0;
  wire a,b,c,d;
  wide_clients_fixture #(.Width(128),.PerRange(0)) legacy(go && !negative,a);
  wide_clients_fixture #(.Width(256),.PerRange(1)) wide(go && !negative,b);
  wide_clients_copy #(.Width(128)) copy128(go,negative,c);
  wide_clients_copy #(.Width(256)) copy256(go,negative,d);
  initial begin
    negative=$test$plusargs("NEGATIVE_UPPER_MASK");
    if(!negative) $display("WIDE_CLIENTS_BEGIN version=1");
    #1;go=1;
    if(!negative) begin
      wait(a && b && c && d);
      $display("WIDE_CLIENTS_COMPONENT_PASS fixtures=2 normal=128 faults=12 copies=128");$finish;
    end
  end
  initial begin #2000000;$fatal(1,"WC_WATCHDOG");end
endmodule
