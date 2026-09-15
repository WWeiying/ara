#!/usr/bin/env python3
"""Compare frozen FPGA dispatcher arithmetic and every dispatcher state/output."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent))
from dispatcher_fpga import OLD_UPDATE, NEW_UPDATE, patch_dispatcher_layout
from dispatcher_control_fpga import patch_dispatcher_control, patch_segment_geometry

REL = "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/ara_dispatcher.sv"
SEG_REL = "hardware/fpga/ara_dsa_vcu118/rtl/ara/hardware/src/segment_sequencer.sv"

FIRST_SEGMENT = """
    // A held, legal two-field load: the decoder first drains to WAIT_IDLE,
    // then starts field zero with a nonzero architectural vstart.
    for (int trial=0; trial<64; trial++) begin
      rst_ni=0; repeat (2) @(negedge clk_i); rst_ni=1; fpga_trial=trial;
      force dut.csr_vtype_q=vtype_t'{vsew:vew_e'(fpga_trial%4),vlmul:LMUL_1,default:'0};
      force reference.csr_vtype_q=vtype_t'{vsew:vew_e'(fpga_trial%4),vlmul:LMUL_1,default:'0};
      force dut.csr_vl_q=11'(128 >> (fpga_trial%4));
      force reference.csr_vl_q=11'(128 >> (fpga_trial%4));
      force dut.csr_vstart_q=11'((fpga_trial/4) % (128 >> (fpga_trial%4)));
      force reference.csr_vstart_q=11'((fpga_trial/4) % (128 >> (fpga_trial%4)));
      acc_req_i='0; acc_req_i.req_valid=1; acc_req_i.resp_ready=1; acc_req_i.acc_cons_en=1;
      acc_req_i.rs1=64'h80000000;
      acc_req_i.insn={3'd1,1'b0,2'b00,1'b1,5'd0,5'd1,
                     3'(trial%4 == 0 ? 0 : (trial%4)+4),5'd8,7'h07};
      ara_req_ready_i=0; ara_idle_i=1; sldu_idle_i=1;
      ara_resp_i='0; ara_resp_valid_i=0; load_complete_i=0; store_complete_i=0;
      #1;
      release dut.csr_vtype_q; release reference.csr_vtype_q;
      release dut.csr_vl_q; release reference.csr_vl_q;
      release dut.csr_vstart_q; release reference.csr_vstart_q;
      cycle();
      ara_req_ready_i=1;
      repeat (4) cycle();
    end
"""


def repair_stimulus():
    """Nonzero repair contexts and every segment phase, including backpressure."""
    # Shared frozen state is released before the checked edge, so the original
    # and candidate must compute identical next state, not merely forced Qs.
    fields = {
        "overlap_elements_per_reg_q": "11'(128 >> (trial%4))",
        "overlap_reg_first_element_q": "11'((trial%8)*(128 >> (trial%4)))",
        "overlap_vl_q": "11'((trial%8+1)*(128 >> (trial%4)) + (trial%3)-1)",
        "overlap_prefix_vl_q": "11'((trial%8)*(128 >> (trial%4)) + (trial%3)-1)",
        "overlap_target_eew_q": "vew_e'(trial%4)",
        "overlap_current_old_eew_q": "vew_e'((trial+1)%4)",
        "overlap_current_old_eew_valid_q": "1'b1",
        "overlap_current_vd_q": "5'(trial%32)",
        "overlap_vd_q": "5'((trial%32)-(trial%8))",
        "overlap_boundary_vd_q": "5'(trial%32)",
        "overlap_boundary_old_eew_q": "vew_e'((trial+1)%4)",
        "overlap_lmul_q": "vlmul_e'(trial%8)",
        "overlap_reg_index_q": "3'(trial%8)",
        "overlap_old_eew_q": "{8{vew_e'((trial+1)%4)}}",
        "overlap_old_eew_valid_q": "8'hff",
        "source_snapshot_eew_q": "vew_e'(trial%4)",
        "source_snapshot_lmul_q": "vlmul_e'(trial%8)",
        "source_snapshot_vl_q": "11'(trial*3)",
        "source_snapshot_vs_q": "5'(trial%32)",
        "vs_buffer_q": "5'(trial%32)",
        "eew_old_buffer_q": "vew_e'((trial+1)%4)",
        "eew_new_buffer_q": "vew_e'(trial%4)",
    }
    states = ("RESHUFFLE", "OVERLAP_PREFIX_FIXUP", "OVERLAP_CAPTURE",
              "OVERLAP_FIXUP", "SOURCE_SNAPSHOT_CAPTURE")
    seg = "i_segment_sequencer.gen_segment_support."
    code = ["for (int repair=0; repair<5; repair++) begin",
            "for (int phase=0; phase<4; phase++) begin",
            "for (int trial=0; trial<64; trial++) begin",
            "rst_ni=0; repeat (2) @(negedge clk_i); rst_ni=1; fpga_trial=trial;",
            "ara_req_ready_i=1'(trial); ara_idle_i=1'(trial>>1); sldu_idle_i=1;",
            "acc_req_i='0; ara_resp_i='0; ara_resp_valid_i=1;",
            "case (repair)"]
    for i, state in enumerate(states):
        code.append(f"{i}: begin force dut.state_q=dut.{state}; "
                    f"force reference.state_q=reference.{state}; end")
    code += ["endcase", "fpga_phase=phase;",
             f"force dut.{seg}state_q[1:0]=2'(fpga_phase);",
             f"force reference.{seg}state_q[1:0]=2'(fpga_phase);"]
    for name, value in fields.items():
        value = value.replace("trial", "fpga_trial")
        code.extend(f"force {inst}.{name} = {value};" for inst in ("dut", "reference"))
    for inst in ("dut", "reference"):
        code += [f"force {inst}.{seg}i_vstart_cnt.i_counter.counter_q=12'(fpga_trial*7);",
                 f"force {inst}.{seg}i_segment_cnt.i_counter.counter_q=4'(fpga_trial%8);"]
    code.append("#1;")
    for inst in ("dut", "reference"):
        for name in list(fields) + ["state_q", seg + "state_q[1:0]",
                                    seg + "i_vstart_cnt.i_counter.counter_q",
                                    seg + "i_segment_cnt.i_counter.counter_q"]:
            code.append(f"release {inst}.{name};")
    code += ["cycle();", "end end end"]
    return "\n".join(code)


def layout_module(source, name, update):
    start = source.index("  function automatic int unsigned lmul_register_count(")
    end = source.index("  // Save eew information before reshuffling", start)
    return """
module NAME #(parameter int VLEN=1024,
    localparam int VLENB=VLEN/8,
    localparam type vlen_t=logic[$clog2(VLEN+1)-1:0]) (
    input vlen_t vstart, vl,
    input logic [63:0] stride,
    input logic scalar_op,
    input rvv_pkg::vlmul_e lmul,
    input rvv_pkg::vew_e eew,
    input logic [4:0] base,
    input rvv_pkg::vew_e [31:0] eew_q,
    input logic [31:0] eew_valid_q,
    output vlen_t source_start, source_end,
    output int unsigned count,
    output logic [2:0] limit,
    output logic needs, mixed,
    output rvv_pkg::vew_e [31:0] eew_d,
    output logic [31:0] eew_valid_d
);
  import rvv_pkg::*;
  import ara_pkg::*;
  struct packed {
    logic [4:0] vd;
    struct packed { vew_e vsew; } vtype;
    vlen_t vstart, vl;
  } ara_req_d;
