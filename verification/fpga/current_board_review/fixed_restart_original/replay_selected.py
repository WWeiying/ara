#!/usr/bin/env python3
"""Two authenticated fixed-point boundary selections on the existing M4 image."""
import argparse
import csv
import json
import os
from pathlib import Path
import re
import signal
import sys
import threading
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'fp_comparison_original'))
import replay_restart_units as shared

read, save, sha, require = shared.read, shared.save, shared.sha, shared.old.require
PLAN, RUN = HERE / 'candidate04_plan01', HERE / 'candidate04_run01'
UNIT = 'ara-fixed-boundary-candidate04-01.service'
NAMES = {'fixed_e8_m4_single776', 'fixed_e8_m4_pair775_776'}
QUOTAS = dict(whole=6, nf7=2, nf8=8, prefix5=2, fp=2, fpmerge=1, fixed=2)
SIGNALS = shared.SIGNALS


class AbortLatch(shared.AbortLatch):
    def publish(self, path, record, eligible):
        # Same reviewed07 snapshot decision, only the terminal status is scoped.
        require(threading.current_thread() is threading.main_thread() and
                len(threading.enumerate()) == 1, 'Publication requires joined workers and main thread')
        good = dict(record, status='PASS_2_FIXED_SOURCE_SELECTIONS_M4', aborted=False)
        bad = dict(record, status='NOT_PASS', aborted=True)
        good_path, bad_path = path.with_suffix('.pass.tmp'), path.with_suffix('.notpass.tmp')
        save(good_path, good)
        save(bad_path, bad)
        previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
        try:
            with self.lock:
                require(self.terminal is None, 'Terminal publication is single-use')
                passed = eligible and not self.is_set() and not (signal.sigpending() & SIGNALS)
                os.replace(good_path if passed else bad_path, path)
                self.terminal = passed
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous)
            good_path.unlink(missing_ok=True)
            bad_path.unlink(missing_ok=True)
        return passed


def resource_math(live, available, units):
    require(set(units) == set(QUOTAS) and len(set(units.values())) == 7, 'Seven distinct reservation owners required')
    require(all(re.fullmatch(r'ara-[A-Za-z0-9_-]+\.service', u) for u in units.values()), 'Invalid unit')
    counts = {k: 0 for k in units}
    unknown = []
    for process in live:
        parts = {p for line in process['cgroup'].splitlines() for p in line.split('/')}
        owners = [k for k, unit in units.items() if unit in parts]
        require(len(owners) <= 1, 'Ambiguous ownership')
        if owners: counts[owners[0]] += 1
        else: unknown.append(process)
    total = sum(max(QUOTAS[k], counts[k]) for k in units) + len(unknown)
    require(counts['fixed'] <= 2 and total <= 24 and available >= 32 * 1024**3, 'Resource gate failed, no retry')
    return dict(counts=counts, unknown=unknown, reservations=QUOTAS, total_live_plus_reserved=total,
                mem_available_bytes=available, cap=24, time=time.time())


def resources(units):
    available = int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines()
                         if x.startswith('MemAvailable:'))) * 1024
    return resource_math(shared.scan_simv(), available, units)


def strict_console(entry, text):
    lines = [s.strip() for s in text.splitlines()]
    return (not shared.prior.BAD.search(text) and
        not re.search(r'RVV_MATRIX_FAILED|FIXED_\w*FAIL', text) and
        all(lines.count(marker) == 1 for marker in entry['pass_markers']) and
        len(re.findall(r'^RVV_MATRIX_PASS\b', text, re.M)) == 1 and
        re.findall(r'FIXED_ORIGINAL_TRIAL index=(\d+)', text) == [str(x['trial']) for x in entry['contexts']] and
        'Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish' in text)


