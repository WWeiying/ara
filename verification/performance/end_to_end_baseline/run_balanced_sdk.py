#!/usr/bin/env python3
"""Frozen real QKV/FFN ELFs on matched 256-bit original/balanced SoCs."""
import argparse
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, VERIFY, RUNS
from prepare_balanced_soc import REFERENCE, REFERENCE_SHA
from run_wide_soc_smoke import elf_admission, check_platform
from run_supply_sdk import bind, PROGRAMS, acceptance_gate
import check_balanced_sdk as checker
import run_balanced_handoff as handoff

PROGRAMS_BY_KIND = {
    'prefill': (RUNS / PROGRAMS['prefill'][0], 'build.json', PROGRAMS['prefill'][1],
                'FULL_QWEN3_SDK_BUILT_NOT_EXECUTED', 128, 16384),
    'ffn': (RUNS / 'e2e_ffn_native_build_20261106_01', 'build.json',
            '3bd54bcf04cd670d2ad836cb0ee7a35591c4a25c15c1d537b67feeff2b43a2d4',
            'REAL_QWEN3_FFN_SDK_BUILT_NOT_EXECUTED', 12, 1536),
}


def oracle(build, kind):
    if kind == 'prefill':
        return checker.supply.oracle(build, kind)
    require(kind == 'ffn', 'Known real-data SDK workload required')
    return ([(build / f'ffn_{part}_expected.bin').read_bytes() for part in range(3)],
            [(build / name).read_bytes() for name in ('ffn_quantized.bin', 'down_quantized.bin')],
            list(struct.unpack('<3I', (build / 'profiles.bin').read_bytes())),
            [struct.unpack('<I', (build / f'ffn_{part}_flags.bin').read_bytes())[0] for part in range(3)])


def program_contract(value, kind, state, commands, outputs):
    require(value['state'] == state and value['commands'] == commands and value['outputs'] == outputs and
            value['m'] == 4 and value['trials'] == 1 and value['preparation_included'] and
            not value['cold_weight_repack_included'] and not value['whole_model'] and not value['full_ggml'],
            'Frozen real-data program contract differs')
    require((value['n'], value['k']) ==
            (([2048, 1024, 1024], 2048) if kind == 'prefill' else (128, [2048, 2048, 6144])),
            'Full N QKV or fixed N128/full K FFN shape required')


def handoff_gate(root, expected, soc, pins):
    bind(pins, root / 'result.json', expected)
    value = json.loads((root / 'result.json').read_text())
    require(value['state'] == handoff.STATE and value['post_pins_match'] and
            value['independent_protocol_checked'] and value['simv'] == soc['simv'] and value['width'] == 256,
            'Balanced M4 handoff has not passed on the actual candidate image')
    bind(pins, root / 'source-pins.json', value['source_pins_sha256'])
    for collection in (json.loads((root / 'source-pins.json').read_text()), value['artifacts']):
        for path, sha in collection.items():
            bind(pins, path, sha)
    text = (root / 'work/run.vcs.log').read_text()
    require(handoff.check_program(text, 'handoff') == value['measured'] and
            check_platform(text, 256) == value['platform'], 'Handoff raw replay differs')
    protocol = json.loads((root / 'work/uvm_result.json').read_text())
    require(protocol['status'] == 'PASS' and protocol['sim_image_sha256'] == soc['image_pins'] and
            protocol['elf_sha256'] == value['elf_sha256'] and
            protocol['log_sha256'] == digest(root / 'work/run.vcs.log') and
            protocol['vector_trace_sha256'] == digest(root / 'work/vector_trace.csv'),
            'Handoff protocol or executable identity differs')