FUNCTIONS
  always_comb begin
    source_start=slidedown_source_start(vstart,stride,lmul,eew);
    source_end=slidedown_source_end(vl,stride,scalar_op,lmul,eew);
    count=active_register_count(lmul,eew,vstart,vl);
    limit=active_register_limit(lmul,eew,vstart,vl);
    needs=active_group_needs_reshuffle(base,lmul,eew,vstart,vl);
    mixed=active_group_has_mixed_eew(base,lmul,eew,vstart,vl);
    ara_req_d.vd=base; ara_req_d.vtype.vsew=eew;
    ara_req_d.vstart=vstart; ara_req_d.vl=vl;
    eew_d=eew_q; eew_valid_d=eew_valid_q;
    begin
      automatic vlmul_e destination_lmul=lmul;
UPDATE
    end
  end
endmodule
""".replace("NAME", name).replace("FUNCTIONS", source[start:end]).replace("UPDATE", update)


BENCH = r"""
module layout_tb;
  timeunit 1ns; timeprecision 1ps;
  import rvv_pkg::*;
  logic [2:0] done='0;
  for (genvar cfg=0; cfg<3; cfg++) begin : configs
    localparam int VLEN = cfg==0 ? 64 : cfg==1 ? 1024 : 65536;
    localparam int W=$clog2(VLEN+1);
    logic [W-1:0] vstart,vl,a_start,b_start,a_end,b_end;
    logic [63:0] stride;
    logic scalar_op;
    vlmul_e lmul;
    vew_e eew;
    logic [4:0] base;
    vew_e [31:0] eew_q,a_eew,b_eew;
    logic [31:0] eew_valid_q,a_valid,b_valid;
    int unsigned a_count,b_count;
    logic [2:0] a_limit,b_limit;
    logic a_needs,b_needs,a_mixed,b_mixed;
    int checks=0;
    layout_before #(.VLEN(VLEN)) a (.source_start(a_start),.source_end(a_end),
      .count(a_count),.limit(a_limit),.needs(a_needs),.mixed(a_mixed),
      .eew_d(a_eew),.eew_valid_d(a_valid),.*);
    layout_after #(.VLEN(VLEN)) b (.source_start(b_start),.source_end(b_end),
      .count(b_count),.limit(b_limit),.needs(b_needs),.mixed(b_mixed),
      .eew_d(b_eew),.eew_valid_d(b_valid),.*);
    task automatic check;
      #1;
      assert ({a_start,a_end,a_count,a_limit,a_needs,a_mixed,a_eew,a_valid} ===
              {b_start,b_end,b_count,b_limit,b_needs,b_mixed,b_eew,b_valid})
        else $fatal(1,"layout VLEN=%0d check=%0d start=%0d vl=%0d stride=%h scalar=%b lmul=%0d eew=%0d base=%0d start=%0d/%0d end=%0d/%0d count=%0d/%0d",
          VLEN,checks,vstart,vl,stride,scalar_op,lmul,eew,base,
          a_start,b_start,a_end,b_end,a_count,b_count);
      checks++;
    endtask
    initial begin
      vstart=0;vl=0;stride=0;scalar_op=0;lmul=LMUL_1;eew=EW8;base=0;
      eew_valid_q='1;
      for (int i=0;i<32;i++) eew_q[i]=vew_e'(i%4);
      // All starts/ends immediately around all register boundaries, including
      // reversed/empty intervals, fractional LMUL and base clipping at v31.
      for (int e=0;e<8;e++) begin
        eew=vew_e'(e);
        for (int m=0;m<8;m++) begin
          lmul=vlmul_e'(m);
          for (int s=0;s<=9;s++) for (int t=0;t<=9;t++) begin
            for (int ds=-1;ds<=1;ds++) for (int dt=-1;dt<=1;dt++) begin
              vstart=W'(((s*(VLEN/8))>>e)+ds);
              vl=W'(((t*(VLEN/8))>>e)+dt);
              base=5'((s+t)%2 ? 0 : 24+(s+t)%8);
              eew_valid_q=(s+t)%3 ? '1 : 32'ha5a55a5a;
              scalar_op=1'(s+t);stride=64'(s);
              check();
            end
          end
        end
      end
      // Exercise low-word carry/borrow and the original modulo-2^64 wrap.
      for (int i=0;i<(1<<W);i++) begin
        vstart=W'(i);vl=W'(i);eew=vew_e'(i%4);lmul=vlmul_e'(i%8);
        for (int edge_case=0;edge_case<8;edge_case++) begin
          case(edge_case)
            0: stride=64'd0;
            1: stride=64'd1;
            2: stride=(64'd1<<W)-1;
            3: stride=(64'd1<<W);
            4: stride=(64'd1<<W)+1;
            5: stride=64'hffffffffffffffff-64'(i);
            6: stride=64'hffffffffffffffff;
            7: stride=64'hffffffffffffffff-64'(i)+1;
          endcase
          scalar_op=0;check();scalar_op=1;check();
        end
      end
      repeat (20000) begin
        vstart=W'($urandom);vl=W'($urandom);stride={$urandom,$urandom};
        eew=vew_e'($urandom_range(0,7));lmul=vlmul_e'($urandom_range(0,7));
        base=5'($urandom);scalar_op=1'($urandom);eew_valid_q=$urandom;
        for (int i=0;i<32;i++) eew_q[i]=vew_e'($urandom_range(0,3));
        check();
      end
      $display("PASS FPGA layout VLEN=%0d checks=%0d",VLEN,checks);
      done[cfg]=1;
    end
  end
  initial begin wait (&done); $display("FPGA layout equivalence PASS"); $finish; end
  initial begin #3000000; $fatal(1,"layout watchdog"); end
endmodule
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output", type=Path)
    ap.add_argument("--reference", default="74042fbd")
    ap.add_argument("--vcs", default="vcs")
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    pkg = ROOT / "hardware/fpga/ara_dsa_vcu118"
    rtl = pkg / "rtl/ara/hardware"
    before = subprocess.check_output(["git", "show", f"{args.reference}:{REL}"],
                                     cwd=ROOT, text=True)
    after = (ROOT / REL).read_text()
    if patch_dispatcher_control(patch_dispatcher_layout(before)) != after:
        raise RuntimeError("FPGA dispatcher differs from the reviewed transform")
    common = [pkg / p for p in (
        "rtl/common_cells/src/cf_math_pkg.sv", "rtl/axi/src/axi_pkg.sv",
        "rtl/fpnew/src/fpnew_pkg.sv", "rtl/cva6/core/include/config_pkg.sv",
        "rtl/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv",
        "rtl/cva6/core/include/riscv_pkg.sv", "rtl/ara/hardware/include/rvv_pkg.sv",
        "rtl/ara/hardware/include/ara_pkg.sv")]
    flags = [args.vcs, "-full64", "-sverilog", "-timescale=1ns/1ps",
             "+incdir+" + str(pkg / "rtl/common_cells/include"),
             "+incdir+" + str(rtl / "include"), "+incdir+" + str(out)]
    results = {}
    (out / "layout.sv").write_text(layout_module(before, "layout_before", OLD_UPDATE) +
                                  layout_module(after, "layout_after", NEW_UPDATE) + BENCH)

    def run(name, sources, top, extra=()):
        with (out / f"{name}_compile.log").open("w") as log:
            subprocess.run(flags + list(extra) + [str(p) for p in common + sources] +
                           ["-top", top, "-o", f"{name}_simv"], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=240)
        with (out / f"{name}_run.log").open("w") as log:
            subprocess.run([str(out / f"{name}_simv"), "+ntb_random_seed=1"], cwd=out,
                           stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        result = (out / f"{name}_run.log").read_text()
        print(result, flush=True)
        if "equivalence PASS" not in result or re.search(r"Fatal:|Error:", result):
            raise RuntimeError(f"{name} did not pass")
        results[name] = result

    run("layout", [out / "layout.sv"], "layout_tb")
    # Derive types and state checks from the frozen FPGA sources, never the
    # concurrently edited main RTL or its Bender dependency checkout.
    ara = (rtl / "src/ara.sv").read_text()
    a = ara.index("  // Interfaces between Ara's dispatcher and Ara's backend\n")
    b = ara.index("  } ara_resp_t;", a) + len("  } ara_resp_t;")
    (out / "dispatcher_check_pkg.sv").write_text("""package dispatcher_check_pkg;
  import ara_pkg::*; import rvv_pkg::*;
  localparam config_pkg::cva6_cfg_t CVA6Cfg = build_config_pkg::build_config(cva6_config_pkg::cva6_cfg);
  localparam int VLEN=1024, NrLanes=4;
  typedef logic[$clog2(VLEN+1)-1:0] vlen_t;
  `include "ara/intf_typedef.svh"
  `CVA6_TYPEDEF_EXCEPTION(exception_t, CVA6Cfg)
  `CVA6_INTF_TYPEDEF_ACC_REQ(accelerator_req_t, CVA6Cfg, fpnew_pkg::roundmode_e)
  `CVA6_INTF_TYPEDEF_ACC_RESP(accelerator_resp_t, CVA6Cfg, exception_t)
""" + ara[a:b] + "\nendpackage\n")
    reference = re.sub(r"\bara_dispatcher\b", "ara_dispatcher_reference", before)
    reference = re.sub(r"\bsegment_sequencer\b", "segment_sequencer_reference", reference)
    (out / "reference.sv").write_text(reference)
    old_segment = subprocess.check_output(["git", "show", f"{args.reference}:{SEG_REL}"],
                                          cwd=ROOT, text=True)
    segment = (ROOT / SEG_REL).read_text()
    if patch_segment_geometry(old_segment) != segment:
        raise RuntimeError("FPGA sequencer differs from the reviewed transform")
    (out / "segment_reference.sv").write_text(re.sub(
        r"\bsegment_sequencer\b", "segment_sequencer_reference", old_segment))
    bench = subprocess.check_output([
        "git", "show", f"{args.reference}:verification/timing/dispatcher_equivalence_tb.sv"
    ], cwd=ROOT, text=True)
    original_bench = bench
    bench = bench.replace("  int seed=", "  int fpga_trial, fpga_phase;\n"
                          "  int fpga_eew_checks=0, fpga_segment_first=0, fpga_segment_later=0;\n"
                          "  int seed=")
    bench = bench.replace("  task automatic compare_outputs;", """  task automatic compare_outputs;
    if (dut.ara_req_valid_d && dut.ara_req_d.use_vd && ara_req_ready_i &&
        dut.state_q != dut.OVERLAP_PREFIX_FIXUP) begin
      fpga_eew_checks++;
      if (dut.is_segment_mem_op && !dut.illegal_insn &&
          dut.i_segment_sequencer.gen_segment_support.state_q == 0) fpga_segment_first++;
      if (dut.i_segment_sequencer.gen_segment_support.state_q == 1) fpga_segment_later++;
      assert ({dut.fpga_eew_req.vl, dut.fpga_eew_req.vstart, dut.fpga_eew_req.vd,
               dut.fpga_eew_req.emul, dut.fpga_eew_req.vtype.vsew,
               dut.single_register_result(dut.fpga_eew_req.op)} ===
              {dut.ara_req_d.vl, dut.ara_req_d.vstart, dut.ara_req_d.vd,
               dut.ara_req_d.emul, dut.ara_req_d.vtype.vsew,
               dut.single_register_result(dut.ara_req_d.op)})
        else $fatal(1,"speculative EEW differs at write cycle=%0d",checks);
    end
""")
    bench = bench.replace("    foreach (state_visits[i])\n", repair_stimulus() + FIRST_SEGMENT +
                          "\n    foreach (state_visits[i])\n")
    bench = bench.replace("    $finish;", """    assert (fpga_eew_checks>100 && fpga_segment_first>0 && fpga_segment_later>0)
      else $fatal(1,"insufficient EEW geometry coverage checks=%0d first=%0d later=%0d",
                  fpga_eew_checks,fpga_segment_first,fpga_segment_later);
    $display("FPGA EEW metadata checks=%0d first_segment=%0d later_segment=%0d",
             fpga_eew_checks,fpga_segment_first,fpga_segment_later);
    $finish;""")
    (out / "dispatcher_equivalence_tb.sv").write_text(bench)
    states = set(re.findall(r"^\s*(\w+_q[q]?)\s*<=", after, re.M))
    states.update(re.findall(r"`FF\(\s*(\w+_q)\s*,", after))
    segstates = set(re.findall(r"^\s*(\w+_q)\s*<=", segment, re.M))
    segstates.update(("segment_cnt_q", "vstart_cnt_q"))
    states.update("i_segment_sequencer.gen_segment_support." + s for s in segstates)
    (out / "dispatcher_state_check.svh").write_text("\n".join(
        f'assert (dut.{s} === reference.{s}) else $fatal(1,"state {s} cycle=%0d",checks);'
        for s in sorted(states)) + "\n")
    run("dispatcher", [pkg / "rtl/cva6/core/include/build_config_pkg.sv",
        rtl / "include/qbs_pkg.sv", rtl / "include/akv_pkg.sv",
        out / "dispatcher_check_pkg.sv", pkg / "rtl/common_cells/src/popcount.sv",
        pkg / "rtl/common_cells/src/delta_counter.sv", pkg / "rtl/common_cells/src/counter.sv",
        rtl / "src/segment_sequencer.sv", out / "segment_reference.sv",
        out / "reference.sv", ROOT / REL,
        out / "dispatcher_equivalence_tb.sv"], "dispatcher_equivalence_tb",
        ["+define+FOR_VERIFY+ARA_QBS_ENABLE+ARA_AKV_ENABLE+ARA_AKV_V2_ENABLE"])
    (out / "result.json").write_text(json.dumps({
        "state": "PASS", "reference": args.reference,
        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
        "testbench_sha256": hashlib.sha256(bench.encode()).hexdigest(),
        "original_testbench_sha256": hashlib.sha256(original_bench.encode()).hexdigest(),
        "segment_before_sha256": hashlib.sha256(old_segment.encode()).hexdigest(),
        "segment_after_sha256": hashlib.sha256(segment.encode()).hexdigest(),
        "layout_vectors": {vlen: int(count) for vlen, count in re.findall(
            r"PASS FPGA layout VLEN=(\d+) checks=(\d+)", results["layout"])},
        "dispatcher_comparison": re.search(
            r"Dispatcher equivalence PASS[^\n]*", results["dispatcher"]).group(),
        "eew_metadata_comparison": re.search(
            r"FPGA EEW metadata checks=[^\n]*", results["dispatcher"]).group(),
        "registered_state_signals": len(states), "vivado_timing_verified": False,
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
