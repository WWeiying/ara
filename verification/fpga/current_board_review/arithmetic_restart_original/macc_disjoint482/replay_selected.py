#!/usr/bin/env python3
"""Exact two MACC source selections; parent-only launch after fixed2 releases."""
import argparse
import csv
import importlib.util
import io
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent.parent
sys.path.insert(0, str(REVIEW / 'fp_comparison_original'))
import replay_restart_units as shared

read, save, sha, require = shared.read, shared.save, shared.sha, shared.old.require
PLAN, RUN = HERE / 'candidate04_plan01', HERE / 'candidate04_run01'
UNIT = 'ara-macc-boundary-candidate04-01.service'
FIXED = REVIEW / 'fixed_restart_original'
FIXED_UNIT = 'ara-fixed-boundary-candidate04-01.service'
FIXED_PLAN_SHA = '9a31f50d44c245bc7439db5a462bac3eed54c2eecae74ffeae5931d3ea6995f0'
FIXED_CHECKER_SHA = '8e005917ec3742853e823189aa54774dd5965ab82c6ed7ae218fff84cef339c1'
require(sha(FIXED / 'replay_selected.py') == FIXED_CHECKER_SHA, 'Reviewed fixed checker changed')
spec = importlib.util.spec_from_file_location('immutable_fixed_terminal_checker', FIXED / 'replay_selected.py')
fixed_checker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixed_checker
spec.loader.exec_module(fixed_checker)
NAMES = {'macc_e8_m4_single481', 'macc_e8_m4_pair480_481'}
QUOTAS = dict(whole=6, nf7=2, nf8=8, prefix5=2, fp=2, fpmerge=1, macc=2)
UNITS = dict(whole='ara-whole1134-candidate04-01.service', nf7='ara-indexed-nf7-candidate02-06.service',
    nf8='ara-nf8-full192-candidate04-01.service', prefix5='ara-arithmetic-prefix5-candidate04-01.service',
    fp='ara-fp-original-restart-candidate04-02.service', fpmerge='ara-fp-merge195-candidate04-01.service',
    macc=UNIT, fixed=FIXED_UNIT)
SIGNALS = shared.SIGNALS
BAD = re.compile(shared.prior.BAD.pattern + r'|\bRVV_\w*FAIL\w*\b|MACC_\w*FAIL|UNSUPPORTED|\b[Ff][Aa][Tt][Aa][Ll]\b')


class AbortLatch(shared.AbortLatch):
    def publish(self, path, record, eligible):
        require(threading.current_thread() is threading.main_thread() and len(threading.enumerate()) == 1,
                'Publication requires joined workers and main thread')
        good, bad = path.with_suffix('.pass.tmp'), path.with_suffix('.notpass.tmp')
        save(good, dict(record, status='PASS_2_MACC_SOURCE_SELECTIONS_M4', aborted=False))
        save(bad, dict(record, status='NOT_PASS', aborted=True))
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            with self.lock:
                require(self.terminal is None, 'Terminal publication is single-use')
                passed = eligible and not self.is_set() and not (signal.sigpending() & SIGNALS)
                os.replace(good if passed else bad, path)
                self.terminal = passed
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            good.unlink(missing_ok=True); bad.unlink(missing_ok=True)
        return passed


def resource_math(live, available, units):
    require(units == UNITS, 'Exact coordinated units required, including current FP-merge')
    counts = {k: 0 for k in units}; unknown = []
    for process in live:
        parts = {p for line in process['cgroup'].splitlines() for p in line.split('/')}
        owners = [k for k, unit in units.items() if unit in parts]
        require(len(owners) <= 1, 'Ambiguous ownership')
        if owners: counts[owners[0]] += 1
        else: unknown.append(process)
    require(counts['fixed'] == 0, 'Fixed2 has not released; do not add MACC2 beside it')
    total = sum(max(QUOTAS[k], counts[k]) for k in QUOTAS) + len(unknown)
    require(counts['macc'] <= 2 and total <= 24 and available >= 32 * 1024**3, 'Resource gate failed; no retry')
    return dict(counts=counts, unknown=unknown, reservations=QUOTAS, total_live_plus_reserved=total,
                mem_available_bytes=available, cap=24, fixed_reservation_replaced=True, time=time.time())


