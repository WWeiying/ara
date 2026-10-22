#!/usr/bin/env python3
"""One explicitly authorized reference; no compilation or retry capability."""
import argparse
import json
from pathlib import Path
import resource
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from prepare import HERE, SPIKE, ISA, sha, save

OUT = HERE / 'reference03M'
STEPS = 3000000
RAW = 256 * 1024 * 1024


def prepare_approval():
    OUT.mkdir(exist_ok=False)
    sourceproof = json.loads((HERE / 'sourceproof.json').read_text())
    pins = dict(sourceproof['external_pins'])
    for folder in ('prepared', 'soc', 'spike', 'host'):
        for path in (HERE / folder).rglob('*'):
            if path.is_file():
                pins[str(path)] = sha(path)
    for name in ('prepare.py', 'host.c', 'sourceproof.json', 'host.json',
                 'BOUND_ANALYSIS.md', 'reference03m.py'):
        pins[str(HERE / name)] = sha(HERE / name)
    for path, digest in pins.items():
        assert sha(path) == digest, path
    syms = json.loads((HERE / 'spike/symbols.json').read_text())
    debug = OUT / 'spike.cmd'
    debug.write_text(f'rs {STEPS}\nstr {syms["replay_log"]:x}\nquit\n')
    pins[str(debug)] = sha(debug)
    command = [str(SPIKE), '-d', '--debug-cmd=' + str(debug), '--isa=' + ISA, '-m2',
               '--log-commits', '--log=' + str(OUT / 'commits.log'), str(HERE / 'spike/program.elf')]
    save(OUT / 'approval.json', {
        'status': 'AUTHORIZED_REFERENCE_ONLY_PENDING_ONE_EXECUTION',
        'authority': 'User explicit pre-execution revision: <=3M steps,256MiB raw,120s; static admission required',
        'old_authorization': 'NOT_RUN_STATIC_BOUND_INSUFFICIENT',
        'old_reference_executions': 0, 'new_reference_executions_allowed': 1,
        'software_changed_for_bound': False, 'oracle_changed': False,
        'static_lower_bound': 1801190, 'static_upper_envelope': 2070768,
        'limits': {'steps': STEPS, 'seconds': 120, 'raw_bytes': RAW},
        'command': command, 'pins': pins, 'no_DUT': True, 'no_retry': True})
    save(OUT / 'approval.pin.json', {'sha256': sha(OUT / 'approval.json')})


def run_once():
    pin = json.loads((OUT / 'approval.pin.json').read_text())
    assert sha(OUT / 'approval.json') == pin['sha256']
    approval = json.loads((OUT / 'approval.json').read_text())
    assert approval['limits'] == {'steps': STEPS, 'seconds': 120, 'raw_bytes': RAW}
    for path, digest in approval['pins'].items():
        assert sha(path) == digest, path
    # The exclusive sentinel survives any timeout, parse failure or interruption.
    with (OUT / 'ATTEMPT_STARTED.json').open('x') as stream:
        json.dump({'time': time.time(), 'approval_sha256': pin['sha256']}, stream)
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (RAW, RAW))
    start = time.monotonic()
    rc, error = None, None
    with (OUT / 'spike.log').open('x') as stream:
        try:
            proc = subprocess.run(approval['command'], stdout=stream, stderr=subprocess.STDOUT,
                                  timeout=120, preexec_fn=limits)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            error = 'WALL_BOUND_120_SECONDS'
    unchanged = all(sha(path) == digest for path, digest in approval['pins'].items())
    save(OUT / 'execution.json', {'status': 'EXECUTED_PENDING_RAW_AUDIT',
        'returncode': rc, 'error': error, 'elapsed_s': time.monotonic() - start,
        'input_pins_unchanged': unchanged, 'approval_sha256': pin['sha256'],
        'raw': {p.name: {'bytes': p.stat().st_size, 'sha256': sha(p)}
                for p in (OUT / 'commits.log', OUT / 'spike.log') if p.exists()},
        'retry_allowed': False})
    assert rc == 0 and not error and unchanged, 'reference stopped; retain evidence, no retry'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['prepare', 'run'])
    args = parser.parse_args()
    prepare_approval() if args.action == 'prepare' else run_once()
