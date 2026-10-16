#!/usr/bin/env python3
"""Execute the sealed MMU address-composition block; not a board reproduction.

TLB lookup results and previous-cycle page size are explicit boundary inputs.
No PTW, cache, CPU, or FPGA implementation is simulated by this probe.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "verification/cva6"))
import run_load_contract as contract

PREFIX = """`timescale 1ns/1ps
module mmu_ppn_slice_tb;
  localparam config_pkg::cva6_cfg_t CVA6Cfg =
      build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  localparam int PPNWMin = (CVA6Cfg.PPNW - 1 > 29) ? 29 : CVA6Cfg.PPNW - 1;
  typedef struct packed {logic [CVA6Cfg.PPNW-1:0] ppn;} pte_t;
  pte_t dtlb_content, dtlb_g_content, dtlb_pte_q, dtlb_gpte_q;
  logic [CVA6Cfg.VLEN-1:0] lsu_vaddr_q, lsu_vaddr_n;
  logic [CVA6Cfg.PPNW-1:0] lsu_dtlb_ppn_o;
  logic [CVA6Cfg.PLEN-1:0] lsu_paddr_o;
  logic [CVA6Cfg.PtLevels-2:0] dtlb_is_page_q, dtlb_is_page;
  logic en_ld_st_translation_i=1, en_ld_st_g_translation_i=0;
  typedef struct packed {logic valid;} ex_t;
  ex_t misaligned_ex_q;
  logic lsu_valid_o;
  logic clk=0, rst=0;
  logic reference_ppn=0;
  wire [43:0] tested_ppn=reference_ppn ? lsu_paddr_o[55:12] : lsu_dtlb_ppn_o;
  wire mapped_pop, mapped_request;
  load_unit mapped_load (
    .clk_i(clk), .rst_ni(rst), .flush_i(1'b0), .valid_i(1'b1),
    .\\lsu_ctrl_i[valid] (1'b1), .\\lsu_ctrl_i[vaddr] (lsu_vaddr_n),
    .\\lsu_ctrl_i[tinst] (32'b0), .\\lsu_ctrl_i[hs_ld_st_inst] (1'b0),
    .\\lsu_ctrl_i[hlvx_inst] (1'b0), .\\lsu_ctrl_i[overflow] (1'b0),
    .\\lsu_ctrl_i[g_overflow] (1'b0), .\\lsu_ctrl_i[data] (64'b0),
    .\\lsu_ctrl_i[be] (8'hff), .\\lsu_ctrl_i[fu] (4'd1),
    .\\lsu_ctrl_i[operation] (8'd38), .\\lsu_ctrl_i[trans_id] (3'd3),
    .pop_ld_o(mapped_pop), .paddr_i(lsu_paddr_o),
    .dtlb_ppn_i(tested_ppn), .dtlb_hit_i(1'b1),
    .\\ex_i[cause] (64'b0), .\\ex_i[tval] (64'b0), .\\ex_i[tval2] (41'b0),
    .\\ex_i[tinst] (32'b0), .\\ex_i[gva] (1'b0), .\\ex_i[valid] (1'b0),
    .page_offset_matches_i(1'b0), .store_buffer_empty_i(1'b1),
    .commit_tran_id_i(3'd0), .dcache_wbuffer_not_ni_i(1'b1),
    .\\req_port_i[data_gnt] (1'b1), .\\req_port_i[data_rvalid] (1'b0),
    .\\req_port_i[data_rid] (1'b0), .\\req_port_i[data_rdata] (64'b0),
    .\\req_port_i[data_ruser] (2'b0), .\\req_port_o[data_req] (mapped_request)
  );
  int mismatches=0;
  always_comb begin
    lsu_valid_o=1;
"""
SUFFIX = """
    end
  end
  task automatic sample(string name, logic[63:0] va, logic[43:0] pte,
                        logic[1:0] previous_page, logic[55:0] expected_pa);
    lsu_vaddr_n=va; lsu_vaddr_q=va;
    reference_ppn=0;
    dtlb_content.ppn=pte; dtlb_pte_q.ppn=pte;
    dtlb_is_page_q=previous_page; dtlb_is_page=previous_page;
    #1;
    if(lsu_paddr_o !== expected_pa) $fatal(1,"PROBE_ORACLE_ERROR physical address");
    $display("PPN_CASE %s va=%h ppn=%h expected=%h paddr=%h mismatch=%0d",
        name,va,lsu_dtlb_ppn_o,expected_pa[55:12],lsu_paddr_o,
        lsu_dtlb_ppn_o !== expected_pa[55:12]);
    $display("MAPPED_LOAD %s cache_request=%b pop=%b commit_mismatch=1",name,mapped_request,mapped_pop);
    if(lsu_dtlb_ppn_o !== expected_pa[55:12]) mismatches++;
    reference_ppn=1; #1;
    if(mapped_pop !== 1'b1) $fatal(1,"PROBE_CONTROL_ERROR correct DDR PPN must allow pop");
    $display("MAPPED_CONTROL %s correct_ppn_pop=%b",name,mapped_pop);
    reference_ppn=0;
  endtask
  initial begin
    misaligned_ex_q='0; dtlb_g_content='0; dtlb_gpte_q='0;
    #201; clk=1; #1; clk=0; rst=1;
    sample("4K",64'hffffffd602e10b80,44'h82e10,2'b00,56'h82e10b80);
    sample("2M",64'hffffffd602e10b80,44'h82e00,2'b10,56'h82e10b80);
    sample("1G",64'hffffffd602e10b80,44'h80000,2'b01,56'h82e10b80);
    sample("1G_low_offset",64'hffffffd600008b80,44'h80000,2'b01,56'h80008b80);
    sample("2M_peripheral_alias",64'hffffffd602e08b80,44'h82e00,2'b10,56'h82e08b80);
    sample("2M_external_NI_alias",64'hffffffd602e40b80,44'h82e00,2'b10,56'h82e40b80);
    sample("board_current_task",64'hffffffd602803b80,44'h82800,2'b10,56'h82803b80);
    reference_ppn=0; #1;
    if(mapped_pop !== 1'b0) $fatal(1,"Board-address NI reproduction did not block pop");
    sample("board_irq_task",64'hffffffd602804780,44'h82800,2'b10,56'h82804780);
    reference_ppn=0; #1;
    if(mapped_pop !== 1'b0) $fatal(1,"IRQ board-address NI reproduction did not block pop");
    $display("PPN_PROBE_DONE mismatches=%0d scope=composition_only_not_board",mismatches);
    $finish;
  end
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--load-netlist", type=Path, required=True)
    parser.add_argument("--unisims", type=Path, required=True)
    parser.add_argument("--mmu-source", type=Path,
                        help="Explicit repair candidate; sealed baseline stays unchanged")
    parser.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()
    output = contract.validate_output(args.output, args.package)
    output.mkdir(parents=True)
    (output / "build").mkdir()
    manifest = contract.freeze_inputs(args.package, output)
    source_name = "rtl/cva6/core/cva6_mmu/cva6_mmu.sv"
    data = (args.package / source_name).read_bytes()
    seal = contract.parse_checksums((args.package / "SHA256SUMS").read_bytes())
    if contract.digest(data) != seal[source_name]:
        raise ValueError("MMU source differs from seal")
    baseline_sha = contract.digest(data)
    if args.mmu_source:
        data = args.mmu_source.read_bytes()
    source = data.decode()
    start = source.index("    lsu_paddr_o = (CVA6Cfg.PLEN)")
    end = source.index("      // ---------\n      // DTLB Hit", start)
    contract.freeze_bytes(output / "inputs/cva6_mmu.original.sv", data)
    suffix = SUFFIX
    if args.expect_fixed:
        suffix = suffix.replace("mapped_pop !== 1'b0", "mapped_pop !== 1'b1")
        suffix = suffix.replace("Board-address NI reproduction did not block pop",
                                "Repaired board-address load remains blocked")
        suffix = suffix.replace("IRQ board-address NI reproduction did not block pop",
                                "Repaired IRQ board-address load remains blocked")
        suffix = suffix.replace(
            '    $display("PPN_PROBE_DONE',
            """    if(mismatches != 0) $fatal(1,"Repaired PPN differs from oracle");
    // Current 2M translation must not depend on any previous page size.
    for(int old_page=0; old_page<3; old_page++) begin
      dtlb_is_page_q=old_page; #1;
      if(lsu_dtlb_ppn_o !== 44'h82804 || mapped_pop !== 1'b1)
        $fatal(1,"Current PPN contaminated by previous page size");
    end
    dtlb_is_page=0; dtlb_content.ppn=44'h92345; #1;
    if(lsu_dtlb_ppn_o !== 44'h92345) $fatal(1,"4K after superpage");
    dtlb_is_page=1; dtlb_content.ppn=44'h80000; #1;
    if(lsu_dtlb_ppn_o !== 44'h82804) $fatal(1,"1G after 4K");
    for(int page=0; page<3; page++) begin
      for(int offset=0; offset<256; offset++) begin
        lsu_vaddr_n=64'hffffffd600000000 | (64'(offset*104729) & 64'h3fffffff);
        dtlb_is_page=page; dtlb_is_page_q=(page+1)%3;
        dtlb_content.ppn=44'h80000;
        #1;
        case(page)
          0: if(lsu_dtlb_ppn_o !== 44'h80000) $fatal(1,"4K offset");
          1: if(lsu_dtlb_ppn_o !== (44'h80000 | ((lsu_vaddr_n>>12)&44'h3ffff)))
               $fatal(1,"1G offset");
          2: if(lsu_dtlb_ppn_o !== (44'h80000 | ((lsu_vaddr_n>>12)&44'h1ff)))
               $fatal(1,"2M offset");
        endcase
      end
    end
    dtlb_is_page=0; dtlb_content.ppn=44'h10; #1;
    if(mapped_pop !== 1'b0) $fatal(1,"True NI access must still wait for commit");
    en_ld_st_translation_i=0; lsu_vaddr_n=64'h82804780; #1;
    if(lsu_dtlb_ppn_o !== 44'h82804) $fatal(1,"Bare address");
    $display("REPAIR_REGRESSION offsets=768 page_switch=PASS real_NI=PASS bare=PASS");
    $display("PPN_PROBE_DONE""")
    contract.freeze_bytes(output / "inputs/mmu_ppn_slice_tb.sv",
                          (PREFIX + source[start:end] + suffix).encode())
    netlist = args.load_netlist.read_bytes()
    contract.freeze_bytes(output / "inputs/load_mapped.v", netlist)
    contract.freeze_bytes(output / "inputs/runner.py", Path(__file__).read_bytes())
    contract.save(output / "primitive_hashes.json", {
        p.name: contract.digest(p.read_bytes()) for p in sorted(args.unisims.glob("*.v"))})
    contract.save(output / "extraction.json", dict(source=source_name,
        sha256=contract.digest(data), baseline_sha256=baseline_sha,
        expect_fixed=args.expect_fixed, first_line=source[:start].count("\n")+1,
        end_line_exclusive=source[:end].count("\n")+1,
        scope="verbatim composition block with controlled TLB boundary inputs",
        load_netlist_sha256=contract.digest(netlist),
        hardware_validated=False, ptw_simulated=False, mmu_netlist_simulated=False))
    manifest["compile_sources"] = [p for p in manifest["compile_sources"]
                                   if not p.endswith("/load_unit.sv")]
    manifest["compile_sources"] += ["load_mapped.v", "mmu_ppn_slice_tb.sv"]
    manifest["top"] = "mmu_ppn_slice_tb"
    for name, command, timeout in (
        ("compile",contract.compile_command(output,"vcs",manifest) +
         ["-top","glbl","+libext+.v","-y",str(args.unisims)],180),
        ("run",[str(output / "build/simv"),"-no_save"],30)):
        with (output / (name+".log")).open("w") as log:
            result = subprocess.run(command,cwd=output / "build",stdout=log,
                                    stderr=subprocess.STDOUT,timeout=timeout)
        text = (output / (name+".log")).read_text()
        if result.returncode or contract.BUILD_ERROR.search(text):
            raise RuntimeError(name+" failed; inspect log")
    if "PPN_PROBE_DONE" not in text:
        raise RuntimeError("Missing final marker")
    print(text)


if __name__ == "__main__":
    main()