def resources(units):
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                         if x.startswith('MemAvailable:'))) * 1024
    return resource_math(shared.scan_simv(), available, units)


def strict_console(entry, text):
    lines = [s.strip() for s in text.splitlines()]
    return (not BAD.search(text) and
        all(lines.count(m) == 1 for m in ['BOARD_CASE_BEGIN ' + entry['cases'][0], *entry['pass_markers']]) and
        len(re.findall(r'^RVV_MATRIX_PASS\b', text, re.M)) == 1 and
        re.findall(r'MACC_ORIGINAL_TRIAL index=(\d+)', text) == [str(x['trial']) for x in entry['contexts']] and
        text.count('Core Test *** SUCCESS *** (tohost = 0)') == 1 and '$finish' in text)


def check_trace(entry, path):
    sequence = entry['helper']; pcs = {x['pc'] for x in sequence}
    regs = [0] * 32
    calls, active, index, retired, last = [], None, 0, 0, -1
    with path.open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle']); require(cycle >= last, 'Nonmonotonic trace'); last = cycle
            if row['event'] != 'retire': continue
            require(int(row['trap'], 0) == 0 and int(row['order']) == retired, 'Trap/missing retire row')
            retired += 1
            pc, insn = int(row['pc'], 16), int(row['insn'], 16)
            rd, value = int(row['rd']), int(row['rd_wdata'], 16)
            if pc == sequence[0]['pc']:
                require(active is None and len(calls) < len(entry['contexts']), 'Unexpected helper call')
                expected = entry['contexts'][len(calls)]
                require([regs[i] for i in range(10, 18)] ==
                        [*entry['operand_addresses'][:3], 512, 512, entry['operand_addresses'][3], expected['vstart'], 0],
                        'Original operands/VL/start/rm pointers or context changed')
                active, index = dict(original_trial=expected['trial'], begin_cycle=cycle), 0
            if active is not None:
                require(pc == sequence[index]['pc'] and insn == sequence[index]['insn'], 'Original13 helper sequence changed')
                if index in (0, 5, 10): require(rd == 5 and value == 512, 'Helper VL is not512')
                if index == 6: require(rd == 28 and value == 0, 'Original b[0] scalar load changed')
                if index in (7, 8): require(regs[16] == expected['vstart'], 'vstart setup changed')
                if index == 8: active.update(target_cycle=cycle, vl=regs[13], vstart=regs[16], rm=regs[17])
                if index == 9:
                    require(rd == 10 and value == 0, 'Returned full vstart is not zero')
                    active['returned_vstart'] = value
                index += 1
                if index == len(sequence):
                    active['end_cycle'] = cycle; calls.append(active); active = None
            else: require(pc not in pcs, 'Helper entered in middle')
            if rd: regs[rd] = value
    require(active is None and retired and len(calls) == entry['configurations'], 'Incomplete/wrong target count')
    return dict(retired=retired, last_cycle=last, target_count=len(calls), contexts=calls)


def fixed_disposition(review):
    require(review['fixed_disposition'] in ('ACCEPTED_PASS', 'FAILURE_HOLD') and
            review.get('fixed_terminal_parent_reviewed') is True, 'Explicit parent fixed-terminal decision required')
    require(review['fixed_plan_sha256'] == FIXED_PLAN_SHA and review['units'] == UNITS,
            'Wrong predecessor/units')
    if review['fixed_disposition'] == 'FAILURE_HOLD':
        require(bool(review.get('fixed_failure_reason', '').strip()), 'Failure hold requires an explicit reason')
    return review['fixed_disposition']


