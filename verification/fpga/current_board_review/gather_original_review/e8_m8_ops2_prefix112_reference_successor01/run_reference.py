#!/usr/bin/env python3
"""One explicitly admitted software reference; never builds or launches DUT."""
import hashlib
import json
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from reference_check import HERE, NAME, MAX_RETIRED, OBJDUMP, symbol, model, audit_trace, require, ReferenceBoundExceeded
from prepare_successor import SPIKE

OLD = HERE.parent / 'e8_m8_ops2_prefix112_prepare01'
ADMISSION = HERE.parent / 'e8_m8_ops2_prefix112_reference_admission01/review.json'
ADMISSION_SHA = '05c5c38d985229b2e9a6133786a11a373b6a9d02ecad6c98e8b7c9bf2bcbf3c8'
MAX_LOG = 805306368


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def check_pins(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: ' + path)


def main():
    require(sha(ADMISSION) == ADMISSION_SHA, 'Admission drift')
    admission = read(ADMISSION)
    require(admission['decision'] == 'AUTHORIZE_ONE_REFERENCE_SUCCESSOR_5050000_NOT_DUT', 'Wrong admission')
    require(admission['new_limits'] == dict(total_debug_steps=5050000, seconds=120,
                output_bytes_per_file=MAX_LOG, one_attempt_only=True), 'Limit drift')
    require(all(admission['constraints'].values()), 'Constraints drift')
    require((HERE/'reference_check.py').read_bytes() == (OLD/'reference_check.py').read_bytes().replace(
        b'MAX_RETIRED = 1024, 112, 5_000_000', b'MAX_RETIRED = 1024, 112, 5_050_000'), 'Checker changed beyond ceiling')
    pins = read(OLD/'baseline_pins.json')
    check_pins(pins)
    for path in sorted(OLD.rglob('*')):
        if path.is_file():
            pins[str(path)] = sha(path)
    pins[str(ADMISSION)] = ADMISSION_SHA
    for key in ('old_result', 'independent_bound_review', 'spike_elf', 'soc_elf'):
        entry = admission[key]
        require(sha(entry['path']) == entry['sha256'], key + ' drift')
        pins[entry['path']] = entry['sha256']
    require(read(OLD/'reference/not_completed.json')['status'] == 'NOT_COMPLETED_WITHIN_BOUND', 'Old status changed')
    require(not (OLD/'READY.json').exists(), 'Do not replace old incomplete status')
    require(sha(SPIKE) == 'c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2', 'Spike drift')
    pins[str(SPIKE)] = sha(SPIKE)
    for module in ('audit_accepted8.py', 'prepare_successor.py', 'prepare_batch.py'):
        path = HERE.parent/module
        pins[str(path)] = sha(path)
    for path in HERE.glob('*.py'):
        pins[str(path)] = sha(path)
    require(sha(OLD/'host/host_gate.json') == 'c3994321b79307a1fa5110f7a21d6df92df64eab3fc2989b3de23df5ea22513b', 'Host12 drift')
    require(sha(OLD/'source_elf_proof.json') == 'e84846e23d5320e6474a5e4876aebecb4c124067e593c7b51fff93bb459d80e1', 'Source proof drift')
    host = read(OLD/'host/host_gate.json')
    require(len(host['tests']) == 12 and all(row['status'] == 'PASS' for row in host['tests']), 'Reused Host12 incomplete')
    gold = model()
    require(gold == read(OLD/'host_expected.json'), 'Oracle changed')
    check_pins(pins)
    save(HERE/'input_pins.json', pins)
    save(HERE/'admission_pin.json', dict(path=str(ADMISSION), sha256=ADMISSION_SHA, review=admission))
    reference = HERE/'reference'
    reference.mkdir()  # Exclusive one-attempt sentinel, including failed executions.
    elf = Path(admission['spike_elf']['path'])
    debug = reference/'spike.cmd'
    debug.write_text(f'rs {MAX_RETIRED}\nstr {symbol(elf,"replay_log",OBJDUMP)[0]:x}\nquit\n')
    command = [str(SPIKE), '-d', '--debug-cmd='+str(debug), '--isa=rv64gcv_zvl1024b', '-m2',
               '--log-commits', '--log='+str(reference/'commits.log'), str(elf)]
    save(reference/'command.json', dict(command=command, seconds=120, total_debug_steps=MAX_RETIRED,
        output_bytes_per_file=MAX_LOG, one_attempt_only=True, compilation=False, dut=False))

    def limit_file():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG, MAX_LOG))

    def incomplete(evidence):
        check_pins(pins)
        record = dict(status='NOT_COMPLETED_WITHIN_BOUND', evidence=evidence, retry=False,
            old_artifacts_unchanged=True, elapsed_s=elapsed, dut=False,
            commit_sha256=sha(reference/'commits.log') if (reference/'commits.log').exists() else None)
        save(reference/'not_completed.json', record)
        print(record['status'], flush=True)

    start = time.monotonic()
    try:
        with (reference/'spike.log').open('x') as stream:
            run = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=120, preexec_fn=limit_file)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic()-start
        save(reference/'execution.json', dict(status='TIMEOUT', elapsed_s=elapsed))
        incomplete(dict(reason='wall_time_limit'))
        return
    elapsed = time.monotonic()-start
    save(reference/'execution.json', dict(returncode=run.returncode, elapsed_s=elapsed, command=command))
    if run.returncode == -signal.SIGXFSZ:
        incomplete(dict(reason='per_output_file_size_limit'))
        return
    require(run.returncode == 0, 'Reference execution nonzero; no retry')
    print('Single Spike execution returned; checking complete raw oracle and HTIF.', flush=True)
    try:
        raw = audit_trace(reference/'commits.log', elf, gold)
    except ReferenceBoundExceeded as error:
        incomplete(error.evidence)
        return
    require(raw['total_commit_records_to_htif'] <= MAX_RETIRED and elapsed < 120, 'Execution bound')
    require(all(p.stat().st_size <= MAX_LOG for p in (reference/'commits.log', reference/'spike.log')), 'File bound')
    save(reference/'reference.json', dict(**raw, elapsed_s=elapsed, returncode=run.returncode,
        commit_sha256=sha(reference/'commits.log'), commit_bytes=(reference/'commits.log').stat().st_size,
        limits=admission['new_limits']))
    (reference/'runtime.log').write_text(raw['reconstructed_console'])
    check_pins(pins)
    print(raw['status'], raw['firmware_retired_to_htif_store'], flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if not (HERE/'error.json').exists():
            save(HERE/'error.json', dict(status='STOPPED_NO_RETRY', error=repr(error), dut=False))
        raise
