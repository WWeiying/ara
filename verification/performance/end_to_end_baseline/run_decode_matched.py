#!/usr/bin/env python3
"""Run frozen real-data RVV/SDK ABBA only after same-platform RVV acceptance."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, RUNS, VERIFY
from run_supply_sdk import bind
import run_decode_rvv_rtl as predecessor
import check_decode_matched as checker
import check_decode_matched_activity as activity

BUILD = RUNS / 'e2e_decode_matched_build_20261106_01'
BUILD_SHA = '420ef73ec51acafa3104b5a964d7548e96dea584a45b21aab1010f613880761f'
ELF_SHA = '78ac4ba24c0269b877ca7e79c605775fee6e283c0347c896154006e9236d7ec3'


def build_inputs(pins):
    bind(pins, BUILD / 'build.json', BUILD_SHA)
    report = json.loads((BUILD / 'build.json').read_text())
    require(report['state'] == 'REAL_DECODE_MATCHED_ABBA_BUILT_NOT_EXECUTED' and
            report['post_pins_match'] and not report['runtime_accepted'] and
            not report['performance_measured'] and report['elf_sha256'] == ELF_SHA and
            (report['m'], report['n'], report['trials'], report['outputs'], report['native_commands']) ==
            (1, 64, 4, 1792, 28) and report['order'] == [0, 1, 1, 0] and
            report['full_k'] and not report['whole_model'] and report['preparation_included'],
            'Unaccepted matched build/workload')
    bind(pins, BUILD / 'source-pins.json', report['source_pins_sha256'])
    for name, sha in json.loads((BUILD / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
    for name, sha in report['artifacts'].items(): bind(pins, name, sha)
    bind(pins, report['elf'], ELF_SHA)
    return report


def accepted_predecessor(width, config, pins):
    root = RUNS / f'e2e_decode_rvv_rtl{width}_20261106_01'
    path = root / 'result.json'
    value = json.loads(path.read_text())
    require(value['state'] == 'REAL_DECODE_RVV_RTL_ISA_PASS' and value['post_pins_match'] and
            value['width'] == width and value['performance_measured'] and
            value['independent_protocol_checked'] and value['elf_sha256'] == predecessor.ELF_SHA and
            value['image_pins'] == config['soc']['image_pins'], 'Predecessor RVV gate failed')
    bind(pins, path)
    bind(pins, root / 'source-pins.json', value['source_pins_sha256'])
    for name, sha in json.loads((root / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
    for name, sha in value['artifacts'].items(): bind(pins, name, sha)
    work = root / 'work'; text = (work / 'run.vcs.log').read_text()
    measured = predecessor.checker.check(text, config['golden'], config['packed'])
    require(measured == value['measured'] and
            predecessor.checker.compare_isa(measured, config['isa']['measured']) ==
            value['independent_isa_comparison'] and predecessor.timing(text) == value['rtl_timing'],
            'Predecessor independent raw replay differs')
    protocol = json.loads((work / 'uvm_result.json').read_text())
    require(protocol['status'] == 'PASS' and protocol['log_sha256'] == digest(work / 'run.vcs.log') and
            protocol['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
            protocol['elf_sha256'] == predecessor.ELF_SHA and
            protocol['sim_image_sha256'] == config['soc']['image_pins'], 'Predecessor protocol identity differs')
    return dict(path=str(path), sha256=digest(path), independently_replayed=True)


def wait_predecessor(width, config, pins, timeout):
    # The existing worker writes result.json once, after all correctness gates.
    root = RUNS / f'e2e_decode_rvv_rtl{width}_20261106_01'
    libc = ctypes.CDLL(None, use_errno=True)
    libc.inotify_init1.argtypes = [ctypes.c_int]; libc.inotify_init1.restype = ctypes.c_int
    libc.inotify_add_watch.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32]
    libc.inotify_add_watch.restype = ctypes.c_int
    fd = libc.inotify_init1(os.O_CLOEXEC | os.O_NONBLOCK)
    require(fd >= 0, 'Completion notification unavailable')
    try:
        require(libc.inotify_add_watch(fd, os.fsencode(root), 0x8 | 0x80) >= 0,
                'Existing RVV worker directory required')
        deadline = time.monotonic() + timeout
        while True:
            if (root / 'result.json').exists():
                try: return accepted_predecessor(width, config, pins)
                except json.JSONDecodeError: pass
            remaining = deadline - time.monotonic()
            require(remaining > 0 and select.select([fd], [], [], remaining)[0], 'RVV completion deadline')
            os.read(fd, 65536)
    finally: os.close(fd)


def inputs(width):
    config, pins = predecessor.inputs(width)
    report = build_inputs(pins)
    require(report['preload_segments'][str(width)] ==
            predecessor.elf_admission(Path(report['elf']).read_bytes(), width // 8),
            'Matched ELF physical preload geometry differs')
    for name in ('run_decode_matched.py', 'test_run_decode_matched.py',
                 'check_decode_matched.py', 'test_decode_matched.py',
                 'check_decode_matched_activity.py', 'test_decode_matched_activity.py'):
        bind(pins, HERE / name)
    return config, report, pins


def run(width, output, timeout, execute):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS) and 1 <= timeout <= 10800,
            'Fresh sole-verification directory and at most three-hour simulation required')
    out.mkdir(parents=True, exist_ok=False); work = out / 'work'; work.mkdir()
    result = dict(state='PREPARING', width=width, child_pid=None, performance_measured=False,
                  whole_model=False, synthesis_run=False, exact_mixed_elf_spike_executed=False)
    pins, commands = {}, []
    def save(): (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
    def inventory(): (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
    def command(argv, label, limit):
        argv = list(map(str, argv)); bind(pins, argv[0]); verify_pins(pins)
        result['state'] = label; commands.append(dict(argv=argv, timeout_seconds=limit)); save()
        env = dict(os.environ, PATH='/usr/bin:/bin', PYTHONPATH=str(VERIFY / 'verification'),
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', READELF='/usr/bin/readelf')
        with (work / (label.lower()+'.log')).open('xb') as stream:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=stream,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        result['child_pid'] = None; commands[-1]['returncode'] = code
        require(code == 0, label+' failed'); verify_pins(pins)
    try:
        config, report, pins = inputs(width)
        soc, elf = config['soc'], Path(report['elf'])
        result.update(elf=str(elf), elf_sha256=ELF_SHA, simv=soc['simv'], image_pins=soc['image_pins'],
                      build_result_sha256=digest(BUILD / 'build.json'),
                      prerequisite_result_sha256=config['prerequisite_result_sha256'])
        verify_pins(pins); inventory()
        if execute:
            result['state'] = 'WAITING_ACCEPTED_RVV_COMPLETION_EVENT'; save()
            result['rvv_predecessor'] = wait_predecessor(width, config, pins, 10800)
            verify_pins(pins); inventory()
            command([soc['simv'], '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD='+str(elf),
                     '+TESTCASE=matched_decode_abba', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                     '+VECTOR_TRACE='+str(work / 'vector_trace.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                     '+ARA_UVM_TRACE_LIMIT=2000000'], 'SIMULATION', timeout)
            text = (work / 'run.vcs.log').read_text()
            result['platform'] = predecessor.check_platform(text, width)
            result['measured'] = activity.check(text, width, *checker.oracle(BUILD))
            command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                     '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                     '--log', work / 'run.vcs.log', '--simv', soc['simv'], '--elf', elf,
                     '--output', work / 'uvm_result.json'], 'PROTOCOL', 600)
            p = json.loads((work / 'uvm_result.json').read_text())
            require(p['status'] == 'PASS' and p['log_sha256'] == digest(work / 'run.vcs.log') and
                    p['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and
                    p['elf_sha256'] == ELF_SHA and p['sim_image_sha256'] == soc['image_pins'],
                    'Matched protocol identity/check differs')
            result.update(state='REAL_DECODE_MATCHED_ABBA_RTL_PASS', performance_measured=True,
                          independent_protocol_checked=True, checked_guest_outputs=1792,
                          completed_instrumentation_matched=True)
        else: result['state'] = 'REAL_DECODE_MATCHED_ABBA_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
            limits=['Seven real N64 output prefixes with full K; not complete model',
                    'Guest compares every output bit; host checks hashes, state, counts and protocol',
                    'Original arithmetic objects reused; mixed custom-opcode ELF not executed by plain Spike',
                    'One ABBA per platform, original native runtime; no cold weight repack or PPA result',
                    'Flat physical RAM; not Linux/MMU permission acceptance'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['artifacts'] = {str(p): digest(p) for p in (
            *work.glob('*.log'), work / 'vector_trace.csv', work / 'uvm_result.json',
            out / 'source-pins.json', out / 'commands.json') if p.is_file()}
        (out / 'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--width', type=int, choices=(128, 256), required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=10800)
    p.add_argument('--execute-reviewed', action='store_true')
    def stop(sig, _frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    a = p.parse_args(); run(a.width, a.output, a.timeout, a.execute_reviewed)