def check_trace(entry, path):
    sequence = entry['helper']
    pcs = {x['pc'] for x in sequence}
    regs = [0] * 32
    calls, active, index, retired, last = [], None, 0, 0, -1
    with path.open() as stream:
        for row in csv.DictReader(stream):
            cycle = int(row['cycle'])
            require(cycle >= last, 'Nonmonotonic trace')
            last = cycle
            if row['event'] != 'retire': continue
            require(int(row['trap'], 0) == 0 and int(row['order']) == retired, 'Trap or missing retire row')
            retired += 1
            pc, insn = int(row['pc'], 16), int(row['insn'], 16)
            rd, value = int(row['rd']), int(row['rd_wdata'], 16)
            if pc == sequence[0]['pc']:
                require(active is None and len(calls) < len(entry['contexts']), 'Unexpected extra helper call')
                expected = entry['contexts'][len(calls)]
                active, index = dict(original_trial=expected['trial'], begin_cycle=cycle), 0
            if active is not None:
                require(pc == sequence[index]['pc'] and insn == sequence[index]['insn'], 'Original helper retirement sequence changed')
                if index in (0, 5, 21): require(value == 512 and rd == 5, 'Helper VL is not512')
                if index == 7: require(regs[16] == expected['vstart'], 'vstart setup differs')
                if index == 8: active['saved_vxrm'] = value
                if index == 9: active['saved_vxsat'] = value
                if index == 11: require(regs[7] == expected['vxrm'], 'vxrm setup differs')
                if index == 13: require(regs[7] == expected['initial_vxsat'], 'sticky vxsat setup differs')
                if index == 14:
                    require([regs[x] for x in (13,14,16,17)] ==
                            [512,512,expected['vstart'],expected['control']], 'Target argument context differs')
                    active.update(target_cycle=cycle, vstart=regs[16], control=regs[17], vl=regs[13])
                if index == 15: require(rd == 10 and value == 0, 'Returned vstart is not zero')
                if index == 16:
                    require(rd == 6 and value == expected['expected_vxsat'], 'Returned vxsat differs')
                    active['returned_vxsat'] = value
                if index == 19: require(regs[29] == active['saved_vxrm'], 'vxrm restore differs')
                if index == 20: require(regs[30] == active['saved_vxsat'], 'vxsat restore differs')
                index += 1
                if index == len(sequence):
                    active['end_cycle'] = cycle
                    calls.append(active)
                    active = None
            else:
                require(pc not in pcs, 'Helper entered in the middle')
            if rd: regs[rd] = value
    require(active is None and retired and len(calls) == entry['configurations'], 'Incomplete/wrong target count')
    return dict(retired=retired, last_cycle=last, target_count=len(calls), contexts=calls)


def execute(plan, out, abort, dry=False, units=None):
    ledger, repo, (parent, options, case, _), engine = shared.old.identity()
    entries = plan['cases']
    engine.FAIL_RE = re.compile(engine.FAIL_RE.pattern + '|' + shared.prior.BAD.pattern + r'|RVV_MATRIX_FAILED|FIXED_\w*FAIL', engine.FAIL_RE.flags)
    class Checked(parent):
        def __init__(self, *args):
            super().__init__(*args)
            self.cancel_event = abort
        def _run_test(self, test, image):
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, SIGNALS)
            try:
                if not dry and not abort.is_set(): save(out.parent / 'admission' / (test.name + '.json'), resources(units))
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    entry = entries[test.name]
                    require(result.returncode == 0 and strict_console(entry, (result.artifact_dir / 'console.log').read_text()), 'Original raw oracle/rc veto')
                    require(sha(result.artifact_dir / 'input.elf') == entry['sha256'], 'Private ELF differs')
                    command = read(result.artifact_dir / 'command.json')['command']
                    require([x for x in command if x.startswith('+PRELOAD=')] ==
                            ['+PRELOAD=' + str(result.artifact_dir / 'input.elf')], 'Not using exact private ELF')
                    save(result.artifact_dir / 'fixed_trace_audit.json', check_trace(entry, result.artifact_dir / 'commit_trace.csv'))
                elif result.status != 'DRY_RUN': abort.set()
                return abort.accept(result)
            except BaseException:
                abort.set()
                raise
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)
    tests = [case(name, 'app', '', Path(e['path']), name, 1800) for name,e in entries.items()]
    opts = options(repo, out, 'default', 2, 1, dry, False, True, Path(ledger['simv']), True, None)
    return Checked(opts, tests, sys.argv).run()