def fixed_gate(review):
    disposition = fixed_disposition(review)
    plan_path = FIXED / 'candidate04_plan01/plan.json'
    require(sha(plan_path) == FIXED_PLAN_SHA, 'Fixed plan drift')
    plan = read(plan_path); root = Path(plan['output'])
    require(root == FIXED / 'candidate04_run01' and plan['unit'] == FIXED_UNIT, 'Wrong fixed run')
    evidence = review['fixed_evidence']
    mandatory = {'launch', 'complete'} if disposition == 'ACCEPTED_PASS' else {'launch'}
    require(set(evidence) == mandatory, 'Exact predecessor evidence set required')
    records = {}; digests = {}
    for key, value in evidence.items():
        path = root / (key + '.json')
        require(value['path'] == str(path) and sha(path) == value['sha256'], 'Wrong/drifted fixed evidence')
        records[key] = read(path); digests[str(path)] = value['sha256']
    require(records['launch']['plan_sha256'] == FIXED_PLAN_SHA, 'No authenticated fixed launch')
    if disposition == 'ACCEPTED_PASS':
        done, meta, rows = records['complete'], read(root / 'replay/run.json'), read(root / 'replay/summary.json')
        require(done['status'] == 'PASS_2_FIXED_SOURCE_SELECTIONS_M4' and done['aborted'] is False and
                done['pins_unchanged'] is True and done['plan_sha256'] == FIXED_PLAN_SHA and
                done['image_sha256'] == shared.prior.IMAGE_SHA and done['finished'] > 0,
                'Fixed data not accepted terminal PASS')
        require(meta['status'] == 'COMPLETE' and meta['status_counts'] == {'PASS': 2} and
                set(meta['tests']) == fixed_checker.NAMES and len(meta['tests']) == 2 and
                meta['simv'] == read(shared.prior.IMAGE / 'image.json')['simv'], 'Fixed runner not complete/exact image')
        for summary in (rows, done['results']):
            require(len(summary) == 2 and {r['name'] for r in summary} == fixed_checker.NAMES and
                    all(r['status'] == 'PASS' and r['returncode'] == 0 for r in summary), 'Fixed results incomplete')
        shared.verify(plan['pins'])
        for name, entry in plan['cases'].items():
            folder = root / 'replay/tests' / name
            require(all(Path(next(r for r in summary if r['name'] == name)['artifact_dir']) == folder
                        for summary in (rows, done['results'])), 'Fixed artifact path differs')
            require(sha(folder / 'input.elf') == entry['sha256'], 'Fixed private ELF drift')
            inputs = read(folder / 'inputs.json'); ledger = read(shared.prior.IMAGE / 'image.json')
            require(inputs['binary'] == dict(source=entry['path'], path=str(folder / 'input.elf'), sha256=entry['sha256']) and
                    inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Fixed actual input/image differs')
            command = read(folder / 'command.json')['command']
            require([x for x in command if x.startswith('+PRELOAD=')] == ['+PRELOAD=' + str(folder / 'input.elf')], 'Wrong fixed preload')
            require(fixed_checker.strict_console(entry, (folder / 'console.log').read_text()), 'Fixed raw oracle failed')
            runlog = folder / 'work/run.vcs.log'
            if runlog.exists(): require(not BAD.search(runlog.read_text()), 'Fixed secondary raw log failed')
            audit = fixed_checker.check_trace(entry, folder / 'commit_trace.csv')
            require(audit == read(folder / 'fixed_trace_audit.json') == done['audits'][name], 'Fixed actual CSV differs')
            for file in ('console.log', 'commit_trace.csv', 'input.elf', 'fixed_trace_audit.json', 'inputs.json', 'command.json'):
                digests[str(folder / file)] = sha(folder / file)
            if runlog.exists(): digests[str(runlog)] = sha(runlog)
        require(done['runner_sha256'] == sha(root / 'replay/run.json'), 'Fixed runner record drift')
        for file in ('run.json', 'summary.json'): digests[str(root / 'replay' / file)] = sha(root / 'replay' / file)
    # Missing unit alone never releases slots: authenticated launch + parent
    # disposition above precede these independent service/process/cgroup checks.
    service = shared.dependency.query_unit(FIXED_UNIT)
    absent = shared.dependency.absence([FIXED_UNIT])
    return dict(disposition=disposition, data_accepted=disposition == 'ACCEPTED_PASS',
                service=service, absence=absent, evidence_sha256=digests,
                failure_reason=review.get('fixed_failure_reason', ''))


def own_service():
    require(UNIT in {p for line in Path('/proc/self/cgroup').read_text().splitlines() for p in line.split('/')},
            'Wrong actual MACC service cgroup')
    fields = {'Id', 'KillMode', 'RuntimeMaxUSec'}
    result = subprocess.run(['systemctl', '--user', 'show', UNIT, '--property=' + ','.join(sorted(fields)), '--no-pager'],
        text=True, capture_output=True, timeout=5, check=False, env=shared.dependency.bus_environment())
    props = dict(line.split('=', 1) for line in result.stdout.splitlines())
    require(result.returncode == 0 and not result.stderr.strip() and set(props) == fields and props['Id'] == UNIT and
            props['KillMode'] == 'control-group' and props['RuntimeMaxUSec'] in ('2h 10min', '7800s'),
            'Service must enforce RuntimeMaxSec7800 and KillModecontrol-group')
    return props


def execute(plan, out, abort, dry=False):
    ledger, repo, (parent, options, case, _), engine = shared.old.identity()
    entries = plan['cases']
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + '|' + BAD.pattern, engine.FAIL_RE.flags)
    class Checked(parent):
        def __init__(self, *args):
            super().__init__(*args); self.cancel_event = abort
        def _run_test(self, test, image):
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                if not dry and not abort.is_set():
                    save(out.parent / 'admission' / (test.name + '.json'), resources(UNITS))
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    entry = entries[test.name]; folder = result.artifact_dir
                    require(result.returncode == 0 and strict_console(entry, (folder / 'console.log').read_text()), 'Raw oracle/exit veto')
                    require(sha(folder / 'input.elf') == entry['sha256'], 'Private ELF differs')
                    inputs = read(folder / 'inputs.json')
                    require(inputs['binary'] == dict(source=entry['path'], path=str(folder / 'input.elf'), sha256=entry['sha256']) and
                            inputs['simv'] == dict(path=ledger['simv'], image_sha256=ledger['files']), 'Actual input/image differs')
                    command = read(folder / 'command.json')['command']
                    require([x for x in command if x.startswith('+PRELOAD=')] == ['+PRELOAD=' + str(folder / 'input.elf')], 'Wrong preload')
                    save(folder / 'macc_trace_audit.json', check_trace(entry, folder / 'commit_trace.csv'))
                elif result.status != 'DRY_RUN': abort.set()
                return abort.accept(result)
            except BaseException:
                abort.set(); raise
            finally: signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    tests = [case(name, 'app', '', Path(entry['path']), name, 7200) for name, entry in entries.items()]
    opts = options(repo, out, 'default', 2, 1, dry, False, True, Path(ledger['simv']), True, None)
    return Checked(opts, tests, sys.argv).run()


