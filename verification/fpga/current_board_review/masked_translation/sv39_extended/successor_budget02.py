#!/usr/bin/env python3
"""One authorized budget-only successor; sealed payload and checker are unchanged."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
import successor as su

OUT = su.HERE / 'candidate02_extended8_02'
OLD = su.HERE / 'candidate02_extended8_01'
INNER = 1800
OUTER = 2100
TESTS = su.HERE / 'budget02_host_tests.json'


def command(out, execute=False):
    cmd = su.command(out, execute)
    su.require(su.one_arg(cmd, '--timeout') == '1200', 'Inherited budget changed')
    cmd[cmd.index('--timeout') + 1] = str(INNER)
    if not execute:
        cmd[cmd.index('--out') + 1] = str(out / 'budget_dryrun')
    validate_command(cmd, out, execute)
    return cmd


def validate_command(cmd, out, execute):
    expected = su.command(out, execute)
    expected[expected.index('--timeout') + 1] = str(INNER)
    if not execute:
        expected[expected.index('--out') + 1] = str(out / 'budget_dryrun')
    su.require(cmd == expected, 'Only budget/output relocation is authorized')
    su.require(su.one_arg(cmd, '--jobs') == '1', 'Only one job authorized')


def validate_contract(contract):
    su.require(contract['inner_timeout_s'] == 1800 and contract['outer_timeout_s'] == 2100,
               'Fixed budget differs')
    su.require(contract['jobs'] == 1 and contract['output'] == str(OUT), 'Wrong attempt/jobs')
    su.require(contract['elf_sha256'] == 'a0219fef355612a36370851a6a4d3011bb30991afbc19459068c3728526ea982',
               'Original ELF identity differs')
    su.require(contract['image_sha256'] == '384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810',
               'Original image identity differs')


def preflight():
    tests = su.read(TESTS)
    su.require(tests['status'] == 'HOST_NEGATIVE_TESTS_PASS_NOT_DUT', 'Host checks missing')
    su.verify_pins(tests['pins'])
    old = su.read(OLD / 'preflight.json')
    su.verify_pins(old['pins'])
    su.verify_pins(su.read(OLD / 'worker.json')['gate']['pins'])
    # Preserve all existing attempt artifacts, including raw CANCELLED evidence.
    preserved = {str(p): su.sha(p) for p in sorted(OLD.rglob('*')) if p.is_file()}
    su.preflight(OUT)
    pre = su.read(OUT / 'preflight.json')
    su.require(su.read(OUT / 'programs/programs.json') == su.read(OLD / 'programs/programs.json'),
               'Program manifest changed')
    su.require(pre['image_files'] == old['image_files'] and pre['elf_sha256'] == old['elf_sha256'],
               'Payload/image changed')
    gate = su.parent_gate(su.check_image())
    cmd = command(OUT)
    su.save(OUT / 'budget_dryrun_command.json', cmd)
    with (OUT / 'budget_dryrun.log').open('x') as log:
        subprocess.run(cmd, cwd=su.ref.base.ROOT, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    result = su.read(OUT / 'budget_dryrun/summary.json')
    su.require(len(result) == 1 and result[0]['status'] == 'DRY_RUN', 'Budget dry run failed')
    paths = [Path(__file__), su.HERE / 'test_successor_budget02.py', TESTS,
             OUT / 'preflight.json', OUT / 'budget_dryrun_command.json',
             OUT / 'budget_dryrun/summary.json']
    pins = {**preserved, **pre['pins'], **gate['pins'],
            **su.read(su.REFERENCE / 'input_pins.json'), **{str(p): su.sha(p) for p in paths}}
    contract = dict(status='BUDGET02_PREFLIGHT_PASS_NOT_LAUNCHED', output=str(OUT),
                    inner_timeout_s=INNER, outer_timeout_s=OUTER, jobs=1,
                    elf_sha256=pre['elf_sha256'], image_sha256=pre['image_sha256'], pins=pins,
                    command=command(OUT, True), parent=gate['status'],
                    delta='Only orchestration timeout 1200->1800 inner, 1200->2100 outer; output relocated',
                    fail_fast='Unchanged ELF stops subsequent cases on first mx_errors; no retry or successor launch',
                    acceptance='Unchanged CSV checker: 6227 comparisons, CSR restore, magic, CTRL and UART')
    validate_contract(contract)
    su.verify_pins(pins)
    su.save(OUT / 'budget_preflight.json', contract)
    print(contract['status'], OUT, flush=True)


def worker(authorized):
    su.require(authorized, 'Explicit authorization required')
    contract = su.read(OUT / 'budget_preflight.json')
    validate_contract(contract)
    validate_command(contract['command'], OUT, True)
    su.verify_pins(contract['pins'])
    image = su.check_image()
    su.require(su.sha(su.IMAGE / 'image.json') == contract['image_sha256'], 'Image ledger drift')
    gate = su.parent_gate(image)
    su.save(OUT / 'worker.json', dict(pid=os.getpid(), started_unix=time.time(), gate=gate,
            command=contract['command'], budget_preflight_sha256=su.sha(OUT / 'budget_preflight.json')))
    started = time.monotonic()
    passed = False
    terminal = dict(status='CANDIDATE02_EXTENDED8_NOT_PASS', scope='Only these eight cases, not Linux or general closure')
    try:
        with (OUT / 'worker.log').open('x') as log:
            child = subprocess.Popen(contract['command'], cwd=su.ref.base.ROOT,
                    stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            code = child.wait()
        analysis = su.csv_check.analyze(OUT / 'run/tests/extended8/commit_trace.csv',
                                       su.read(su.REFERENCE / 'soc.symbols.json'))
        su.save(OUT / 'csv_analysis.json', analysis)
        summary = su.read(OUT / 'run/summary.json')
        passed = code == 0 and len(summary) == 1 and summary[0]['name'] == 'extended8' and \
            summary[0]['status'] == 'PASS' and summary[0]['returncode'] == 0 and \
            analysis['status'] == 'EXTENDED8_CSV_ORACLE_PASS'
        terminal.update(returncode=code, summary=summary, analysis_sha256=su.sha(OUT / 'csv_analysis.json'))
    except Exception as error:
        terminal['error'] = str(error)
    try:
        su.verify_pins(contract['pins'])
        su.verify_pins(gate['pins'])
        su.verify_pins(su.read(su.REFERENCE / 'input_pins.json'))
        su.require(su.check_image() == image, 'Post-run image drift')
        su.require(su.sha(OUT / 'budget_preflight.json') == su.read(OUT / 'worker.json')['budget_preflight_sha256'],
                   'Budget contract changed')
        terminal['post_hashes'] = 'ALL_PRE_RUN_PINS_AND_IMAGE_UNCHANGED'
    except Exception as error:
        passed = False
        terminal['post_hash_error'] = str(error)
    terminal.update(status='CANDIDATE02_EXTENDED8_PASS' if passed else 'CANDIDATE02_EXTENDED8_NOT_PASS',
                    elapsed_s=time.monotonic()-started, elf_sha256=contract['elf_sha256'],
                    image_sha256=contract['image_sha256'])
    su.save(OUT / 'complete.json', terminal)
    return int(not passed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['preflight', 'worker'])
    parser.add_argument('--authorize-run', action='store_true')
    args = parser.parse_args()
    if args.action == 'preflight':
        preflight()
    else:
        sys.exit(worker(args.authorize_run))
