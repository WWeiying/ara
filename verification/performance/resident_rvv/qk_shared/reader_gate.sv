// SPDX-License-Identifier: Apache-2.0
module reader_gate_tb;
  import akv_pkg::*;
  logic clk=0, rst=0;
  always #5 clk=~clk;
  logic cancel=0, start=0, ready, qk=0, heads=0;
  logic [6:0] tokens=1;
  logic [7:0] dimensions=64;
  logic [3:0] words=4;
  logic [2:0] base=0;
  logic coefficient_valid=0, coefficient_ready;
  logic [31:0] coefficient=0;
  logic row_read, query_read, column_start, column_busy, column_valid;
  logic [5:0] row_token;
  logic [3:0] row_word, query_word;
  logic [2:0] query_row;
  logic [6:0] column_dimension, column_tokens;
  logic [1:0] column_index, column_packet;
  logic [255:0] row_data, query_data, column_data;
  logic [3:0][1023:0] panel;
  logic stream_valid, stream_ready, stream_kind, done, done_ready=0, error, busy;
  logic [3:0] stream_active, lane_valid, lane_ready=0;
  logic [3:0][63:0] stream_data, lane_data;
  logic lane_kind, empty, conflict, write_busy;
  logic qwrite=0, kvwrite=0;
  logic [4:0] write_slot=0;
  logic [5:0] write_token=0;
  logic [7:0] write_offset=0;
  logic [127:0] write_data=0;
  akv_stream_e write_stream=AKV_STREAM_K;
  int epoch=0, cycle=0, case_id=0, checks=0;
  int raw_index=0, lane_index[4], qreads=0, columns=0, vreads=0;
  int stalls=0, lane_stalls=0, held_done=0, qlatency=0, vlatency=0;
  bit monitor=0, skew=0, stalled=0;
  logic [3:0] lane_stalled=0;
  logic [260:0] held_stream;
  logic [3:0][64:0] held_lane;
  int normal_cases=0, cancel_cases=0, reset_cases=0, invalid_cases=0;

  akv_resident_pv_reader dut (
    .clk_i(clk), .rst_ni(rst), .cancel_i(cancel), .start_valid_i(start),
    .start_ready_o(ready), .tokens_i(tokens), .words_i(words),
    .coefficient_valid_i(coefficient_valid), .coefficient_ready_o(coefficient_ready),
    .coefficient_i(coefficient), .row_read_o(row_read), .row_token_o(row_token),
    .row_word_o(row_word), .row_data_i(row_data), .stream_valid_o(stream_valid),
    .stream_ready_i(stream_ready), .stream_is_value_o(stream_kind), .stream_data_o(stream_data),
    .done_valid_o(done), .done_ready_i(done_ready), .done_error_o(error), .busy_o(busy),
    .qk_i(qk), .two_heads_i(heads), .dimensions_i(dimensions), .query_base_i(base),
    .query_read_o(query_read), .query_row_o(query_row), .query_word_o(query_word),
    .query_data_i(query_data), .column_start_o(column_start),
    .column_dimension_o(column_dimension), .column_tokens_o(column_tokens),
    .column_busy_i(column_busy), .column_valid_i(column_valid),
    .column_index_o(column_index), .column_packet_o(column_packet),
    .column_data_i(column_data), .stream_active_o(stream_active)
  );
  assign column_data=panel[column_index][256*column_packet+:256];
  akv_unified_context context_dut (
    .clk_i(clk), .rst_ni(rst), .abort_i(1'b0),
    .legacy_write_valid_i(qwrite), .legacy_write_slot_i(write_slot),
    .legacy_write_offset_i(write_offset), .legacy_row_bytes_i(9'd256),
    .legacy_write_data_i(write_data), .legacy_write_strb_i(16'hffff), .legacy_write_busy_o(),
    .v2_write_valid_i(kvwrite), .v2_write_stream_i(write_stream),
    .v2_write_token_i(write_token), .v2_write_offset_i(write_offset),
    .v2_write_data_i(write_data), .v2_write_strb_i(16'hffff), .v2_write_busy_o(),
    .write_busy_o(write_busy), .legacy_replay_read_i(query_read),
    .legacy_replay_slot_i({2'b0,query_row}), .legacy_replay_word_i(query_word),
    .legacy_replay_data_o(query_data), .v2_row_read_i(row_read), .v2_row_stream_i(AKV_STREAM_V),
    .v2_row_token_i(row_token), .v2_row_word_i(row_word), .v2_row_data_o(row_data),
    .column_start_i(column_start), .column_stream_i(AKV_STREAM_K),
    .column_dimension_i(column_dimension), .column_count_i(3'd4),
    .column_token_count_i(column_tokens), .column_busy_o(column_busy),
    .column_valid_o(column_valid), .column_data_o(panel), .column_bank_cycle_o(), .conflict_o(conflict)
  );
  resident_payload_fanout fanout (
    .clk_i(clk), .rst_ni(rst), .cancel_i(cancel), .valid_i(stream_valid),
    .ready_o(stream_ready), .active_i(stream_active), .is_value_i(stream_kind),
    .data_i(stream_data), .valid_o(lane_valid), .ready_i(lane_ready),
    .is_value_o(lane_kind), .data_o(lane_data), .empty_o(empty)
  );

  function automatic logic [15:0] value(input int kind, row, dim);
    // Disjoint, finite F16 encodings, unique across all stored Q/K/V elements.
    return 16'((epoch ? 32768 : 0)+(kind==0 ? 4096 : kind==1 ? 8192 : 16384)+row*128+dim);
  endfunction
  function automatic int offset(input int halfword);
    case (halfword)
      0: return 0;
      1: return 8;
      2: return 4;
      default: return 12;
    endcase
  endfunction
  function automatic logic [31:0] coeff(input int token);
    return {value(0,1,token),value(0,0,token)};
  endfunction
  function automatic int lane_packets(input int lane);
    return tokens>lane ? (int'(tokens)+15-lane)/16 : 0;
  endfunction
  function automatic logic [63:0] expected(input int lane, index, packets);
    int dim, packet, token;
    logic [63:0] result;
    result=0;
    if (qk) begin
      dim=index/(packets+1);
      packet=index%(packets+1)-1;
      if (packet<0) begin
        result[15:0]=value(0,base,dim);
        result[31:16]=heads ? value(0,int'(base)+1,dim) : 16'b0;
      end else for (int h=0;h<4;h++) begin
        token=16*packet+lane+offset(h);
        result[16*h+:16]=token<tokens ? value(1,token,dim) : 16'b0;
      end
    end else begin
      token=index/(int'(words)+1);
      packet=index%(int'(words)+1)-1;
      if (packet<0) result={32'b0,coeff(token)};
      else for (int h=0;h<4;h++)
        result[16*h+:16]=value(2,token,16*packet+lane+offset(h));
    end
    return result;
  endfunction

  // Pre-edge protocol checks; response checks use the post-edge SRAM outputs.
  always @(posedge clk) begin : check
    bit qr, vr;
    int qr_row, qr_word, vr_row, vr_word, packets, packet;
    logic [3:0] mask;
    cycle++;
    if (cycle>400000) $fatal(1,"GATE_TIMEOUT case=%0d",case_id);
    qr=query_read && rst; vr=row_read && rst;
    qr_row=query_row; qr_word=query_word; vr_row=row_token; vr_word=row_word;
    if (rst && !cancel) begin
      if (conflict) $fatal(1,"CONTEXT_CONFLICT");
      if (stalled && (!stream_valid || {stream_kind,stream_active,stream_data}!==held_stream))
        $fatal(1,"UNSTABLE_READER case=%0d",case_id);
      for (int l=0;l<4;l++)
        if (lane_stalled[l] && (!lane_valid[l] || {lane_kind,lane_data[l]}!==held_lane[l]))
          $fatal(1,"UNSTABLE_LANE case=%0d lane=%0d",case_id,l);
      if (monitor) begin
        packets=(int'(tokens)+15)/16;
        if (qr) begin
          if (!qk || query_row!==3'(int'(base)+qreads%(1+int'(heads))) ||
              query_word!==4'(qreads/(1+int'(heads)))) $fatal(1,"Q_ADDRESS case=%0d",case_id);
          qreads++;
        end
        if (vr) begin
          if (qk || row_token!==6'(vreads/int'(words)) || row_word!==4'(vreads%int'(words)))
            $fatal(1,"V_ADDRESS case=%0d",case_id);
          vreads++;
        end
        if (column_start) begin
          if (!qk || column_dimension!==7'(columns*4) || column_tokens!==tokens ||
              qreads!=(columns/4+1)*(1+int'(heads))) $fatal(1,"PANEL_ADDRESS case=%0d",case_id);
          columns++;
        end
        if (stream_valid) begin
          packet=raw_index%(packets+1)-1;
          mask=0;
          for (int l=0;l<4;l++) mask[l]=!qk || ((packet<0 ? 0 : packet*16)+l<tokens);
          if (stream_active!==mask || stream_kind!==(qk ? packet>=0 : raw_index%(int'(words)+1)!=0))
            $fatal(1,"STREAM_MASK_KIND case=%0d index=%0d",case_id,raw_index);
          if (qk && stream_kind && (column_index!==2'((raw_index/(packets+1))%4) ||
              column_packet!==2'(packet) || column_busy || !column_valid))
            $fatal(1,"PANEL_SLICE case=%0d",case_id);
          for (int l=0;l<4;l++)
            if (stream_data[l]!==expected(l,raw_index,packets))
              $fatal(1,"RAW_DATA case=%0d index=%0d lane=%0d got=%h want=%h",case_id,
                     raw_index,l,stream_data[l],expected(l,raw_index,packets));
          if (stream_ready) raw_index++;
          else stalls++;
        end
        for (int l=0;l<4;l++) if (lane_valid[l]) begin
          if ((qk && tokens<=l) || lane_kind!==(qk ? lane_index[l]%(lane_packets(l)+1)!=0 :
              lane_index[l]%(int'(words)+1)!=0) ||
              lane_data[l]!==expected(l,lane_index[l],lane_packets(l)))
            $fatal(1,"LANE_DATA case=%0d lane=%0d index=%0d",case_id,l,lane_index[l]);
          if (lane_ready[l]) begin lane_index[l]++; checks++; end
          else lane_stalls++;
        end
      end
    end
    stalled=rst && !cancel && stream_valid && !stream_ready;
    held_stream={stream_kind,stream_active,stream_data};
    lane_stalled=rst && !cancel ? lane_valid & ~lane_ready : 0;
    for (int l=0;l<4;l++) held_lane[l]={lane_kind,lane_data[l]};
    #1;
    if (qr) begin
      for (int i=0;i<16;i++) if (query_data[16*i+:16]!==value(0,qr_row,qr_word*16+i))
        $fatal(1,"Q_SRAM_LATENCY row=%0d word=%0d",qr_row,qr_word);
      qlatency++;
    end
    if (vr) begin
      for (int i=0;i<16;i++) if (row_data[16*i+:16]!==value(2,vr_row,vr_word*16+i))
        $fatal(1,"V_SRAM_LATENCY row=%0d word=%0d",vr_row,vr_word);
      vlatency++;
    end
  end

  always @(negedge clk) begin
    for (int l=0;l<4;l++) lane_ready[l]=!skew || ((cycle+3*l)%13>l+2 && cycle%41>=7);
  end
  task automatic tick;
    @(negedge clk); #1;
  endtask
  task automatic fill;
    for (int row=0;row<8;row++) for (int part=0;part<16;part++) begin
      tick(); qwrite=1; write_slot=5'(row); write_offset=8'(part*16);
      for (int i=0;i<8;i++) write_data[16*i+:16]=value(0,row,part*8+i);
    end
    tick(); qwrite=0;
    do tick(); while (write_busy);
    for (int kind=1;kind<=2;kind++) for (int row=0;row<64;row++)
      for (int part=0;part<16;part++) begin
        tick(); kvwrite=1; write_stream=kind==1 ? AKV_STREAM_K : AKV_STREAM_V;
        write_token=6'(row); write_offset=8'(part*16);
        for (int i=0;i<8;i++) write_data[16*i+:16]=value(kind,row,part*8+i);
      end
    tick(); kvwrite=0; tick();
  endtask
  task automatic launch(input bit mode, input int t,h,d,b,s);
    tick();
    if (!ready || !empty || column_busy) $fatal(1,"UNCLEAN_LAUNCH");
    qk=mode; tokens=7'(t); heads=h==2; dimensions=8'(d); words=4'(d/16); base=3'(b);
    skew=s!=0; raw_index=0; qreads=0; columns=0; vreads=0;
    for (int l=0;l<4;l++) lane_index[l]=0;
    monitor=1; start=1; coefficient_valid=!mode; coefficient=coeff(0); case_id++;
    tick(); start=0;
  endtask
  task automatic retire(input bit bad);
    coefficient_valid=0;
    repeat (5) begin
      tick();
      if (!done || error!==bad || stream_valid || query_read || row_read || column_start || ready)
        $fatal(1,"DONE_NOT_HELD");
      held_done++;
    end
    done_ready=1; tick(); done_ready=0; tick();
    if (!ready || busy || done) $fatal(1,"NOT_IDLE");
  endtask
  task automatic run_shape(input bit mode, input int t,h,d,b,s);
    int timeout_count;
    launch(mode,t,h,d,b,s);
    timeout_count=0;
    while (!done || !empty) begin
      tick();
      coefficient=coeff(raw_index/(int'(words)+1));
      if (++timeout_count>15000) $fatal(1,"CASE_TIMEOUT case=%0d",case_id);
    end
    if (error || raw_index!=(mode ? d*(1+(t+15)/16) : t*(1+d/16)) ||
        qreads!=(mode ? d/16*h : 0) || columns!=(mode ? d/4 : 0) || vreads!=(mode ? 0 : t*d/16))
      $fatal(1,"WORK_COUNTS case=%0d raw=%0d q=%0d k=%0d v=%0d",case_id,raw_index,qreads,columns,vreads);
    for (int l=0;l<4;l++)
      if (lane_index[l]!=(mode ? (t>l ? d*(1+lane_packets(l)) : 0) : t*(1+d/16)))
        $fatal(1,"LANE_COUNTS case=%0d lane=%0d",case_id,l);
    retire(0); monitor=0; normal_cases++;
    $display("READER_GATE_CASE qk=%0d tokens=%0d heads=%0d dimensions=%0d base=%0d skew=%0d qreads=%0d columns=%0d vreads=%0d",
             mode,t,h,d,b,s,qreads,columns,vreads);
  endtask
  task automatic interrupt_case(input int phase, input bit reset_it);
    int timeout_count, busy_cycles, repeat_pulses;
    launch(phase!=0,64,2,128,6,1);
    timeout_count=0;
    // Stop with a real SRAM response pending, a running gather, or a held packet.
    while (!(phase==0 ? row_read : phase==1 ? query_read : phase==2 ? column_start :
             stream_valid && stream_kind && !stream_ready)) begin
      tick();
      if (++timeout_count>1000) $fatal(1,"INTERRUPT_PHASE_MISSING");
    end
    tick(); monitor=0;
    if (reset_it) begin
      rst=0; coefficient_valid=0; repeat (3) tick(); rst=1; tick();
      if (!ready || !empty || column_busy || done || stream_valid) $fatal(1,"RESET_RECOVERY");
      reset_cases++; epoch=1-epoch; fill();
    end else begin
      if (phase==2 && !column_busy) $fatal(1,"CANCEL_BUSY_NOT_EXERCISED");
      cancel=1; coefficient_valid=0; tick();
      timeout_count=0; busy_cycles=0; repeat_pulses=0;
      do begin
        if (stream_valid || row_read || query_read || column_start || ready)
          $fatal(1,"CANCEL_DRAIN_REQUEST_LEAK");
        if (column_busy) begin
          busy_cycles++;
          if (done) $fatal(1,"CANCEL_TERMINAL_BEFORE_COLUMN_DRAIN");
        end
        cancel=phase==2 && timeout_count==1;
        if (cancel) repeat_pulses++;
        if (!done) begin
          tick();
          if (++timeout_count>12) $fatal(1,"CANCEL_DRAIN_TIMEOUT");
        end
      end while (!done);
      cancel=0;
      if (column_busy || stream_valid || row_read || query_read || column_start)
        $fatal(1,"CANCEL_TERMINAL_LEAK");
      if (phase==2 && (busy_cycles==0 || repeat_pulses!=1)) $fatal(1,"MISSING_BUSY_CANCEL_REPEAT");
      $display("READER_GATE_CANCEL phase=%0d busy_cycles=%0d repeat_pulses=%0d",phase,busy_cycles,repeat_pulses);
      retire(1); cancel_cases++;
    end
    $display("READER_GATE_INTERRUPT phase=%0d reset=%0d",phase,reset_it);
    run_shape(0,1,1,64,0,1);
    run_shape(1,17,2,96,3,1);
  endtask
  task automatic invalid(input int t,h,d,b);
    launch(1,t,h,d,b,0); monitor=0;
    if (!done || !error || qreads || columns || stream_valid) $fatal(1,"BAD_COMMAND_ACCEPTED");
    retire(1); invalid_cases++;
  endtask

  initial begin
    int ts[6]='{1,2,3,9,17,64};
    int ds[3]='{64,96,128};
    repeat (3) tick(); rst=1; tick();
    if ($bits(dut.data_q)!=512 || $size(dut.data_q)!=2 ||
        $bits(context_dut.i_kv_store.column_data_q)!=4096 ||
        context_dut.i_q_store.NumWords!=64 || context_dut.i_kv_store.BankDepth!=128)
      $fatal(1,"STORAGE_GEOMETRY");
    fill();
    for (int s=0;s<2;s++) for (int di=0;di<3;di++) for (int h=1;h<=2;h++)
      for (int ti=0;ti<6;ti++) begin
        run_shape(0,ts[ti],h,ds[di],0,s);
        run_shape(1,ts[ti],h,ds[di],ti%2==0 ? 3 : 8-h,s);
        run_shape(0,ts[ti],h,ds[di],0,s);
      end
    for (int r=0;r<2;r++) for (int p=0;p<4;p++) interrupt_case(p,r!=0);
    invalid(0,1,64,0); invalid(65,1,64,0); invalid(1,1,32,0); invalid(1,2,64,7);
    if (stalls==0 || lane_stalls==0) $fatal(1,"NO_BACKPRESSURE");
    $display("READER_GATE_PASS normal=%0d cancel=%0d reset=%0d invalid=%0d checks=%0d qlatency=%0d vlatency=%0d stalls=%0d lane_stalls=%0d held_done=%0d",
             normal_cases,cancel_cases,reset_cases,invalid_cases,checks,qlatency,vlatency,stalls,lane_stalls,held_done);
    $finish;
  end
endmodule