def terminal(results, out):
    meta, summary = read(out / 'run.json'), read(out / 'summary.json')
    require(meta['status'] == 'COMPLETE' and meta['status_counts'] == {'PASS': 2}, 'Not COMPLETE/exact2 PASS')
    require(len(results) == len(summary) == 2 and {r.name for r in results} == {r['name'] for r in summary} == NAMES, 'Wrong exact membership')
    for result in results:
        row = next(r for r in summary if r['name'] == result.name)
        require(result.status == row['status'] == 'PASS' and result.returncode == row['returncode'] == 0 and
                str(result.artifact_dir) == row['artifact_dir'], 'Terminal result disagreement')


def prepare():
    PLAN.mkdir(exist_ok=False)
    source = HERE / 'selected01'
    pins = read(source / 'pins.json')
    shared.verify(pins)
    entries = read(source / 'soc/programs.json')['programs']
    require(set(entries) == NAMES, 'Only two reviewed source selections')
    # Original RNG fixture: vsmul saturation only occurs for (-128)*(-128).
    x = 0x937ad68de41c725f
    saturating_indices = []
    for i in range(512):
        x ^= (x << 13) & ((1 << 64)-1); x ^= x >> 7; x ^= (x << 17) & ((1 << 64)-1)
        a, b = x & 255, (x >> 19) & 255
        if i % 8 == 0: a = b = 0
        elif i % 8 == 1: a, b = 255, 1
        elif i % 8 == 2: a, b = 128, 255
        elif i % 8 == 3: b = 8
        if a == b == 128: saturating_indices.append(i)
    require(not saturating_indices, 'Review expected final vxsat for this fixture')
    for name, entry in entries.items():
        entry['contexts'] = read(source / name / 'scope.json')['selected_original_calls']
        for context in entry['contexts']: context['expected_vxsat'] = context['initial_vxsat']
        body = (source / name / 'soc/program.dis').read_text().split('<op_0>:\n')[1].split('\n\n')[0]
        entry['helper'] = [dict(pc=int(m[1],16),insn=int(m[2],16)) for m in re.finditer(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s',body,re.M)]
        require(len(entry['helper']) == 24 and entry['helper'][14]['insn'] == 0x9c880c57, 'Original helper layout')
    ledger, *_ = shared.old.identity()
    previous = read(shared.PLAN / 'plan.json')['pins']
    for path,digest in previous.items():
        if Path(path).is_relative_to(Path(ledger['snapshot'])) or Path(path).is_relative_to(shared.prior.IMAGE): pins[path] = digest
    import unittest
    import test_replay_selected
    with (PLAN / 'host_tests.log').open('x') as log:
        result = unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_replay_selected))
    require(result.wasSuccessful(), 'Host gate failed')
    save(PLAN / 'host_gate.json',dict(status='PASS',count=result.testsRun,log_sha256=sha(PLAN / 'host_tests.log')))
    pins.update(shared.local_modules())
    for path in (PLAN / 'host_tests.log',PLAN / 'host_gate.json', source / 'pins.json', source / 'soc/programs.json'):
        pins[str(path)] = sha(path)
    plan = dict(status='PREPARED_NOT_AUTHORIZED',cases=entries,pins=pins,image=str(shared.prior.IMAGE),
        image_sha256=shared.prior.IMAGE_SHA,jobs=2,timeout_s=1800,outer_s=2400,unit=UNIT,output=str(RUN),
        no_build=True,stop_first_fail=True,original_prefix777_acceptance=False,
        final_vxsat_basis=dict(min_times_min_indices=saturating_indices,sticky_preserved=True))
    save(PLAN / 'plan.json',plan)
    abort = AbortLatch()
    with abort.signals(): rows = execute(plan,PLAN / 'dryrun',abort,True)
    require(not abort.is_set() and len(rows)==2 and {r.name for r in rows}==NAMES and
            all(r.status=='DRY_RUN' for r in rows),'Dry-run differs')
    shared.verify(pins); shared.module_gate(pins)
    units = dict(whole='ara-whole1134-candidate04-01.service',nf7='ara-indexed-nf7-candidate02-06.service',
        nf8='ara-nf8-full192-candidate04-01.service',prefix5='ara-arithmetic-prefix5-candidate04-01.service',
        fp='ara-fp-original-restart-candidate04-02.service',fpmerge='ara-fpmerge-original-candidate04-01.service',fixed=UNIT)
    save(PLAN / 'review.template.json',dict(parent_authorized=False,plan_sha256=sha(PLAN / 'plan.json'),
        image_sha256=shared.prior.IMAGE_SHA,units=units,fpmerge_unit_parent_confirmed=False))
    save(PLAN / 'preflight.json',dict(status='READY_NOT_LAUNCHED',plan_sha256=sha(PLAN / 'plan.json'),
        pins_unchanged=True,pin_count=len(pins),DUT_started=False,
        resource_snapshot=resources(units),fpmerge_unit_is_proposed=True))
    print('READY_NOT_LAUNCHED',sha(PLAN / 'plan.json'))