def terminal(results, out):
    meta, summary = read(out / 'run.json'), read(out / 'summary.json')
    require(meta['status'] == 'COMPLETE' and meta['status_counts'] == {'PASS': 2} and
            len(meta['tests']) == 2 and set(meta['tests']) == NAMES, 'Not COMPLETE/exact2 PASS')
    require(len(results) == len(summary) == 2 and {r.name for r in results} == {r['name'] for r in summary} == NAMES, 'Wrong membership')
    for result in results:
        row = next(r for r in summary if r['name'] == result.name)
        require(result.status == row['status'] == 'PASS' and result.returncode == row['returncode'] == 0 and
                str(result.artifact_dir) == row['artifact_dir'], 'Result/summary disagreement')


def entries():
    source = HERE / 'selected01'; data = read(source / 'soc/programs.json')['programs']
    require(set(data) == NAMES, 'Only exact selected2 allowed')
    for name, entry in data.items():
        entry['contexts'] = read(source / name / 'scope.json')['selected_original_calls']
        symbols = read(source / name / 'soc/symbols.json')
        entry['operand_addresses'] = [symbols['a'], symbols['b'], symbols['out'] + 1, symbols['mask']]
        body = (source / name / 'soc/program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        entry['helper'] = [dict(pc=int(m[1], 16), insn=int(m[2], 16)) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s', body, re.M)]
        require(len(entry['helper']) == 13 and entry['helper'][8]['insn'] == 0xb5042c57, 'Original helper layout')
    return data


