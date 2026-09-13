// SPDX-License-Identifier: SHL-0.51
module addrgen_end_case import ara_pkg::*; import cf_math_pkg::*; #(
  parameter int AxiAddrWidth=64, AxiDataWidth=128, VLEN=1024,
  localparam int clog2_AxiStrobeWidth=$clog2(AxiDataWidth/8),
  localparam type axi_addr_t=logic[AxiAddrWidth-1:0],
  localparam type vlen_t=logic[$clog2(VLEN+1)-1:0]
) (output logic done=0);
  logic[AxiAddrWidth-13:0] next_2page_msb;
  vlen_t num_bytes;
  axi_addr_t addr, aligned_start_addr, aligned_end_addr, aligned_next_start_addr;
  axi_addr_t ref_end, ref_next;
  logic[clog2_AxiStrobeWidth:0] eff_axi_dw;
  logic[idx_width(clog2_AxiStrobeWidth):0] eff_axi_dw_log;
  addrgen_end_dut #(.AxiAddrWidth(AxiAddrWidth), .AxiDataWidth(AxiDataWidth), .VLEN(VLEN)) dut (.*);
  addrgen_end_reference #(.AxiAddrWidth(AxiAddrWidth), .AxiDataWidth(AxiDataWidth), .VLEN(VLEN)) reference (
      .aligned_end_addr(ref_end), .aligned_next_start_addr(ref_next), .*);
  initial begin
    for (int trial=0; trial<12000; trial++) begin
      addr = axi_addr_t'({$urandom, $urandom});
      if (trial<4096) addr = {AxiAddrWidth{1'b1}} ^ axi_addr_t'(trial);
      num_bytes = vlen_t'($urandom);
      if (trial%13==0) num_bytes=0;
      if (trial%13==1) num_bytes=1;
      if (trial%13==2) num_bytes='1;
      eff_axi_dw_log = (trial/13)%(clog2_AxiStrobeWidth+1);
      eff_axi_dw = 1 << eff_axi_dw_log;
      aligned_start_addr = axi_addr_t'(axi_pkg::aligned_addr(addr, clog2_AxiStrobeWidth));
      next_2page_msb = addr[AxiAddrWidth-1:12]+1'b1;
      #1;
      assert ({aligned_end_addr, aligned_next_start_addr} === {ref_end, ref_next})
        else $fatal(1,"addrgen width=%0d data=%0d addr=%h bytes=%0d dw=%0d got=%h/%h ref=%h/%h",
            AxiAddrWidth,AxiDataWidth,addr,num_bytes,eff_axi_dw,
            aligned_end_addr,aligned_next_start_addr,ref_end,ref_next);
    end
    $display("AddrGen case PASS address=%0d data=%0d vlen=%0d checks=12000",AxiAddrWidth,AxiDataWidth,VLEN);
    done=1;
  end
endmodule

module addrgen_end_equivalence_tb;
  wire [11:0] done;
  for (genvar address=0; address<2; address++) begin
    for (genvar data=0; data<3; data++) begin
      for (genvar vl=0; vl<2; vl++) begin
        addrgen_end_case #(.AxiAddrWidth(32 << address), .AxiDataWidth(64 << data),
            .VLEN(vl==0 ? 1024 : 65536)) test_case (.done(done[(address*3+data)*2+vl]));
      end
    end
  end
  initial begin
    wait (&done);
    $display("AddrGen equivalence PASS configurations=12 checks=144000");
    $finish;
  end
endmodule
