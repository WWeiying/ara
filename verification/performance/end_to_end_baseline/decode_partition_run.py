#!/usr/bin/env python3
"""Reviewed per-partition execution; never wait for/relabel old timed-out runs."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import RUNS, HERE, ROOT, VERIFY
from run_supply_sdk import bind, acceptance_gate
from continue_wide_soc import SOC_HASH
from run_wide_soc_smoke import elf_admission, check_platform
from decode_partition_build import OWNED, BASE_SHA, BASE_ELF_SHA
from decode_partition_driver import contract, ORDER
import decode_partition_check as checker


def accept_program(report, group):
    wanted = dict(state='DECODE_PARTITIONS_BUILT_NOT_EXECUTED', target_executed=False, rtl_executed=False,
                  performance_measured=False, production_library_changed=False, whole_model=False,
                  parent_build_sha256=BASE_SHA, parent_elf_sha256=BASE_ELF_SHA,
                  compiled_translation_units=2, arithmetic_objects_recompiled=False,
                  order=list(ORDER), post_pins_match=True)
    require(all(report.get(k) == v for k, v in wanted.items()) and len(report.get('groups', [])) == 2 and
            len(report.get('reused_objects', {})) == 15, 'Partition program provenance/scope differs')
    for i, item in enumerate(report['groups']):
        require(all(item.get(k) == v for k, v in contract(i).items()), 'Partition identity/work differs')
    return report['groups'][contract(group)['group']]


def inputs(build, build_sha, group, width):
    require(width in (128, 256) and re.fullmatch('[0-9a-f]{64}', build_sha or ''), 'Explicit width/build SHA required')
    build = build.resolve(strict=True)
    require(build.is_relative_to(RUNS), 'Sole-verification build required')
    pins = {}; bind(pins, build/'build.json', build_sha)
    report = json.loads((build/'build.json').read_text()); program = accept_program(report, group)
    bind(pins, build/'source-pins.json', report['source_pins_sha256'])
    for values in (json.loads((build/'source-pins.json').read_text()), report['artifacts']):
        for p, sha in values.items(): bind(pins, p, sha)
    elf = Path(program['elf']); bind(pins, elf, program['elf_sha256'])
    loads = elf_admission(elf.read_bytes(), width//8)
    require(loads == program['preload_segments'][str(width)], 'Physical preload geometry changed')
    root = RUNS/f'e2e_physical_wide_soc{width}_20261106_01'
    bind(pins, root/'result.json', SOC_HASH[width]); soc = json.loads((root/'result.json').read_text())
    require(soc['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['post_pins_match'] and
            soc['width'] == width, 'Physical platform differs')
    bind(pins, root/'source-pins.json', soc['source_pins_sha256'])
    for values in (json.loads((root/'source-pins.json').read_text()), soc['artifacts'], soc['image_pins']):
        for p, sha in values.items(): bind(pins, p, sha)
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
            bind(pins, path)
    for name in OWNED: bind(pins, HERE/name)
    for path in (Path(sys.executable), *(VERIFY/'verification/ara_verify').glob('*.py')): bind(pins, path)
    gate = acceptance_gate(pins)
    return dict(program=program, soc=soc, elf=elf, loads=loads, prerequisite_result_sha256=gate), pins


def accept_protocol(value, elf_sha, log_sha, trace_sha, images):
    require(value.get('status') == 'PASS' and value.get('elf_sha256') == elf_sha and
            value.get('log_sha256') == log_sha and value.get('vector_trace_sha256') == trace_sha and
            value.get('sim_image_sha256') == images, 'Independent protocol/ELF/log/image binding differs')


def run(build, build_sha, group, width, output, timeout, execute):
    contract(group)
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS) and 1 <= timeout <= 10800,
            'Fresh sole-verification output and at most three-hour simulation required')
    out.mkdir(parents=True, exist_ok=False); work = out/'work'; work.mkdir()
    pins, commands = {}, []
    result = dict(state='PREPARING', group=group, width=width, child_pid=None,
                  performance_measured=False, independent_protocol_checked=False,
                  whole_model=False, continuous_seven_part_run=False, exact_mixed_elf_spike_executed=False)

    def save(): (out/'status.json').write_text(json.dumps(result, indent=2)+'\n')

    def command(argv, label, limit):
        argv = list(map(str, argv)); bind(pins, argv[0]); verify_pins(pins)
        result['state'] = label; commands.append(dict(label=label, argv=argv, timeout_seconds=limit)); save()
        env = dict(os.environ, PATH='/usr/bin:/bin', PYTHONPATH=str(VERIFY/'verification'),
                   PYTHONDONTWRITEBYTECODE='1', LC_ALL='C', READELF='/usr/bin/readelf')
        with (work/(label.lower()+'.log')).open('xb') as log:
            child = subprocess.Popen(argv, cwd=work, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            result['child_pid'] = child.pid; save()
            try: code = child.wait(timeout=limit)
            except BaseException:
                os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
        result['child_pid'] = None; commands[-1]['returncode'] = code
        require(code == 0, label+' failed; retain original evidence'); verify_pins(pins)

    try:
        config, pins = inputs(build, build_sha, group, width)
        program, soc, elf = config['program'], config['soc'], config['elf']
        result.update(elf=str(elf), elf_sha256=program['elf_sha256'], build_result_sha256=build_sha,
                      simv=soc['simv'], image_pins=soc['image_pins'], preload_segments=config['loads'],
                      prerequisite_result_sha256=config['prerequisite_result_sha256'],
                      admission='New full per-partition RTL numeric/CSR/protocol gates; old workers unchanged')
        verify_pins(pins); (out/'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        if execute:
            command([soc['simv'], '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
                     f'+TESTCASE=decode_partition_{group}', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                     '+VECTOR_TRACE='+str(work/'vector_trace.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                     '+ARA_UVM_TRACE_LIMIT=2000000'], 'SIMULATION', timeout)
            text = (work/'run.vcs.log').read_text()
            result['platform'] = check_platform(text, width)
            result['measured'] = checker.check(text, group, width, *checker.oracle(build))
            command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                     '--require-axi', '--require-axi-write', '--vector-trace', work/'vector_trace.csv',
                     '--log', work/'run.vcs.log', '--simv', soc['simv'], '--elf', elf,
                     '--output', work/'uvm_result.json'], 'PROTOCOL', 600)
            protocol = json.loads((work/'uvm_result.json').read_text())
            accept_protocol(protocol, program['elf_sha256'], digest(work/'run.vcs.log'),
                            digest(work/'vector_trace.csv'), soc['image_pins'])
            result.update(state='DECODE_PARTITION_RTL_ISA_PROTOCOL_PASS', performance_measured=True,
                          independent_protocol_checked=True, checked_guest_outputs=program['outputs_checked'])
        else: result['state'] = 'DECODE_PARTITION_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True, source_pins_sha256=digest(out/'source-pins.json'), limits=[
            'Partition full-K N64 ledger, not a continuous seven-part run or full model',
            'Every selected output and activation byte checked on target; host verifies checksums, not an all-word dump',
            'RVV uses original N128 Spike bits sliced to N64; native uses separate QBS C-reference bits',
            'Mixed ELF not executed by plain Spike; no ISA-model performance comparison',
            'Flat physical memory only; not translated MMU/PMP/Linux, PPA or FPGA acceptance',
            'Original predecessor timeouts and stopped matched gates are retained, not reclassified'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['artifacts'] = {str(p): digest(p) for p in (*work.glob('*.log'), work/'vector_trace.csv',
            work/'uvm_result.json', out/'source-pins.json', out/'commands.json') if p.is_file()}
        (out/'result.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True); p.add_argument('--build-sha256', required=True)
    p.add_argument('--group', type=int, choices=(0, 1), required=True)
    p.add_argument('--width', type=int, choices=(128, 256), required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--timeout', type=int, default=10800)
    p.add_argument('--execute-reviewed', action='store_true')
    def stop(sig, _frame): raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM): signal.signal(sig, stop)
    a = p.parse_args(); run(a.build, a.build_sha256, a.group, a.width, a.output, a.timeout, a.execute_reviewed)
