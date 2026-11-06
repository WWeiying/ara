#!/usr/bin/env python3
"""Same SDK ELF on accepted physical 128/256-bit full-processor images."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, VERIFY, RUNS, ROOT
from continue_wide_soc import SOC_HASH
from run_wide_soc_smoke import elf_admission, check_platform
import check_supply_sdk as checker

GATE = RUNS / 'e2e_physical_wide_acceptance_20261106_01'
PROGRAMS = {
    'decode': ('e2e_decode_native_build_20261106_02',
               'e8568f5735ef31c597819c3135dd1876760278ec4e1f62011b67e6d58f708b88',
               'REAL_QWEN3_DECODE_SDK_BUILT_NOT_EXECUTED', 28, 896),
    'prefill': ('e2e_full_qwen3_qkv_build_20261106_02',
                '1d55ba64a5b53f7f13a001596c80f0d3b6e09be34cf5b9af00e32a7f5dc2610a',
                'FULL_QWEN3_SDK_BUILT_NOT_EXECUTED', 128, 16384),
}


def bind(pins, path, sha=None):
    path = Path(path).resolve(strict=True)
    actual = digest(path)
    require(sha is None or actual == sha, 'Input identity differs: ' + str(path))
    require(str(path) not in pins or pins[str(path)] == actual, 'Conflicting input identity')
    pins[str(path)] = actual


def inputs(kind, width):
    require(kind in PROGRAMS and width in SOC_HASH, 'Unknown supply experiment')
    pins = {}
    soc_root = RUNS / f'e2e_physical_wide_soc{width}_20261106_01'
    build, sha, state, commands, outputs = PROGRAMS[kind]; build = RUNS / build
    bind(pins, soc_root / 'result.json', SOC_HASH[width]); bind(pins, build / 'build.json', sha)
    soc = json.loads((soc_root / 'result.json').read_text())
    program = json.loads((build / 'build.json').read_text())
    require(soc['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['post_pins_match'] and
            soc['width'] == width, 'Wrong physical full-SoC build')
    require(program['state'] == state and program['commands'] == commands and program['outputs'] == outputs and
            program['trials'] == 1 and program['preparation_included'] and
            not program['cold_weight_repack_included'] and not program['whole_model'] and not program['full_ggml'],
            'SDK work identity differs')
    require((program['m'], program['n'], program['k']) ==
            ((1, 128, list(checker.decode.K)) if kind == 'decode' else (4, list(checker.prefill.N), 2048)),
            'SDK geometry differs')
    if kind == 'decode':
        require(program['profiles'] == list(checker.decode.PROFILE) and program['existing_context_reuse'],
                'Original Decode profile/context reuse not retained')
    for root, report in ((soc_root, soc), (build, program)):
        bind(pins, root / 'source-pins.json', report['source_pins_sha256'])
        for name, expected in json.loads((root / 'source-pins.json').read_text()).items(): bind(pins, name, expected)
        for name, expected in report['artifacts'].items(): bind(pins, name, expected)
    for name, expected in soc['image_pins'].items(): bind(pins, name, expected)
    elf = Path(program['elf']); bind(pins, elf, program['elf_sha256'])
    loads = elf_admission(elf.read_bytes(), width // 8)
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(root) for root in (ROOT, VERIFY)):
            bind(pins, path)
    for path in (VERIFY / 'verification/ara_verify').glob('*.py'): bind(pins, path)
    for path in (HERE / 'test_supply_decode.py', HERE / 'test_supply_sdk.py', HERE / 'test_supply_run.py',
                 Path(__file__), Path(sys.executable)):
        bind(pins, path)
    return dict(soc=soc, program=program, build=build, preload_segments=loads), pins


def _acceptance_gate(pins):
    from continue_wide_soc import MEMORY, MEMORY_ELF, HANDOFF, require_terminal
    path = GATE / 'result.json'; bind(pins, path)
    value = json.loads(path.read_text())
    require(value['state'] == 'PHYSICAL_WIDE_MEMORY_AND_HANDOFF_PASS' and value['post_pins_match'],
            'Physical memory/handoff acceptance not complete')
    bind(pins, GATE / 'source-pins.json')
    for name, sha in json.loads((GATE / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
    handoff = json.loads((HANDOFF / 'result.json').read_text())
    for width, memory in zip((128, 256), MEMORY):
        for root, expected_elf in ((memory, MEMORY_ELF), (GATE / f'handoff{width}', handoff['elf_sha256'])):
            child = require_terminal(root, width, expected_elf)
            require(child is not None and child['simv'] ==
                    str(RUNS / f'e2e_physical_wide_soc{width}_20261106_01/sim/simv'), 'Wrong smoke image')
            bind(pins, root / 'result.json'); bind(pins, root / 'source-pins.json', child['source_pins_sha256'])
            for name, sha in json.loads((root / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
            for name, sha in child['artifacts'].items(): bind(pins, name, sha)
    return pins[str(path.resolve())]


def acceptance_gate(pins):
    # A producer may still be writing result.json. Never retain a partial
    # publication's digest if parsing or validation needs to be retried.
    candidate = dict(pins)
    sha = _acceptance_gate(candidate)
    pins.update(candidate)
    return sha


def run(kind, width, output, timeout, execute):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS) and 1 <= timeout <= 10800,
            'Fresh bounded sole-verification output required')
    out.mkdir(parents=True, exist_ok=False); work = out / 'work'; work.mkdir()
    result = dict(state='PREPARING', kind=kind, width=width, child_pid=None,
                  performance_measured=False, whole_model=False, synthesis_run=False)
    commands, pins = [], {}
    def save(): (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')
    def command(argv, label, limit):
        argv = list(map(str, argv)); bind(pins, argv[0]); verify_pins(pins)
        commands.append(dict(argv=argv, timeout_seconds=limit)); result['state'] = label; save()
        env = dict(os.environ, PATH='/usr/bin:/bin', PYTHONPATH=str(VERIFY / 'verification'),
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', READELF='/usr/bin/readelf')
        with (work / (label.lower() + '.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        result['child_pid'] = None; commands[-1]['returncode'] = code
        require(code == 0, label + ' failed'); verify_pins(pins)
    try:
        config, pins = inputs(kind, width)
        soc, program, build = (config[k] for k in ('soc', 'program', 'build'))
        expected = checker.oracle(build, kind)
        result.update(elf=program['elf'], elf_sha256=program['elf_sha256'], simv=soc['simv'],
                      image_pins=soc['image_pins'], preload_segments=config['preload_segments'])
        if execute: result['prerequisite_result_sha256'] = acceptance_gate(pins)
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        if execute:
            command([soc['simv'], '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + program['elf'],
                     '+TESTCASE=physical_supply_' + kind, '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                     '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                     '+ARA_UVM_TRACE_LIMIT=2000000'], 'SIMULATION', timeout)
            text = (work / 'run.vcs.log').read_text()
            result['platform'] = check_platform(text, width)
            result['measured'] = checker.check(text, kind, width, expected)
            command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                     '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                     '--log', work / 'run.vcs.log', '--simv', soc['simv'], '--elf', program['elf'],
                     '--output', work / 'uvm_result.json'], 'PROTOCOL', 600)
            p = json.loads((work / 'uvm_result.json').read_text())
            require(p['status'] == 'PASS' and p['log_sha256'] == digest(work / 'run.vcs.log') and
                    p['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
                    p['elf_sha256'] == program['elf_sha256'] and p['sim_image_sha256'] == soc['image_pins'],
                    'Independent protocol identity/check differs')
            result.update(state='PHYSICAL_SUPPLY_SDK_PASS', performance_measured=True,
                          independent_protocol_checked=True)
        else: result['state'] = 'PHYSICAL_SUPPLY_SDK_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
                      limits=['Same ELF, fixed matrix-dot, fixed 16 MiB actual generic SRAM; not DDR scaling',
                              'SDK workload only, not full-graph/token/model timing',
                              'Flat physical RAM; no translated Linux/PMP wide-path acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        result['artifacts'] = {str(p): digest(p) for p in (
            *work.glob('*.log'), work / 'vector_trace.csv', work / 'uvm_result.json',
            out / 'source-pins.json', out / 'commands.json') if p.is_file()}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=tuple(PROGRAMS), required=True)
    parser.add_argument('--width', type=int, choices=(128, 256), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=7200)
    parser.add_argument('--execute-reviewed', action='store_true')
    def stop(sig, _frame): raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    args = parser.parse_args()
    run(args.kind, args.width, args.output, args.timeout, args.execute_reviewed)
