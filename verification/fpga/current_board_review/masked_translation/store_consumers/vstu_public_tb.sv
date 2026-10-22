`timescale 1ns/1ps
module vstu_public_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  localparam int NrLanes=4, VLEN=1024;
  localparam config_pkg::cva6_cfg_t Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  typedef logic [10:0] vlen_t;
  typedef logic [15:0] vaddr_t;
  typedef logic [7:0] strb_t;
  `include "ara/ara_typedef.svh"
  `include "ara/intf_typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, Cfg)
  typedef struct packed {logic [255:0] data; logic [31:0] strb;
    logic last; logic user;} axi_w_t;
  typedef struct packed {logic [3:0] id; logic [1:0] resp; logic user;} axi_b_t;

  logic clk_i=0, rst_ni=0;
  always #5 clk_i=~clk_i;
  axi_w_t axi_w_o;
  axi_b_t axi_b_i;
  logic axi_w_valid_o, axi_w_ready_i, axi_b_valid_i, axi_b_ready_o;
  logic store_pending_o, store_complete_o;
  pe_req_t pe_req_i;
  pe_resp_t pe_resp_o;
  logic pe_req_valid_i, pe_req_ready_o;
  logic [NrVInsn-1:0] pe_vinsn_running_i;
  logic stu_current_burst_exception_o;
  exception_t store_b_exception_o;
  vlen_t store_b_exception_vstart_o;
  addrgen_axi_req_t axi_addrgen_req_i;
  logic axi_addrgen_req_valid_i, axi_addrgen_req_ready_o, addrgen_illegal_store_i;
  elen_t [3:0] stu_operand_i;
  logic [3:0] stu_operand_valid_i, stu_operand_ready_o;
  logic lsu_ex_flush_i;
  strb_t [3:0] mask_i, mask_word_o;
  logic [3:0] mask_valid_i, mask_word_valid_o;
  vid_t mask_owner_id_i, mask_owner_id_o;
  vlen_t mask_first_element_i, mask_first_element_o;
  logic mask_ready_o, idle_o;
  vstu #(.NrLanes(NrLanes), .VLEN(VLEN), .vaddr_t(vaddr_t),
    .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t), .exception_t(exception_t),
    .AxiDataWidth(256), .AxiAddrWidth(64), .axi_w_t(axi_w_t), .axi_b_t(axi_b_t)) dut (.*);

  int variant, owner=-1, cycle_no, trace_fd;
  int first_elem, limit_elem, stop_elem, old_sew;
  bit masked, all_off, burst, fault, b_errors, feeding;
  int lane_cursor[4], mask_cursor, word_limit;
  int expected_w, expected_b, expected_desc;
  logic [255:0] expected_data[64];
  logic [31:0] expected_strb[64];
  bit expected_last[64];
  int w_count, b_count, last_count, desc_count, skip_count;
  int done_count, complete_count, abort_count, error_count, accepts;
  int b_due[64], b_release, b_next_cycle;
  int fault_offer, fault_accept, last_b_cycle, done_cycle;
  bit desc_pop, pe_accept;

  function automatic byte pattern(int id, int byte_index);
    return byte'(8'h39 ^ (variant*23) ^ (id*91) ^ (byte_index*37));
  endfunction
  function automatic bit enabled(int elem);
    return !masked || (!all_off && elem%3==1);
  endfunction
  function automatic longint unsigned base_addr();
    return 64'h40001000 + owner*64'h1000;
  endfunction
  // Independent physical layout formula; never call the DUT shuffle helper.
  function automatic int physical_byte(int seq, int sew);
    int width_bytes, ordinal, reverse_slot;
    width_bytes=1<<sew;
    ordinal=seq/(4*width_bytes);
    reverse_slot=0;
    for (int bitno=0;bitno<3-sew;bitno++)
      reverse_slot=(reverse_slot<<1)|((ordinal>>bitno)&1);
    return ((seq/width_bytes)%4)*8 + reverse_slot*width_bytes + seq%width_bytes;
  endfunction

  task automatic drive_streams;
    stu_operand_i='0; stu_operand_valid_i='0;
    mask_i='0; mask_valid_i='0;
    mask_owner_id_i=vid_t'(owner); mask_first_element_i=vlen_t'(mask_cursor*16);
    if (feeding) begin
      for (int lane=0;lane<4;lane++) begin
        stu_operand_valid_i[lane]=lane_cursor[lane]<word_limit;
        for (int seq=0;seq<32;seq++) begin
          int p;
          p=physical_byte(seq,old_sew);
          if (p/8==lane)
            stu_operand_i[lane][8*(p%8)+:8]=pattern(owner,lane_cursor[lane]*32+seq);
        end
      end
      if (masked && mask_cursor<word_limit) begin
        mask_valid_i='1;
        for (int seq=0;seq<32;seq++) begin
          int p;
          p=physical_byte(seq,1);
          mask_i[p/8][p%8]=enabled(mask_cursor*16+seq/2);
        end
      end
    end
    axi_w_ready_i=!(variant==0 && owner==0) && cycle_no%5>=2;
    axi_b_i='0;
    if (b_errors) axi_b_i.resp=b_count==0 ? 2'b10 : 2'b11;
    axi_b_valid_i=b_count<last_count && cycle_no>=b_due[b_count] &&
                  cycle_no>=b_release && cycle_no>=b_next_cycle;
  endtask

  task automatic check_completion;
    if (w_count!=expected_w || last_count!=expected_b || b_count!=expected_b ||
        desc_count!=expected_desc)
      $fatal(1,"EARLY_COMPLETION case=%0d owner=%0d w=%0d/%0d last=%0d/%0d b=%0d desc=%0d/%0d",
             variant,owner,w_count,expected_w,last_count,expected_b,b_count,desc_count,expected_desc);
  endtask

  task automatic tick;
    drive_streams();
    @(posedge clk_i);
    desc_pop=axi_addrgen_req_valid_i && axi_addrgen_req_ready_o;
    pe_accept=pe_req_valid_i && pe_req_ready_o;
    if (rst_ni && owner>=0) begin
      $fdisplay(trace_fd,"%0d,%0d,%0d,%b,%b,%b,%b,%b,%b,%h,%b,%b,%b,%b,%b,%b,%b,%b,%h,%0d,%0d,%0d",
        variant,owner,cycle_no,pe_req_valid_i,pe_req_ready_o,
        axi_addrgen_req_valid_i,axi_addrgen_req_ready_o,axi_addrgen_req_i.is_skip,
        axi_addrgen_req_i.is_exception,axi_w_o.strb,axi_w_valid_o,axi_w_ready_i,
        axi_w_o.last,axi_b_valid_i,axi_b_ready_o,store_complete_o,
        stu_current_burst_exception_o,idle_o,pe_resp_o.vinsn_done,w_count,b_count,desc_count);
      if (pe_accept) begin
        accepts++;
        $display("ACCEPT case=%0d owner=%0d cycle=%0d vl=%0d start=%0d vm=%b oldeew=%0d",
                 variant,owner,cycle_no,limit_elem,first_elem,!masked,old_sew);
      end
      for (int lane=0;lane<4;lane++)
        if (stu_operand_valid_i[lane] && stu_operand_ready_o[lane]) lane_cursor[lane]++;
      if (mask_ready_o) begin
        $display("MASK_INPUT case=%0d owner=%0d cycle=%0d first=%0d bits=%h",
                 variant,owner,cycle_no,mask_first_element_i,mask_i);
        mask_cursor++;
      end
      if (axi_addrgen_req_valid_i &&
          (axi_addrgen_req_i.is_skip || axi_addrgen_req_i.is_exception) && axi_w_valid_o)
        $fatal(1,"SKIP_OR_EXCEPTION_WVALID");
      if (axi_w_valid_o && axi_w_ready_i) begin
        if (w_count>=expected_w) $fatal(1,"EXTRA_W");
        if (axi_w_o.strb!==expected_strb[w_count] || axi_w_o.last!==expected_last[w_count])
          $fatal(1,"W_SHAPE w=%0d strb=%h expected=%h last=%b expected=%b",
                 w_count,axi_w_o.strb,expected_strb[w_count],axi_w_o.last,expected_last[w_count]);
        for (int b=0;b<32;b++)
          if (expected_strb[w_count][b] && axi_w_o.data[b*8+:8]!==expected_data[w_count][b*8+:8])
            $fatal(1,"W_DATA w=%0d byte=%0d actual=%h expected=%h",w_count,b,
                   axi_w_o.data[b*8+:8],expected_data[w_count][b*8+:8]);
        $display("W case=%0d owner=%0d cycle=%0d beat=%0d strb=%h last=%b data=%h",
                 variant,owner,cycle_no,w_count,axi_w_o.strb,axi_w_o.last,axi_w_o.data);
        w_count++;
        if (axi_w_o.last) begin b_due[last_count]=cycle_no+5; last_count++; end
      end
      if (axi_b_valid_i && axi_b_ready_o) begin
        if (b_count>=last_count) $fatal(1,"UNOWNED_B");
        $display("B case=%0d owner=%0d cycle=%0d index=%0d resp=%b",
                 variant,owner,cycle_no,b_count,axi_b_i.resp);
        b_count++; last_b_cycle=cycle_no; b_next_cycle=cycle_no+4;
      end
      if (expected_b==0 && axi_b_ready_o) $fatal(1,"NO_B_OBLIGATION_READY");
      if (desc_pop) begin
        desc_count++;
        if (axi_addrgen_req_i.is_skip) skip_count++;
        if (axi_addrgen_req_i.is_exception) begin
          fault_accept=cycle_no;
          if (b_count!=expected_b) $fatal(1,"FAULT_MARKER_BEFORE_B_DRAIN");
        end
        $display("DESC case=%0d owner=%0d cycle=%0d elem=%0d skip=%b ex=%b",
                 variant,owner,cycle_no,axi_addrgen_req_i.elem_start,
                 axi_addrgen_req_i.is_skip,axi_addrgen_req_i.is_exception);
      end
      if (store_complete_o) begin
        complete_count++;
        check_completion();
        if (complete_count!=1) $fatal(1,"DUPLICATE_STORE_COMPLETE");
      end
      if (stu_current_burst_exception_o) begin
        abort_count++;
        if (!fault || abort_count!=1) $fatal(1,"WRONG_ABORT");
      end
      if (store_b_exception_o.valid) begin
        error_count++;
        if (!b_errors || error_count!=1 || store_b_exception_o.cause!==riscv::ST_ACCESS_FAULT ||
            store_b_exception_o.tval!==base_addr()+2 || store_b_exception_vstart_o!==vlen_t'(1))
          $fatal(1,"WRONG_B_ERROR cause=%h va=%h start=%0d",
                 store_b_exception_o.cause,store_b_exception_o.tval,store_b_exception_vstart_o);
        $display("B_ERROR case=%0d owner=%0d cycle=%0d va=%h start=%0d",
                 variant,owner,cycle_no,store_b_exception_o.tval,store_b_exception_vstart_o);
      end
      if (|pe_resp_o.vinsn_done) begin
        if (pe_resp_o.vinsn_done!==(NrVInsn'(1)<<owner)) $fatal(1,"WRONG_DONE_ID");
        done_count++; done_cycle=cycle_no;
        check_completion();
        if (done_count!=1 || complete_count!=1) $fatal(1,"DUPLICATE_OR_UNPAIRED_DONE");
        $display("DONE case=%0d owner=%0d cycle=%0d w=%0d b=%0d desc=%0d",
                 variant,owner,cycle_no,w_count,b_count,desc_count);
      end
    end
    #1;
    @(negedge clk_i);
    cycle_no++;
    if (cycle_no>600) $fatal(1,"BOUNDED_WATCHDOG case=%0d owner=%0d",variant,owner);
  endtask

  task automatic reset_case;
    owner=-1; feeding=0; rst_ni=0; cycle_no=0;
    pe_req_i='0; pe_req_valid_i=0; pe_vinsn_running_i='0;
    axi_addrgen_req_i='0; axi_addrgen_req_valid_i=0;
    addrgen_illegal_store_i=0; lsu_ex_flush_i=0;
    b_count=0; last_count=0; b_errors=0; mask_cursor=0;
    repeat(3) tick();
    rst_ni=1;
    repeat(2) tick();
  endtask

  task automatic setup_store(int id);
    owner=id; feeding=0;
    masked=1; all_off=0; burst=0; fault=0; b_errors=0;
    first_elem=0; limit_elem=20; stop_elem=20; old_sew=0;
    if (id==0) begin
      case (variant)
        0: begin all_off=1; first_elem=3; end
        1,2: begin fault=1; stop_elem=7; b_errors=variant==2; end
        3: first_elem=3;
        4: begin masked=0; burst=1; limit_elem=32; stop_elem=32; end
        5: begin fault=1; first_elem=1; stop_elem=1; end
      endcase
    end else begin
      first_elem=2; limit_elem=9; stop_elem=9; old_sew=3;
    end
    word_limit=((fault ? stop_elem+1 : limit_elem)*2+31)/32;
    for (int l=0;l<4;l++) lane_cursor[l]=(first_elem*2)/32;
    mask_cursor=(first_elem*2)/32;
    w_count=0; b_count=0; last_count=0; desc_count=0; skip_count=0;
    done_count=0; complete_count=0; abort_count=0; error_count=0; accepts=0;
    b_release=fault ? 100000 : 0; b_next_cycle=0;
    fault_offer=-1; fault_accept=-1; last_b_cycle=-1; done_cycle=-1;
    expected_w=0; expected_b=0;
    for (int w=0;w<64;w++) begin
      expected_data[w]='0; expected_strb[w]='0; expected_last[w]=1;
    end
    if (burst) begin
      expected_w=2; expected_b=1; expected_desc=1;
      expected_last[0]=0;
      for (int b=0;b<64;b++) begin
        expected_strb[b/32][b%32]=1;
        expected_data[b/32][(b%32)*8+:8]=pattern(owner,b);
      end
    end else begin
      expected_desc=stop_elem-first_elem+int'(fault);
      for (int elem=first_elem;elem<stop_elem;elem++) if (enabled(elem)) begin
        for (int b=0;b<2;b++) begin
          int pos;
          pos=(elem*2+b)%32;
          expected_strb[expected_w][pos]=1;
          expected_data[expected_w][pos*8+:8]=pattern(owner,elem*2+b);
        end
        expected_w++;
      end
      expected_b=expected_w;
    end
    $display("CONFIG case=%0d owner=%0d first=%0d vl=%0d stop=%0d mask=%b alloff=%b burst=%b fault=%b berror=%b expected_w=%0d expected_b=%0d expected_desc=%0d",
             variant,owner,first_elem,limit_elem,stop_elem,masked,all_off,burst,fault,b_errors,
             expected_w,expected_b,expected_desc);
    pe_req_i='0; pe_req_i.id=vid_t'(owner); pe_req_i.vfu=VFU_StoreUnit;
    pe_req_i.op=VSE; pe_req_i.vm=!masked;
    pe_req_i.vtype.vsew=EW16; pe_req_i.vtype.vlmul=LMUL_1;
    pe_req_i.old_eew_vs1=vew_e'(old_sew); pe_req_i.eew_vs1=EW16;
    pe_req_i.vl=vlen_t'(limit_elem); pe_req_i.vstart=vlen_t'(first_elem);
    pe_req_i.emul=LMUL_1; pe_req_i.use_vs1=1;
    pe_vinsn_running_i[owner]=1; pe_req_valid_i=1;
    do tick(); while (!pe_accept);
    pe_req_valid_i=0; feeding=1;
  endtask

  task automatic send_descriptor(int elem, bit terminal);
    // Model AddrGen's mask-window prerequisite through public mask outputs.
    if (masked)
      while (mask_word_valid_o!==4'b1111 || mask_owner_id_o!==vid_t'(owner) ||
             mask_first_element_o!==vlen_t'((elem/16)*16)) tick();
    axi_addrgen_req_i='0;
    axi_addrgen_req_i.is_exception=terminal;
    axi_addrgen_req_i.is_skip=!terminal && !burst && !enabled(elem);
    axi_addrgen_req_i.addr=axi_addrgen_req_i.is_skip ? 0 : base_addr()+elem*2;
    axi_addrgen_req_i.vaddr=base_addr()+elem*2;
    axi_addrgen_req_i.elem_start=elem;
    axi_addrgen_req_i.size=burst ? 5 : 1;
    axi_addrgen_req_i.len=burst ? 1 : 0;
    axi_addrgen_req_valid_i=1;
    if (terminal) begin
      fault_offer=cycle_no;
      b_release=cycle_no+12;
      $display("FAULT_OFFER case=%0d owner=%0d cycle=%0d pending_b=%0d release=%0d",
               variant,owner,cycle_no,last_count-b_count,b_release);
    end
    do tick(); while (!desc_pop);
    axi_addrgen_req_valid_i=0;
  endtask

  task automatic finish_store;
    while (done_count==0) tick();
    feeding=0; pe_vinsn_running_i[owner]=0;
    repeat(5) tick();
    if (idle_o!==1 || store_pending_o!==0 || accepts!=1 || done_count!=1 ||
        complete_count!=1 || abort_count!=int'(fault) || error_count!=int'(b_errors))
      $fatal(1,"DIRTY_OR_BAD_TERMINAL idle=%b pending=%b accept=%0d done=%0d complete=%0d abort=%0d error=%0d",
             idle_o,store_pending_o,accepts,done_count,complete_count,abort_count,error_count);
    if (fault && expected_b>0 && (fault_accept<fault_offer+12 || fault_accept<last_b_cycle))
      $fatal(1,"FAULT_DRAIN_DELAY_NOT_EXERCISED");
    if (skip_count!=expected_desc-expected_b-int'(fault) && !burst)
      $fatal(1,"BAD_SKIP_COUNT");
    $display("STORE_PASS case=%0d owner=%0d w=%0d b=%0d desc=%0d skips=%0d fault_offer=%0d fault_accept=%0d last_b=%0d done=%0d idle=%b",
             variant,owner,w_count,b_count,desc_count,skip_count,
             fault_offer,fault_accept,last_b_cycle,done_cycle,idle_o);
  endtask

  initial begin
    trace_fd=$fopen("cycles.csv","w");
    $fdisplay(trace_fd,"case,owner,cycle,pe_valid,pe_ready,desc_valid,desc_ready,skip,exception,wstrb,wvalid,wready,wlast,bvalid,bready,complete,abort,idle,done,w_count,b_count,desc_count");
    for (variant=0;variant<6;variant++) begin
      reset_case();
      for (int id=0;id<2;id++) begin
        setup_store(id);
        if (burst) send_descriptor(0,0);
        else for (int elem=first_elem;elem<stop_elem;elem++) send_descriptor(elem,0);
        if (fault) send_descriptor(stop_elem,1);
        finish_store();
      end
      $display("CASE_PASS case=%0d successor_no_reset=1",variant);
    end
    $display("SUITE_PASS cases=6 stores=12");
    $fclose(trace_fd);
    $finish;
  end
endmodule