def inputs(kind, balanced, soc_root, soc_sha, smoke, smoke_sha):
    require(kind in PROGRAMS_BY_KIND and type(balanced) is int and balanced in (0, 1), 'Explicit known candidate')
    pins = {}
    bind(pins, soc_root / 'result.json', soc_sha)
    soc = json.loads((soc_root / 'result.json').read_text())
    config = soc['config']
    require(soc['post_pins_match'] and soc['width'] == 256 and
            all(config[key] == value for key, value in dict(
                sim_axi_data_width='256', sim_l2_bytes='16777216', qbs_wide_weight_ingress='1',
                nr_lanes='4', vlen='1024', qbs_matrix_dot='1').items()), 'Matched physical platform required')
    if balanced:
        require(soc['state'] == 'BALANCED_SOC_BUILT_NOT_EXECUTED' and soc['mode'] == 1 and
                soc['prepared_sha256'] == handoff.PREPARED_SHA and config['qbs_balanced_matrix_dot'] == '1',
                'Reviewed balanced SoC snapshot required')
    else:
        require(soc_root == REFERENCE and soc_sha == REFERENCE_SHA and
                soc['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED', 'Exact 256-bit original SoC required')
    build, name, sha, state, commands, outputs = PROGRAMS_BY_KIND[kind]
    bind(pins, build / name, sha)
    program = json.loads((build / name).read_text())
    program_contract(program, kind, state, commands, outputs)
    for root, record in ((soc_root, soc), (build, program)):
        bind(pins, root / 'source-pins.json', record['source_pins_sha256'])
        for collection in (json.loads((root / 'source-pins.json').read_text()), record['artifacts']):
            for path, expected in collection.items():
                bind(pins, path, expected)
    for path, sha in soc['image_pins'].items():
        bind(pins, path, sha)
    bind(pins, program['elf'], program['elf_sha256'])
    loads = elf_admission(Path(program['elf']).read_bytes(), 32)
    if balanced:
        require(smoke is not None and smoke_sha is not None, 'Balanced handoff receipt is mandatory')
        handoff_gate(smoke, smoke_sha, soc, pins)
    else:
        acceptance_gate(pins)
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
            bind(pins, path)
    for path in (HERE / 'test_run_balanced_sdk.py', HERE / 'test_check_balanced_sdk.py',
                 HERE / 'test_run_balanced_handoff.py', HERE / 'test_balanced_soc_handoff.py', Path(sys.executable),
                 *(VERIFY / 'verification/ara_verify').glob('*.py')):
        bind(pins, path)
    return dict(soc=soc, program=program, build=build, preload_segments=loads), pins


def run(args):
    out = args.output.absolute()
    require(args.execute_reviewed and out == out.resolve() and out.is_relative_to(RUNS) and
            1 <= args.timeout <= 10800, 'Reviewed bounded fresh verification run required')
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    pins, commands = {}, []
    result = dict(state='PREPARING', child_pid=None, kind=args.kind, balanced=args.balanced,
                  physical_bits=256, performance_measured=False, whole_model=False, synthesis_run=False)

    def save():
        (out / 'status.json').write_text(json.dumps(result, indent=2) + '\n')

    def command(argv, label, limit):
        argv = list(map(str, argv))
        bind(pins, argv[0])
        verify_pins(pins)
        row = dict(argv=argv, label=label, timeout_seconds=limit)
        commands.append(row)
        env = {k: v for k, v in os.environ.items() if k not in ('LD_PRELOAD', 'PYTHONPATH')}
        env.update(PATH='/usr/bin:/bin', PYTHONPATH=str(VERIFY / 'verification'),
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', READELF='/usr/bin/readelf')
        with (work / (label + '.console.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=stream, stderr=subprocess.STDOUT,
                                     start_new_session=True)
            result.update(state=label, child_pid=child.pid)
            save()
            try:
                code = child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
                raise
        result['child_pid'] = None
        row['returncode'] = code
        require(code == 0, label + ' failed; retain original evidence')
        verify_pins(pins)

    try:
        config, pins = inputs(args.kind, args.balanced, args.soc, args.soc_sha, args.handoff, args.handoff_sha)
        soc, program, build = (config[key] for key in ('soc', 'program', 'build'))
        expected = oracle(build, args.kind)
        _, specialization = checker.checker(args.kind, args.balanced)
        (out / 'checker-specialization.json').write_text(json.dumps(specialization, indent=2) + '\n')
        bind(pins, out / 'checker-specialization.json')
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result.update(simv=soc['simv'], image_pins=soc['image_pins'], soc=str(args.soc), soc_sha256=args.soc_sha,
                      elf=program['elf'], elf_sha256=program['elf_sha256'], build=str(build),
                      preload_segments=config['preload_segments'])
        command([soc['simv'], '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + program['elf'],
                 '+TESTCASE=balanced_sdk_' + args.kind, '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                 '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                 '+ARA_UVM_TRACE_LIMIT=2000000'], 'simulation', args.timeout)
        text = (work / 'run.vcs.log').read_text()
        result['platform'] = check_platform(text, 256)
        result['measured'] = checker.check(text, args.kind, args.balanced, expected)
        command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                 '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                 '--log', work / 'run.vcs.log', '--simv', soc['simv'], '--elf', program['elf'],
                 '--output', work / 'uvm_result.json'], 'protocol', 600)
        protocol = json.loads((work / 'uvm_result.json').read_text())
        require(protocol['status'] == 'PASS' and protocol['log_sha256'] == digest(work / 'run.vcs.log') and
                protocol['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
                protocol['elf_sha256'] == program['elf_sha256'] and protocol['sim_image_sha256'] == soc['image_pins'],
                'Independent protocol evidence differs')
        verify_pins(pins)
        result.update(state='BALANCED_SDK_SAME_ELF_RTL_PROTOCOL_PASS', post_pins_match=True,
                      independent_protocol_checked=True, performance_measured=True,
                      limits=['Fixed actual 256-bit generic RAM; not external DDR timing',
                              'Full N QKV or N128/full K FFN captured SDK region, not full GGML/token/model',
                              'No cold weight repack, translated Linux/PMP, area, power or FPGA acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        save()
        (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        if not (out / 'source-pins.json').exists():
            (out / 'source-pins.json').write_text(json.dumps(pins, indent=2) + '\n')
        result['source_pins_sha256'] = digest(out / 'source-pins.json')
        result['artifacts'] = {str(path): digest(path) for path in (
            *work.glob('*.log'), work / 'vector_trace.csv', work / 'uvm_result.json',
            out / 'source-pins.json', out / 'commands.json', out / 'checker-specialization.json') if path.is_file()}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=tuple(PROGRAMS_BY_KIND), required=True)
    p.add_argument('--balanced', type=int, choices=(0, 1), required=True)
    p.add_argument('--soc', type=Path, required=True)
    p.add_argument('--soc-sha', required=True)
    p.add_argument('--handoff', type=Path)
    p.add_argument('--handoff-sha')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=7200)
    p.add_argument('--execute-reviewed', action='store_true')
    args = p.parse_args()
    def stop(sig, _frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    run(args)
