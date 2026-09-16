#!/usr/bin/env python3
"""Build focused miters from the exact pre-edit and current RTL sources."""
import argparse
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
ROUND = Path("hardware/deps/fpnew/vendor/openc910/C910_RTL_FACTORY/gen_rtl/vfdsu/rtl/ct_vfdsu_round.v")


def one(pattern, text):
    matches = re.findall(pattern, text, re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f"expected one match for {pattern}, found {len(matches)}")
    return matches[0]


def address_module(name, source):
    body = one(r"(^  function automatic void set_end_addr\b.*?^  endfunction)", source)
    return f"""module {name} import ara_pkg::*; import cf_math_pkg::*; #(
  parameter int AxiAddrWidth=64, AxiDataWidth=128, VLEN=1024,
  localparam int clog2_AxiStrobeWidth=$clog2(AxiDataWidth/8),
  localparam type axi_addr_t=logic[AxiAddrWidth-1:0],
  localparam type vlen_t=logic[$clog2(VLEN+1)-1:0]
) (
  input logic[AxiAddrWidth-13:0] next_2page_msb,
  input vlen_t num_bytes,
  input axi_addr_t addr, aligned_start_addr,
  input logic[clog2_AxiStrobeWidth:0] eff_axi_dw,
  input logic[idx_width(clog2_AxiStrobeWidth):0] eff_axi_dw_log,
  output axi_addr_t aligned_end_addr, aligned_next_start_addr
);
  import axi_pkg::aligned_addr;
  axi_addr_t aligned_start_addr_d;
{body}
  always_comb set_end_addr(next_2page_msb, num_bytes, addr, eff_axi_dw,
      eff_axi_dw_log, aligned_start_addr, aligned_end_addr, aligned_next_start_addr);
endmodule
"""


def round_bench(source):
    ports = re.findall(r"^(input|output)\s*(\[\d+\s*:\s*\d+\])?\s+(\w+)\s*;", source, re.M)
    if len(ports) != 60 or len({p[2] for p in ports}) != 60:
        raise ValueError(f"unexpected round module interface: {len(ports)} ports")
    declarations, inputs, outputs, connections = [], [], [], []
    controls = {"forever_cpuclk", "cpurst_b", "cp0_vfpu_icg_en", "cp0_yy_clk_en", "pad_yy_icg_scan_en"}
    for direction, width, name in ports:
        declarations.append(f"  logic {width} {name};")
        if direction == "input" and name not in controls:
            inputs.append(f"      {name} = {{$urandom, $urandom}};")
        if direction == "output":
            declarations.append(f"  logic {width} ref_{name};")
            outputs.append(name)
        connections.append(f".{name}({'ref_' if direction == 'output' else ''}{name})")
    lhs = ", ".join(outputs)
    rhs = ", ".join("ref_" + name for name in outputs)
    return "\n".join([
        "module vfdsu_round_equivalence_tb;", *declarations,
        "  int seed=32'h7c35a204;",
        "  ct_vfdsu_round dut (.*);",
        "  ct_vfdsu_round_reference reference (" + ", ".join(connections) + ");",
        "  initial forever begin #5; forever_cpuclk = ~forever_cpuclk; end",
        "  initial begin",
        "    forever_cpuclk=0; cpurst_b=0; cp0_vfpu_icg_en=1; cp0_yy_clk_en=1; pad_yy_icg_scan_en=0;",
        "    seed=$urandom(seed);",
        "    #12;",
        "    for (int trial=0; trial<30000; trial++) begin",
        "      @(negedge forever_cpuclk);", *inputs,
        "      cpurst_b = trial % 997 != 0;",
        "      vfdsu_ex3_rm=3'(trial%8);",
        "      {vfdsu_ex3_double,vfdsu_ex3_single,vfdsu_ex3_half,vfdsu_ex3_bfloat}=4'(trial%16);",
        "      if (trial<220) begin",
        "        total_qt_rt_58 = (58'd1 << (trial%58))-1'b1;",
        "        vfdsu_ex3_result_denorm_round_add_num = 53'd1 << (trial%53);",
        "      end",
        "      @(posedge forever_cpuclk); #1;",
        f"      assert ({{{lhs}}} === {{{rhs}}})",
        "        else $fatal(1, \"round mismatch trial=%0d mode=%0d got=%h ref=%h\",",
        "            trial,vfdsu_ex3_rm,vfdsu_ex4_frac,ref_vfdsu_ex4_frac);",
        "    end",
        '    $display("VFDSU round equivalence PASS cycles=30000 outputs=25");',
        "    $finish;", "  end", "endmodule", ""])


