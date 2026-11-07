#!/usr/bin/env python3
"""Bounded VCS wiring test of the actual ara_soc TARGET_SRAM_MC source block."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNS = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OUT = RUNS / 'e2e_soc_sram_mc_wide_20261106_01'
DUT = ROOT / 'hardware/src/ara_soc.sv'
REGISTERS = ROOT / 'hardware/deps/common_cells/include/common_cells/registers.svh'
OWNED = (DUT, HERE / 'ara_soc_sram_mc_tb.sv', HERE / 'run_soc_sram_mc.py', HERE / 'test_soc_sram_mc.py')
CONFIGS = ((8, 8192, 0), (32, 8192, 0), (64, 16384, 0), (128, 8192, 0), (128, 65536, 1),
           (256, 8192, 0), (256, 16384, 0), (256, 32768, 1), (512, 8192, 0), (512, 16384, 1))


def extracted_slice(text):
    start, end = '  // TARGET_SRAM_MC_BEGIN\n', '  // TARGET_SRAM_MC_END\n'
    require(text.count(start) == text.count(end) == 1, 'Unique actual SRAM MC source markers required')
    body = text.split(start, 1)[1].split(end, 1)[0]
    parameters = re.findall(r'parameter\s+int\s+unsigned\s+L2NumWords\s*=\s*([^,\n]+),', text)
    require(len(parameters) == 1, 'Actual default memory geometry declaration required')
    latency = re.findall(r"(?m)^\s*`FF\(l2_rvalid, l2_req, 1'b0\);", text)
    require(len(latency) == 1, 'Actual one-cycle memory completion declaration required')
    wrapper = ('`timescale 1ns/1ps\n`include "registers.svh"\n'
        'module ara_soc_sram_mc_slice #(\n'
        '  parameter int unsigned AxiDataWidth = 128,\n'
        f'  parameter int unsigned L2NumWords = {parameters[0]},\n'
        '  parameter int unsigned AxiAddrWidth = 64\n'
        ')(input logic clk_i, rst_ni, l2_req, l2_we,\n'
        '  input logic [AxiAddrWidth-1:0] l2_addr,\n'
        '  input logic [AxiDataWidth-1:0] l2_wdata,\n'
        '  input logic [AxiDataWidth/8-1:0] l2_be,\n'
        '  output logic [AxiDataWidth-1:0] l2_rdata, output logic l2_rvalid);\n' + body +
        latency[0].strip() + '\n'
        '  always @(negedge clk_i) begin\n'
        '    #1;\n'
        '    if (!rst_ni) begin\n'
        '      if (dram_bank_ren !== \'0 || l2_rvalid !== 0) $fatal(1, "MC_SELECTOR_RESET_FAIL");\n'
        '    end else begin\n'
        '      if ($isunknown(dram_bank_ren) || !$onehot0(dram_bank_ren))\n'
        '        $fatal(1, "MC_SELECTOR_VALIDITY_FAIL");\n'
        '    end\n'
        '  end\n'
        '  if (AxiDataWidth < 128) begin : gen_padding_check\n'
        '    always @(negedge clk_i) begin\n'
        '      #1;\n'
        '      if (rst_ni && (dram_bweb[127:AxiDataWidth] !== \'1 ||\n'
        '                     dram_wdata[127:AxiDataWidth] !== \'0))\n'
        '        $fatal(1, "MC_UNUSED_COLUMN_BITS_FAIL");\n'
        '    end\n'
        '  end\nendmodule\n')
    return wrapper, body, parameters[0]


def expected_case(case_id):
    width, words, default = CONFIGS[case_id]
    size, banks = width // 8, words // 8192
    pool = [bank * 8192 + offset for bank in range(banks) for offset in (0, 1, 8190, 8191)]
    full = (1 << size) - 1
    events = []
    add = lambda req, we, word, mask=full, phase=0: events.append((req, we, word, mask, phase))
    for word in pool: add(1, 1, word)
    for word in pool: add(1, 0, word)
    for byte in range(size):
        word = (byte % banks) * 8192 + (8191 if byte % 2 else 0)
        add(1, 1, word, 1 << byte, byte)
        add(1, 0, word, full, byte)
        add(0, 1, pool[(byte + 4) % len(pool)], full, byte)
        add(1, 0, word, full, byte)
    add(1, 1, pool[0], 0); add(1, 0, pool[0])
    add(1, 0, pool[-1]); add(1, 1, pool[0])
    for _ in range(3): add(0, 1, pool[0])
    add(1, 0, pool[0])
    state = 0x31415926 + case_id
    for _ in range(128):
        state = (1664525 * state + 1013904223) & 0xffffffff
        word, phase = pool[(state >> 2) % len(pool)], (state >> 10) % size
        mode = state & 3
        mask = sum(((state >> (byte % 32)) & 1) << byte for byte in range(size))
        add(int(mode != 0), int(mode != 1), word, full if mode == 2 else mask, phase)
    events.append(None)  # selector reset, with no payload reset
    add(1, 0, pool[0]); add(1, 0, pool[-1]); add(0, 1, pool[0]); add(0, 0, pool[-1], 0)
    result = dict(id=case_id, width=width, words=words, banks=banks, columns=max(1, width // 128),
                  default_depth=default, **dict.fromkeys(('steps', 'reads', 'writes', 'idle', 'masked',
                                                       'zero_mask', 'holds', 'switches'), 0))
    previous_bank, phases = None, set()
    for event in events:
        if event is None:
            previous_bank = None
            continue
        req, we, word, mask, phase = event
        result['steps'] += 1
        if req and we:
            result['writes'] += 1
            result['masked'] += mask != full
            result['zero_mask'] += mask == 0
        if req and not we:
            result['reads'] += 1
            result['switches'] += previous_bank is not None and previous_bank != word // 8192
            previous_bank = word // 8192
        else: result['holds'] += 1
        result['idle'] += not req
        if req: phases.add(phase)
    result.update(phases=len(phases), checked_read_bytes=result['reads'] * size, resets=2)
    return result


def fields(line, tag):
    require(line.startswith(tag + ' '), 'Wrong MC result prefix')
    pairs = [word.split('=') for word in line[len(tag) + 1:].split()]
    require(pairs and all(len(pair) == 2 and re.fullmatch('[a-z_]+', pair[0]) and pair[1].isdigit()
                          for pair in pairs), 'Malformed MC numeric result')
    require(len({key for key, value in pairs}) == len(pairs), 'Duplicate MC result field')
    return {key: int(value) for key, value in pairs}


def check(text):
    require(not re.search(r'Fatal:|Error[-:]|Assertion[^\n]*failed|MC_\w*FAIL|UVM_(?:ERROR|FATAL)', text),
            'Simulator/assertion failure even if process returned zero')
    lines = text.replace('\r', '').splitlines()
    cases = [fields(line, 'MC_CASE_PASS') for line in lines if line.startswith('MC_CASE_PASS')]
    require(sorted(cases, key=lambda row: row['id']) == [expected_case(i) for i in range(len(CONFIGS))],
            'Missing/duplicate/inexact memory data and coverage checks')
    terminal = [fields(line, 'MC_COMPONENT_PASS') for line in lines if line.startswith('MC_COMPONENT_PASS')]
    require(terminal == [dict(cases=10)] and sum(line.startswith('MC_') for line in lines) == 11,
            'Missing/extra component terminal record')
    return dict(cases=sorted(cases, key=lambda row: row['id']),
                checked_read_bytes=sum(row['checked_read_bytes'] for row in cases),
                transactions=sum(row['steps'] for row in cases), selector_reset_checked=True,
                unused_narrow_mask_bits_checked=True, fixed_default_bytes=1048576,
                oracle='Independent byte-addressed scoreboard and functional 8192x128 macro; Q holds on write')


def run(output):
    output = output.absolute()
    require(output == output.resolve() and output.is_relative_to(RUNS), 'Fresh sole-verification component output')
    output.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='SOC_SRAM_MC_COMPONENT_FAIL', performance_measured=False, synthesis_run=False,
                  full_soc_accepted=False, foundry_macro_accepted=False, wide_macro_preload_accepted=False)

    def pin(path):
        path = Path(path).resolve(strict=True)
        sha = digest(path)
        require(str(path) not in pins or pins[str(path)] == sha, 'Input drift: ' + str(path))
        pins[str(path)] = sha

    def command(argv, label, timeout):
        argv = list(map(str, argv)); pin(argv[0]); verify_pins(pins)
        record = dict(label=label, argv=argv, timeout_seconds=timeout); commands.append(record)
        result['active_command'] = label
        (output / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
        with (output / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=output, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            try: code = child.wait(timeout=timeout)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        record['returncode'] = code; verify_pins(pins)
        text = (output / (label + '.log')).read_text()
        require(code == 0 and not re.search(r'Error[-:]|Fatal:', text), label + ' failed; preserve first attempt')
        return text

    try:
        snapshot = output / 'source-snapshot'; snapshot.mkdir()
        for source in (*OWNED, REGISTERS, HERE / 'audit.py'):
            pin(source); target = snapshot / source.name
            target.write_bytes(source.read_bytes()); pin(target)
            require(digest(source) == digest(target), 'Source snapshot differs')
        generated, body, default_expression = extracted_slice((snapshot / DUT.name).read_text())
        slice_file = snapshot / 'ara_soc_sram_mc_slice.sv'; slice_file.write_text(generated); pin(slice_file)
        pin(sys.executable)
        command([sys.executable, '-B', HERE / 'test_soc_sram_mc.py'], 'unit-tests', 60)
        vcs = shutil.which('vcs'); require(vcs is not None, 'Host VCS unavailable')
        pin(vcs)
        vcs1 = Path(vcs).resolve().parent.parent / 'linux64/bin/vcs1'
        if vcs1.is_file(): pin(vcs1)
        build = output / 'build'; build.mkdir()
        image = build / 'simv'
        (output / 'source-pins-precompile.json').write_text(json.dumps(pins, indent=2) + '\n')
        log = command([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                       '+incdir+' + str(snapshot), slice_file, snapshot / 'ara_soc_sram_mc_tb.sv',
                       '-top', 'ara_soc_sram_mc_tb', '-Mdir=' + str(build / 'csrc'), '-o', image], 'compile', 180)
        require(not re.search(r'Warning-\[', log), 'Unexpected VCS compile diagnostic')
        pin(image)
        for library in sorted(build.rglob('*.so')): pin(library)
        (output / 'source-pins-presimulation.json').write_text(json.dumps(pins, indent=2) + '\n')
        measured = check(command([image], 'functional', 60))
        verify_pins(pins)
        result.update(state='SOC_SRAM_MC_EXTRACTED_COMPONENT_PASS', measured=measured,
                      post_pins_match=True, actual_source_sha256=pins[str(DUT.resolve())],
                      extracted_block_sha256=hashlib.sha256(body.encode()).hexdigest(),
                      default_words_expression=default_expression, active_command=None,
                      limitations=['Actual ara_soc MC block and default geometry extracted without copying DUT logic',
                                   'Independent functional SRAM model, Q held on write; not foundry model/timing/PPA',
                                   'Component only, not full SoC, FPGA, MMU/PMP or physical implementation acceptance',
                                   '256-bit macro preload NOT accepted: existing hardcoded 8-bank adapter needs updating',
                                   'Existing unrelated/dirty TB and all frozen worker inputs left unchanged'])
    except BaseException as exc:
        result.update(error=repr(exc), post_pins_match=False)
        raise
    finally:
        (output / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        result['source_pins_sha256'] = digest(output / 'source-pins.json')
        result['artifacts'] = {str(path): digest(path) for path in sorted(output.rglob('*'))
            if path.is_file() and not path.is_relative_to(output / 'build') and path.name not in ('status.json', 'result.json')}
        (output / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
        (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    run(parser.parse_args().output)
