#!/usr/bin/env python3
"""Matched registered-boundary DC comparison of the exact production return blocks.

Exclude unchanged SRAMs. Extract rather than reimplement each routing block;
the added input/output registers and constraints are identical on both sides.
Run this worker directly under systemd --user, using the established EDA container.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(p):
    return json.loads(p.read_text())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output', type=Path)
    p.add_argument('--component', required=True, type=Path)
    a = p.parse_args(); out = a.output.resolve(); comp = a.component.resolve()
    out.mkdir(parents=True, exist_ok=False)
    # Import the pinned functional runner for common hashing/status utilities.
    import run_vrf_return as test
    pins = read(comp/'source-pins.json')
    for f, digest in pins.items():
        if test.sha(Path(f)) != digest: raise ValueError('Component drift: '+f)
    if read(comp/'status.json')['state'] != 'PASS': raise ValueError('Functional gate not passed')
    status = dict(state='PREPARING')
    def state(**kw):
        status.update(kw); test.save(out/'status.json', status); print(json.dumps(status), flush=True)
    wrapper = '''module vrf_return_timing import ara_pkg::*; (
  input logic clk_i, rst_ni,
  input elen_t [7:0] data_i,
  input logic [7:0] valid_i,
  input opqueue_e [7:0] target_i,
  output elen_t [NrOperandQueues-1:0] data_o,
  output logic [NrOperandQueues-1:0] valid_o
);
  localparam int NrBanks = 8;
  localparam int DataWidth = 64;
  elen_t [7:0] rdata;
  logic [7:0] rdata_valid_q;
  opqueue_e [7:0] tgt_opqueue_q;
  elen_t [NrOperandQueues-1:0] operand_o;
  logic [NrOperandQueues-1:0] operand_valid_o;
  always_ff @(posedge clk_i) begin
    rdata <= data_i;
    data_o <= operand_o;
  end
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      rdata_valid_q <= '0; tgt_opqueue_q <= '0; valid_o <= '0;
    end else begin
      rdata_valid_q <= valid_i; tgt_opqueue_q <= target_i; valid_o <= operand_valid_o;
    end
  end
'''
    try:
        shutil.copy2(__file__, out/'worker.py')
        tcl = (HERE/'shared_alu_ppa.tcl').read_text()
        paths = [f'src/{Path(x).name}' for x in test.PACKAGES]
        paths += [f'src/{n}.sv' for n in test.CELLS] + ['src/vrf_return_timing.sv']
        tcl, count = re.subn(r'set sources \{.*?\}', 'set sources {'+' '.join(paths)+'}', tcl, count=1, flags=re.S)
        if count != 1: raise ValueError('Cannot identify inherited source list')
        tcl = tcl.replace('set_app_var search_path [concat ./src $search_path]',
                          'set_app_var search_path [concat ./src ./include $search_path]')
        tcl = tcl.replace('elaborate simd_alu_timing', 'elaborate vrf_return_timing')
        tcl = tcl.replace('SHARED_ALU_PPA_COMPLETE', 'VRF_RETURN_PPA_COMPLETE')
        for variant, rtl in [('baseline', comp/'baseline.sv'), ('candidate', comp/'src/vector_regfile.sv')]:
            d = out/variant; d.mkdir()
            shutil.copytree(comp/'src', d/'src')
            shutil.copytree(comp/'include', d/'include')
            original = rtl.read_text()
            marker = '  //  Multiplexer  //'
            start = original.index(marker)
            start = original.index('\n\n', start)+2
            block = original[start:original.index('endmodule : vector_regfile', start)]
            (d/'src/vrf_return_timing.sv').write_text(wrapper + block + '\nendmodule\n')
            (d/'return_block.sv.txt').write_text(block)
            (d/'run.tcl').write_text(tcl)
            shutil.copy2(ROOT/'backend/syn/ara_soc/v1-dc/global_scripts/synopsys_dc.setup.env', d/'library_env.tcl')
        own_pins = {str(f):test.sha(f) for f in out.rglob('*') if f.is_file()}
        test.save(out/'source-pins.json', own_pins)
        test.save(out/'manifest.json', dict(component=str(comp), period_ns=1.0, setup_uncertainty_ns=0.15,
            scope='Exact return routing, same registered boundary, no SRAM/SoC area or physical signoff',
            extraction='From Multiplexer section through endmodule; surrounding registers identical'))
        for variant in ('baseline', 'candidate'):
            state(state='SYNTHESIZING', active=variant)
            d = out/variant
            with (d/'dc.log').open('w') as f:
                proc = subprocess.run(['docker','exec','-u',f'{os.getuid()}:{os.getgid()}',
                    '-e',f'HOME={Path.home()}','-w',str(d),'synopsys_workspace','bash','-lc',
                    'exec timeout --signal=TERM --kill-after=30s 7200 dc_shell -f run.tcl'],
                    stdout=f, stderr=subprocess.STDOUT)
            text = (d/'dc.log').read_text(errors='replace')
            if proc.returncode or 'VRF_RETURN_PPA_COMPLETE' not in text or re.search(r'(?m)^Error:', text):
                raise ValueError('DC failure: '+variant)
        for f, digest in own_pins.items():
            if test.sha(Path(f)) != digest: raise ValueError('Input drift: '+f)
        metrics = {}
        for variant in ('baseline', 'candidate'):
            metrics[variant] = dict(
                (line.split('\t')[0], float(line.split('\t')[1]))
                for line in (out/variant/'metrics.tsv').read_text().splitlines())
        test.save(out/'report.json', dict(state='PASS', metrics=metrics,
            area_reduction_pct=100*(1-metrics['candidate']['area_um2']/metrics['baseline']['area_um2'])))
        state(state='PASS', active=None)
        return 0
    except Exception as exc:
        state(state='FAIL', reason=str(exc)); raise


if __name__ == '__main__':
    raise SystemExit(main())
