#!/usr/bin/env python3
"""Freeze real pre/post RTL and run bounded VCS cycle equivalence + integer oracle."""
import argparse
import hashlib
import difflib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REL = 'hardware/src/vlsu/qbs/qbs_fp_accumulator.sv'
BEFORE = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def one_replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected unique source anchor: {old!r}')
    return text.replace(old, new)


def rename_module(data, suffix):
    name = b'qbs_fp_accumulator'
    data = one_replace(data, b'module ' + name + b'\n', b'module ' + name + suffix + b'\n')
    return one_replace(data, b'endmodule : ' + name, b'endmodule : ' + name + suffix)


def scope_body(source):
    source = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
    source = re.sub(r'  localparam fpu_implementation_t CastImplementation =.*?\n  };', '', source, flags=re.S)
    start = source.index('  if (SplitIssue) begin : gen_cast_port')
    stop = source.index('  if (HalfScaleIssue)', start)
    source = source[:start] + source[stop:]
    source = source.replace('logic [2:0][31:0] cast_operands;', 'logic [31:0] cast_operand;')
    source = source.replace('cast_operands[0]', 'cast_operand').replace('cast_operands', 'cast_operand')
    return re.sub(r'\s+', '', source)


def cast_wrapper(source, name):
    constants = re.search(r'  localparam fpu_features_t FpuFeatures =.*?\n  };', source, re.S)
    assert constants
    implementation = re.search(r'  localparam fpu_implementation_t CastImplementation =.*?\n  };', source, re.S)
    start = source.index('  if (SplitIssue) begin : gen_cast_port')
    stop = source.index('  if (HalfScaleIssue)', start)
    # Preserve the actual generate block (including the unused single-port branch).
    block = source[start:stop]
    assert 'end else begin : gen_single_port' in block
    assert block.rstrip().endswith('end')
    return '''module %s(
      input logic clk_i,rst_ni,cast_found,input logic [31:0] operand,
      input logic [3:0] cast_index,output logic cast_ready,cast_out_valid,cast_busy,
      output logic [31:0] cast_result,output fpnew_pkg::status_t cast_status,
      output logic [3:0] cast_tag_out);
      import fpnew_pkg::*; import qbs_pkg::*;
      localparam bit SplitIssue = 1;
      typedef logic [3:0] fp_tag_t;
      wire [2:0][31:0] cast_operands = {64'b0,operand};
      wire [31:0] cast_operand = operand;
    ''' % name + constants[0] + '\n' + (implementation[0] if implementation else '') + '\n' + block + '\nendmodule\n'


MONITOR = r'''
  wire direct_done;
  qbs_cast_oracle_20261122 direct_check(direct_done);
  for (genvar p = 0; p < 3; p++) begin : compare_pair
    always @(negedge clk) if (rst_n && !clear) begin
      assert ({ready[p],busy[p],update[p],flags[p],issues[p],updates[p],cursor[p]} ===
              {ready[p+3],busy[p+3],update[p+3],flags[p+3],issues[p+3],updates[p+3],cursor[p+3]})
        else $fatal(1,"Accumulator cycle/control mismatch pair=%0d",p);
      if (update[p]) assert ({update_index[p],update_data[p]} ===
                             {update_index[p+3],update_data[p+3]})
        else $fatal(1,"Accumulator update mismatch pair=%0d",p);
      assert ({gen_dut[p].dut.cast_found,gen_dut[p].dut.cast_ready,
               gen_dut[p].dut.cast_fire,gen_dut[p].dut.cast_out_valid,
               gen_dut[p].dut.cast_busy,gen_dut[p].dut.entry_valid_q,
               gen_dut[p].dut.entry_inflight_q,gen_dut[p].dut.accumulator_valid_q,
               gen_dut[p].dut.schedule_rr_q,gen_dut[p].dut.cast_rr_q,
               gen_dut[p].dut.half_rr_q,gen_dut[p].dut.table_occupancy_sum_o,
               gen_dut[p].dut.table_occupancy_max_o,gen_dut[p].dut.table_full_cycles_o} ===
              {gen_dut[p+3].dut.cast_found,gen_dut[p+3].dut.cast_ready,
               gen_dut[p+3].dut.cast_fire,gen_dut[p+3].dut.cast_out_valid,
               gen_dut[p+3].dut.cast_busy,gen_dut[p+3].dut.entry_valid_q,
               gen_dut[p+3].dut.entry_inflight_q,gen_dut[p+3].dut.accumulator_valid_q,
               gen_dut[p+3].dut.schedule_rr_q,gen_dut[p+3].dut.cast_rr_q,
               gen_dut[p+3].dut.half_rr_q,gen_dut[p+3].dut.table_occupancy_sum_o,
               gen_dut[p+3].dut.table_occupancy_max_o,gen_dut[p+3].dut.table_full_cycles_o})
        else $fatal(1,"Accumulator scheduling/state mismatch pair=%0d",p);
      if (gen_dut[p].dut.cast_out_valid)
        assert ({gen_dut[p].dut.cast_result,gen_dut[p].dut.cast_status,gen_dut[p].dut.cast_tag_out} ===
                {gen_dut[p+3].dut.cast_result,gen_dut[p+3].dut.cast_status,gen_dut[p+3].dut.cast_tag_out})
          else $fatal(1,"Accumulator cast mismatch pair=%0d",p);
      for (int e=0; e<16; e++) if (gen_dut[p].dut.entry_valid_q[e]) begin
        assert (gen_dut[p].dut.entry_state_q[e] === gen_dut[p+3].dut.entry_state_q[e])
          else $fatal(1,"Entry state mismatch");
      end
      for (int a=0; a<128; a++) if (gen_dut[p].dut.accumulator_valid_q[a])
        assert (gen_dut[p].dut.accumulator_data_q[a%8][a/8] ===
                gen_dut[p+3].dut.accumulator_data_q[a%8][a/8])
          else $fatal(1,"Bank value mismatch pair=%0d index=%0d",p,a);
    end
  end
'''


