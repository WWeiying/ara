#!/usr/bin/env python3
"""Execute the unchanged real-GGML RVV ELF against its exact-ELF ISA oracle."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

from audit import digest, require, verify_pins
from prepare_wide_soc import HERE, ROOT, VERIFY, RUNS
from continue_wide_soc import SOC_HASH
from run_supply_sdk import bind, acceptance_gate
from run_wide_soc_smoke import elf_admission, check_platform
from collect_decode_rvv_build import BASE, ELF_SHA
import check_decode_rvv as checker

ISA = RUNS / 'e2e_decode_rvv_isa_20261106_03'
ISA_SHA = 'ee50533a21dfa06092a352582d552a4bb64f00eb823cc2442128966fdf5c4944'


def timing(text):
    tags = ('RVV_DECODE_PREP', 'RVV_DECODE_PART', 'RVV_DECODE_RESULT')
    rows = {tag: [checker.fields(line, tag) for line in text.replace('\r', '').splitlines()
                  if line.startswith(tag+' ')] for tag in tags}
    require(tuple(map(len, rows.values())) == (4, 7, 1), 'Incomplete timed work')
    return dict(preparation=rows[tags[0]], parts=rows[tags[1]], total=rows[tags[2]][0],
                complete_call_ratio_accepted=False,
                limits=['Timed CSR observations differ from the existing SDK driver; both seed VCSR=5',
                        'RTL cycle records only; no ratio with ISA-model cycle values'])


def reference(pins):
    bind(pins, ISA / 'result.json', ISA_SHA)
    value = json.loads((ISA / 'result.json').read_text())
    require(value['state'] == 'EXACT_ELF_RVV_SPIKE_REFERENCE_PASS' and value['post_pins_match'] and
            value['elf_sha256'] == ELF_SHA and not value['performance_measured'] and
            not value['rtl_executed'] and not value['target_elf_changed'] and
            not value['spike_binary_changed'] and value['independent_isa_output_words'] == 896 and
            value['csr_records'] == 11, 'Unaccepted independent RVV reference')
    bind(pins, ISA / 'source-pins.json', value['source_pins_sha256'])
    for name, sha in json.loads((ISA / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
    for name, sha in value['artifacts'].items(): bind(pins, name, sha)
    golden = [(BASE / f'part_{p}_expected.bin').read_bytes() for p in range(7)]
    packed = [(BASE / f'activation_{s}.bin').read_bytes() for s in range(4)]
    measured = checker.check((ISA / 'spike.log').read_text(), golden, packed, isa_model=True)
    require(measured == value['measured'], 'ISA raw-log replay differs')
    for part, data in enumerate(measured['outputs_hex']):
        require((ISA / f'isa_output_{part}.bin').read_bytes() == bytes.fromhex(data),
                'Exported ISA output differs from execution')
    return value, golden, packed


def inputs(width):
    require(width in SOC_HASH, 'Unknown physical platform')
    pins = {}
    isa, golden, packed = reference(pins)
    root = RUNS / f'e2e_physical_wide_soc{width}_20261106_01'
    bind(pins, root / 'result.json', SOC_HASH[width])
    soc = json.loads((root / 'result.json').read_text())
    require(soc['state'] == 'PHYSICAL_WIDE_SOC_BUILT_NOT_EXECUTED' and soc['post_pins_match'] and
            soc['width'] == width, 'Wrong physical SoC')
    bind(pins, root / 'source-pins.json', soc['source_pins_sha256'])
    for name, sha in json.loads((root / 'source-pins.json').read_text()).items(): bind(pins, name, sha)
    for group in ('artifacts', 'image_pins'):
        for name, sha in soc[group].items(): bind(pins, name, sha)
    elf = Path(isa['elf']); bind(pins, elf, ELF_SHA)
    loads = elf_admission(elf.read_bytes(), width//8)
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).is_file() and any(Path(path).resolve().is_relative_to(r) for r in (ROOT, VERIFY)):
            bind(pins, path)
    for path in (HERE / 'test_decode_rvv_rtl.py', Path(__file__), Path(sys.executable),
                 *(VERIFY / 'verification/ara_verify').glob('*.py')): bind(pins, path)
    gate_sha = acceptance_gate(pins)
    return dict(isa=isa, golden=golden, packed=packed, soc=soc, elf=elf, preload_segments=loads,
                prerequisite_result_sha256=gate_sha), pins


def run(width, output, timeout, execute):
    out = output.absolute()
    require(out == out.resolve() and out.is_relative_to(RUNS) and 1 <= timeout <= 10800,
            'Fresh, bounded sole-verification run required')
    out.mkdir(parents=True, exist_ok=False); work = out / 'work'; work.mkdir()
    result = dict(state='PREPARING', width=width, child_pid=None, performance_measured=False,
                  whole_model=False, complete_call_ratio_accepted=False, synthesis_run=False)
    pins, commands = {}, []
    def save(): (out / 'status.json').write_text(json.dumps(result, indent=2)+'\n')
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
        config, pins = inputs(width)
        soc, elf = config['soc'], config['elf']
        result.update(elf=str(elf), elf_sha256=ELF_SHA, simv=soc['simv'], image_pins=soc['image_pins'],
                      preload_segments=config['preload_segments'], reference_result_sha256=ISA_SHA,
                      prerequisite_result_sha256=config['prerequisite_result_sha256'])
        (out / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        if execute:
            command([soc['simv'], '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD='+str(elf),
                     '+TESTCASE=physical_decode_rvv', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                     '+VECTOR_TRACE='+str(work / 'vector_trace.csv'), '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                     '+ARA_UVM_TRACE_LIMIT=2000000'], 'SIMULATION', timeout)
            text = (work / 'run.vcs.log').read_text()
            result['platform'] = check_platform(text, width)
            measured = checker.check(text, config['golden'], config['packed'])
            result['independent_isa_comparison'] = checker.compare_isa(measured, config['isa']['measured'])
            result['measured'], result['rtl_timing'] = measured, timing(text)
            command([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                     '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                     '--log', work / 'run.vcs.log', '--simv', soc['simv'], '--elf', elf,
                     '--output', work / 'uvm_result.json'], 'PROTOCOL', 600)
            p = json.loads((work / 'uvm_result.json').read_text())
            require(p['status'] == 'PASS' and p['log_sha256'] == digest(work / 'run.vcs.log') and
                    p['vector_trace_sha256'] == digest(work / 'vector_trace.csv') and p['elf_sha256'] == ELF_SHA and
                    p['sim_image_sha256'] == soc['image_pins'], 'Independent protocol identity/check differs')
            result.update(state='REAL_DECODE_RVV_RTL_ISA_PASS', performance_measured=True,
                          independent_protocol_checked=True)
        else: result['state'] = 'REAL_DECODE_RVV_RTL_PREFLIGHT_NOT_RUN'
        verify_pins(pins)
        result.update(post_pins_match=True, source_pins_sha256=digest(out / 'source-pins.json'),
                      limits=['Seven real N128 prefixes, full K; not complete model or full output dimensions',
                              'RVV versus SDK total-call comparison awaits instrumentation alignment or bound',
                              'Flat physical memory; not MMU/PMP/Linux validation'])
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc)); raise
    finally:
        save(); (out / 'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        result['artifacts'] = {str(p):digest(p) for p in (
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
