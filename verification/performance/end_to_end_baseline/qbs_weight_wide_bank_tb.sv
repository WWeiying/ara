`timescale 1ns/1ps
module qbs_weight_wide_bank_tb;
  logic clk=0;
  always #5 clk=~clk;
  logic rst_n=0, clear=0, valid=0, ready, write_enable=0;
  logic read_req=0, read_ready, read_valid;
  qbs_pkg::qbs_weight_profile_e profile=qbs_pkg::QBS_WEIGHT_PROFILE_Q4_K;
  logic [2:0] rows=1;
  logic group_mode=0;
  logic [1:0] row=0;
  logic [9:0] offset=0;
  logic [255:0] data=0;
  logic [31:0] strb=0;
  logic [7:0] read_k=0;
  logic [127:0] window [4][2];
  logic [7:0] side [4][20];
  logic [3:0] row_complete;
  logic all_complete, pending;
  logic [10:0] accepted_bytes, committed_bytes;
  wire [3:0][1:0] output_waiting;
  wire [3:0][1:0] assembler_ready,assembler_valid,targeted;

  qbs_weight_wide_bank dut (
    .clk_i(clk),.rst_ni(rst_n),.clear_i(clear),.profile_i(profile),.row_count_i(rows),
    .group_mode_i(group_mode),.row_i(row),.offset_i(offset),.data_i(data),.strb_i(strb),
    .valid_i(valid),.ready_o(ready),.write_enable_i(write_enable),.read_i(read_req),
    .read_ready_o(read_ready),.read_valid_o(read_valid),.read_k_i(read_k),.window_o(window),
    .side_o(side),.row_complete_o(row_complete),.all_complete_o(all_complete),.pending_o(pending),
    .accepted_bytes_o(accepted_bytes),.committed_bytes_o(committed_bytes)
  );

  bit checking=0, automatic_write=0, window_known=0, was_complete=0;
  int traffic=0, ticks=0, salt=0, cfg_p=1, cfg_rows=1, cfg_size=144, cfg_elements=256;
  int epoch_accepted=0, epoch_payload=0, epoch_side=0, last_read_k=0;
  int epoch_reads=0;
  int next_native [4], row_payload [4], row_side [4];
  logic [3:0] previous_rows=0;
  logic [31:0] write_random=32'h731bc5d9;
  byte native_value [4][210], payload_value [4][2][128], side_value [4][20];
  bit native_accepted [4][210], payload_present [4][2][128], payload_written [4][2][128];
  bit side_present [4][20], side_seen [4][20];
  int payload_origin [4][2][128], side_origin [4][20];
  longint unsigned input_total=0, packets_total=0, payload_total=0, side_total=0, reads_total=0, read_bytes_total=0;
  longint unsigned idle_total=0, early_reads=0, input_stalls=0, blocked_outputs=0;
  int logical_low_bytes=0,logical_high_bytes=0,assembler_payload_bits=0;
  int normal_cases=0, reuse_cases=0, abort_cases=0, cancel_cases=0;
  int max_drain=0,profile_max_drain=0,unthrottled_stalls=0;
  longint unsigned mixed_target_stalls=0,side_mixed_stalls=0;

  // Explicit native-byte table; no package mapping/block/address helper calls.
  task automatic regions(input int p, output int size, elements, ls, ln, hs, hn, ss);
    case(p)
      1: begin size=144;elements=256;ls=16;ln=128;hs=0;hn=0;ss=0;end
      2: begin size=210;elements=256;ls=0;ln=128;hs=128;hn=64;ss=192;end
      3: begin size=18;elements=32;ls=2;ln=16;hs=0;hn=0;ss=0;end
      4: begin size=176;elements=256;ls=48;ln=128;hs=16;hn=32;ss=0;end
      5: begin size=110;elements=256;ls=32;ln=64;hs=0;hn=32;ss=96;end
      6: begin size=34;elements=32;ls=2;ln=32;hs=0;hn=0;ss=0;end
      7: begin size=84;elements=256;ls=16;ln=64;hs=0;hn=0;ss=0;end
      8: begin size=22;elements=32;ls=6;ln=16;hs=0;hn=0;ss=0;end
      9: begin size=18;elements=32;ls=2;ln=16;hs=0;hn=0;ss=0;end
      default:$fatal(1,"WB_ORACLE_PROFILE");
    endcase
  endtask

  task automatic locate(input int p,native, output int plane,destination);
    int size,elements,ls,ln,hs,hn,ss;
    regions(p,size,elements,ls,ln,hs,hn,ss);
    if(native<0 || native>=size) $fatal(1,"WB_ORACLE_NATIVE_RANGE");
    plane=2;destination=native-ss;
    if(native>=ls && native<ls+ln) begin plane=0;destination=native-ls;end
    else if(hn!=0 && native>=hs && native<hs+hn) begin plane=1;destination=native-hs;end
    else if(p==7 && native>=80) destination=native-64;
  endtask

  // Old 16-byte word addresses, independent arithmetic formulas.
  function automatic int word16(input int p,k,plane);
    case(p)
      1,4:return plane==0 ? (k/64)*2+(k/16)%2 : (k/16)%2;
      2:return plane==0 ? (k/128)*4+(k/16)%4 : (k/128)*2+(k/16)%2;
      5,7:return plane==0 ? (k/128)*2+(k/16)%2 : (k/16)%2;
      6:return plane==0 ? (k/16)%2 : 0;
      default:return 0;
    endcase
  endfunction

  function automatic byte pattern(input int p,r,b,epoch);
    // Nonzero side bytes let the public side validity be audited independently.
    return 8'(1+((p*17+r*53+b*37+epoch*71+b/7)%255));
  endfunction

  task automatic check_windows(input int k, input bit count_bytes);
    int start;
    for(int r=0;r<4;r++) begin
      for(int p=0;p<2;p++) begin
        start=word16(cfg_p,k,p)*16;
        for(int b=0;b<16;b++) begin
          if(r<cfg_rows && start+b<128 && payload_present[r][p][start+b]) begin
            if(!payload_written[r][p][start+b] || window[r][p][8*b+:8] !== payload_value[r][p][start+b])
              $fatal(1,"WB_READ_BYTE p=%0d row=%0d plane=%0d k=%0d byte=%0d",cfg_p,r,p,k,b);
            if(count_bytes) read_bytes_total++;
          end
        end
        if(r>=cfg_rows && window[r][p] !== 0) $fatal(1,"WB_INACTIVE_WINDOW");
      end
    end
  endtask

  task automatic check_control_known;
    if($isunknown({rst_n,clear,valid,read_req,write_enable,ready,read_ready,read_valid,
                   all_complete,pending,row_complete,accepted_bytes,committed_bytes,dut.map_valid,dut.map_ready}))
      $fatal(1,"WB_UNKNOWN_CONTROL_OR_COUNT");
  endtask

  // Observe actual SRAM requests, not the DUT's count/write helper signals.
  for(genvar r=0;r<4;r++) begin:gen_observe_row
    for(genvar p=0;p<2;p++) begin:gen_observe_plane
      wire mem_req=dut.gen_rows[r].gen_plane[p].i_payload.req_i;
      wire mem_we=dut.gen_rows[r].gen_plane[p].i_payload.we_i;
      wire [2:0] mem_addr=dut.gen_rows[r].gen_plane[p].i_payload.addr_i;
      wire [255:0] mem_data=dut.gen_rows[r].gen_plane[p].i_payload.wdata_i;
      wire [31:0] mem_be=dut.gen_rows[r].gen_plane[p].i_payload.be_i;
      assign output_waiting[r][p]=dut.gen_rows[r].gen_plane[p].i_assembler.write_valid_o;
      assign assembler_ready[r][p]=dut.gen_rows[r].gen_plane[p].i_assembler.ready_o;
      assign assembler_valid[r][p]=dut.gen_rows[r].gen_plane[p].i_assembler.valid_i;
      assign targeted[r][p]=dut.i_mapper.count_o[r][p]!=0;
      initial begin
        if(dut.gen_rows[r].gen_plane[p].i_payload.NumWords != (p==0?4:2) ||
           dut.gen_rows[r].gen_plane[p].i_payload.DataWidth != 256)
          $fatal(1,"WB_REAL_SRAM_GEOMETRY");
        if(p==0) logical_low_bytes+=dut.gen_rows[r].gen_plane[p].i_payload.NumWords*
            dut.gen_rows[r].gen_plane[p].i_payload.DataWidth/8;
        else logical_high_bytes+=dut.gen_rows[r].gen_plane[p].i_payload.NumWords*
            dut.gen_rows[r].gen_plane[p].i_payload.DataWidth/8;
        assembler_payload_bits+=$bits(dut.gen_rows[r].gen_plane[p].i_assembler.carry_data_q)+
                                $bits(dut.gen_rows[r].gen_plane[p].i_assembler.output_data_q);
      end
      always @(posedge clk) begin
        if(checking && mem_req && mem_we) begin
          if(!rst_n || clear || !write_enable || (read_req && read_ready) || mem_be==0 ||
             int'(mem_addr)>=(p==0?4:2)) $fatal(1,"WB_INVALID_PHYSICAL_WRITE");
          for(int b=0;b<32;b++) begin
            if(mem_be[b]) begin
              if(r>=cfg_rows || !payload_present[r][p][32*int'(mem_addr)+b] ||
                 payload_written[r][p][32*int'(mem_addr)+b] ||
                 !native_accepted[r][payload_origin[r][p][32*int'(mem_addr)+b]] ||
                 mem_data[8*b+:8] !== payload_value[r][p][32*int'(mem_addr)+b])
                $fatal(1,"WB_PHYSICAL_WRITE_BYTE row=%0d plane=%0d word=%0d byte=%0d",r,p,mem_addr,b);
              payload_written[r][p][32*int'(mem_addr)+b]=1;
              row_payload[r]++;epoch_payload++;payload_total++;
            end
          end
        end
        if(checking && mem_req && !mem_we && !(read_req && read_ready)) $fatal(1,"WB_UNREQUESTED_SRAM_READ");
      end
    end
  end

  always @(posedge clk) begin:monitor
    logic request_now;
    bit stalled_packet;
    logic [3:0][19:0] held_side_valid;
    logic [3:0][19:0][7:0] held_side_data;
    int k_now,n,target,native;
    ticks++;
    if(checking) begin
      check_control_known();
      if(!rst_n || clear) begin
        window_known=0;previous_rows=0;was_complete=0;
        #1;
        check_control_known();
        if(read_valid || read_ready || all_complete || pending || row_complete!=0 ||
           accepted_bytes!=0 || committed_bytes!=0) $fatal(1,"WB_CLEAR_STATE");
        for(int r=0;r<4;r++) begin
          for(int p=0;p<2;p++) if(window[r][p] !== 0) $fatal(1,"WB_CLEAR_WINDOW");
          for(int s=0;s<20;s++) if(side[r][s] !== 0) $fatal(1,"WB_CLEAR_SIDE");
        end
      end else begin
        stalled_packet=0;
        if(dut.map_valid) begin
          if($isunknown({dut.map_valid,dut.map_ready,targeted,assembler_ready,assembler_valid,
                         dut.i_mapper.side_mask_o})) $fatal(1,"WB_UNKNOWN_ATOMIC_CONTROL");
          if(!dut.map_ready) begin
            stalled_packet=1;
            if(|(targeted & assembler_valid & assembler_ready)) $fatal(1,"WB_PARTIAL_ASSEMBLER_ACCEPT");
            held_side_valid=dut.side_valid_q;
            for(int r=0;r<4;r++) for(int s=0;s<20;s++) held_side_data[r][s]=dut.side_q[r][s];
            if($countones(targeted)>=2 && |(targeted & assembler_ready) && |(targeted & ~assembler_ready)) begin
              mixed_target_stalls++;
              if(|dut.i_mapper.side_mask_o) side_mixed_stalls++;
            end
          end
        end
        if(window_known) check_windows(last_read_k,0);
        request_now=read_req && read_ready;k_now=int'(read_k);
        if(read_req && !read_ready) early_reads++;
        if(valid && ready) begin
          n=$countones(strb);
          if(n==0 || (strb & (strb+32'd1))!=0) $fatal(1,"WB_DRIVER_PREFIX");
          for(int b=0;b<n;b++) begin
            target=group_mode ? (int'(offset)+b)/cfg_size : int'(row);
            native=group_mode ? (int'(offset)+b)%cfg_size : int'(offset)+b;
            if(target>=cfg_rows || native>=cfg_size || native_accepted[target][native] ||
               native!=next_native[target] || data[8*b+:8] !== native_value[target][native])
              $fatal(1,"WB_DRIVER_UNIQUE_ORDER");
            native_accepted[target][native]=1;next_native[target]++;
          end
          epoch_accepted+=n;input_total+=n;packets_total++;
        end else if(valid) input_stalls++;
        if(!write_enable && |output_waiting) blocked_outputs++;
        #1;
        check_control_known();
        if(stalled_packet) begin
          if(dut.side_valid_q !== held_side_valid) $fatal(1,"WB_PARTIAL_SIDE_VALID");
          for(int r=0;r<4;r++) for(int s=0;s<20;s++)
            if(dut.side_q[r][s] !== held_side_data[r][s]) $fatal(1,"WB_PARTIAL_SIDE_DATA");
          // Older assembler outputs may still write SRAM here; that is legal.
        end
        for(int r=0;r<4;r++) begin
          for(int s=0;s<20;s++) begin
            if(side[r][s] !== 0) begin
              if(r>=cfg_rows || !side_present[r][s] ||
                 !native_accepted[r][side_origin[r][s]] || side[r][s] !== side_value[r][s])
                $fatal(1,"WB_SIDE_METADATA row=%0d side=%0d",r,s);
              if(!side_seen[r][s]) begin side_seen[r][s]=1;row_side[r]++;epoch_side++;side_total++;end
            end else if(side_seen[r][s]) $fatal(1,"WB_SIDE_LOST_BEFORE_CLEAR");
          end
          if(row_complete[r] && (r>=cfg_rows || next_native[r]!=cfg_size ||
                                 row_payload[r]+row_side[r]!=cfg_size)) $fatal(1,"WB_EARLY_ROW_COMPLETE");
          if(previous_rows[r] && !row_complete[r]) $fatal(1,"WB_ROW_COMPLETE_NOT_PERSISTENT");
        end
        previous_rows=row_complete;
        if(int'(accepted_bytes)!=epoch_accepted || int'(committed_bytes)!=epoch_payload+epoch_side ||
           int'(committed_bytes)>int'(accepted_bytes)) $fatal(1,"WB_COUNTERS accepted=%0d/%0d committed=%0d/%0d",
             accepted_bytes,epoch_accepted,committed_bytes,epoch_payload+epoch_side);
        if(epoch_accepted>epoch_payload+epoch_side && !pending) $fatal(1,"WB_LOST_PENDING");
        if(all_complete && (epoch_accepted!=cfg_rows*cfg_size || epoch_payload+epoch_side!=cfg_rows*cfg_size ||
                           pending || row_complete!=4'((1<<cfg_rows)-1))) $fatal(1,"WB_EARLY_ALL_COMPLETE");
        if(was_complete && !all_complete) $fatal(1,"WB_ALL_COMPLETE_NOT_PERSISTENT");
        was_complete=all_complete;
        if(read_ready !== all_complete) $fatal(1,"WB_READ_READY_GATE");
        if(read_valid !== request_now) $fatal(1,"WB_SYNCHRONOUS_READ_VALID");
        if(request_now) begin window_known=1;last_read_k=k_now;reads_total++;epoch_reads++;check_windows(k_now,1);end
        else if(window_known) begin check_windows(last_read_k,0);idle_total++;end
        else for(int r=0;r<4;r++) for(int p=0;p<2;p++)
          if(window[r][p] !== 0) $fatal(1,"WB_WINDOW_BEFORE_FIRST_READ");
      end
    end
  end

  always @(negedge clk) begin
    if(automatic_write) begin
      write_random={write_random[30:0],write_random[31]^write_random[21]^write_random[1]^write_random[0]};
      write_enable=traffic==0 || ticks%8==0 || (write_random[0] && write_random[3]);
    end
  end

  task automatic clear_epoch(input bit use_reset);
    automatic_write=0;
    if(clk!==0) @(negedge clk);
    valid=0;read_req=0;write_enable=0;
    if(use_reset) rst_n=0;else clear=1;
    @(negedge clk);rst_n=1;clear=0;
  endtask

  task automatic configure(input int p,nrows);
    int elements,ls,ln,hs,hn,ss,plane,dest;
    regions(p,cfg_size,elements,ls,ln,hs,hn,ss);
    cfg_p=p;cfg_rows=nrows;cfg_elements=elements;salt++;
    profile=qbs_pkg::qbs_weight_profile_e'(p);rows=3'(nrows);
    epoch_accepted=0;epoch_payload=0;epoch_side=0;epoch_reads=0;
    window_known=0;previous_rows=0;was_complete=0;
    for(int r=0;r<4;r++) begin
      next_native[r]=0;row_payload[r]=0;row_side[r]=0;
      for(int b=0;b<210;b++) begin native_accepted[r][b]=0;native_value[r][b]=pattern(p,r,b,salt);end
      for(int q=0;q<2;q++) for(int b=0;b<128;b++) begin
        payload_present[r][q][b]=0;payload_written[r][q][b]=0;payload_value[r][q][b]=0;payload_origin[r][q][b]=0;
      end
      for(int s=0;s<20;s++) begin side_present[r][s]=0;side_seen[r][s]=0;side_value[r][s]=0;side_origin[r][s]=0;end
      if(r<nrows) for(int b=0;b<cfg_size;b++) begin
        locate(p,b,plane,dest);
        if(plane<2) begin payload_present[r][plane][dest]=1;payload_value[r][plane][dest]=native_value[r][b];payload_origin[r][plane][dest]=b;end
        else begin side_present[r][dest]=1;side_value[r][dest]=native_value[r][b];side_origin[r][dest]=b;end
      end
    end
    checking=1;
  endtask

  task automatic send_native(input int grouped,phase, input int abort_stage);
    int cursor[4],r,limit,n,physical_phase,bound,target,native,total_cursor;
    bit held,fire,stop,first_drive;
    for(int i=0;i<4;i++) cursor[i]=0;
    r=0;held=0;bound=0;stop=0;total_cursor=0;first_drive=1;
    read_req=1;read_k=0;
    while(!stop) begin
      if(!first_drive) @(negedge clk);
      first_drive=0;
      limit=grouped?cfg_rows*cfg_size:cfg_size;
      physical_phase=grouped?phase:(phase+r*cfg_size)%32;
      n=cursor[r]==0?32-physical_phase:32;
      if(n>limit-cursor[r]) n=limit-cursor[r];
      group_mode=1'(grouped);row=2'(grouped?cfg_rows-1:r);offset=10'(cursor[r]);
      strb=n==32?'1:(32'd1<<n)-1;
      valid=held || traffic==0 || ticks%3!=0;
      for(int b=0;b<32;b++) begin
        target=grouped?(cursor[r]+b)/cfg_size:r;native=grouped?(cursor[r]+b)%cfg_size:cursor[r]+b;
        data[8*b+:8]=b<n?native_value[target][native]:8'(8'ha5^b);
      end
      @(posedge clk);fire=valid && ready;#2;
      if(fire) begin cursor[r]+=n;total_cursor+=n;held=0;end else if(valid) held=1;
      if(abort_stage==0 && fire) stop=1;
      else if(abort_stage==1 && |output_waiting) stop=1;
      else if(abort_stage<0 && total_cursor==cfg_rows*cfg_size) stop=1;
      if(!grouped && fire && !stop) begin
        r=(r+1)%cfg_rows;
        while(cursor[r]==cfg_size) r=(r+1)%cfg_rows;
      end
      bound++;
      if(bound>512) $fatal(1,"WB_INPUT_TIMEOUT");
    end
  endtask

  task automatic finish_epoch;
    int bound;
    automatic_write=0;
    @(negedge clk);valid=0;read_req=0;write_enable=1;
    bound=0;
    // After the final input edge: mapper transfer, first assembler word,
    // optional last carry flush. Draining is unthrottled for these three edges.
    check_control_known();
    while(all_complete!==1'b1 || pending!==1'b0) begin
      @(negedge clk);check_control_known();bound++;if(bound>3) $fatal(1,"WB_DRAIN_BOUND");
    end
    if(bound>max_drain) max_drain=bound;
    if(bound>profile_max_drain) profile_max_drain=bound;
    if(epoch_accepted!=cfg_rows*cfg_size || epoch_payload+epoch_side!=cfg_rows*cfg_size)
      $fatal(1,"WB_FINAL_NATIVE_COUNTS");
    if(epoch_reads!=0) $fatal(1,"WB_EARLY_ACCEPTED_READ");
    for(int k=0;k<cfg_elements;k+=16) begin
      @(negedge clk);read_req=1;read_k=8'(k);
      @(posedge clk);if(!read_ready) $fatal(1,"WB_COMPLETED_READ_NOT_READY");#2;
    end
    @(negedge clk);read_req=0;
    repeat(3) begin read_k=read_k^8'h10;@(posedge clk);#2;@(negedge clk);end
    if(epoch_reads!=cfg_elements/16) $fatal(1,"WB_PER_EPOCH_READ_COUNT");
  endtask

  task automatic run_epoch(input int p,nrows,grouped,phase,schedule, input bit reuse);
    int old_stalls;
    if(!reuse) clear_epoch(0);
    configure(p,nrows);traffic=schedule;automatic_write=1;write_enable=schedule==0;
    old_stalls=int'(input_stalls);
    send_native(grouped,phase,-1);
    if(schedule==0) begin
      unthrottled_stalls+=int'(input_stalls)-old_stalls;
      if(int'(input_stalls)!=old_stalls) $fatal(1,"WB_UNTHROTTLED_II1");
    end
    finish_epoch();
    if(reuse) reuse_cases++;else normal_cases++;
  endtask

  task automatic abort_and_reuse(input int p,grouped,stage,use_reset);
    int a,c,outputs,rp,rn;
    longint unsigned old_packets;
    clear_epoch(0);configure(p,4);traffic=0;automatic_write=0;write_enable=0;
    old_packets=packets_total;
    send_native(grouped,0,stage);
    a=epoch_accepted;c=epoch_payload+epoch_side;outputs=$countones(output_waiting);
    if(!pending || all_complete || read_ready || epoch_payload!=0 || (stage==1 && outputs==0))
      $fatal(1,"WB_ABORT_FIXTURE");
    clear_epoch(1'(use_reset));
    $display("WB_ABORT_PASS profile=%0d group=%0d stage=%0d reset=%0d packets=%0d accepted=%0d committed=%0d discarded=%0d outputs=%0d",
      p,grouped,stage,use_reset,packets_total-old_packets,a,c,a-c,outputs);
    abort_cases++;
    rp=p%9+1;rn=p%4+1;
    // No extra clear/idle epoch between deassertion and the reused input.
    run_epoch(rp,rn,1-grouped,(p*7+stage)%32,0,1);
    $display("WB_REUSE_PASS profile=%0d rows=%0d group=%0d phase=%0d",rp,rn,1-grouped,(p*7+stage)%32);
    read_req=1;read_k=0;
    @(posedge clk);if(!read_ready) $fatal(1,"WB_CANCEL_READ_NOT_ACCEPTED");#2;
    if(!read_valid) $fatal(1,"WB_CANCEL_FIXTURE");
    if(epoch_reads!=cfg_elements/16+1) $fatal(1,"WB_CANCEL_READ_COUNT");
    clear_epoch(1'(use_reset));cancel_cases++;
    if(read_valid || pending || all_complete) $fatal(1,"WB_CANCEL_READ_LEAK");
  endtask

  initial begin
    longint unsigned a,c,s,rd,rb,id,pk,ms,sm;
    int before_cases;
    repeat(3) @(negedge clk);rst_n=1;
`ifdef TARGET_SRAM_MC
    $fatal(1,"WB_GENERIC_REAL_SRAM_REQUIRED");
