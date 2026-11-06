`timescale 1ns/1ps
module qbs_weight_wide_mapper_tb;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0, clear = 0, valid = 0, ready, out_valid, out_ready = 0;
  qbs_pkg::qbs_weight_profile_e profile = qbs_pkg::QBS_WEIGHT_PROFILE_Q4_K, out_profile;
  logic [2:0] rows = 1, out_rows;
  logic group_mode = 0, out_group;
  logic [1:0] row = 0, out_row;
  logic [9:0] offset = 0, out_offset;
  logic [255:0] data = 0, out_data;
  logic [31:0] strb = 0, out_strb;
  logic [3:0][1:0][4:0] starts;
  logic [3:0][1:0][5:0] counts;
  logic [3:0][1:0][7:0] offsets;
  logic [3:0][1:0] lasts;
  logic [3:0][19:0] side_mask;
  logic [3:0][19:0][4:0] side_sources;
  localparam int PacketBits = $bits(out_profile) + $bits(out_rows) + $bits(out_group) +
      $bits(out_row) + $bits(out_offset) + $bits(out_data) + $bits(out_strb) +
      $bits(starts) + $bits(counts) + $bits(offsets) + $bits(lasts) +
      $bits(side_mask) + $bits(side_sources);
  wire [PacketBits-1:0] observed_packet = {out_profile,out_rows,out_group,out_row,out_offset,
      out_data,out_strb,starts,counts,offsets,lasts,side_mask,side_sources};
  bit queued = 0, automatic_sink = 0, send_head = 0, send_tail = 0;
  int mode = 0, ticks = 0, cases = 0, abort_cases = 0;
  int saved_profile, saved_rows, saved_row, saved_offset, saved_amount;
  bit saved_group, saved_head, saved_tail;
  logic [255:0] saved_data;
  logic [31:0] saved_strb;
  longint unsigned accepted = 0, decoded = 0, payload = 0, side_bytes = 0;
  longint unsigned packets = 0, discarded = 0, last_count = 0;
  longint unsigned heads = 0, fulls = 0, tails = 0, cross_rows = 0, cross_planes = 0;
  int stalls = 0, output_stalls = 0;
  string negative = "";

  qbs_weight_wide_mapper dut (
    .clk_i(clk), .rst_ni(rst_n), .clear_i(clear), .profile_i(profile), .row_count_i(rows),
    .group_mode_i(group_mode), .row_i(row), .offset_i(offset), .data_i(data), .strb_i(strb),
    .valid_i(valid), .ready_o(ready), .valid_o(out_valid), .ready_i(out_ready),
    .profile_o(out_profile), .row_count_o(out_rows), .group_mode_o(out_group), .row_o(out_row),
    .offset_o(out_offset), .data_o(out_data), .strb_o(out_strb), .source_start_o(starts),
    .count_o(counts), .payload_offset_o(offsets), .payload_last_o(lasts),
    .side_mask_o(side_mask), .side_source_index_o(side_sources)
  );

  // Independent explicit native region table. Never call a package mapper.
  task automatic regions(input int p, output int bytes_n, low_start, low_n, high_start, high_n, side_start);
    case (p)
      1: begin bytes_n=144; low_start=16; low_n=128; high_start=0; high_n=0; side_start=0; end
      2: begin bytes_n=210; low_start=0; low_n=128; high_start=128; high_n=64; side_start=192; end
      3: begin bytes_n=18; low_start=2; low_n=16; high_start=0; high_n=0; side_start=0; end
      4: begin bytes_n=176; low_start=48; low_n=128; high_start=16; high_n=32; side_start=0; end
      5: begin bytes_n=110; low_start=32; low_n=64; high_start=0; high_n=32; side_start=96; end
      6: begin bytes_n=34; low_start=2; low_n=32; high_start=0; high_n=0; side_start=0; end
      7: begin bytes_n=84; low_start=16; low_n=64; high_start=0; high_n=0; side_start=0; end
      8: begin bytes_n=22; low_start=6; low_n=16; high_start=0; high_n=0; side_start=0; end
      9: begin bytes_n=18; low_start=2; low_n=16; high_start=0; high_n=0; side_start=0; end
      default: $fatal(1, "TB invalid oracle profile");
    endcase
  endtask

  task automatic golden(input int p, native, output int plane, local_offset, output bit last_byte);
    int block_n, ls, ln, hs, hn, ss;
    regions(p, block_n, ls, ln, hs, hn, ss);
    if (native < 0 || native >= block_n) $fatal(1, "TB oracle native overflow");
    plane = 2;
    local_offset = native - ss;
    last_byte = 0;
    if (native >= ls && native < ls + ln) begin
      plane = 0;
      local_offset = native - ls;
      last_byte = native == ls + ln - 1;
    end else if (hn != 0 && native >= hs && native < hs + hn) begin
      plane = 1;
      local_offset = native - hs;
      last_byte = native == hs + hn - 1;
    end else if (p == 7 && native >= 80) local_offset = native - 64;
  endtask

  task automatic check_packet;
    int block_n, ls, ln, hs, hn, ss;
    int used [32];
    bit touched_rows [4], touched_planes [3];
    int source, n, plane, local_offset, expected_row, native, nr, np;
    bit last_byte;
    logic [255:0] shifted;
    if (!queued) $fatal(1, "TB unexpected output packet");
    if ({out_profile,out_rows,out_group,out_row,out_offset,out_data,out_strb} !==
        {4'(saved_profile),3'(saved_rows),saved_group,2'(saved_row),10'(saved_offset),saved_data,saved_strb})
      $fatal(1, "TB registered data/metadata mismatch");
    regions(saved_profile, block_n, ls, ln, hs, hn, ss);
    for (int i=0; i<32; i++) used[i]=0;
    for (int r=0; r<4; r++) touched_rows[r]=0;
    for (int p=0; p<3; p++) touched_planes[p]=0;
    for (int r=0; r<4; r++) begin
      for (int p=0; p<2; p++) begin
        n = int'(counts[r][p]);
        if (n == 0) begin
          if ({starts[r][p],offsets[r][p],lasts[r][p]} !== '0) $fatal(1, "TB inactive segment metadata");
        end else begin
          if (r >= saved_rows || n > 32 || int'(starts[r][p])+n > saved_amount)
            $fatal(1, "TB segment out of compacted source prefix");
          shifted = out_data >> (8*int'(starts[r][p]));
          for (int j=0; j<n; j++) begin
            source = int'(starts[r][p])+j;
            expected_row = saved_group ? (saved_offset+source)/block_n : saved_row;
            native = saved_group ? (saved_offset+source)%block_n : saved_offset+source;
            golden(saved_profile,native,plane,local_offset,last_byte);
            if (r != expected_row || p != plane || int'(offsets[r][p])+j != local_offset ||
                shifted[8*j +: 8] !== saved_data[8*source +: 8])
              $fatal(1, "TB decoded payload mismatch profile=%0d row=%0d plane=%0d source=%0d", saved_profile,r,p,source);
            if (j == n-1 && lasts[r][p] !== last_byte) $fatal(1, "TB wrong profile-region last");
            used[source]++;
            touched_rows[r]=1;
            touched_planes[p]=1;
            payload++;
          end
          if (lasts[r][p]) last_count++;
        end
      end
      for (int s=0; s<20; s++) begin
        if (side_mask[r][s]) begin
          source = int'(side_sources[r][s]);
          if (r >= saved_rows || source >= saved_amount) $fatal(1, "TB side source out of prefix");
          expected_row = saved_group ? (saved_offset+source)/block_n : saved_row;
          native = saved_group ? (saved_offset+source)%block_n : saved_offset+source;
          golden(saved_profile,native,plane,local_offset,last_byte);
          if (r != expected_row || plane != 2 || local_offset != s ||
              out_data[8*source +: 8] !== saved_data[8*source +: 8]) $fatal(1, "TB side metadata mismatch");
          used[source]++;
          touched_rows[r]=1;
          touched_planes[2]=1;
          side_bytes++;
        end else if (side_sources[r][s] !== 0) $fatal(1, "TB inactive side source nonzero");
      end
    end
    for (int i=0; i<32; i++)
      if (used[i] != (i < saved_amount ? 1 : 0)) $fatal(1, "TB native byte missing/duplicated source=%0d", i);
    nr=0; np=0;
    for (int r=0; r<4; r++) nr += int'(touched_rows[r]);
    for (int p=0; p<3; p++) np += int'(touched_planes[p]);
    if (nr > 1) cross_rows++;
    if (np > 1) cross_planes++;
    decoded += saved_amount;
    packets++;
    if (saved_head) heads++;
    if (saved_tail) tails++;
    if (saved_amount == 32) fulls++;
  endtask

  always @(posedge clk) begin
    ticks++;
    if (!rst_n || clear) begin
      if (queued) discarded += saved_amount;
      queued = 0;
    end else if (negative == "") begin
      if (out_valid && out_ready) begin check_packet(); queued=0; end
      if (out_valid && !out_ready) output_stalls++;
      if (valid && ready) begin
        if (queued) $fatal(1, "TB elastic slot overwritten");
        queued=1;
        saved_profile=int'(profile); saved_rows=int'(rows); saved_group=group_mode;
        saved_row=int'(row); saved_offset=int'(offset); saved_data=data; saved_strb=strb;
        saved_amount=$countones(strb); saved_head=send_head; saved_tail=send_tail;
        accepted += saved_amount;
      end else if (valid) stalls++;
    end
  end

  always @(negedge clk)
    if (automatic_sink) out_ready = mode == 0 || (ticks % 7 != 2 && ticks % 7 != 3);

  task automatic run_case(input int p, row_n, grouped, base_phase, traffic_mode);
    int block_n, ls, ln, hs, hn, ss, limit, cursor, n, phase, stream_rows, bound, old_stalls;
    bit held;
    regions(p,block_n,ls,ln,hs,hn,ss);
    mode=traffic_mode;
    automatic_sink=1;
    stream_rows=grouped ? 1 : row_n;
    old_stalls=stalls;
    for (int r=0; r<stream_rows; r++) begin
      cursor=0; held=0; bound=0;
      limit=grouped ? row_n*block_n : block_n;
      phase=grouped ? base_phase : (base_phase+r*block_n)%32;
      while (cursor<limit) begin
        @(negedge clk);
        n=cursor == 0 ? 32-phase : 32;
        if (n > limit-cursor) n=limit-cursor;
        profile=qbs_pkg::qbs_weight_profile_e'(p); rows=3'(row_n);
        group_mode=1'(grouped); row=2'(grouped ? row_n-1 : r); offset=10'(cursor);
        strb=n == 32 ? '1 : (32'd1 << n)-1;
        valid=held || traffic_mode == 0 || ticks%3 != 0;
        send_head=cursor == 0 && phase != 0;
        send_tail=cursor+n == limit && (phase+limit)%32 != 0;
        for (int b=0; b<32; b++) data[8*b +: 8]=8'((cursor+b)*37 ^ p*19 ^ row_n*23 ^ r*51 ^ base_phase*7);
        @(posedge clk);
        if (valid && ready) begin cursor+=n; held=0; end
        else if (valid) held=1;
        bound++;
        if (bound > 256) $fatal(1, "TB input progress timeout");
      end
    end
    @(negedge clk); valid=0;
    bound=0;
    while (queued || out_valid) begin
      @(negedge clk); bound++;
      if (bound>32) $fatal(1, "TB output progress timeout");
    end
    if (traffic_mode == 0 && stalls != old_stalls) $fatal(1, "TB input II must be one at unstalled sink");
    cases++;
  endtask

  task automatic abort_case(input int p, grouped, use_reset);
    int block_n, ls, ln, hs, hn, ss, n;
    logic [PacketBits-1:0] retained_packet;
    regions(p,block_n,ls,ln,hs,hn,ss);
    automatic_sink=0;
    @(negedge clk);
    out_ready=0; profile=qbs_pkg::qbs_weight_profile_e'(p); rows=4; group_mode=1'(grouped);
    row=0; offset=0; n=grouped || block_n>=32 ? 32 : block_n;
    strb=n==32 ? '1 : (32'd1<<n)-1;
    data={8{32'hc0decafe}}; valid=1;
    @(posedge clk);
    if (!ready) $fatal(1, "TB abort input not accepted");
    @(negedge clk);
    if (!out_valid) $fatal(1, "TB abort has no staged packet");
    retained_packet=observed_packet;
    // Present a new input too: clear/reset must block both handshakes.
    if (use_reset) rst_n=0; else clear=1;
    #1;
    if (out_valid || ready) $fatal(1, "TB abort did not gate handshakes");
    if (observed_packet !== retained_packet) $fatal(1, "TB invalid payload was reset asynchronously");
    @(negedge clk);
    if (observed_packet !== retained_packet) $fatal(1, "TB invalid payload was cleared/reset");
    valid=0; rst_n=1; clear=0; out_ready=1;
    repeat (3) begin @(negedge clk); if (out_valid || queued) $fatal(1, "TB aborted packet leaked"); end
    abort_cases++;
  endtask

  task automatic check_reduction_vector(input logic [31:0] mask);
    int n, first_index;
    logic [31:0] first;
    n=0; first_index=0; first=0;
    for (int b=0; b<32; b++) begin
      if (mask[b]) begin
        if (n==0) begin first[b]=1; first_index=b; end
        n++;
      end
    end
    if (dut.popcount32(mask) !== 6'(n) || dut.first_one32(mask) !== first ||
        dut.encode_onehot32(first) !== 5'(first_index)) $fatal(1, "TB parallel reduction mismatch");
  endtask

  task automatic check_reductions;
    logic [31:0] mask;
    check_reduction_vector(0);
    check_reduction_vector('1);
    for (int start=0; start<32; start++)
      for (int length=1; length<=32; length++)
        check_reduction_vector((32'hffffffff >> (32-length)) << start);
    mask=32'h91e10da5;
    for (int i=0; i<256; i++) begin
      mask={mask[30:0],mask[31]^mask[21]^mask[1]^mask[0]};
      check_reduction_vector(mask);
    end
    $display("WIDE_REDUCTION_PASS vectors=1282");
  endtask

  initial begin
    longint unsigned dp, db, dl, ds, dh, df, dt, dr, dx, dlast;
    int old_cases;
    repeat (3) @(negedge clk); rst_n=1;
    if ($value$plusargs("NEGATIVE=%s",negative)) begin
      @(negedge clk);
      valid=1; out_ready=1; strb=1;
      if (negative=="empty") strb=0;
      else if (negative=="prefix") strb=32'h5;
      else if (negative=="row_range") begin offset=140; strb=32'hff; end
      else if (negative=="group_range") begin group_mode=1; rows=4; offset=830; strb='1; profile=qbs_pkg::QBS_WEIGHT_PROFILE_Q6_K; end
      else if (negative=="row") row=1;
      else if (negative=="rows") rows=0;
      else if (negative=="profile") profile=qbs_pkg::QBS_WEIGHT_PROFILE_INVALID;
      else if (negative=="unknown") strb='x;
      else $fatal(1, "TB unknown negative name");
      #1;
      if (negative!="unknown" && ready !== 0) $fatal(1, "TB invalid input was partially accepted");
      $display("WIDE_NEGATIVE_ARMED name=%s",negative);
      @(posedge clk); #1;
      $fatal(1, "WIDE_NEGATIVE_NOT_REJECTED");
    end
    $display("WIDE_MAPPER_EPOCH epoch=2");
    check_reductions();
    for (int p=1; p<=9; p++) begin
      dp=packets; db=decoded; dl=payload; ds=side_bytes; dh=heads; df=fulls;
      dt=tails; dr=cross_rows; dx=cross_planes; dlast=last_count; old_cases=cases;
      for (int row_n=1; row_n<=4; row_n++)
        for (int grouped=0; grouped<2; grouped++)
          for (int phase=0; phase<32; phase++)
            for (int traffic_mode=0; traffic_mode<2; traffic_mode++)
              run_case(p,row_n,grouped,phase,traffic_mode);
      $display("WIDE_PROFILE_PASS profile=%0d cases=%0d packets=%0d decoded=%0d payload=%0d side=%0d lasts=%0d heads=%0d fulls=%0d tails=%0d cross_rows=%0d cross_planes=%0d",
        p,cases-old_cases,packets-dp,decoded-db,payload-dl,side_bytes-ds,last_count-dlast,
        heads-dh,fulls-df,tails-dt,cross_rows-dr,cross_planes-dx);
    end
    for (int p=1; p<=9; p++)
      for (int grouped=0; grouped<2; grouped++)
        for (int use_reset=0; use_reset<2; use_reset++) abort_case(p,grouped,use_reset);
    if (stalls==0 || output_stalls==0) $fatal(1, "TB backpressure not exercised");
    if (accepted != decoded+discarded || payload+side_bytes != decoded || queued)
      $fatal(1, "TB final byte conservation failed");
    $display("WIDE_MAPPER_COMPONENT_PASS cases=%0d packets=%0d decoded=%0d payload=%0d side=%0d lasts=%0d abort_cases=%0d accepted=%0d discarded=%0d stalls=%0d output_stalls=%0d",
      cases,packets,decoded,payload,side_bytes,last_count,abort_cases,accepted,discarded,stalls,output_stalls);
    $finish;
  end
  initial begin #10000000; $fatal(1, "TB mapper watchdog"); end
endmodule