def make_tb(source):
    # Unroll only the testbench generate loop to keep both real modules' internals
    # directly accessible to the inherited checker and cycle equivalence monitor.
    source = one_replace(source, 'module qbs_fp_split_tb;', 'module qbs_cast_equiv_20261122_tb;')
    source = one_replace(source, 'localparam int Modes = 3;', 'localparam int Modes = 6;')
    source = one_replace(source, 'localparam int Rounds = 4;', 'localparam int Rounds = 8;')
    source = one_replace(source, '.SplitIssue(mode != 0), .HalfScaleIssue(mode == 2)',
                         '.SplitIssue(mode % 3 != 0), .HalfScaleIssue(mode % 3 == 2)')
    start = source.index('  for (genvar mode = 0; mode < Modes; mode++) begin : gen_dut')
    stop = source.index('\n  always @(posedge clk)', start)
    body = source[start:stop]
    blocks = []
    inner = body[body.index('\n')+1:body.rfind('\n  end')]
    for mode in range(6):
        chunk = re.sub(r'\bmode\b', str(mode), inner)
        chunk = chunk.replace('qbs_fp_accumulator #(',
                              'qbs_fp_accumulator_before #(' if mode < 3 else 'qbs_fp_accumulator_after #(')
        blocks.append(f'  if (1) begin : mode_{mode}\n{chunk}\n  end\n')
    source = source[:start] + ''.join(blocks) + source[stop:]
    source = re.sub(r'gen_dut\[(\d+)\]', lambda m: f'mode_{m[1]}', source)
    # Emit each comparison block with concrete paths, avoiding dynamic hierarchical indexes.
    monitor = MONITOR[:MONITOR.index('  for (genvar p')]
    comparison = MONITOR[MONITOR.index('    always @(negedge'):MONITOR.rfind('\n  end')]
    for p in range(3):
        part = comparison.replace('gen_dut[p+3]', f'mode_{p+3}').replace('gen_dut[p]', f'mode_{p}')
        part = re.sub(r'\bp\b', str(p), part)
        monitor += part
    source = one_replace(source, '    $finish;',
                         '    assert (direct_done) else $fatal(1,"Oracle unfinished");\n'
                         '    $display("ACCUMULATOR_CYCLE_EQUIV_PASS modes=3 epochs=2");\n    $finish;')
    return one_replace(source, '  if (1) begin : mode_0', monitor + '\n  if (1) begin : mode_0')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    before = subprocess.check_output(['git', 'show', f'{BEFORE}:{REL}'], cwd=ROOT)
    after = (ROOT / REL).read_bytes()
    if b'fpnew_cast_multi #(' not in after or b'CastImplementation' in after:
        raise ValueError('Candidate is not the real direct-cast successor')
    if scope_body(before.decode()) != scope_body(after.decode()):
        raise ValueError('RTL changes outside fixed split cast scope')
    pins = {}
    def put(rel, data):
        dest = out / 'inputs' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        pins[rel] = sha(data)
        return dest
    old_path = put('before.sv', rename_module(before, b'_before'))
    new_path = put('after.sv', rename_module(after, b'_after'))
    put('real_before.sv', before)
    put('real_after.sv', after)
    (out / 'source.diff').write_text(''.join(difflib.unified_diff(
        before.decode().splitlines(True), after.decode().splitlines(True),
        fromfile=BEFORE + ':' + REL, tofile='captured-working:' + REL)))
    wrappers = put('ports.sv', (cast_wrapper(before.decode(), 'cast_before') + cast_wrapper(after.decode(), 'cast_after')).encode())
    base = (ROOT / 'verification/qbs/qbs_fp_split_tb.sv').read_bytes()
    put('parent_tb.sv', base)
    tb = put('tb.sv', make_tb(base.decode()).encode())
    oracle = put('oracle.sv', Path(__file__).with_name('qbs_cast_oracle_20261122.sv').read_bytes())
    put('runner.py', Path(__file__).read_bytes())
    sources = ['hardware/deps/common_cells/src/cf_math_pkg.sv',
               'hardware/deps/axi/src/axi_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
               'hardware/include/qbs_pkg.sv', 'hardware/deps/common_cells/src/lzc.sv',
               'hardware/deps/common_cells/src/rr_arb_tree.sv']
    sources += ['hardware/deps/fpnew/src/' + name + '.sv' for name in (
        'lfsr_sr', 'fpnew_classifier', 'fpnew_rounding', 'fpnew_cast_multi',
        'fpnew_fma', 'fpnew_opgroup_fmt_slice', 'fpnew_opgroup_multifmt_slice',
        'fpnew_opgroup_block', 'fpnew_top')]
    sources += ['hardware/src/vlsu/qbs/qbs_half_scale.sv']
    files = [put(rel, (ROOT / rel).read_bytes()) for rel in sources]
    includes = []
    for directory in ['hardware/include', 'hardware/deps/common_cells/include', 'hardware/deps/axi/include']:
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file():
                put(str(path.relative_to(ROOT)), path.read_bytes())
        includes.append('+incdir+' + str(out / 'inputs' / directory))
    cmd = [shutil.which('vcs') or 'vcs', '-full64', '-sverilog', '-timescale=1ns/1ps',
           '-assert', 'svaext', '+lint=TFIPC-L', '-l', 'compile.log', *includes,
           *map(str, files), str(old_path), str(new_path), str(wrappers), str(oracle),
           str(tb), '-top', 'qbs_cast_equiv_20261122_tb', '-o', 'simv']
    receipt = dict(schema='qbs-cast-cycle-equiv-v1', before_commit=BEFORE,
                   before_sha256=sha(before), after_sha256=sha(after), pins=pins, scope_guard='PASS',
                   compile=cmd, run=['./simv', '-l', 'run.log'], status='PREPARED')
    manifest = out / 'receipt.json'
    manifest.write_text(json.dumps(receipt, indent=2) + '\n')
    try:
        with (out / 'compile.stdout').open('w') as log:
            subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300, check=True)
        with (out / 'run.stdout').open('w') as log:
            subprocess.run(receipt['run'], cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=True)
        log = (out / 'run.log').read_text()
        if 'CAST_ORACLE_PASS' not in log or 'ACCUMULATOR_CYCLE_EQUIV_PASS' not in log or re.search(r'Fatal:|Error:', log):
            raise ValueError('Missing pass coverage or simulator errors')
        for rel, digest in pins.items():
            if sha((out / 'inputs' / rel).read_bytes()) != digest:
                raise ValueError('Frozen source drift: ' + rel)
        receipt['status'] = 'PASS'
        receipt['working_candidate_still_identical'] = sha((ROOT / REL).read_bytes()) == sha(after)
    except Exception as exc:
        receipt.update(status='FAIL', error=str(exc))
        raise
    finally:
        manifest.write_text(json.dumps(receipt, indent=2) + '\n')
    print(manifest)


if __name__ == '__main__':
    main()
