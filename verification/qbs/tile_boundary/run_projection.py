#!/usr/bin/env python3
"""Replay an immutable, previously checked projection ELF on reviewed new RTL."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
from run_ordinary import checked_review, runtime

CHECK = ROOT/'verification/qbs/m4_group_sums/projection/check.py'
spec = importlib.util.spec_from_file_location('retire_projection_check', CHECK)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)
BASE = ROOT/'verification/out/m4-sums-qkv-vcs-20261029-01'
ELF = ROOT/'verification/out/m4-sums-qkv-build-20261029-01/qbs_current_projection_soc'
ELF_SHA = 'ef66be1e29bae12c63dd780b296bec441a348e6c608bdb2202daa8ca64556a60'


def run(args):
    s = runtime.s
    out = args.output.resolve()
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(), 'Fresh output required')
    out.mkdir()
    work = out/'work'
    work.mkdir()
    owner = runtime.Execution(out)
    owner.env['PYTHONPATH'] = str(ROOT/'verification')
    owner.env['PYTHONDONTWRITEBYTECODE'] = '1'
    owner.state.update(simulations_launched=0)
    owner.save()
    result = dict(state='PREFLIGHT', whole_model=False, performance_measured=False)
    try:
        soc, pins, image = checked_review(args.soc_build, args.expected_soc_sha256)
        old = s.read_json(BASE/'result.json')
        s.require(old['state'] == 'PASS' and old['post_pins_match'] is True and
                  old['elf_sha256'] == ELF_SHA == s.digest(ELF), 'Historical binary identity')
        old_raw = check.check_output((BASE/'work/run.vcs.log').read_text())
        old_raw['traffic'] = check.check_trace(BASE/'work/vector_trace.csv')
        s.require(old_raw == old['measured'], 'Historical raw measurement mismatch')
        old_uvm = s.read_json(BASE/'work/uvm_result.json')
        s.require(old_uvm['status'] == 'PASS' and not old_uvm.get('issues'), 'Old protocol failure')
        files = [ELF, BASE/'result.json', BASE/'work/run.vcs.log',
                 BASE/'work/vector_trace.csv', BASE/'work/uvm_result.json', CHECK,
                 Path(__file__), HERE/'run_ordinary.py']
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
                files.append(Path(name).resolve())
        s.merge_pins(pins, s.hashes(files))
        s.atomic_json(out/'source-pins.json', pins)
        simv = Path(soc['simv'])
        def identity():
            s.verify_pins(pins)
            runtime.verify_current(soc, image, pins)
        identity()
        if args.execute:
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           simv.parent, ELF], out/'image-contract.log', 180, 'IMAGE_CONTRACT')
            owner.state['simulations_launched'] = 1
            owner.save()
            owner.execute([simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(ELF),
                '+TESTCASE=q8k_current_projection', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log', args.timeout, 'RUNNING')
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
                work/'vector_trace.csv', '--log', work/'run.vcs.log', '--simv', simv,
                '--elf', ELF, '--output', work/'uvm_result.json'], work/'checker.log', 600, 'CHECKING')
            measured = check.check_output((work/'run.vcs.log').read_text())
            measured['traffic'] = check.check_trace(work/'vector_trace.csv')
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['status'] == 'PASS' and not uvm.get('issues'), 'Protocol check failed')
            result.update(state='PASS', measured=measured, performance_measured=True)
        else:
            result['state'] = 'PREFLIGHT_NOT_RUN'
        identity()
        result.update(post_pins_match=True, elf_sha256=ELF_SHA, image_pins=image,
                      source_pins_sha256=s.digest(out/'source-pins.json'),
                      historical_binary_replay=True, current_software_rebuild_claim=False)
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        result['simulations_launched'] = owner.state['simulations_launched']
        s.atomic_json(out/'result.json', result)
        owner.state.update(state=result['state'], child_pid=None)
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--expected-soc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 10800:
        parser.error('timeout must be 1..10800')
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