`endif
    $display("WB_SUITE_BEGIN version=1");
    $display("WB_RESOURCE mapper_packet_bits=%0d logical_low_bytes=%0d logical_high_bytes=%0d logical_sram_bytes=%0d target_sram_mc_min_words=8 target_sram_mc_physical_bytes=2048 compute_window_bits=%0d assembler_payload_bits=%0d side_storage_bits=%0d compiled_target_sram_mc=0",
      $bits(dut.i_mapper.packet_q),logical_low_bytes,logical_high_bytes,logical_low_bytes+logical_high_bytes,
      $bits(window[0][0]),assembler_payload_bits,$bits(dut.side_q));
    for(int p=1;p<=9;p++) begin
      profile_max_drain=0;
      a=input_total;pk=packets_total;c=payload_total;s=side_total;rd=reads_total;rb=read_bytes_total;id=idle_total;
      ms=mixed_target_stalls;sm=side_mixed_stalls;before_cases=normal_cases;
      for(int nrows=1;nrows<=4;nrows++) for(int grouped=0;grouped<2;grouped++)
        for(int phase=0;phase<32;phase++) for(int schedule=0;schedule<2;schedule++)
          run_epoch(p,nrows,grouped,phase,schedule,0);
      $display("WB_PROFILE_PASS profile=%0d cases=%0d packets=%0d native=%0d payload=%0d side=%0d reads=%0d read_bytes=%0d idle=%0d max_drain=%0d unthrottled_stalls=%0d mixed_stalls=%0d side_mixed_stalls=%0d",
        p,normal_cases-before_cases,packets_total-pk,input_total-a,payload_total-c,side_total-s,reads_total-rd,read_bytes_total-rb,idle_total-id,profile_max_drain,unthrottled_stalls,mixed_target_stalls-ms,side_mixed_stalls-sm);
    end
    for(int p=1;p<=9;p++) for(int grouped=0;grouped<2;grouped++)
      for(int stage=0;stage<2;stage++) for(int use_reset=0;use_reset<2;use_reset++)
        abort_and_reuse(p,grouped,stage,use_reset);
    if(input_stalls==0 || blocked_outputs==0 || early_reads==0) $fatal(1,"WB_BACKPRESSURE_OR_EARLY_READ_NOT_EXERCISED");
    if(mixed_target_stalls==0 || side_mixed_stalls==0) $fatal(1,"WB_MIXED_TARGET_STALL_NOT_EXERCISED");
    $display("WB_BANK_COMPONENT_PASS cases=%0d reuse_cases=%0d abort_cases=%0d cancel_cases=%0d packets=%0d accepted=%0d payload=%0d side=%0d reads=%0d read_bytes=%0d idle=%0d input_stalls=%0d blocked_outputs=%0d early_reads=%0d max_drain=%0d unthrottled_stalls=%0d mixed_stalls=%0d side_mixed_stalls=%0d",
      normal_cases,reuse_cases,abort_cases,cancel_cases,packets_total,input_total,payload_total,side_total,reads_total,read_bytes_total,idle_total,input_stalls,blocked_outputs,early_reads,max_drain,unthrottled_stalls,mixed_target_stalls,side_mixed_stalls);
    $finish;
  end
  initial begin #20000000;$fatal(1,"WB_WATCHDOG");end
endmodule
