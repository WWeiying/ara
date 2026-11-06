`timescale 1ns/1ps
module qbs_wide_compute_tb #(parameter bit Wide = 0);
  import qbs_pkg::*;
  import fpnew_pkg::*;
  localparam int WB = Wide ? 32 : 16;
  logic clk=0, rst_n=0;
  always #5 clk=~clk;
  logic command_valid=0, command_ready, fault=0, fault_done;
  qbs_weight_profile_e profile;
  qbs_activation_layout_e activation_layout;
  qbs_weight_layout_e weight_layout;
  logic [3:0] m;
  logic [5:0] n;
  logic [8:0] kb;
  logic wvalid=0,wready,wbank=0,wgroup=0;
  logic [2:0] wrows=0;
  logic [1:0] wrow=0;
  logic [9:0] woffset=0;
  logic [WB*8-1:0] wdata=0;
  logic [WB-1:0] wstrb=0;
  logic avalid=0,aready;
  logic [7:0] ak=0;
  logic [1:0] actx=0;
  logic [11:0] aoffset=0;
  logic [127:0] adata=0;
  logic [15:0] astrb=0;
  logic [7:0] expected_k;
  logic [5:0] expected_row;
  logic [2:0] expected_rows;
  logic expected_bank,need_a,need_w;
  logic result_valid,result_consumed=0,result_read_valid,busy;
  logic [6:0] read_index=0;
  logic [3:0] read_row=0;
  logic [31:0] read_data,bank_data[8];
  logic [7:0] bank_valid;
  logic [4:0] flags;
  logic [31:0] tiles,weights,activations,pairs,capacity,dots,uops,updates;
  logic phase_compute;
  qbs_compute_engine #(.WideWeightIngress(Wide),.WideMatrixDot(1'b1)) dut (
    .clk_i(clk),.rst_ni(rst_n),.command_valid_i(command_valid),.command_ready_o(command_ready),
    .command_weight_profile_i(profile),.command_activation_profile_i(qbs_default_activation_profile(profile)),
    .command_weight_layout_i(weight_layout),.command_activation_layout_i(activation_layout),
    .command_m_i(m),.command_n_i(n),.command_k_blocks_i(kb),.command_activation_lookahead_i(1'b0),
    .command_seed_i(1'b0),.seed_valid_i(1'b0),.seed_ready_o(),.seed_row_i('0),.seed_mask_i('0),
    .seed_data_i('{default:'0}),.seed_done_i(1'b0),.fault_i(fault),.fault_done_o(fault_done),
    .weight_write_valid_i(wvalid),.weight_write_ready_o(wready),.weight_write_bank_i(wbank),
    .weight_write_row_count_i(wrows),.weight_write_group_i(wgroup),.weight_write_row_i(wrow),
    .weight_write_offset_i(woffset),.weight_write_data_i(wdata),.weight_write_strb_i(wstrb),
    .activation_write_valid_i(avalid),.activation_write_ready_o(aready),.activation_write_k_block_i(ak),
    .activation_write_context_i(actx),.activation_write_offset_i(aoffset),
    .activation_write_data_i(adata),.activation_write_strb_i(astrb),
    .expected_k_block_o(expected_k),.expected_activation_k_block_o(),.expected_row_base_o(expected_row),
    .expected_row_count_o(expected_rows),.expected_weight_bank_o(expected_bank),
    .activation_block_needed_o(need_a),.weight_block_needed_o(need_w),
    .result_valid_o(result_valid),.result_consumed_i(result_consumed),.result_read_index_i(read_index),
    .result_read_valid_o(result_read_valid),.result_read_data_o(read_data),.result_bank_read_row_i(read_row),
    .result_bank_read_valid_o(bank_valid),.result_bank_read_data_o(bank_data),.result_fflags_o(flags),
    .busy_o(busy),.phase_activation_load_o(),.phase_weight_load_o(),.phase_compute_o(phase_compute),
    .phase_drain_o(),.weight_prefetch_wait_cycles_o(),.tiles_computed_o(tiles),.weight_bytes_o(weights),
    .activation_bytes_o(activations),.useful_pairs_o(pairs),.pair_capacity_o(capacity),
    .dot_active_cycles_o(dots),.fp_uop_issue_o(uops),.fp_table_occupancy_sum_o(),
    .fp_table_occupancy_max_o(),.fp_table_full_cycles_o(),.accumulator_updates_o(updates)
  );

  byte wmem[256][32][210],amem[256][2336];
  bit wseen[256][32][210],aseen[256][2336],oseen[128];
  logic [31:0] golden[128];
  int profile_id,m_i,n_i,k_i,wl_i,al_i,block_size,act_size,storage_m,expected_flags;
  int expected_c[8],case_id=0,episode=0;
  int wbytes=0,abytes=0,wbeats=0,stalls=0,overlap=0,result_wait=0,probe_edges=0,probe_bytes=0;
  int normal_count=0,recovery_count=0,fault_count=0,total_overlap=0,total_stalls=0;
  int request_k[128],slot_k[16];
  bit checking=0,tracing=0,probe_enabled=0;
  wire pending_weight;
  if(Wide) begin:gen_pending
    assign pending_weight=dut.gen_weight_storage[0].gen_wide.pending;
  end else begin:gen_pending_legacy
    assign pending_weight=dut.i_block_adapter_bank0.weight_write_pending;
  end

  function automatic int size_for(input int p);
    case(p)
      1:return 144;2:return 210;3:return 18;4:return 176;5:return 110;
      6:return 34;7:return 84;8:return 22;9:return 18;
      default:$fatal(1,"WC_PROFILE");
    endcase
    return 0;
  endfunction

  task automatic known_controls;
    if($isunknown({command_ready,wready,aready,result_valid,result_read_valid,busy,flags,
       need_a,need_w,expected_k,expected_row,expected_rows,expected_bank,fault_done,
       tiles,weights,activations,pairs,capacity,dots,uops,updates})) $fatal(1,"WC_UNKNOWN_CONTROL");
  endtask

`define FP dut.i_fp_accumulator
  task automatic fp_event(input int slot,kind,operation,modifier,rounding,
                           input logic [31:0] a,b,c);
    int acc;
    acc=int'(`FP.entry_accumulator_index_q[slot]);
    if($isunknown({a,b,c,`FP.entry_state_q[slot]})) $fatal(1,"WC_UNKNOWN_FP_EVENT");
    $display("WC_FP episode=%0d acc=%0d block=%0d kind=%0d state=%0d op=%0d mod=%0d rm=%0d a=%08h b=%08h c=%08h",
      episode,acc,slot_k[slot],kind,int'(`FP.entry_state_q[slot]),operation,modifier,rounding,a,b,c);
  endtask

  always @(posedge clk) begin:monitor
    int read_k_now,oldword;
    bit owned_probe,read_now;
    if(checking && rst_n) begin
      known_controls();
      if(wvalid && wready) begin
        wbytes+=$countones(wstrb);wbeats++;
        if(phase_compute && wbank!=dut.active_weight_bank_q) overlap++;
      end
      if(avalid && aready) abytes+=$countones(astrb);
      if(wvalid && !wready) stalls++;
      if(tracing) begin
        if(`FP.request_valid_i && `FP.request_ready_o) begin
          slot_k[int'(`FP.request_slot_i)]=request_k[int'(`FP.request_accumulator_index_i)];
          request_k[int'(`FP.request_accumulator_index_i)]++;
        end
        if(`FP.cast_fire) fp_event(int'(`FP.cast_index),0,int'(I2F),0,int'(RNE),`FP.cast_operands[0],0,0);
        if(`FP.fp_fire) fp_event(int'(`FP.fp_tag_in),1,int'(`FP.fp_operation),int'(`FP.fp_operation_modifier),
          int'(`FP.fp_round_mode),`FP.fp_operands[0],`FP.fp_operands[1],`FP.fp_operands[2]);
        if(`FP.half_fire) fp_event(int'(`FP.half_index),2,0,0,int'(RNE),
          `FP.entry_scale_value_q[`FP.half_index],0,0);
      end
      owned_probe=Wide && probe_enabled && wvalid && wbank==0 && wrows==1 &&
          dut.weight_bank_row_count_q[0]==4 && !dut.clear_weight[0];
      read_now=dut.buffer_read_valid && dut.active_weight_bank_q==0;
      read_k_now=int'(dut.buffer_read_k_base);
      if(owned_probe) begin
        if(wready || dut.bank0_row_count!==3'd4 || dut.all_weight_complete[0]!==1'b1)
          $fatal(1,"WC_OWNED_FUTURE_TAIL_METADATA");
        probe_edges++;
      end
      #1;
      known_controls();
      if(owned_probe && !dut.clear_weight[0]) begin
        if(dut.bank0_row_count!==3'd4 || dut.all_weight_complete[0]!==1'b1)
          $fatal(1,"WC_OWNED_EPOCH_CHANGED");
        for(int r=0;r<4;r++) for(int b=0;b<16;b++)
          if(dut.weight_side_bank[0][r][b] !== wmem[0][r][b]) $fatal(1,"WC_OWNED_SIDE_CHANGED");
        if(read_now) begin
          oldword=(read_k_now/64)*2+(read_k_now/16)%2;
          for(int r=0;r<4;r++) for(int b=0;b<16;b++) begin
            if(dut.weight_window_bank[0][r][0][8*b+:8] !== wmem[0][r][16+oldword*16+b])
              $fatal(1,"WC_OWNED_FOUR_ROW_WINDOW");
            probe_bytes++;
          end
        end
      end
    end
  end