def prepare():
    require(not PLAN.exists(), 'Fresh plan required')
    source = HERE / 'selected01'; pins = read(source / 'pins.json'); shared.verify(pins)
    data = entries(); ledger, *_ = shared.old.identity()
    for path, digest in read(shared.PLAN / 'plan.json')['pins'].items():
        if Path(path).is_relative_to(Path(ledger['snapshot'])) or Path(path).is_relative_to(shared.prior.IMAGE): pins[path] = digest
    import unittest
    import test_replay_selected as tests
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
    PLAN.mkdir(); (PLAN / 'host_tests.log').write_text(log.getvalue())
    save(PLAN / 'host_gate.json', dict(status='PASS' if result.wasSuccessful() else 'FAIL', count=result.testsRun,
                                    log_sha256=sha(PLAN / 'host_tests.log')))
    require(result.wasSuccessful(), 'Host gate failed; preserve this plan')
    pins.update(shared.local_modules())
    for path in (PLAN / 'host_tests.log', PLAN / 'host_gate.json', source / 'pins.json', source / 'complete.json',
                 source / 'soc/programs.json', FIXED / 'candidate04_plan01/plan.json'):
        pins[str(path)] = sha(path)
    plan = dict(status='PREPARED_NOT_AUTHORIZED', cases=data, pins=pins, image=str(shared.prior.IMAGE),
        image_sha256=shared.prior.IMAGE_SHA, jobs=2, timeout_s=7200, outer_s=7800, unit=UNIT, output=str(RUN),
        no_build=True, stop_first_fail=True, retries=0, original_prefix482_acceptance=False,
        reservations=QUOTAS, units=UNITS, predecessor_fixed_plan_sha256=FIXED_PLAN_SHA,
        release_contract='Fixed actual terminal + strict accepted data OR explicit parent failure-hold; replace fixed2 with macc2',
        reference_costs=read(source / 'costs.json')['rows'])
    save(PLAN / 'plan.json', plan)
    abort = AbortLatch()
    with abort.signals(): rows = execute(plan, PLAN / 'dryrun', abort, True)
    require(not abort.is_set() and len(rows) == 2 and {r.name for r in rows} == NAMES and
            all(r.status == 'DRY_RUN' for r in rows), 'Dry-run differs')
    shared.verify(pins); shared.module_gate(pins)
    save(PLAN / 'review.template.json', dict(parent_authorized=False, plan_sha256=sha(PLAN / 'plan.json'),
        image_sha256=shared.prior.IMAGE_SHA, units=UNITS, fixed_terminal_parent_reviewed=False,
        fixed_plan_sha256=FIXED_PLAN_SHA, fixed_disposition='PENDING', fixed_failure_reason='',
        fixed_evidence={}, fpmerge_unit_parent_confirmed=False))
    save(PLAN / 'preflight.json', dict(status='READY_NOT_LAUNCHED_WAIT_PARENT_FIXED_TERMINAL',
        plan_sha256=sha(PLAN / 'plan.json'), pins_unchanged=True, pin_count=len(pins), host_tests=result.testsRun,
        dryrun_names=sorted(NAMES), dryrun_summary_sha256=sha(PLAN / 'dryrun/summary.json'),
        admission_checked=False, fixed_terminal_checked=False, DUT_started=False))
    print('READY_NOT_LAUNCHED', sha(PLAN / 'plan.json'))


