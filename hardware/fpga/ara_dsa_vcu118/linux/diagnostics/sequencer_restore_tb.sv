// SPDX-License-Identifier: SHL-0.51
`timescale 1ns/1ps
module sequencer_restore_tb;
  import ara_pkg::*;
  import rvv_pkg::*;
  typedef logic [10:0] vlen_t;
  typedef struct packed {
    logic [63:0] cause, tval;
    logic [40:0] tval2;
    logic [31:0] tinst;
    logic gva, valid;
  } exception_t;
  `include "ara/ara_typedef.svh"
  `include "sequencer_types.svh"
  logic clk_i=0, rst_ni=0;
  ara_req_t ara_req_i='0;
  ara_resp_t ara_resp_o;
  pe_req_t pe_req_o;
  pe_resp_t [7:0] pe_resp_i='0;
  logic ara_req_valid_i=0, ara_req_ready_o, ara_resp_valid_o, ara_idle_o;
  logic ara_store_accepted_o, pe_req_valid_o;
  logic [7:0] pe_vinsn_running_o, pe_req_ready_i='1;
  logic [7:0][7:0] global_hazard_table_o;
  logic alu_vinsn_done_i=0, mfpu_vinsn_done_i=0;
  logic [63:0] pe_scalar_resp_i=0;
  logic pe_scalar_resp_valid_i=0, pe_scalar_resp_ready_o;
  logic addrgen_ack_i=0, addrgen_fof_exception_i=0;
  exception_t addrgen_exception_i='0;
  vlen_t addrgen_exception_vstart_i=0;
  logic lsu_current_burst_exception_i=0;
  logic [4:0] qbs_fflags_i=0;
  logic qbs_fflags_valid_i=0;
  int responses=0, issues=0, completions=0, cycles=0;
  logic [7:0] owned=0;
  int due[8]='{default:0};
  int ack_due=0, gap=0, serial_mode=0;
  int alias_setting=0;
  wire alias_value=alias_setting!=0;
  bit request_seen=0;
  always #5 clk_i=~clk_i;

`ifdef MAPPED_SEQ
  `include "sequencer_mapped.svh"
`else
  ara_sequencer #(.NrLanes(4), .VLEN(1024), .ara_req_t(ara_req_t),
    .ara_resp_t(ara_resp_t), .pe_req_t(pe_req_t), .pe_resp_t(pe_resp_t),
    .exception_t(exception_t)) dut (.*);
`endif

  // AddrGen accepts each maintained request once; load completions are
  // delayed independently of its scalar-side acknowledgement.
  always @(negedge clk_i) begin
    addrgen_ack_i=0;
    pe_resp_i='0;
    if(rst_ni) begin
      cycles++;
      if(!pe_req_valid_o) request_seen=0;
      if(pe_req_valid_o && !request_seen) begin
        if(owned[pe_req_o.id]) $fatal(1,"Live ID reused");
        if(pe_req_o.op != VLE || pe_req_o.vl != 1024 ||
           pe_req_o.vd != 5'((issues%4)*8))
          $fatal(1,"Wrong issued restore payload index=%0d",issues);
        if(|{pe_req_o.hazard_vs1,pe_req_o.hazard_vs2,
             pe_req_o.hazard_vm,pe_req_o.hazard_vd})
          $fatal(1,"Unexpected stale restore hazard index=%0d",issues);
        request_seen=1;
        owned[pe_req_o.id]=1;
        ack_due=cycles+1+gap;
        due[pe_req_o.id]=cycles+20+gap;
        issues++;
      end
      if(ack_due!=0 && cycles==ack_due) begin
        addrgen_ack_i=1;
        ack_due=0;
      end
      for(int i=0;i<8;i++) if(owned[i] && cycles==due[i]) begin
        pe_resp_i[4+OffsetLoad].vinsn_done[i]=1;
        owned[i]=0;
        completions++;
      end
      if(cycles>10000) $fatal(1,"Timeout issues=%0d responses=%0d done=%0d running=%h",
                              issues,responses,completions,pe_vinsn_running_o);
    end
  end
  always @(posedge clk_i) if(rst_ni && ara_resp_valid_o) begin
    if(!ara_req_ready_o || ara_resp_o.exception.valid)
      $fatal(1,"Bad scalar response");
    responses++;
  end
  initial begin
    void'($value$plusargs("GAP=%d",gap));
    void'($value$plusargs("SERIAL=%d",serial_mode));
    void'($value$plusargs("ALIAS=%d",alias_setting));
    #200;
    @(negedge clk_i); #1; rst_ni=1;
    repeat(4) @(negedge clk_i);
    for(int n=0;n<32;n++) begin
      #1;
      ara_req_i='0;
      ara_req_i.token=!(n%2);
      ara_req_i.op=VLE;
      ara_req_i.vm=1;
      ara_req_i.vd=5'((n%4)*8);
      ara_req_i.use_vd=1;
      ara_req_i.vl=1024;
      ara_req_i.emul=LMUL_8;
      ara_req_i.vtype.vlmul=LMUL_8;
      ara_req_i.vtype.vsew=EW8;
      ara_req_i.vtype.vta=1;
      ara_req_i.vtype.vma=1;
      ara_req_valid_i=1;
      // Observe the response on an edge, then withdraw the request.
      do @(posedge clk_i); while(!ara_resp_valid_o);
      @(negedge clk_i); #1; ara_req_valid_i=0;
      if(serial_mode) begin
        do @(negedge clk_i); while(!ara_idle_o);
        repeat(3) @(negedge clk_i);
      end else repeat(2) @(negedge clk_i);
    end
    repeat(100) @(negedge clk_i);
    if(issues!=32 || responses!=32 || completions!=32 ||
       ara_idle_o!==1 || pe_vinsn_running_o!==0)
      $fatal(1,"Incomplete drain");
    $display("SEQUENCER_RESTORE_PASS issues=%0d responses=%0d completions=%0d serial=%0d gap=%0d",
             issues,responses,completions,serial_mode,gap);
    $finish;
  end
endmodule
