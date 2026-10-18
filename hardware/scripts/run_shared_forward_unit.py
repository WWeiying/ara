#!/usr/bin/env python3
"""Test the actual capture block extracted from operand_requester, with hashes.

This checks storage/selection, not requester matching or instruction ownership;
the matched SoC regression and in-RTL original-response assertion cover those.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--vcs', default='vcs')
    parser.add_argument('--negative-control', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    rtl = root / 'hardware/src/lane/operand_requester.sv'
    source = rtl.read_text()
    begin = source.index('  assign forwarded_operand_valid_o = forwarded_operand_valid_q;')
    end = source.index('`ifdef ARA_RED_CHAIN_BYPASS_4LANE\n  // MFPU result addresses', begin)
    block = source[begin:end]
    assert block.count('a_shared_forward_payload:') == 1
    header = '''module shared_forward_capture_dut (
input logic clk_i, rst_ni,
input logic [8:0] operand_forward_fire, operand_forward_reduction_cache_fire,
input logic [8:0] operand_forward_reduction_cache_index, operand_forward_sldu_cache_fire,
input logic [8:0] operand_forward_mfpu_fire,
input logic [1:0][63:0] reduction_result_cache_wdata_q,
input logic [63:0] recent_sldu_result_wdata_q, recent_mfpu_result_wdata_q, sldu_result_wdata,
input logic [8:0][63:0] operand_forward_data,
output logic [8:0][63:0] forwarded_operand_o,
output logic [8:0] forwarded_operand_valid_o
);
localparam int NrOperandQueues = 9;
localparam bit ArithmeticOnlyForwarding = 0;
localparam int MulFPUC = 4;
typedef logic [63:0] elen_t;
elen_t [8:0] forwarded_operand_q;
logic [8:0] forwarded_operand_valid_q;
'''
    (out / 'dut.sv').write_text(header + block + '\nendmodule\n')
    shutil.copy2(rtl, out / 'operand_requester_snapshot.sv')
    shutil.copy2(root / 'hardware/tb/shared_forward_capture_tb.sv', out / 'tb.sv')
    command = [args.vcs, '-full64', '-sverilog', '-timescale=1ns/1ps',
               '+define+ARA_RED_SHARED_FORWARD_CAPTURE', '+define+ARA_RED_CHAIN_BYPASS_4LANE',
               '-top', 'shared_forward_capture_tb', 'dut.sv', 'tb.sv', '-o', 'simv']
    manifest = {'command': command, 'source_sha256': hashlib.sha256(rtl.read_bytes()).hexdigest(),
                'extracted_block_sha256': hashlib.sha256(block.encode()).hexdigest(),
                'test_sha256': hashlib.sha256((out / 'tb.sv').read_bytes()).hexdigest()}
    runtime=['./simv']+(['+INJECT_SOURCE_MISMATCH'] if args.negative_control else [])
    manifest['negative_control']=args.negative_control
    for stage, cmd in [('compile', command), ('run', runtime)]:
        path = out / (stage + '.log')
        with path.open('w') as log:
            proc = subprocess.run(cmd, cwd=out, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        text = path.read_text(errors='replace')
        errors = re.findall(r'^.*(?:Error-|Error:|Fatal:|\bFAIL\b|started at .*failed at).*$', text, re.M)
        passed = proc.returncode == 0 and not errors and (stage == 'compile' or 'SHARED_FORWARD_CAPTURE_PASS' in text)
        if stage=='run' and args.negative_control:
            passed=('NEGATIVE_CONTROL_COMPLETED' in text and
                    'shared forwarding response differs' in text and 'payload mismatch' in text)
            manifest['negative_control_detected']=passed
        manifest[stage] = {'pass': passed, 'returncode': proc.returncode, 'errors': errors,
                           'log_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
        (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
        if not passed:
            raise SystemExit('Failed: ' + str(path))
    print((out / 'run.log').read_text())


if __name__ == '__main__':
    main()