def work(approved, review_path, review_hash, authorize):
    require(sys.flags.optimize == 0 and authorize and approved == sha(PLAN / 'plan.json'), 'Explicit approved plan required')
    require(review_path is not None and sha(review_path) == review_hash and not RUN.exists(), 'Pinned review/fresh output required')
    plan, review = read(PLAN / 'plan.json'), read(review_path)
    require(review['parent_authorized'] is True and review['fpmerge_unit_parent_confirmed'] is True and
            review['plan_sha256'] == approved and review['image_sha256'] == shared.prior.IMAGE_SHA and
            review['units'] == UNITS, 'Wrong approval/units')
    require(set(plan['cases']) == NAMES and plan['jobs'] == 2 and plan['timeout_s'] == 7200 and
            plan['outer_s'] == 7800 and plan['no_build'] and plan['retries'] == 0, 'Execution contract changed')
    abort = AbortLatch()
    with abort.signals():
        service = own_service()
        RUN.mkdir(); (RUN / 'admission').mkdir()
        save(RUN / 'attempt.json', dict(plan_sha256=approved, review_sha256=review_hash, service=service, time=time.time()))
        record = dict(plan_sha256=approved, image_sha256=shared.prior.IMAGE_SHA, original_prefix482_acceptance=False)
        eligible = False
        try:
            shared.verify(plan['pins']); shared.old.identity(); shared.module_gate(plan['pins'])
            predecessor = fixed_gate(review)
            admission = resources(UNITS)
            require(admission['counts']['macc'] == 0 and not abort.is_set(), 'Own simulation already live/aborted')
            save(RUN / 'launch.json', dict(plan_sha256=approved, review_sha256=review_hash,
                 predecessor=predecessor, admission=admission, time=time.time()))
            results = execute(plan, RUN / 'replay', abort)
            record['results'] = [dict(name=r.name, status=r.status, returncode=r.returncode, elapsed_s=r.elapsed_s,
                                      artifact_dir=str(r.artifact_dir), reason=r.reason) for r in results]
            terminal(results, RUN / 'replay')
            shared.verify(plan['pins']); shared.verify(predecessor['evidence_sha256']); shared.old.identity(); shared.module_gate(plan['pins'])
            require(sha(PLAN / 'plan.json') == approved and sha(review_path) == review_hash, 'Approval drift')
            record.update(pins_unchanged=True, runner_sha256=sha(RUN / 'replay/run.json'),
                audits={r.name: read(r.artifact_dir / 'macc_trace_audit.json') for r in results},
                raw_pins={str(r.artifact_dir / n): sha(r.artifact_dir / n) for r in results
                          for n in ('console.log', 'commit_trace.csv', 'input.elf', 'inputs.json', 'command.json', 'macc_trace_audit.json')})
            eligible = True
        except BaseException as error:
            abort.set(); record['error'] = f'{type(error).__name__}: {error}'
        record['finished'] = time.time()
        return int(not abort.publish(RUN / 'complete.json', record, eligible))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare', 'work'])
    parser.add_argument('--authorize-run', action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    env = shared.prior.shared.environment(); os.environ.clear(); os.environ.update(env)
    if args.mode == 'prepare': prepare()
    else: raise SystemExit(work(args.approved_plan_sha256, args.review, args.review_sha256, args.authorize_run))