def round_timing_module(source):
    ports = re.findall(r"^(input|output)\s*(\[\d+\s*:\s*\d+\])?\s+(\w+)\s*;", source, re.M)
    declarations = ["  input logic clk_i, rst_ni"]
    regs, reset, update, connections = [], [], [], []
    for direction, width, name in ports:
        if name in ("forever_cpuclk", "cpurst_b"):
            connections.append(f".{name}({'clk_i' if name == 'forever_cpuclk' else 'rst_ni'})")
            continue
        declarations.append(f"  {direction} logic {width} {name}")
        if direction == "input":
            regs.append(f"  logic {width} {name}_q;")
            reset.append(f"      {name}_q <= '0;")
            update.append(f"      {name}_q <= {name};")
        connections.append(f".{name}({name}{'_q' if direction == 'input' else ''})")
    return ("module vfdsu_round_timing (\n" + ",\n".join(declarations) + "\n);\n"
            + "\n".join(regs) + "\n  always_ff @(posedge clk_i or negedge rst_ni) begin\n"
            + "    if (!rst_ni) begin\n" + "\n".join(reset) + "\n    end else begin\n"
            + "\n".join(update) + "\n    end\n  end\n  ct_vfdsu_round i_round ("
            + ", ".join(connections) + ");\nendmodule\n")


def akv_count_module(current, previous):
    function = one(r"(^  function automatic logic \[6:0\] capped_tile_count\b.*?^  endfunction)", current)
    remaining = one(r"  assign refill_remaining = (.*?);", current)
    old_count = one(r"fill_tile_count_q <=\s*(unsigned'\(context_kv_length_q\).*?);", previous)
    guard = "command_tile_start_i >= context_kv_length_q"
    if guard not in current or guard not in previous:
        raise ValueError("full-width refill range check changed")
    return f"""module akv_count_cone import ara_pkg::*; import akv_pkg::*; #(
    parameter int VAddrWidth=64
) (
    input logic [15:0] context_kv_length_q,
    input logic [VAddrWidth-1:0] command_tile_start_i,
    input akv_command_e command_i,
    output logic valid,
    output logic [6:0] count, reference_count
);
{function}
    logic [15:0] refill_remaining;
    assign refill_remaining = {remaining};
    assign valid = !({guard});
    assign count = capped_tile_count(refill_remaining, command_i == AKV_COMMAND_V2_REFILL);
    assign reference_count = {old_count};
endmodule
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--address-only", action="store_true")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    current = (ROOT / "hardware/src/vlsu/addrgen.sv").read_text()
    previous = (args.before_dir / "addrgen.sv").read_text()
    (args.output / "addrgen_cones.sv").write_text(
        address_module("addrgen_end_dut", current) +
        address_module("addrgen_end_reference", previous))
    if args.address_only:
        return
    previous_round = (args.before_dir / "ct_vfdsu_round.v").read_text()
    (args.output / "round_reference.v").write_text(
        re.sub(r"\bct_vfdsu_round\b", "ct_vfdsu_round_reference", previous_round))
    (args.output / "round_tb.sv").write_text(round_bench((ROOT / ROUND).read_text()))
    (args.output / "akv_count_cone.sv").write_text(akv_count_module(
        (ROOT / "hardware/src/vlsu/akv/akv_engine.sv").read_text(),
        (args.before_dir / "akv_engine.sv").read_text()))


if __name__ == "__main__":
    main()