def work(approved, review_path, review_hash, authorize):
    require(sys.flags.optimize == 0 and authorize and approved == sha(PLAN / 'plan.json'), 'Explicit plan approval required')
    require(review_path is not None and sha(review_path)==review_hash and not RUN.exists(), 'Pinned review and fresh output required')
    abort = AbortLatch()
    with abort.signals():
        plan, review = read(PLAN / 'plan.json'), read(review_path)
        require(review['parent_authorized'] is True and review['fpmerge_unit_parent_confirmed'] is True and
                review['plan_sha256']==approved and review['image_sha256']==shared.prior.IMAGE_SHA and
                review['units']['fixed']==UNIT,'Wrong approval/unit')
        require(UNIT in {p for line in Path('/proc/self/cgroup').read_text().splitlines() for p in line.split('/')}, 'Wrong actual service cgroup')
        require(set(plan['cases'])==NAMES and plan['jobs']==2 and plan['timeout_s']==1800 and plan['no_build'], 'Execution contract changed')
        shared.verify(plan['pins']); shared.old.identity(); shared.module_gate(plan['pins'])
        admission = resources(review['units'])
        require(not abort.is_set(), 'Aborted before launch')
        RUN.mkdir(); (RUN / 'admission').mkdir()
        save(RUN / 'launch.json',dict(plan_sha256=approved,review_sha256=review_hash,admission=admission,time=time.time()))
        record = dict(plan_sha256=approved,image_sha256=shared.prior.IMAGE_SHA,original_prefix777_acceptance=False)
        eligible = False
        try:
            results = execute(plan,RUN / 'replay',abort,units=review['units'])
            record['results'] = [dict(name=r.name,status=r.status,returncode=r.returncode,elapsed_s=r.elapsed_s,
                                      artifact_dir=str(r.artifact_dir),reason=r.reason) for r in results]
            terminal(results,RUN / 'replay')
            shared.verify(plan['pins']); shared.old.identity(); shared.module_gate(plan['pins'])
            require(sha(PLAN / 'plan.json')==approved and sha(review_path)==review_hash,'Approval drift')
            record.update(pins_unchanged=True,runner_sha256=sha(RUN / 'replay/run.json'),
                audits={r.name:read(r.artifact_dir / 'fixed_trace_audit.json') for r in results})
            eligible = True
        except BaseException as error:
            abort.set(); record['error'] = f'{type(error).__name__}: {error}'
        record['finished'] = time.time()
        return int(not abort.publish(RUN / 'complete.json',record,eligible))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','work'])
    parser.add_argument('--authorize-run',action='store_true')
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--review',type=Path)
    parser.add_argument('--review-sha256')
    args = parser.parse_args()
    env=shared.prior.shared.environment(); os.environ.clear(); os.environ.update(env)
    if args.mode=='prepare': prepare()
    else: raise SystemExit(work(args.approved_plan_sha256,args.review,args.review_sha256,args.authorize_run))
