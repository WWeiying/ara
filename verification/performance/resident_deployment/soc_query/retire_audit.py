#!/usr/bin/env python3
"""Offline successor for the mixed-event commit CSV; never reruns the simulator."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ORIGINAL = OUT/'enablement_soc_resident_deployment_query_20261112_022423'
ORIGINAL_REVIEW = 'e6cfff80596188dbdbba126c437ad3e9613526b467bb2d760ff43c0b90597c99'
ORIGINAL_RESULT = '98ac7c1bf508826602ac917c05c5a1f32cb9fc6713ba1fc7587046705d3b077e'
RAW = {'work/run.vcs.log': '932cb139e067563bbc0f1a635244661327fd1d6c6d56ce0374c9c9d7b3c4ca71',
       'work/commit.csv': '54b6aa7e4d65fc57e3a73374ee3b01a66df3ebc6627615db27c3e4201cc48051',
       'work/query.elf': 'cb58eb878a5a4f7fe4932fa0d313d61d03f0fd04db02319a0fdea7d0570e764e'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')


def derive(text):
    old = '        if instruction & 0x707F == 0x405B:\n'
    if text.count(old) != 1:
        raise ValueError('Unrecognized mixed-event checker preimage')
    return text.replace(old, "        if row['event'] == 'retire' and instruction & 0x707F == 0x405B:\n")


def modules():
    path = ORIGINAL/'inputs/query_smoke.py'
    spec = importlib.util.spec_from_file_location('original_mixed_event_query', path)
    original = importlib.util.module_from_spec(spec); spec.loader.exec_module(original)
    original.require(sha(ORIGINAL/'source-pins.json') == ORIGINAL_REVIEW, 'Original review drift')
    pins = original.read(ORIGINAL/'source-pins.json')
    original.verify({path: pins[str(path)]})
    successor = types.ModuleType('query_retirement_only_successor'); successor.__file__ = str(path)
    exec(compile(derive(path.read_text()), 'offline_retire_successor.py', 'exec'), successor.__dict__)
    return original, successor


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); out = args.output.resolve()
    old, new = modules()
    old.require(out.parent == OUT and out.name.startswith('enablement_soc_resident_deployment_query_audit_')
                and not out.exists(), 'Fresh independent offline-audit output required')
    out.mkdir()
    pins = old.read(ORIGINAL/'execution-pins.json') | old.read(ORIGINAL/'source-pins.json')
    pins.update({str(ORIGINAL/name): digest for name, digest in RAW.items()})
    pins[str(ORIGINAL/'result.json')] = ORIGINAL_RESULT
    for name in ('execution-pins.json', 'source-pins.json', 'artifact-pins.json'):
        pins[str(ORIGINAL/name)] = sha(ORIGINAL/name)
    for name, digest in old.read(ORIGINAL/'artifact-pins.json').items():
        pins[str(ORIGINAL/name)] = digest
    for path in (Path(__file__).resolve(), HERE/'retire_audit_test.py'):
        pins[str(path)] = sha(path)
    image = Path(old.read(ORIGINAL/'plan.json')['image'])
    monitor = image/'source/hardware/tb/ara_commit_monitor.sv'
    pins[str(monitor)] = old.read(image/'source-pins.json')[str(monitor)]
    old.verify(pins); save(out/'source-pins.json', pins)
    report = dict(state='FAIL', original_worker_state='FAIL', original_worker_relabelled=False,
                  simulator_rerun=False, image_rebuilt=False, full_model_executed=False,
                  scope='Offline RVFI/CVXIF audit only: classify retire vs arch_start/cvx_req')
    try:
        terminal = old.read(ORIGINAL/'result.json')
        old.require(terminal['state'] == 'FAIL' and terminal['error'] ==
                    "ValueError('Malformed AKVINFO retirement')", 'Unknown original failure')
        text = (ORIGINAL/'work/run.vcs.log').read_text()
        with (ORIGINAL/'work/commit.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        try:
            old.check_native(text, rows)
        except ValueError as error:
            old.require(str(error) == 'Malformed AKVINFO retirement', 'Original failure changed')
        else:
            raise ValueError('Original checker failure not reproduced')
        semantics = monitor.read_text()
        old.require('%0d,arch_start,' in semantics and '%0d,cvx_req,' in semantics and
                    '%0d,retire,' in semantics, 'Reaudit mixed-event CSV semantics')
        native = new.check_native(text, rows)
        save(out/'native.json', native)
        commands = [[sys.executable, '-B', str(HERE/'retire_audit_test.py')],
            [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--log',
             str(ORIGINAL/'work/run.vcs.log'), '--simv', str(image/'sim/simv'), '--elf',
             str(ORIGINAL/'work/query.elf'), '--output', str(out/'protocol.json')]]
        save(out/'commands.json', commands)
        env = old.read(ORIGINAL/'plan.json')['environment'].copy()
        env['PYTHONPATH'] = str(ORIGINAL/'inputs/verification')
        for index, argv in enumerate(commands):
            old.verify(pins)
            with (out/f'command-{index}.log').open('x') as stream:
                subprocess.run(argv, cwd=out, env=env, stdout=stream, stderr=subprocess.STDOUT,
                               timeout=120, check=True)
        proof = old.read(out/'protocol.json')
        imagepins = old.read(image/'image-pins.json')
        old.require(proof['status'] == 'PASS' and proof['issues'] == [] and
                    proof['elf_sha256'] == RAW['work/query.elf'] and proof['log_sha256'] == RAW['work/run.vcs.log']
                    and proof['simv_sha256'] == sha(image/'sim/simv') and proof['sim_image_sha256'] ==
                    {p: h for p, h in imagepins.items() if p == str(image/'sim/simv') or p.endswith('.so')},
                    'Independent protocol/image/ELF proof failed')
        counts = proof['contract_counts']
        old.require(counts['requests'] == counts['responses'] and counts['requests'] >= 7 and
                    all(counts[k] == 0 for k in ('exceptions', 'protocol_errors', 'outstanding', 'mmu_request_cycles')),
                    'Query exception/drain/VLSU failure')
        old.require(all(v == 0 for name in ('backend_counts', 'axi_read_counts', 'axi_write_counts')
                        for v in proof[name].values()) and proof['uvm_backend_event_count'] == 0,
                    'Query entered compute/backend/VLSU')
        old.verify(pins)
        report.update(state='PASS', native=native, protocol_pass=True, post_pins_match=True,
                      source_pins_sha256=sha(out/'source-pins.json'), original_failure_reproduced=True)
    except BaseException as error:
        report['error'] = repr(error)
    save(out/'result.json', report)
    artifacts = {str(path.relative_to(out)): sha(path) for path in out.rglob('*') if path.is_file()}
    save(out/'artifact-pins.json', artifacts)
    print(json.dumps(report), flush=True)
    return int(report['state'] != 'PASS')


if __name__ == '__main__':
    raise SystemExit(main())
