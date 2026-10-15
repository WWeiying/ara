#!/usr/bin/env python3
"""Offline-only recovery. Never invoke a simulator or write prior evidence."""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import traceback
sys.dont_write_bytecode = True
import checker as c
import fatal_contract as fatal

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'segment_full144_vcs_m8_plan01'
RUN = OLD/'prepared02'
ROOT = RUN/'replay'/c.NAME
PLAN_SHA = '1c349adc821b8fb4d1076674e267baa16bdc128b32cc9338bb77ac259ecb616f'
sha, require, read = c.m.sha, c.require, c.read
module = importlib.util.spec_from_file_location('sealed_segment_replay', OLD/'replay.py')
r = importlib.util.module_from_spec(module)
module.loader.exec_module(r)

def save(path, value):
    with Path(path).open('x') as fp:
        json.dump(value, fp, indent=2); fp.write('\n'); fp.flush(); os.fsync(fp.fileno())

def bindings(out):
    require(sha(RUN/'plan.json') == PLAN_SHA, 'Original plan drift')
    plan = read(RUN/'plan.json')
    require(plan['spec'] == c.specification(), 'Original source/spec drift')
    require(read(RUN/'complete.json')['status'] == 'NOT_PASS', 'Original failure record changed')
    require(read(ROOT/'audit_wait.json')['returncode'] == 1 and
            "KeyError: 'replay_mismatch'" in (ROOT/'audit.log').read_text(), 'Original checker error identity')
    outcome = read(ROOT/'child_outcome.unvalidated.json')
    monitor = read(ROOT/'monitor_numeric.unvalidated.json')
    require(type(outcome['returncode']) is int and outcome['returncode'] == monitor['returncode'] == 0 and
            not outcome['timed_out'] and not outcome['failure_seen'] and not outcome['aborted'],
            'No completed genuine simulator receipt')
    ledger, repo, _ = r.common.image_context(Path(plan['image']))
    r.metadata(ROOT, plan, ledger)
    pins = dict(plan['pins'])
    for path in (RUN/'plan.json', RUN/'complete.json', RUN/'launch.json',
                 ROOT/'audit_wait.json', ROOT/'audit.log', ROOT/'child_outcome.unvalidated.json',
                 ROOT/'monitor_numeric.unvalidated.json', ROOT/'command.json', ROOT/'inputs.json',
                 ROOT/'console.log', ROOT/'commit_trace.csv', ROOT/'input.elf', ROOT/'work/run.vcs.log',
                 fatal.NM.resolve(), fatal.OBJDUMP.resolve(), Path(sys.executable).resolve()):
        pins[str(path)] = sha(path)
    for path in HERE.glob('*.py'): pins[str(path)] = sha(path)
    for item in list(sys.modules.values()):
        path = getattr(item, '__file__', None)
        if path and Path(path).is_file() and ('/openproject/' in path or '/fpga_runs/' in path):
            pins[str(Path(path).resolve())] = sha(path)
    r.verify(plan['pins']); r.verify(pins)
    save(out/'input_pins.json', pins)
    facts = fatal.inspect(plan['spec'])
    fatal_pcs = fatal.validate(plan['spec'], facts)
    save(out/'symbol_contract.json', dict(actual_symbols=facts['symbols'],
        absent_optional_replay_mismatch='replay_mismatch' not in facts['symbols'],
        fatal_pcs=sorted(fatal_pcs), actual_nm=facts['nm'],
        source_elf_sha256=plan['spec']['elf_sha256'], same_private_elf=True,
        old_plan_sha256=PLAN_SHA, no_synthetic_symbol=True))
    return plan, ledger, pins

def audit(out):
    plan, ledger, pins = bindings(out)
    host = read(HERE/'host01/wait.json')
    require(host['returncode'] == 0 and not host['timeout'], 'Required focused Host did not pass')
    for path, value in host['script_pins'].items(): require(sha(path) == value, 'Host code drift')
    save(out/'host_binding.json', {str(HERE/'host01/wait.json'): sha(HERE/'host01/wait.json'),
                                 str(HERE/'host01/output.log'): sha(HERE/'host01/output.log')})
    # One strict traversal. The unchanged generic validator subsequently checks
    # transport/architecture lifecycle; it is not a second numerical audit.
    observer = c.Checker(plan['spec'])
    try:
        with (ROOT/'commit_trace.csv').open() as fp:
            rows = csv.DictReader(fp)
            require(rows.fieldnames == c.FIELDS, 'Original CSV schema')
            for row in rows: observer.row(row)
        strict = observer.finish()
        strict['backend_coverage'] = observer.backend_coverage()
    except BaseException as error:
        save(out/'first_error.json', dict(error=repr(error), rows=observer.rows,
            retired=observer.retired, cycle=observer.cycle, current_case=observer.current,
            last_pc=observer.last_pc, current_row=locals().get('row'),
            numerical_completed=observer.numerical, capability_completed=observer.capabilities,
            data_error_not_waived=True))
        raise
    from ara_verify.trace import validate_trace
    generic = validate_trace(ROOT/'commit_trace.csv')
    require((strict['rows'], strict['retired'], strict['last_cycle']) ==
            (generic['rows'], generic['retire_count'], generic['last_cycle']), 'Strict/generic identity')
    require(generic['cvx_exception_count'] == strict['capability'] and
            generic['backend_uop_alloc_count'] == generic['backend_uop_done_count'] > 0,
            'Whole CVX/uop protocol')
    outcome = read(ROOT/'child_outcome.unvalidated.json')
    r.outcome_gate(outcome, strict['source_exit'])
    for path in (ROOT/'console.log', ROOT/'work/run.vcs.log'):
        c.protocol(path.read_text(), strict['source_exit'])
    r.metadata(ROOT, plan, ledger)
    r.verify(pins)
    save(out/'result.json', dict(status=strict['status'], strict=strict, generic=generic,
         source_exit=strict['source_exit'], actual_simulator_rc=outcome['returncode'],
         simulator_elapsed_s=outcome['elapsed_s'], pins_unchanged=True,
         evidence_pins_sha256=sha(out/'input_pins.json'), old_NOT_PASS_preserved=True,
         strict_csv_traversals=1, unchanged_generic_traversals=1,
         new_DUT_runs=0, RTL_changed=False, independent_agent_audit=False,
         linux_clone_COW_equivalence=False))

def main():
    p = argparse.ArgumentParser(); p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    require(args.out.resolve().parent == HERE and args.out.is_dir(), 'Only new owned output')
    start = time.monotonic()
    try:
        audit(args.out)
        save(args.out/'executor.json', dict(status='CHECKER_COMPLETED', elapsed_s=time.monotonic()-start))
        return 0
    except BaseException as error:
        traceback.print_exc()
        save(args.out/'failure.json', dict(status='NOT_ACCEPTED', error=repr(error),
             elapsed_s=time.monotonic()-start, retries=0, DUT_runs=0))
        return 1

if __name__ == '__main__': raise SystemExit(main())
