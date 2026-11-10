#!/usr/bin/env python3
"""Frozen SoC/SDK projection execution with independent output/protocol checks."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import shutil
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'
BASE = ROOT / 'verification/performance/chain_profile/build_soc.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def input_pins(base, soc, software):
    hw = json.loads((soc / 'build.json').read_text())
    sw = json.loads((software / 'build.json').read_text())
    base.require(hw['state'] == 'STAGE2_SOC_BUILT_NOT_EXECUTED' and hw['post_pins_match'],
                 'SoC was not built and sealed')
    expected = dict(schema_version=1, config='stage2_lane_coexecution', revision=hw['configuration']['revision'],
                    nr_lanes=4, vlen=1024, qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1,
                    sim_l2_bytes=16777216, shared_simd_multiplier=1, shared_fma=0,
                    qbs_lane_multiplier=hw['configuration']['qbs_lane_multiplier'], ideal_dispatcher=0)
    base.require(hw['configuration'] == expected and expected['qbs_lane_multiplier'] in (0, 1),
                 'Unexpected hardware configuration')
    base.require(sw['state'] == 'BUILT_NOT_EXECUTED' and sw['post_pins_match'] and
                 sw['trials'] in ([4, 4], [8, 8]) and sw['flag_seeds'] == [0, 8] and
                 sw['m'] == 8 and sw['k'] == 2048 and
                 sw['n'] in (32, 64, 96, 128) and sw['context_replay'] is False,
                 'Unexpected software scope')
    pins = {}
    for directory, record in ((soc, hw), (software, sw)):
        pinfile = directory / 'source-pins.json'
        base.require(base.digest(pinfile) == record['source_pins_sha256'], 'Inventory identity differs')
        for name, digest in {**json.loads(pinfile.read_text()), **record.get('image_pins', {})}.items():
            base.require(name not in pins or pins[name] == digest, 'Conflicting hardware/software pins')
            pins[name] = digest
        for path in (pinfile, directory / 'build.json'):
            pins[str(path)] = base.digest(path)
    elf = Path(sw['elf'])
    base.require(elf.is_relative_to(software) and elf.read_bytes()[:4] == b'\x7fELF' and
                 base.digest(elf) == sw['elf_sha256'], 'ELF identity/location differs')
    base.verify(pins)
    return hw, sw, pins


def prepare(args):
    base = load(BASE, 'stage2_projection_base')
    out = args.output.resolve()
    base.require(out.parent == OUT and not out.exists(), 'Fresh direct signoff output required')
    base.require(1 <= args.timeout <= 10800, 'Timeout outside 1..10800 seconds')
    soc, software = args.soc.resolve(strict=True), args.software.resolve(strict=True)
    hw, sw, pins = input_pins(base, soc, software)
    out.mkdir()
    inputs = out / 'inputs'
    inputs.mkdir()
    for source, name in ((Path(__file__), 'run_projection.py'), (BASE, 'base_build.py'),
                         (HERE / 'check_projection.py', 'check_projection.py')):
        target = inputs / name
        shutil.copy2(source, target)
        pins[str(source)] = pins[str(target)] = base.digest(source)
    for path in (ROOT / 'verification/ara_verify').rglob('*.py'):
        pins[str(path)] = base.digest(path)
    contract = ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'
    pins[str(contract)] = base.digest(contract)
    base.save(out / 'selection.json', dict(soc=str(soc), software=str(software), timeout=args.timeout,
              enabled=hw['configuration']['qbs_lane_multiplier'], checker=str(inputs / 'check_projection.py'),
              elf_sha256=sw['elf_sha256'], simv_sha256=base.digest(hw['simv'])))
    pins[str(out / 'selection.json')] = base.digest(out / 'selection.json')
    base.verify(pins)
    base.save(out / 'source-pins.json', pins)
    base.save(out / 'status.json', dict(state='PREPARED_NOT_EXECUTED', child_pid=None))
    print(inputs / 'run_projection.py', flush=True)


def check_loans(text, n, enabled, parse, modes=(4, 8, 8, 4)):
    records = [parse(line, 'STAGE2_SOC_LOAN ') for line in text.splitlines()
               if line.startswith('STAGE2_SOC_LOAN ')]
    totals = [parse(line, 'STAGE2_SOC_LOAN_DONE ') for line in text.splitlines()
              if line.startswith('STAGE2_SOC_LOAN_DONE ')]
    if len(totals) != 4 or {t['lane'] for t in totals} != set(range(4)):
        raise ValueError('Missing/duplicate actual VMFPU terminal accounting')
    commands = len(modes)*(n//16) if enabled else 0
    if len(records) != 4*commands:
        raise ValueError('Missing/extra actual VMFPU loan commands')
    for lane in range(4):
        rows = [r for r in records if r['lane'] == lane]
        if [r['seq'] for r in rows] != list(range(1, commands+1)):
            raise ValueError('Loan command sequence mismatch')
        expected_sum = 0
        for index, row in enumerate(rows):
            mode = modes[index//(n//16)]
            beats = 4096 if mode == 8 else 0
            expected_sum += beats
            if set(row) != {'lane', 'seq', 'accepted', 'core_issued', 'core_completed', 'returned'} or any(
                    row[name] != beats for name in ('accepted', 'core_issued', 'core_completed', 'returned')):
                raise ValueError('Actual multiplier work differs from M4/M8 plan')
        terminal, = [t for t in totals if t['lane'] == lane]
        if terminal != dict(lane=lane, commands=commands, accepted=expected_sum, returned=expected_sum):
            raise ValueError('Lost actual multiplier work')
    return dict(commands_per_lane=commands, totals=totals)


def execute(out):
    if Path(__file__).resolve() != out / 'inputs/run_projection.py':
        raise ValueError('Execute frozen runner only')
    base = load(out / 'inputs/base_build.py', 'stage2_projection_base')
    check = load(out / 'inputs/check_projection.py', 'stage2_projection_check')
    config = json.loads((out / 'selection.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    result = dict(state='FAIL', whole_model=False, performance_measured=False)
    status = dict(state='PREFLIGHT', child_pid=None, started=datetime.now(timezone.utc).isoformat())
    work = out / 'work'
    work.mkdir(exist_ok=False)
    try:
        base.verify(pins)
        hw, sw, _ = input_pins(base, Path(config['soc']), Path(config['software']))
        simv, elf = Path(hw['simv']), Path(sw['elf'])
        os.environ.update(PYTHONPATH=str(ROOT / 'verification'), PYTHONDONTWRITEBYTECODE='1',
                          READELF='/usr/bin/readelf', LC_ALL='C')
        base.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                      simv.parent, elf], work, out / 'image-contract.log', 180,
                     status, out / 'status.json', 'IMAGE_CONTRACT')
        argv = [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
                '+TESTCASE=stage2_projection', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
        base.verify(pins)
        before = time.monotonic()
        base.execute(argv, work, work / 'console.log', config['timeout'], status, out / 'status.json', 'RUNNING')
        wall = time.monotonic()-before
        log = work / 'run.vcs.log'
        measured = check.check_run(log, Path(config['software']), config['enabled'])
        loans = check_loans(log.read_text(), sw['n'], config['enabled'], check.fields, sw['trials'])
        proof = work / 'protocol.json'
        base.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                      '--require-backend', '--require-axi', '--require-axi-write',
                      '--vector-trace', work / 'vector_trace.csv', '--log', log, '--simv', simv,
                      '--elf', elf, '--output', proof], work, work / 'protocol.log', 600,
                     status, out / 'status.json', 'PROTOCOL_CHECK')
        protocol = json.loads(proof.read_text())
        base.require(protocol['status'] == 'PASS' and protocol['issues'] == [] and
                     protocol['elf_sha256'] == sw['elf_sha256'] and
                     protocol['log_sha256'] == base.digest(log) and
                     protocol['vector_trace_sha256'] == base.digest(work / 'vector_trace.csv'),
                     'Independent protocol or identity check failed')
        base.verify(pins)
        result.update(state='PASS', performance_measured=True, post_pins_match=True,
                      measured=measured, actual_lane_multipliers=loans, protocol_checked=True,
                      soc=config['soc'], software=config['software'], enabled=config['enabled'],
                      elf_sha256=sw['elf_sha256'], simv_sha256=base.digest(simv), wall_seconds=wall,
                      source_pins_sha256=base.digest(out / 'source-pins.json'))
    except BaseException as exc:
        result['error'] = repr(exc)
    result['artifacts'] = {str(p): base.digest(p) for p in work.iterdir() if p.is_file()}
    base.save(out / 'result.json', result)
    status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
    base.save(out / 'status.json', status)
    print('STAGE2_PROJECTION_' + result['state'] + ' ' + str(out / 'result.json'), flush=True)
    return int(result['state'] != 'PASS')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('output', type=Path)
    parser.add_argument('--soc', type=Path)
    parser.add_argument('--software', type=Path)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        def interrupted(sig, _frame):
            raise InterruptedError('Signal ' + str(sig))
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, interrupted)
        raise SystemExit(execute(args.output.resolve()))
    if args.soc is None or args.software is None:
        parser.error('--soc and --software are required for preparation')
    prepare(args)