`undef FP

  // Tasks enter/leave on a falling edge. VALID never depends on READY.
  task automatic send_weight(input bit bank,grouped,input int rows,row,offset,count,
                              input logic [WB*8-1:0] data);
    int bound;
    logic [WB*8+WB+16:0] held;
    wbank=bank;wgroup=grouped;wrows=3'(rows);wrow=2'(row);woffset=10'(offset);
    wdata=data;wstrb=count==WB?'1:(WB'(1)<<count)-1;wvalid=1;
    held={wbank,wgroup,wrows,wrow,woffset,wdata,wstrb};bound=0;
    do begin
      @(posedge clk);known_controls();
      if({wbank,wgroup,wrows,wrow,woffset,wdata,wstrb} !== held) $fatal(1,"WC_HELD_WEIGHT_CHANGED");
      bound++;if(bound>100000) $fatal(1,"WC_WEIGHT_TIMEOUT");
    end while(wready!==1'b1);
    @(negedge clk);wvalid=0;
  endtask

  task automatic send_activation(input int k,ctx,offset,count,input logic [127:0] data);
    int bound;
    ak=8'(k);actx=2'(ctx);aoffset=12'(offset);adata=data;
    astrb=count==16?'1:(16'd1<<count)-1;avalid=1;bound=0;
    do begin
      @(posedge clk);known_controls();bound++;
      if(bound>100000) $fatal(1,"WC_ACTIVATION_TIMEOUT");
    end while(aready!==1'b1);
    @(negedge clk);avalid=0;
  endtask

  task automatic await_tile(input int k,base);
    int bound;
    bound=0;
    while(!(busy && int'(expected_k)==k && int'(expected_row)==base)) begin
      @(negedge clk);known_controls();bound++;
      if(bound>100000) $fatal(1,"WC_TILE_CURSOR_TIMEOUT k=%0d row=%0d",k,base);
    end
  endtask

  task automatic weight_tile(input int k,base,rows,input bit bank,early);
    logic [WB*8-1:0] data;
    int cursor,count,limit,row,off,phase;
    bit grouped;
    grouped=wl_i==2;row=0;cursor=0;limit=grouped?rows*block_size:block_size;
    phase=probe_enabled?0:(case_id*7+k*3+base)%WB;
    while(row<rows) begin
      count=cursor==0?WB-phase:WB;if(count>limit-cursor) count=limit-cursor;
      data='0;
      for(int b=0;b<WB;b++) if(b<count) begin
        off=cursor+b;
        data[8*b+:8]=grouped?wmem[k][base+off/block_size][off%block_size]:wmem[k][base+row][off];
      end
      send_weight(bank,grouped,rows,row,cursor,count,data);
      cursor+=count;
      if(cursor==limit) begin cursor=0;row=grouped?rows:row+1;end
      if(!probe_enabled && (cursor+case_id+k)%11==3) @(negedge clk);
    end
  endtask

  task automatic feed_weights;
    bit bank,early;
    int rows;
    for(int k=0;k<k_i;k++) for(int base=0;base<n_i;base+=4) begin
      rows=n_i-base<4?n_i-base:4;
      early=Wide && probe_enabled && k==0 && base==8;
      if(!early) await_tile(k,base);
      else if(!phase_compute || dut.active_weight_bank_q!==1'b0 || dut.bank0_row_count!==3'd4)
        $fatal(1,"WC_FUTURE_TAIL_FIXTURE_NOT_ACTIVE");
      // Tile identity is copied once, never wired to advancing live cursor outputs.
      bank=early?1'b0:expected_bank;
      weight_tile(k,base,rows,bank,early);
    end
  endtask

  task automatic activation_block(input int k);
    logic [127:0] data;
    int offset,count,ctx,limit;
    limit=al_i==1?act_size:storage_m*act_size;
    for(int c=0;c<(al_i==1?m_i:1);c++) begin
      for(offset=0;offset<limit;offset+=16) begin
        count=limit-offset<16?limit-offset:16;data='0;
        for(int b=0;b<16;b++) if(b<count) data[8*b+:8]=amem[k][c*act_size+offset+b];
        ctx=al_i==1?c:0;
        send_activation(k,ctx,offset,count,data);
      end
    end
  endtask

  task automatic feed_activations;
    int bound;
    for(int k=0;k<k_i;k++) begin
      bound=0;
      while(!(need_a && int'(expected_k)==k)) begin
        @(negedge clk);known_controls();bound++;
        if(bound>100000) $fatal(1,"WC_ACTIVATION_CURSOR_TIMEOUT");
      end
      activation_block(k);
    end
  endtask

  task automatic start_command(input bit trace_on,input int id);
    int bound;
    tracing=0;
    while(command_ready!==1'b1) @(negedge clk);
    wbytes=0;abytes=0;wbeats=0;stalls=0;overlap=0;result_wait=0;probe_edges=0;probe_bytes=0;
    for(int a=0;a<128;a++) request_k[a]=0;
    for(int s=0;s<16;s++) slot_k[s]=-1;
    episode=id;
    profile=qbs_weight_profile_e'(profile_id);weight_layout=qbs_weight_layout_e'(wl_i);
    activation_layout=qbs_activation_layout_e'(al_i);m=4'(m_i);n=6'(n_i);kb=9'(k_i);
    @(negedge clk);command_valid=1;bound=0;
    do begin @(posedge clk);bound++;if(bound>32) $fatal(1,"WC_COMMAND_TIMEOUT");end while(!command_ready);
    @(negedge clk);command_valid=0;tracing=trace_on;
  endtask

  task automatic normal_command(input bit recovery,input int id);
    int bound;
    logic [4:0] held_flags;
    start_command(1,id);
    fork feed_weights();feed_activations();join
    bound=0;
    while(result_valid!==1'b1) begin
      @(negedge clk);known_controls();bound++;if(bound>100000) $fatal(1,"WC_RESULT_TIMEOUT");
    end
    if(flags!==5'(expected_flags) || tiles!==32'(expected_c[0]) || weights!==32'(expected_c[1]) ||
       activations!==32'(expected_c[2]) || pairs!==32'(expected_c[3]) || capacity!==32'(expected_c[4]) ||
       dots!==32'(expected_c[5]) || uops!==32'(expected_c[6]) || updates!==32'(expected_c[7]) ||
       wbytes!=expected_c[1] || abytes!=expected_c[2]) $fatal(1,"WC_GOLDEN_COUNTER_OR_FLAGS case=%0d",case_id);
    held_flags=flags;
    repeat(5) begin
      @(negedge clk);known_controls();
      if(result_valid!==1'b1 || command_ready || flags!==held_flags || dut.integer_busy || dut.fp_busy)
        $fatal(1,"WC_RESULT_NOT_HELD");
      result_wait++;
    end
    for(int index=0;index<128;index++) if(oseen[index]) begin
      read_index=7'(index);read_row=4'(index/8);#1;
      if(result_read_valid!==1'b1 || read_data!==golden[index] || bank_valid[index%8]!==1'b1 ||
         bank_data[index%8]!==golden[index]) $fatal(1,"WC_GOLDEN_OUTPUT case=%0d index=%0d",case_id,index);
      $display("WC_OUTPUT episode=%0d index=%0d bits=%08h",episode,index,read_data);
    end
    if(Wide && probe_enabled && (probe_edges==0 || probe_bytes==0)) $fatal(1,"WC_MISSING_OWNED_FUTURE_TAIL");
    $display("WC_CASE episode=%0d case=%0d recovery=%0d profile=%0d m=%0d n=%0d kb=%0d wl=%0d al=%0d flags=%0d tiles=%0d weight=%0d activation=%0d pairs=%0d capacity=%0d dot=%0d uops=%0d updates=%0d accepted=%0d act_accepted=%0d beats=%0d stalls=%0d overlap=%0d result_wait=%0d probe_edges=%0d probe_bytes=%0d",
      episode,case_id,recovery,profile_id,m_i,n_i,k_i,wl_i,al_i,flags,tiles,weights,activations,pairs,capacity,dots,uops,updates,
      wbytes,abytes,wbeats,stalls,overlap,result_wait,probe_edges,probe_bytes);
    total_overlap+=overlap;total_stalls+=stalls;
    if(recovery) recovery_count++;else normal_count++;
    @(negedge clk);result_consumed=1;
    @(negedge clk);result_consumed=0;tracing=0;
    if(command_ready!==1'b1 || result_valid) $fatal(1,"WC_RESULT_RETIRE");
  endtask

  task automatic fault_case(input int kind);
    int bound;
    logic [WB*8-1:0] data;
    bit reached;
    start_command(0,2000+kind);
    if(kind==0) begin
      data='0;for(int b=0;b<WB;b++) data[8*b+:8]=wmem[0][0][b];
      send_weight(0,0,4,0,0,WB,data);
      if(pending_weight!==1'b1) $fatal(1,"WC_PENDING_ABORT_NOT_PENDING");
    end else begin
      weight_tile(0,0,4,0,0);
      activation_block(0);
      reached=0;bound=0;
      while(!reached) begin
        case(kind)
          1:reached=dut.i_profile_engine_int.i_dot_array.quant_valid_q===1'b1;
          2:reached=dut.i_profile_engine_int.i_dot_array.product_valid_q===1'b1;
          3:reached=dut.i_profile_engine_int.correction_operand_q[0].valid===1'b1;
          4:reached=dut.i_profile_engine_int.correction_product_q[0].valid===1'b1;
        endcase
        if(!reached) @(negedge clk);
        bound++;if(bound>2048) $fatal(1,"WC_FAULT_STAGE_NOT_REACHED kind=%0d",kind);
      end
    end
    fault=1;bound=0;
    while(fault_done!==1'b1) begin
      @(negedge clk);known_controls();bound++;
      if(result_valid || wready || aready) $fatal(1,"WC_FAULT_EXPOSED_RESULT_OR_READY");
      if(bound>2048) $fatal(1,"WC_FAULT_DRAIN_TIMEOUT");
    end
    if(dut.integer_busy || dut.fp_busy || dut.i_profile_engine_int.correction_pipeline_busy)
      $fatal(1,"WC_FAULT_NOT_DRAINED");
    @(negedge clk);fault=0;
    if(command_ready!==1'b1 || result_valid || pending_weight) $fatal(1,"WC_FAULT_NOT_RECOVERED");
    $display("WC_FAULT kind=%0d pending=%0d drain=%0d",kind,kind==0,bound);fault_count++;
    normal_command(1,1000+kind);
  endtask

  task automatic read_case(input int fd,ordinal);
    string token;
    int rc,id,k,base,rows,row,offset,ctx,byte_index,output_index;
    logic [15:0] mask;
    logic [127:0] data;
    rc=$fscanf(fd,"%s %d %d %d %d %d %d %d %h",token,id,profile_id,wl_i,al_i,m_i,n_i,k_i,expected_flags);
    if(rc!=9 || token!="CMD" || id!=ordinal || profile_id<1 || profile_id>9 || m_i<1 || m_i>8 ||
       n_i<1 || n_i>(m_i>4?16:32) || k_i<1 || k_i>256 || wl_i<1 || wl_i>2 || al_i<1 || al_i>3)
      $fatal(1,"WC_BAD_COMMAND");
    case_id=id;block_size=size_for(profile_id);act_size=(profile_id inside {1,2,4,5,7})?292:34;
    storage_m=al_i==1?m_i:(al_i==2?4:8);
    for(int a=0;a<128;a++) begin oseen[a]=0;golden[a]=0;end
    for(int kk=0;kk<k_i;kk++) begin
      for(int r=0;r<n_i;r++) for(int b=0;b<block_size;b++) wseen[kk][r][b]=0;
      for(int b=0;b<storage_m*act_size;b++) aseen[kk][b]=0;
      for(int rb=0;rb<n_i;rb+=4) begin
        rc=$fscanf(fd,"%s %d %d %d",token,k,base,rows);
        if(rc!=4 || token!="T" || k!=kk || base!=rb || rows!=(n_i-rb<4?n_i-rb:4)) $fatal(1,"WC_BAD_TILE");
        while(1) begin
          rc=$fscanf(fd,"%s",token);if(rc!=1) $fatal(1,"WC_TRUNCATED_TILE");
          if(token=="ENDT") break;
          if(token=="W") begin
            rc=$fscanf(fd,"%d %d %h %h",row,offset,mask,data);
            if(rc!=4 || row<0 || row>=rows || offset<0 || offset>=block_size || mask==0 ||
               ((17'(mask)+1)&17'(mask))!=0) $fatal(1,"WC_BAD_WEIGHT_RECORD");
            for(int b=0;b<16;b++) if(mask[b]) begin
              if(offset+b>=block_size || wseen[k][base+row][offset+b]) $fatal(1,"WC_DUP_WEIGHT");
              wseen[k][base+row][offset+b]=1;wmem[k][base+row][offset+b]=data[8*b+:8];
            end
          end else if(token=="A") begin
            rc=$fscanf(fd,"%d %d %h %h",ctx,offset,mask,data);
            if(rc!=4 || base!=0 || ctx<0 || ctx>=(al_i==1?m_i:1) || offset<0 || mask==0 ||
               ((17'(mask)+1)&17'(mask))!=0) $fatal(1,"WC_BAD_ACTIVATION_RECORD");
            for(int b=0;b<16;b++) if(mask[b]) begin
              byte_index=ctx*act_size+offset+b;
              if(byte_index>=storage_m*act_size || aseen[k][byte_index]) $fatal(1,"WC_DUP_ACTIVATION");
              aseen[k][byte_index]=1;amem[k][byte_index]=data[8*b+:8];
            end
          end else $fatal(1,"WC_UNEXPECTED_TILE_TOKEN");
        end
      end
      for(int r=0;r<n_i;r++) for(int b=0;b<block_size;b++)
        if(!wseen[kk][r][b]) $fatal(1,"WC_MISSING_WEIGHT_BYTE");
      for(int b=0;b<storage_m*act_size;b++) if(!aseen[kk][b]) $fatal(1,"WC_MISSING_ACTIVATION_BYTE");
    end
    for(int o=0;o<m_i*n_i;o++) begin
      rc=$fscanf(fd,"%s %d %h",token,output_index,data[31:0]);
      if(rc!=3 || token!="O" || output_index<0 || output_index>=128 || oseen[output_index] ||
         output_index/(m_i>4?16:32)>=m_i || output_index%(m_i>4?16:32)>=n_i) $fatal(1,"WC_BAD_OUTPUT");
      oseen[output_index]=1;golden[output_index]=data[31:0];
    end
    rc=$fscanf(fd,"%s %d %d %d %d %d %d %d %d",token,expected_c[0],expected_c[1],expected_c[2],
      expected_c[3],expected_c[4],expected_c[5],expected_c[6],expected_c[7]);
    if(rc!=9 || token!="C") $fatal(1,"WC_BAD_COUNTERS");
    rc=$fscanf(fd,"%s",token);if(rc!=1 || token!="END") $fatal(1,"WC_MISSING_END");
  endtask

  initial begin
    string path,token;
    int fd,rc,cases;
    profile=QBS_WEIGHT_PROFILE_INVALID;weight_layout=QBS_WEIGHT_LAYOUT_ROW_MAJOR;
    activation_layout=QBS_ACTIVATION_LAYOUT_ROW_MAJOR;m=1;n=1;kb=1;
    if(!$value$plusargs("QBS_COMMAND_VECTOR_FILE=%s",path)) $fatal(1,"WC_MISSING_VECTOR_PATH");
    fd=$fopen(path,"r");if(fd==0) $fatal(1,"WC_VECTOR_OPEN");
    rc=$fscanf(fd,"%s %d",token,cases);if(rc!=2 || token!="QBSCMD1" || cases<1) $fatal(1,"WC_BAD_HEADER");
    repeat(4) @(negedge clk);rst_n=1;checking=1;
    $display("WC_CONFIG version=1 wide=%0d weight_bits=%0d matrix=1",Wide,WB*8);
    for(int ordinal=0;ordinal<cases;ordinal++) begin
      read_case(fd,ordinal);
      probe_enabled=profile_id==1 && m_i==4 && n_i==9 && k_i==2;
      if(ordinal==0) for(int kind=0;kind<5;kind++) fault_case(kind);
      normal_command(0,ordinal);
    end
    rc=$fscanf(fd,"%s",token);if(rc!=-1) $fatal(1,"WC_TRAILING_VECTOR_RECORD");
    $fclose(fd);
    if(normal_count!=cases || recovery_count!=5 || fault_count!=5 || total_overlap==0 || total_stalls==0)
      $fatal(1,"WC_MISSING_CAMPAIGN_COVERAGE");
    $display("WC_PASS normal=%0d recovery=%0d faults=%0d overlap=%0d stalls=%0d",normal_count,recovery_count,
      fault_count,total_overlap,total_stalls);
    $finish;
  end
  initial begin #200000000;$fatal(1,"WC_WATCHDOG");end
endmodule
