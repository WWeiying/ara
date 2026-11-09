// SPDX-License-Identifier: Apache-2.0
// Numerical integration only: production VMFPU arithmetic, independent golden records.
module resident_pv_fullstream_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  import fpnew_pkg::*;
  import akv_pkg::*;
  logic clk_i = 0;
  always #5 clk_i = !clk_i;
  logic rst_ni = 0, start_valid_i = 0, start_ready_o;
  logic [3:0] start_active_i = 0, active_o;
  logic [5:0] cmd_elements_i;
  logic cmd_two_heads_i;
  logic [6:0] cmd_tokens_i;
  logic [2:0] cmd_rm_i;
  logic abort_i = 0, abort_rejected_o, busy_o, commit_authorized_o, fatal_error_o;
  logic [3:0] seed_valid_i, seed_ready_o;
  logic [3:0][63:0] seed_data_i;
  logic stream_valid_i, stream_ready_o, stream_is_value_i;
  logic [3:0][63:0] stream_data_i;
  logic [3:0] fpu_valid_o, fpu_ready_i, fpu_result_valid_i, fpu_result_ready_o;
  logic [3:0][2:0][63:0] fpu_operands_o;
  logic [3:0][3:0] fpu_tag_o, fpu_mask_o, fpu_result_tag_i;
  logic [3:0][2:0] fpu_rm_o;
  logic [3:0][63:0] fpu_result_i;
  logic [3:0][4:0] fpu_result_flags_i;
  logic [3:0] result_valid_o, result_ready_i = 0, final_ack_i = 0, ack_rejected_o;
  logic [3:0][63:0] result_data_o;
  logic [3:0][3:0] result_slot_o;
  logic [3:0][7:0] result_be_o;
  logic [3:0][4:0] outstanding_o;
  logic done_valid_o, done_ready_i = 0, done_error_o;
  logic [4:0] done_flags_o;
  logic [3:0] gate = 0, adapter_ready, adapter_held = 0;
  logic [3:0] return_gate = '1, adapter_result_valid;
  int return_stalls[4];
  logic reader_start = 0, reader_ready, reader_busy, reader_done, reader_error;
  logic reader_done_ready = 0, coefficient_valid, coefficient_ready;
  logic [31:0] coefficient;
  logic [3:0] reader_words = 0;
  logic [6:0] reader_tokens = 0;
  logic row_read, write_valid = 0, write_busy, column_busy, column_valid, column_cycle, conflict;
  logic [5:0] row_token, write_token = 0;
  logic [3:0] row_word;
  logic [255:0] row_data;
  logic [7:0] write_offset = 0;
  logic [127:0] write_data = 0;
  akv_stream_e write_stream = AKV_STREAM_K;
  logic [3:0] owned_probe, native_probe;
  int clock_cycle = 0;
  always @(posedge clk_i) clock_cycle <= clock_cycle + 1;
  akv_resident_pv_reader reader (
    .clk_i, .rst_ni, .cancel_i(abort_i), .start_valid_i(reader_start),
    .start_ready_o(reader_ready), .tokens_i(reader_tokens), .words_i(reader_words),
    .coefficient_valid_i(coefficient_valid), .coefficient_ready_o(coefficient_ready),
    .coefficient_i(coefficient), .row_read_o(row_read), .row_token_o(row_token),
    .row_word_o(row_word), .row_data_i(row_data), .stream_valid_o(stream_valid_i),
    .stream_ready_i(stream_ready_o), .stream_is_value_o(stream_is_value_i),
    .stream_data_o(stream_data_i), .done_valid_o(reader_done),
    .done_ready_i(reader_done_ready), .done_error_o(reader_error), .busy_o(reader_busy)
  );
  akv_v2_context context_store (
    .clk_i, .rst_ni, .write_valid_i(write_valid), .write_stream_i(write_stream),
    .write_token_i(write_token), .write_offset_i(write_offset), .write_data_i(write_data),
    .write_strb_i(16'hffff), .write_busy_o(write_busy), .row_read_i(row_read),
    .row_stream_i(AKV_STREAM_V), .row_token_i(row_token), .row_word_i(row_word),
    .row_data_o(row_data), .column_start_i(1'b0), .column_stream_i(AKV_STREAM_K),
    .column_dimension_i(7'b0), .column_count_i(3'd1), .column_token_count_i(7'b0),
    .column_busy_o(column_busy), .column_valid_o(column_valid), .column_data_o(),
    .column_bank_cycle_o(column_cycle), .conflict_o(conflict)
  );
  akv_resident_pv_cluster dut (.*);
  for (genvar l=0; l<4; l++) begin : gen_fpu
    status_t status;
    assign fpu_ready_i[l] = gate[l] && adapter_ready[l];
    assign fpu_result_valid_i[l] = adapter_result_valid[l] && return_gate[l];
    assign fpu_result_flags_i[l] = status;
    resident_vmfpu_adapter adapter (
      .clk_i, .rst_ni, .borrow_busy_i(busy_o), .operands_i(fpu_operands_o[l]),
      .is_boxed_i(3'b111), .rnd_mode_i(roundmode_e'(fpu_rm_o[l])),
      .op_i(FMADD), .op_mod_i(1'b0), .vectorial_op_i(1'b1),
      .tag_i(fpu_tag_o[l]), .simd_mask_i(fpu_mask_o[l]),
      .in_valid_i(fpu_valid_o[l] && gate[l]), .in_ready_o(adapter_ready[l]),
      .flush_i(1'b0), .result_o(fpu_result_i[l]), .status_o(status),
      .extension_bit_o(), .tag_o(fpu_result_tag_i[l]),
      .out_valid_o(adapter_result_valid[l]),
      .out_ready_i(fpu_result_ready_o[l] && return_gate[l]), .busy_o()
    );
    assign owned_probe[l] = adapter.owned;
    assign native_probe[l] = adapter.native_active_q;
  end

  typedef struct packed {
    logic [3:0] mask;
    logic [63:0] a, b, c, result;
    logic [4:0] flags;
  } op_t;
  op_t expected[4][1024];
  bit present[4][1024];
  logic [63:0] seeds[4][16], packets[4][576], commits[4][16], accum[4][16];
  int seed_slot[4][16], packet_kind[4][576], commit_slot[4][16];
  logic [7:0] commit_be[4][16];
  int nseed[4], npacket[4], nop[4], ncommit[4], expected_flags[4];
  int fd[4], count[4], id, elements, heads, tokens, rounding, words, cyc;
  int seeded[4], delivered[4], issued[4], returned[4], written[4], acked[4];
  int next_token[4][16], pending[4][16], ack_due[4][16], accepted_flags[4];
  int packets_in, terminal_age, group_flags, total_issue=0, total_writes=0;
  int cov_request[4], cov_write[4], cov_late=0, cov_same=0, cov_excess=0;
  int cov_max=0, cov_skew=0, cov_done=0, cov_debt_terminal=0;
  bit seed_held[4], fpu_held[4], write_held[4], lane_finished[4], stream_held;
  logic [202:0] fpu_saved[4];
  logic [75:0] write_saved[4];
  logic [15:0] natural_v[64][128];
  logic [255:0] previous_row, stalled_stream;
  bit previous_read = 0, stalled_kind, reader_seen, reader_retired, no_stalls, coefficient_held;
  int source_id, variant, executed = 0;
  int coefficients, reads, values, latency_checks, fill_writes;
  int first_coefficient, first_read, last_read, first_fma, last_fma, last_return;
  int first_seed, last_seed, first_write, last_write, last_ack, reader_done_cycle;
  int cluster_done_cycle, launch_cycle, drain_cycle, stream_stalls;
  int ready_stalls[4], preowner_stalls[4], owned_stalls[4], owned_cycles[4], native_cycles[4];
  int total_reads = 0, total_coefficients = 0, total_fill = 0, total_latency = 0;

`include "source_harness.svh"

  function automatic logic [255:0] natural_row(input int token, word_index);
    logic [255:0] result;
    for (int h=0;h<16;h++) result[16*h+:16]=natural_v[token][16*word_index+h];
    return result;
  endfunction

  // Invert the explicit physical halfslot mapping, independently of shuffle_index.
  task automatic fill_context;
    int offsets[4] = '{0,8,4,12};
    for (int t=0;t<tokens;t++) begin
      for (int l=0;l<4;l++)
        if (packets[l][t*(words+1)] !== packets[0][t*(words+1)] ||
            packets[l][t*(words+1)][63:32] !== 0)
          $fatal(1,"Reader requires equal 32-bit coefficient payloads across lanes");
      for (int w=0;w<words;w++) for (int l=0;l<4;l++) for (int h=0;h<4;h++)
        natural_v[t][16*w+l+offsets[h]]=packets[l][t*(words+1)+1+w][16*h+:16];
    end
    fill_writes=0;
    for (int k=0;k<2;k++) for (int t=0;t<tokens;t++) for (int beat=0;beat<2*words;beat++) begin
      @(negedge clk_i);
      write_valid=1; write_stream=k==0 ? AKV_STREAM_K : AKV_STREAM_V;
      write_token=6'(t); write_offset=8'(16*beat);
      for (int h=0;h<8;h++) write_data[16*h+:16]=
        k==0 ? ~natural_v[t][8*beat+h] : natural_v[t][8*beat+h];
      @(posedge clk_i);
      if (write_busy!==1 || row_read || reader_busy || busy_o || conflict)
        $fatal(1,"Conflicting or unaccepted context fill");
      fill_writes++;
    end
    @(negedge clk_i); write_valid=0;
    total_fill+=fill_writes;
  endtask

  // Count native/ownership intervals through finish_gate, without modifying adapters.
  always @(posedge clk_i) if (rst_ni) begin
    for (int l=0;l<4;l++) begin
      if (owned_probe[l]) owned_cycles[l]++;
      if (native_probe[l]) native_cycles[l]++;
    end
    if (write_busy !== write_valid || conflict || column_busy || column_valid || column_cycle)
      $fatal(1,"Context conflict/column/write protocol");
    if (previous_read) begin
      if (row_data !== previous_row) $fatal(1,"SRAM data changed before reader capture");
      latency_checks++; total_latency++;
    end
    previous_read=row_read;
    if (row_read) begin
      previous_row=natural_row(int'(row_token),int'(row_word));
      #1;
      if (row_data !== previous_row) $fatal(1,"Actual context SRAM latency/data mismatch");
    end
  end

  function automatic logic [63:0] enabled_bits(input logic [3:0] mask);
    for (int k=0;k<4;k++) enabled_bits[k*16+:16] = {16{mask[k]}};
  endfunction

  task automatic read_case(input int number);
    int got, cid, e, h, t, rm, mode, phase, bad, prepared, tok, slot, mask, flags;
    logic [63:0] a,b,c,r;
    group_flags=0;
    for (int l=0;l<4;l++) begin
      got=$fscanf(fd[l], "%d %d %d %d %d %d %d %d %d %d %d %d %h %h",
        cid,e,h,t,rm,mode,phase,bad,nseed[l],npacket[l],nop[l],ncommit[l],expected_flags[l],prepared);
      if (got!=14 || cid!=number || e<1 || e>32 || !(h inside {1,2}) ||
          t<1 || t>64 || rm<0 || rm>4 || mode!=0 || expected_flags[l]>31 ||
          nseed[l]!=((e+3)/4)*h || ncommit[l]!=nseed[l] ||
          npacket[l]!=t*((e+3)/4+1) || nop[l]!=nseed[l]*t)
        $fatal(1,"Invalid normal case header lane=%0d case=%0d",l,number);
      if (l==0) begin id=cid; elements=e; heads=h; tokens=t; rounding=rm; words=(e+3)/4; end
      else if ({cid,e,h,t,rm} !== {id,elements,heads,tokens,rounding})
        $fatal(1,"Lane case order/common shape mismatch");
      group_flags |= expected_flags[l];
      for (int i=0;i<1024;i++) present[l][i]=0;
      for (int i=0;i<nseed[l];i++)
        if ($fscanf(fd[l],"%h %h",seed_slot[l][i],seeds[l][i])!=2 ||
            seed_slot[l][i]!=(i/words)*8+i%words) $fatal(1,"Invalid seed record");
      for (int i=0;i<npacket[l];i++)
        if ($fscanf(fd[l],"%d %h",packet_kind[l][i],packets[l][i])!=2 ||
            packet_kind[l][i]!=(i%(words+1)!=0)) $fatal(1,"Invalid packet record");
      for (int i=0;i<nop[l];i++) begin
        if ($fscanf(fd[l],"%d %h %h %h %h %h %h %h",tok,slot,mask,a,b,c,r,flags)!=8 ||
            tok<0 || tok>=tokens || slot<0 || slot>=16 || slot/8>=heads ||
            slot%8>=words || flags<0 || flags>31 || mask<1 || mask>15)
          $fatal(1,"Invalid FMA record");
        if (present[l][tok*16+slot]) $fatal(1,"Duplicate FMA record");
        expected[l][tok*16+slot]='{4'(mask),a,b,c,r,5'(flags)};
        present[l][tok*16+slot]=1;
      end
      for (int i=0;i<ncommit[l];i++)
        if ($fscanf(fd[l],"%h %h %h",commit_slot[l][i],commit_be[l][i],commits[l][i])!=3 ||
            commit_slot[l][i]!=(i/words)*8+i%words) $fatal(1,"Invalid commit record");
    end
  endtask

  task automatic finish_adapters;
    gen_fpu[0].adapter.finish_gate();
    gen_fpu[1].adapter.finish_gate();
    gen_fpu[2].adapter.finish_gate();
    gen_fpu[3].adapter.finish_gate();
  endtask

  task automatic run_case;
    int s,t,index,balance,old_balance[4];
    logic [63:0] enabled;
    op_t want;
    bit terminal_fire;
    packets_in=0; terminal_age=0; stream_held=0;
    coefficients=0; reads=0; values=0; latency_checks=0; stream_stalls=0;
    reader_seen=0; reader_retired=0; coefficient_held=0;
    first_coefficient=-1; first_read=-1; last_read=-1; first_fma=-1; last_fma=-1; last_return=-1;
    first_seed=-1; last_seed=-1; first_write=-1; last_write=-1; last_ack=-1;
    reader_done_cycle=-1; cluster_done_cycle=-1;
    for (int l=0;l<4;l++) begin
      seeded[l]=0; delivered[l]=0; issued[l]=0; returned[l]=0; written[l]=0; acked[l]=0;
      accepted_flags[l]=0; seed_held[l]=0; fpu_held[l]=0; write_held[l]=0; lane_finished[l]=0;
      ready_stalls[l]=0; preowner_stalls[l]=0; owned_stalls[l]=0;
      owned_cycles[l]=0; native_cycles[l]=0;
      return_gate[l]=!guard_run; return_stalls[l]=0;
      for (int k=0;k<16;k++) begin pending[l][k]=-1; next_token[l][k]=0; accum[l][k]='x; end
    end
    fill_context();
    @(negedge clk_i);
    source_begin();
    start_valid_i=1; start_active_i=4'hf;
    reader_start=1; reader_words=4'(words); reader_tokens=7'(tokens);
    cmd_elements_i=6'(elements); cmd_two_heads_i=heads==2;
    cmd_tokens_i=7'(tokens); cmd_rm_i=3'(rounding);
    @(posedge clk_i);
    launch_cycle=clock_cycle;
    if (import_ready !== 1 || reader_ready !== 1 || start_ready_o !== 1 || dut.lane_cmd_valid !== 4'hf || dut.lane_cmd_ready !== 4'hf)
      $fatal(1,"Non-atomic four-lane launch");
    #1;
    for (cyc=0;cyc<100000;cyc++) begin
      @(negedge clk_i);
      start_valid_i=0; start_active_i=0;
      source_command.elem_count=4;
      source_command_valid=cyc==0 ? 4'hf : 4'h0;
      reader_start=0; reader_words=15; reader_tokens=127;
      // Poison live command fields after capture.
      cmd_elements_i=63; cmd_two_heads_i=!(heads==2); cmd_tokens_i=127; cmd_rm_i=7;
      for (int l=0;l<4;l++) begin
        // Force adapter-visible return pressure, not just pre-adapter input
        // gating. Release after two observed valid/not-ready edges.
        if (guard_run && return_stalls[l]>=2) return_gate[l]=1;
        if (!seed_held[l]) seed_gate[l]=
          no_stalls || (cyc>=4*l && cyc%(l+2)==0);
        if (!adapter_held[l]) gate[l]=no_stalls || ((cyc+l)%(l+3)!=0 && cyc%(17+3*l)>l+2);
        result_ready_i[l]=no_stalls || ((cyc+l)%4!=0 && (l!=3 || cyc%7<2));
        final_ack_i[l]=(no_stalls || l==0) ? result_valid_o[l] && result_ready_i[l] :
          acked[l]<written[l] && ack_due[l][acked[l]]<=cyc;
      end
      if (!coefficient_held) coefficient_gate=no_stalls || cyc%5!=0;
      guard_drive();
      source_drive();
      if (!no_stalls && (cyc==0 || terminal_age==1)) final_ack_i='1;
      done_ready_i=(no_stalls || terminal_age>=4) && import_done && reader_complete_q && reader_retired;
      reader_done_ready=no_stalls || reader_seen;
      @(posedge clk_i);
      for (int l=0;l<4;l++)
        if (adapter_result_valid[l] && !return_gate[l]) return_stalls[l]++;
      source_check();
      if ($isunknown({reader_ready,reader_busy,reader_done,reader_error,row_read,
                      stream_valid_i,stream_is_value_i,coefficient_ready}))
        $fatal(1,"Unknown reader handshake");
      if (no_stalls && (gate!==4'hf || result_ready_i!==4'hf ||
          done_ready_i!==(import_done && reader_complete_q && reader_retired) || !reader_done_ready))
        $fatal(1,"Injected stall in diagnostic replay");
      if (stream_held && (!stream_valid_i || stream_data_i!==stalled_stream ||
                          stream_is_value_i!==stalled_kind))
        $fatal(1,"Reader emission changed under stall");
      if (stream_valid_i) begin
        if (packets_in>=npacket[0]) $fatal(1,"Excess reader emission");
        for (int l=0;l<4;l++)
          if (stream_data_i[l]!==packets[l][packets_in] ||
              stream_is_value_i!==1'(packet_kind[l][packets_in]))
            $fatal(1,"Raw reader emission differs from immutable original packet");
        if (!stream_ready_o) stream_stalls++;
      end
      if (coefficient_valid && coefficient_ready) begin
        if (!stream_valid_i || !stream_ready_o || stream_is_value_i)
          $fatal(1,"Coefficient/stream handshake differs");
        if (first_coefficient<0) begin
          first_coefficient=clock_cycle;
          $display("PV_CONTEXT_START id=%0d owned=%0d gate=%0d ready=%0d",
                   id,owned_probe,gate,adapter_ready);
        end
        coefficients++;
      end
      coefficient_held=coefficient_valid && !coefficient_ready;
      if (row_read) begin
        if (int'(row_token)!=reads/words || int'(row_word)!=reads%words ||
            reads>=tokens*words || coefficients!=reads/words+1 || write_valid ||
            context_store.bank_req!==(8'b1<<row_token[2:0]) || context_store.bank_we!==0 ||
            int'(context_store.bank_addr[row_token[2:0]])!=64+8*(int'(row_token)/8)+int'(row_word))
          $fatal(1,"Context V read order/bank/address mismatch");
        if (first_read<0) first_read=clock_cycle;
        last_read=clock_cycle; reads++;
      end
      if (stream_valid_i && stream_ready_o && stream_is_value_i) values++;
      if (reads-values<0 || reads-values>2) $fatal(1,"Context credit overflow");
      if (reader_done) begin
        if (reader_error || !reader_busy || reader_ready || stream_valid_i || row_read ||
            packets_in!=npacket[0] || coefficients!=tokens || reads!=tokens*words || values!=reads)
          $fatal(1,"Reader done before exact stream drain");
        if (!reader_seen) reader_done_cycle=clock_cycle;
        reader_seen=1;
        if (reader_done_ready) begin
          if (reader_retired) $fatal(1,"Duplicate reader completion");
          reader_retired=1;
        end
      end else if (reader_seen && !reader_retired) $fatal(1,"Reader done withdrawn");
      if ($isunknown({active_o,busy_o,start_ready_o,fatal_error_o,seed_ready_o,stream_ready_o,
          fpu_valid_o,fpu_ready_i,fpu_result_valid_i,fpu_result_ready_o,result_valid_o,
          done_valid_o,done_error_o,done_flags_o,outstanding_o,ack_rejected_o}))
        $fatal(1,"Unknown cluster handshake");
      if (active_o!==4'hf || busy_o!==1 || start_ready_o || fatal_error_o || abort_rejected_o)
        $fatal(1,"Cluster ownership/error mismatch case=%0d",id);
      for (int l=0;l<4;l++) begin
        if (no_stalls && final_ack_i[l] !== (result_valid_o[l] && result_ready_i[l]))
          $fatal(1,"Diagnostic ack must exactly match actual accepted write");
        balance=written[l]-acked[l]; old_balance[l]=balance;
        if (outstanding_o[l]!==5'(balance)) $fatal(1,"Final ack ledger mismatch lane=%0d",l);
        if (balance==16) cov_max++;
        if (fpu_held[l] && (!fpu_valid_o[l] ||
            {fpu_operands_o[l],fpu_tag_o[l],fpu_mask_o[l],fpu_rm_o[l]}!==fpu_saved[l]))
          $fatal(1,"FPU request changed under stall");
        if (write_held[l] && (!result_valid_o[l] ||
            {result_data_o[l],result_slot_o[l],result_be_o[l]}!==write_saved[l]))
          $fatal(1,"Write changed under stall");
        fpu_held[l]=fpu_valid_o[l] && !fpu_ready_i[l];
        fpu_saved[l]={fpu_operands_o[l],fpu_tag_o[l],fpu_mask_o[l],fpu_rm_o[l]};
        adapter_held[l]=fpu_valid_o[l] && gate[l] && !adapter_ready[l];
        write_held[l]=result_valid_o[l] && !result_ready_i[l];
        write_saved[l]={result_data_o[l],result_slot_o[l],result_be_o[l]};
        seed_held[l]=seed_valid_i[l] && !seed_ready_o[l];
        if (fpu_held[l]) begin
          cov_request[l]++; ready_stalls[l]++;
          if (owned_probe[l]) owned_stalls[l]++; else preowner_stalls[l]++;
        end
        if (write_held[l]) cov_write[l]++;
        if (seed_valid_i[l] && seed_ready_o[l]) begin
          if (seeded[l]>=nseed[l] || seed_data_i[l]!==seeds[l][seeded[l]])
            $fatal(1,"Excess or misordered imported seed");
          accum[l][seed_slot[l][seeded[l]]]=seed_data_i[l]; seeded[l]++;
          if (first_seed<0) first_seed=clock_cycle;
          last_seed=clock_cycle;
        end
        // Observe real fanout transfers, not merely the parent ingress count.
        if (dut.payload_valid[l] && dut.payload_ready[l]) begin
          if (delivered[l]>=packets_in || delivered[l]>=npacket[l] ||
              dut.payload_data[l]!==packets[l][delivered[l]] ||
              dut.payload_kind!==1'(packet_kind[l][delivered[l]]))
            $fatal(1,"Misdirected/duplicate payload lane=%0d",l);
          delivered[l]++;
        end
        if (fpu_result_valid_i[l]) begin
          s=int'(fpu_result_tag_i[l]); index=pending[l][s];
          if (index<0) $fatal(1,"Unowned/duplicate return lane=%0d slot=%0d",l,s);
          want=expected[l][index]; enabled=enabled_bits(want.mask);
          if ((fpu_result_i[l]&enabled)!==(want.result&enabled) || fpu_result_flags_i[l]!==want.flags)
            $fatal(1,"SoftFloat return mismatch case=%0d lane=%0d index=%0d got=%h/%h want=%h/%h",
              id,l,index,fpu_result_i[l],fpu_result_flags_i[l],want.result,want.flags);
          if (fpu_result_ready_o[l]) begin
            accum[l][s]=(accum[l][s]&~enabled)|(fpu_result_i[l]&enabled);
            pending[l][s]=-1; returned[l]++;
            last_return=clock_cycle;
          end
        end
        if (fpu_valid_o[l] && fpu_ready_i[l]) begin
          s=int'(fpu_tag_o[l]); t=next_token[l][s]; index=t*16+s;
          if (s/8>=heads || s%8>=words || t>=tokens || seeded[l]!=nseed[l] ||
              pending[l][s]!=-1 || !present[l][index] ||
              delivered[l]<=t*(words+1)+s%8+1 ||
              s!=(issued[l]%heads)*8+(issued[l]/heads)%words)
            $fatal(1,"Illegal accepted FMA case=%0d lane=%0d slot=%0d",id,l,s);
          want=expected[l][index];
          if ({fpu_operands_o[l][0],fpu_operands_o[l][1],fpu_operands_o[l][2],fpu_mask_o[l],fpu_rm_o[l]} !==
              {want.a,want.b,want.c,want.mask,3'(rounding)} || fpu_operands_o[l][2]!==accum[l][s])
            $fatal(1,"Accepted operand/mask/rm mismatch case=%0d lane=%0d index=%0d",id,l,index);
          pending[l][s]=index; next_token[l][s]++; issued[l]++; total_issue++;
          if (first_fma<0) begin
            first_fma=clock_cycle;
            $display("PV_CONTEXT_FIRST_FMA id=%0d owned=%0d gate=%0d ready=%0d",
                     id,owned_probe,gate,adapter_ready);
          end
          last_fma=clock_cycle;
          accepted_flags[l] |= int'(want.flags);
        end
        if (result_valid_o[l]) begin
          if (!commit_authorized_o || issued[l]!=nop[l] || returned[l]!=nop[l] ||
              seeded[l]!=nseed[l] || delivered[l]!=npacket[l] || written[l]>=ncommit[l])
            $fatal(1,"Premature/excess commit");
          s=commit_slot[l][written[l]];
          // Full data comparison also checks disabled bytes retain their seeds.
          if (result_slot_o[l]!==4'(s) || result_be_o[l]!==commit_be[l][written[l]] ||
              result_data_o[l]!==commits[l][written[l]] || result_data_o[l]!==accum[l][s])
            $fatal(1,"Final slot/data/be mismatch case=%0d lane=%0d commit=%0d",id,l,written[l]);
          if (result_ready_i[l]) begin
            ack_due[l][written[l]]=cyc+40+20*l; written[l]++; total_writes++;
            if (first_write<0) first_write=clock_cycle;
            last_write=clock_cycle;
          end
        end
        if (final_ack_i[l]) begin
          if (acked[l]==written[l]) begin
            if (ack_rejected_o[l]!==1) $fatal(1,"Excess ack not rejected");
            cov_excess++;
          end else begin
            if (ack_rejected_o[l]!==0) $fatal(1,"Owned ack rejected");
            if (lane_finished[l]) cov_late++;
            if (result_valid_o[l] && result_ready_i[l]) cov_same++;
            acked[l]++;
            last_ack=clock_cycle;
          end
        end else if (ack_rejected_o[l]) $fatal(1,"Spurious ack rejection");
        if (dut.lane_done[l] && dut.lane_done_ready[l]) lane_finished[l]=1;
      end
      if (guard_cancel && (result_valid_o!=0 || commit_authorized_o || outstanding_o!=0))
        $fatal(1,"Cancelled source gap committed architecture");
      if (delivered[0]!=delivered[3]) cov_skew++;
      if (stream_valid_i && stream_ready_o) packets_in++;
      stream_held=stream_valid_i && !stream_ready_o;
      stalled_stream=stream_data_i; stalled_kind=stream_is_value_i;
      if (dut.group_done && outstanding_o!='0) begin
        if (done_valid_o || dut.group_done_ready) $fatal(1,"Completion bypassed final ack debt");
        cov_debt_terminal++;
      end
      if (!done_valid_o && {done_error_o,done_flags_o}!==6'b0) $fatal(1,"Flags leaked without done");
      if (done_valid_o) begin
        if (cluster_done_cycle<0) cluster_done_cycle=clock_cycle;
        if (!reader_retired || !reader_seen || reader_done_cycle>=clock_cycle)
          $fatal(1,"Cluster completion not distinct from reader completion");
        if (done_error_o!==guard_cancel || done_flags_o!==5'(guard_cancel ? 0 : group_flags) || packets_in!=npacket[0])
          $fatal(1,"Group FMA-only flags/completion mismatch");
        for (int l=0;l<4;l++) begin
          if (old_balance[l]!=0 || written[l]!=(guard_cancel ? 0 : ncommit[l]) || acked[l]!=written[l] ||
              issued[l]!=nop[l] || returned[l]!=issued[l] || accepted_flags[l]!=expected_flags[l] ||
              seeded[l]!=nseed[l] || delivered[l]!=npacket[l] || !lane_finished[l])
            $fatal(1,"Incomplete lane at terminal");
          for (int k=0;k<16;k++) if (pending[l][k]!=-1) $fatal(1,"Unretired arithmetic");
        end
        terminal_age++;
        if (!done_ready_i) cov_done++;
      end else if (terminal_age) $fatal(1,"Done withdrawn under stall");
      terminal_fire=done_valid_o && done_ready_i;
      #1;
      for (int l=0;l<4;l++)
        if (outstanding_o[l]!==5'(written[l]-acked[l])) $fatal(1,"Post-edge final ack counter mismatch");
      if (terminal_fire) begin
        transaction_done_cycle=clock_cycle;
        source_owned=0;
        if (!import_seen || import_busy || import_done) $fatal(1,"Import not held through overall done");
        if (busy_o!==0 || active_o!==0 || done_valid_o!==0) $fatal(1,"Terminal release mismatch");
        @(negedge clk_i);
        seed_gate=0; coefficient_gate=0; gate=0; result_ready_i=0; final_ack_i=0; done_ready_i=0;
        reader_done_ready=0;
        source_finish();
        finish_adapters();
        drain_cycle=clock_cycle;
        if (reader_busy || reader_done || !reader_ready || latency_checks!=reads ||
            fill_writes!=4*tokens*words) $fatal(1,"Reader/context completion ledger");
        for (int l=0;l<4;l++)
          $display("PV_CLUSTER_FP_LANE id=%0d lane=%0d seeds=%0d packets=%0d issued=%0d returned=%0d writes=%0d acks=%0d flags=%0d",
            id,l,seeded[l],delivered[l],issued[l],returned[l],written[l],acked[l],accepted_flags[l]);
        $display("PV_CLUSTER_FP_CASE id=%0d flags=%0d",id,guard_cancel ? 0 : group_flags);
        $display("PV_CONTEXT_CASE id=%0d source=%0d variant=%0d no_stalls=%0d reads=%0d coefficients=%0d values=%0d fills=%0d latency=%0d",
          id,source_id,variant,no_stalls,reads,coefficients,values,fill_writes,latency_checks);
        if (!guard_cancel) $display("PV_CONTEXT_TIME id=%0d launch=%0d first_coeff=%0d first_read=%0d last_read=%0d first_fma=%0d last_fma=%0d last_return=%0d coeff_span=%0d fma_span=%0d first_seed=%0d last_seed=%0d first_write=%0d last_write=%0d last_ack=%0d reader_done=%0d cluster_done=%0d drain=%0d stream_stalls=%0d",
          id,launch_cycle,first_coefficient,first_read,last_read,first_fma,last_fma,last_return,
          last_return-first_coefficient+1,last_return-first_fma+1,first_seed,last_seed,
          first_write,last_write,last_ack,reader_done_cycle,cluster_done_cycle,drain_cycle,stream_stalls);
        for (int l=0;l<4;l++)
          $display("PV_CONTEXT_LANE_TIME id=%0d lane=%0d ready_stalls=%0d preowner_stalls=%0d owned_stalls=%0d owned_cycles=%0d native_cycles=%0d",
            id,l,ready_stalls[l],preowner_stalls[l],owned_stalls[l],owned_cycles[l],native_cycles[l]);
        source_receipt();
        if (guard_run) for (int l=0;l<4;l++) begin
          if (return_stalls[l]!=2) $fatal(1,"Missing explicit FP return pressure");
          $display("PV_RETURN_STALL id=%0d lane=%0d cycles=%0d",id,l,return_stalls[l]);
        end
        total_reads+=reads; total_coefficients+=coefficients; executed++;
        return;
      end
    end
    $fatal(1,"Numerical case watchdog id=%0d",id);
  endtask

  initial begin
    string directory, trailing;
    int magic, schedule, scheduled_id, mode;
    guard_run=$test$plusargs("GUARD_CASES");
    if (!$value$plusargs("CORPUS=%s",directory)) $fatal(1,"Missing corpus");
    for (int l=0;l<4;l++) begin
      fd[l]=$fopen($sformatf("%s/lane%0d.txt",directory,l),"r");
      if (!fd[l] || $fscanf(fd[l],"%h %d",magic,count[l])!=2 || magic!='h50565531 ||
          count[l]<1 || count[l]>1000) $fatal(1,"Invalid corpus header");
      if (l && count[l]!=count[0]) $fatal(1,"Unequal lane case counts");
    end
    repeat (3) @(negedge clk_i);
    rst_ni=1;
    schedule=$fopen($sformatf("%s/schedule.txt",directory),"r");
    if (!schedule) $fatal(1,"Missing selected schedule");
    for (int number=0;number<count[0];number++) begin
      if ($fscanf(schedule,"%d %d %d %d",scheduled_id,source_id,variant,mode)!=4 ||
          scheduled_id!=number || !(mode inside {0,1})) $fatal(1,"Bad schedule");
      no_stalls=1'(mode);
      guard_mode=guard_run ? number+1 : 0;
      read_case(number);
      if (!(elements inside {16,24,32}) || (no_stalls && source_id>2))
        $fatal(1,"Unsupported partial-lane shape or non-real diagnostic replay");
      run_case();
    end
    if ($fscanf(schedule,"%s",trailing)!=-1) $fatal(1,"Trailing schedule");
    $fclose(schedule);
    for (int l=0;l<4;l++) begin
      if ($fscanf(fd[l],"%s",trailing)!=-1) $fatal(1,"Trailing corpus records");
      $fclose(fd[l]);
      if (!cov_request[l] || !cov_write[l]) $fatal(1,"Missing lane-specific stalls");
      $display("PV_CLUSTER_FP_STALL lane=%0d request=%0d write=%0d",l,cov_request[l],cov_write[l]);
    end
    finish_adapters();
    if (!(cov_late && cov_same && cov_excess && cov_max && cov_skew && cov_done && cov_debt_terminal))
      $fatal(1,"Missing final ack/skew coverage");
    $display("PV_CLUSTER_FP_PASS cases=%0d issued=%0d writes=%0d late=%0d same=%0d excess=%0d max16=%0d skew=%0d done_stall=%0d debt_terminal=%0d",
      count[0],total_issue,total_writes,cov_late,cov_same,cov_excess,cov_max,cov_skew,cov_done,cov_debt_terminal);
    $display("PV_CONTEXT_PASS cases=%0d reads=%0d coefficients=%0d fills=%0d latency=%0d",
      executed,total_reads,total_coefficients,total_fill,total_latency);
    $finish;
  end
  initial begin #100000000; $fatal(1,"Global bounded context gate timeout"); end
endmodule
