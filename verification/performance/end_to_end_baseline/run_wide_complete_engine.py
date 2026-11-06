#!/usr/bin/env python3
"""Pair full QBS controllers on true 16/32-byte synthetic AXI service.

This is a command-level fixture, not a SoC or real PMP acceptance. Both images
retain the accepted original arithmetic, golden results and fault checks.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from run_wide_default_engine import HERE, ROOT, RUNS, ORIGINAL, check_geometry, check_log

BASE = RUNS / 'e2e_wide_default_engine_20261106_01'
TRAFFIC = re.compile(r'^WIDE_ENGINE_TRAFFIC case=(\d+) ranges=(\d+) ar=(\d+) '
                     r'beats=(\d+) payload=(\d+) weight=(\d+) activation=(\d+)$', re.M)


def replace_once(text, old, new):
    require(text.count(old) == 1, 'Fixture anchor missing or duplicated: ' + old[:90])
    return text.replace(old, new, 1)


def wrapper_source(text):
    text = replace_once(text, 'parameter int unsigned AxiDataWidth = 128,',
                        'parameter int unsigned AxiDataWidth = 128,\n'
                        '    localparam bit WideWeight = AxiDataWidth == 256,')
    text = replace_once(text, '.WideMatrixDot(WideMatrixDot),',
                        '.WideMatrixDot(WideMatrixDot), .WideWeightIngress(WideWeight),')
    text = replace_once(text, '.req_t(unit_req_t), .rsp_t(unit_rsp_t),',
                        '.PerRangeTransferSize(WideWeight),\n'
                        '    .req_t(unit_req_t), .rsp_t(unit_rsp_t),')
    return text


def bench_source(text):
    text = replace_once(text, "module qbs_engine_tb #(parameter bit Wide = 1'b0);",
                        "module qbs_engine_tb #(parameter bit Wide = 1'b0,\n"
                        '                          parameter int BusWidth = 128);\n'
                        '  initial $display("WIDE_ENGINE_CONFIG bits=%0d matrix=%0d", BusWidth, Wide);')
    text = replace_once(text, 'localparam int unsigned AxiDataWidth = 128;',
                        'localparam int unsigned AxiDataWidth = BusWidth;')
    text = replace_once(text, 'logic [7:0] response_len [2];',
                        'logic [7:0] response_len [2];\n'
                        '  logic [2:0] response_size [2];\n'
                        '  logic [63:0] response_transfer_addr;\n'
                        '  logic [63:0] response_bus_addr;')
    text = replace_once(text, "axi_r.data = {128{memory_epoch[0]}};",
                        'axi_r.data = {AxiDataWidth{memory_epoch[0]}};\n'
                        '    response_transfer_addr = response_addr[response_rd] +\n'
                        "        (64'(response_beat) << response_size[response_rd]);\n"
                        "    response_bus_addr = response_transfer_addr & ~64'(BeatBytes-1);")
    text = replace_once(text, 'memory_byte(response_addr[response_rd] +\n'
                        '                      response_beat * BeatBytes + byte_lane);',
                        'memory_byte(response_bus_addr + byte_lane);')
    text = replace_once(text, 'response_addr[response_rd] + BeatBytes > inject_fault_start',
                        "response_addr[response_rd] + (64'd1 << response_size[response_rd]) > inject_fault_start")
    text = replace_once(text, '(64\'(axi_ar.len) + 1) * BeatBytes',
                        "(64'(axi_ar.len) + 1) * (64'd1 << axi_ar.size)")
    text = replace_once(text, "response_len[1] <= '0;", "response_len[1] <= '0;\n"
                        "      response_size[0] <= '0;\n      response_size[1] <= '0;")
    text = replace_once(text, 'response_len[response_wr] <= axi_ar.len;',
                        'response_len[response_wr] <= axi_ar.len;\n'
                        '        response_size[response_wr] <= axi_ar.size;')
    text = replace_once(text, '      if (case_errors == 0 && functional_only) begin',
                        '      $display("WIDE_ENGINE_TRAFFIC case=%0d ranges=%0d ar=%0d beats=%0d payload=%0d weight=%0d activation=%0d",\n'
                        '               case_id, read_range_count, read_ar_count, read_beat_count,\n'
                        '               read_payload_bytes, weight_bytes, activation_bytes);\n'
                        '      if (case_errors == 0 && functional_only) begin')
    text = replace_once(text, '    $display("QBS engine PASS: %0d functional cases plus four fault classes",',
                        '    $display("WIDE_ENGINE_BUS bits=%0d narrow=%0d wide=%0d upper=%0d",\n'
                        '             BusWidth, narrow_bus_count, wide_bus_count, upper_bus_count);\n'
                        '    $display("QBS engine PASS: %0d functional cases plus four fault classes",')
    # One owner accumulates all counts. No shared initial-block tallies.
    monitor = '''
  integer narrow_bus_count = 0, wide_bus_count = 0, upper_bus_count = 0;
  always @(posedge clk) begin
    if (rst_n && axi_ar_valid && axi_ar_ready) begin
      if (axi_ar.size !== ((BusWidth == 256 &&
          dut.i_shared_reader.i_read_engine.ar_tag_q[15:14] == 2) ? 3'd5 : 3'd4))
        $fatal(1, "Full controller selected wrong transfer size");
      if (axi_ar.size == 4) narrow_bus_count++;
      else if (axi_ar.size == 5) wide_bus_count++;
      if (BusWidth == 256 && axi_ar.size == 4 && axi_ar.addr[4]) upper_bus_count++;
    end
  end
'''
    return replace_once(text, 'endmodule : qbs_engine_tb', monitor + '\nendmodule : qbs_engine_tb')


def check(text, vector, width, gap):
    require(width in (128, 256), 'Unsupported image width')
    require(not re.search(r'Fatal:|Error[-:]|Assertion.*failed', text), 'RTL failure')
    require(text.splitlines().count(f'WIDE_ENGINE_CONFIG bits={width} matrix=0') == 1,
            'Wrong physical service or arithmetic')
    value = check_log(text, 36, 1, gap)
    check_geometry(vector, value['direct'])
    traffic = [list(map(int, row)) for row in TRAFFIC.findall(text)]
    require(len(traffic) == 36 and [row[0] for row in traffic] == list(range(36)),
            'Missing or duplicated command traffic')
    for cid, ranges, ar, beats, payload, weight, activation in traffic:
        require(ar >= ranges and beats >= ar and payload == 16 + weight + activation and
                weight > 0 and activation > 0, 'Invalid transfer/work accounting')
    bus = re.findall(r'^WIDE_ENGINE_BUS bits=(\d+) narrow=(\d+) wide=(\d+) upper=(\d+)$', text, re.M)
    require(len(bus) == 1, 'Missing unique bus acceptance record')
    bits, narrow, wide, upper = map(int, bus[0])
    require(bits == width and narrow > 0 and
            (wide > 0 and upper > 0 if width == 256 else wide == upper == 0),
            'Missing actual wide or upper-half narrow service')
    return dict(**value, traffic=traffic, bus=dict(bits=bits, narrow=narrow, wide=wide, upper=upper))


def check_pair(narrow, wide):
    require([row[:-1] for row in narrow['direct']] == [row[:-1] for row in wide['direct']],
            'Pair command geometry changed')
    require([row[:4] for row in narrow['contexts']] == [row[:4] for row in wide['contexts']],
            'Pair context work changed')
    for a, b in zip(narrow['traffic'], wide['traffic']):
        require(a[:2] == b[:2] and a[4:] == b[4:], 'Pair logical traffic changed')
    return dict(cases=36, context_cases=1, golden_output_and_work_checks_retained=True,
                synthetic_command_cycles={str(width): sum(row[-1] for row in result['direct'])
                                          for width, result in ((128, narrow), (256, wide))},
                synthetic_r_beats={str(width): sum(row[3] for row in result['traffic'])
                                   for width, result in ((128, narrow), (256, wide))})


def run(output):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS), 'Use fresh sole-verification output')
    out.mkdir(parents=True, exist_ok=False)
    pins, commands = {}, []
    result = dict(state='PREPARING', full_soc_tested=False, real_pmp_tested=False,
                  model_speedup_measured=False, synthesis_run=False)

    def pin(path, expected=None):
        path = Path(path).resolve(strict=True)
        actual = digest(path)
        require(expected is None or actual == expected, 'Input identity differs: ' + str(path))
        require(str(path) not in pins or pins[str(path)] == actual, 'Input drift')
        pins[str(path)] = actual

    def command(argv, label, bound):
        argv = list(map(str, argv))
        argv[0] = shutil.which(argv[0]) or argv[0]
        pin(argv[0]); verify_pins(pins)
        row = dict(label=label, argv=argv, timeout=bound)
        commands.append(row)
        result.update(state=label.upper(), child_pid=None)
        with (out / (label + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=out, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            result['child_pid'] = child.pid
            (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
            try:
                code = child.wait(timeout=bound)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        row['returncode'] = code
        result['child_pid'] = None
        verify_pins(pins)
        text = (out / (label + '.log')).read_text()
        require(code == 0 and not re.search(r'Fatal:|Error[-:]|Assertion.*failed', text), label + ' failed')
        return text

    try:
        for path in (Path(__file__), HERE / 'test_wide_complete_engine.py', HERE / 'audit.py',
                     HERE / 'run_wide_default_engine.py', ROOT / 'verification/qbs/run_tile_context_engine.py',
                     ROOT / 'verification/qbs/run_half_scale_soc.py', HERE / 'matrix_replay_probe.svh'):
            pin(path)
        baseline = json.loads((BASE / 'result.json').read_text())
        require(baseline['state'] == 'DEFAULT_COMPLETE_QBS_ENGINE_CYCLES_UNCHANGED', 'Unaccepted baseline')
        pin(BASE / 'result.json')
        pin(BASE / 'source-pins.json', baseline['source_pins_sha256'])
        old = json.loads((BASE / 'source-pins.json').read_text())
        verify_pins(old); verify_pins(baseline['artifacts'])
        pins.update(old)
        vector = ORIGINAL / 'matrix-base.txt'
        pin(vector)
        tree = out / 'tree'
        for path in (BASE / 'tree').rglob('*'):
            if path.is_file():
                pin(path)
                dest = tree / path.relative_to(BASE / 'tree')
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, dest); pin(dest)
        bench = tree / 'wide_complete_tb.sv'
        wrapper = tree / 'wide_complete_wrapper.sv'
        bench.write_text(bench_source((BASE / 'tree/matrix_fault_suite.sv').read_text()))
        wrapper.write_text(wrapper_source((BASE / 'tree/matrix_wrapper.sv').read_text()))
        pin(bench); pin(wrapper)
        command([sys.executable, '-B', HERE / 'test_wide_complete_engine.py'], 'unit-tests', 30)
        sources = [Path(line) for line in (BASE / 'sources.log').read_text().splitlines()]
        require(all(str(path) in old for path in sources), 'Unbound RTL source list')
        vcs = shutil.which('vcs'); require(vcs is not None, 'Host VCS unavailable')
        pin(vcs); pin(Path(vcs).resolve().parent.parent / 'linux64/bin/vcs1')
        measured = {}
        for width in (128, 256):
            build = out / f'build{width}'; build.mkdir()
            image = build / 'simv'
            (out / 'source-pins-precompile.json').write_text(json.dumps(pins, indent=2) + '\n')
            command([vcs, '-full64', '-sverilog', '-timescale=1ns/1ps', '-assert', 'svaext',
                *['+incdir+' + str(tree / path) for path in ('hardware/include',
                    'hardware/deps/common_cells/include', 'hardware/deps/axi/include')],
                '+incdir+' + str(HERE), *[tree / path.relative_to(ROOT) for path in sources],
                wrapper, bench, '-top', 'qbs_engine_tb', '-pvalue+qbs_engine_tb.Wide=0',
                f'-pvalue+qbs_engine_tb.BusWidth={width}', '-Mdir=' + str(build / 'csrc'),
                '-o', image], f'compile{width}', 600)
            pin(image)
            for path in build.rglob('*.so'): pin(path)
            for gap in (0, 3):
                log = command([image, '-no_save', '+QBS_COMMAND_VECTOR_FILE=' + str(vector),
                               f'+QBS_RESPONSE_GAP={gap}'], f'run{width}-gap{gap}', 300)
                measured[f'{width}-gap{gap}'] = check(log, vector.read_text(), width, gap)
        pairs = {str(gap): check_pair(measured[f'128-gap{gap}'], measured[f'256-gap{gap}'])
                 for gap in (0, 3)}
        default = baseline['measured']
        require(json.loads(json.dumps(measured['128-gap0']['direct'])) == default['direct'] and
                json.loads(json.dumps(measured['128-gap0']['contexts'])) == default['contexts'],
                'New AXI fixture changed accepted original timing')
        result.update(state='WIDE_COMPLETE_QBS_COMMAND_PAIR_PASS', measured=measured, pairs=pairs,
                      default_timing_preserved=True,
                      limitations=['Synthetic one-full-bus-word-per-cycle AXI memory, not physical SoC',
                                   'Original arithmetic configuration, not WideMatrixDot throughput claim',
                                   'Synthetic translation/PMA fault checks, not real CVA6 PMP proof',
                                   'Command cycles exclude SDK preparation and whole GGML/model execution'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(p): digest(p) for p in out.iterdir()
                               if p.is_file() and p.name not in ('result.json', 'status.json')}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
