#!/usr/bin/env python3
"""M8-only same-input recovery and controls; max3 jobs, no rebuild/retry."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import math
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
G = HERE.parent
spec = importlib.util.spec_from_file_location('m7_controls', G/'memory_candidate07_controls16/regression.py')
m7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m7)
require, read, sha = m7.require, m7.read, m7.sha
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image')
ADDRGEN = 'hardware/src/vlsu/addrgen.sv'
ADDRGEN_SHA = '1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2'
UNIT = 'ara-m8-recovery20-01.service'
STAGES = ('indexed1', 'regression19')
OUTER_S = 6600


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def check_receipt(receipt, budget):
    require(type(receipt.get('returncode')) is int and receipt['returncode'] == 0, 'Actual numeric child rc0 required')
    require(all(receipt.get(k) is False for k in ('timed_out', 'failure_seen', 'abort_set')), 'Child abort/failure/unknown')
    elapsed = receipt.get('elapsed_s')
    require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= budget, 'Child budget')


def check_delta(old, new, relocated=None):
    require(set(old) == set(new) and len(new) == 539, 'Exact 539-source membership')
    changed = {p for p in old if old[p] != new[p]}
    relocated = relocated or {}
    require(changed == {ADDRGEN} | set(relocated), 'M7 to M8 must change only AddrGen plus exact root relocation')
    for name, (before, after, oldroot, newroot) in relocated.items():
        require(name in ('frozen.filelist','hardware/bender') and
                before.replace(oldroot,newroot) == after, 'Non-relocation helper difference')
    require(new[ADDRGEN] == ADDRGEN_SHA, 'Not reviewed indexed alignment guard')


def check_csv_result(kind, result):
    status, checks = {'indexed':('INDEXED_PREFIX_CSV_PASS',966),
                      'load':('MASK_DRAIN_CSV_PASS',914), 'store':('MASK_DRAIN_CSV_PASS',914),
                      'resident':('CSV_FULL_ORACLE_PASS',5215)}[kind]
    require(result.get('status') == status and type(result.get('checks')) is int and
            result['checks'] == checks, 'Checker full-scope result rejected')
    if kind == 'resident':
        require(result.get('rounds') == 50 and result.get('backing_words_read') == 32768 and
                result.get('pte_words_read') == 1536 and result.get('repairs') == 0 and
                result.get('retries') == 0, 'Resident50 memory/PTE/no-fault scope')


def image_context(approved):
    require(approved and sha(IMAGE/'image.json') == approved, 'Exact accepted M8 image digest required')
    m7.base.IMAGE = IMAGE
    ledger, repo, framework = m7.base.image_context()
    require(ledger['configuration_sha256'] == m7.CONFIGURATION_SHA, 'Configuration differs from M7')
    oldledger = read(m7.M7/'image.json')
    require(sha(m7.M7/'image.json') == m7.M7_SHA, 'M7 baseline image drift')
    oldrepo = Path(oldledger['snapshot'])/'sources'
    old = read(Path(oldledger['snapshot'])/'snapshot.json')['files']
    new = read(Path(ledger['snapshot'])/'snapshot.json')['files']
    relocated = {n:((oldrepo/n).read_bytes(),(repo/n).read_bytes(),str(oldrepo).encode(),str(repo).encode())
                 for n in ('frozen.filelist','hardware/bender')}
    check_delta(old, new, relocated)
    return ledger, repo, framework


def scope():
    pins, cases = {}, []
    def pin(path, expected=None):
        digest = sha(path)
        require(expected is None or digest == expected, 'Baseline identity changed: '+str(path))
        pins[str(path)] = digest
    controls = G/'memory_candidate07_controls16/prepared01'
    pin(controls/'plan.json', '10320629ffe1ef6220d4480278b666f05f0dd1d4ca9f68a162a8d7e37b606bd5')
    pin(controls/'complete.json', '96f69e44275022b106a904036cc18eb7319b74a6a9ececc067b97073cb414b35')
    baseline = read(controls/'complete.json')
    require(baseline['status'] == 'PASS_M7_CONTROLS16_ARCHITECTURAL' and baseline['aborted'] is False
            and baseline['pins_unchanged'] is True, 'M7 controls not accepted')
    prior = read(controls/'plan.json')
    pins.update(prior['pins'])
    require(len(prior['cases']) == len(baseline['results']) == 16, '16 controls required')
    for c0 in prior['cases']:
        c = dict(c0, stage='regression19', kind='control')
        require(c['timeout_s'] == 180, 'Control budget drift')
        record = next(r for r in baseline['results'] if r['name'] == c['id'])
        require(record['status'] == 'PASS' and type(record['returncode']) is int and record['returncode'] == 0,
                'M7 control actual result')
        csv = Path(record['artifact_dir'])/'commit_trace.csv'
        pin(csv, baseline['evidence_pins'][str(csv)])
        c['baseline_csv'] = str(csv)
        cases.append(c)
    for kind, dirname, plan_sha in (
        ('indexed', 'indexed_early_illegal_sv39_prepare01', 'e83158226b6d59668069109b8e2b63b0e70dd197653c8b1131d50d0177778d4b'),
        ('load', 'mask_drain_sv39_prepare01', '798c39ec339621a5a66c09ba0af883d996ad43eaae0fdc1ebee11c23a1e15ecd'),
        ('store', 'mask_drain_sv39_prepare01', '30f0ebd54cd35fca856e7cd9b45781f22eab10b1b76b967bfb3b15d6e242157c')):
        old = G/'masked_translation'/dirname/('vcs_m7_'+kind+'01')
        pin(old/'plan.json', plan_sha)
        p = read(old/'plan.json')
        pins.update(p['pins'])
        c = dict(p['case'], stage='indexed1' if kind == 'indexed' else 'regression19',
                 kind=kind, symbols=str(Path(p['reference'])/'soc.symbols.json'))
        require(c['timeout_s'] == (900 if kind == 'indexed' else 3600), 'Boundary budget drift')
        pin(old/'complete.json')
        if kind != 'indexed':
            t = read(old/'complete.json')
            require(t['status'] == 'M7_MASK_DRAIN_'+kind.upper()+'_PASS' and t['aborted'] is False
                    and t['pins_unchanged'] is True and t['retries'] == 0, 'M7 pair baseline failed')
            root = Path(t['results'][0]['artifact_dir'])
            pin(root/'child_exit.json', t['evidence_pins'][str(root/'child_exit.json')])
            check_receipt(read(root/'child_exit.json'), c['timeout_s'])
        else:
            require(read(old/'complete.json')['status'] == 'NOT_PASS', 'Preserve original failure')
        cases.append(c)
    resident_old = G/'indexed_overlap_original/repair06_worker/prepared01'
    pin(resident_old/'plan.json', 'd2053cb571e3df53a4ec846d440b0eb3eca72f61b4b048ecad196060ac7903b8')
    pin(resident_old/'complete.json', '5346d4623f744603f1a2d65677d7bed74615746bf8ec112d8604d9505f6bfd48')
    rp, rt = read(resident_old/'plan.json'), read(resident_old/'complete.json')
    require(rt['status'] == 'PASS_3_REFERENCE03_FULL50_M6' and rt['aborted'] is False and
            rt['pins_unchanged'] is True, 'Resident M6 baseline not accepted')
    pins.update(rp['pins'])
    rc = dict(next(c for c in rp['cases'] if c['id'] == 'd32m2_i64_resident_ov1'))
    rr = next(r for r in rt['results'] if r['name'] == rc['id'])
    require(rr['status'] == 'PASS' and type(rr['returncode']) is int and rr['returncode'] == 0 and
            rc['timeout_s'] == 2400 and rc['fault'] is False and rc['rounds'] == 50 and rc['checks'] == 5215,
            'Resident exact50/5215/no-fault/budget scope')
    baseline_csv = Path(rr['artifact_dir'])/'commit_trace.csv'
    pin(baseline_csv, rt['evidence_pins'][str(baseline_csv)])
    rc.update(stage='regression19',kind='resident',symbols=str(Path(rp['reference'])/rc['id']),
              baseline_csv=str(baseline_csv))
    cases.append(rc)
    cases.sort(key=lambda c: (STAGES.index(c['stage']), {'indexed':0,'load':1,'store':2,'resident':3}.get(c['kind'],4)))
    require(len(cases) == len({c['id'] for c in cases}) == 20, 'Exact distinct20')
    for c in cases:
        pin(Path(c['elf']), c['sha256'])
    for file in ('worker.py', 'check_case.py', 'test_host.py', 'host02.json'):
        pin(HERE/file)
    m7.base.verify_pins(pins)
    return cases, pins


def prepare(out, approved, handoff, handoff_sha):
    require(sha(handoff) == handoff_sha, 'Build handoff identity')
    host = read(HERE/'host02.json')
    require(host['passed'] is True and host['worker_sha256'] == sha(Path(__file__)) and
            host['tests_sha256'] == sha(HERE/'test_host.py'), 'Host gate')
    cases, pins = scope()
    ledger, repo, _ = image_context(approved)
    pins.update(m7.image_pins(IMAGE, ledger, repo))
    pins[str(handoff)] = handoff_sha
    out.mkdir(exist_ok=False)
    save(out/'plan.json', dict(status='PREPARED_NOT_RUN', cases=cases, pins=pins,
        image=str(IMAGE), image_sha256=approved, jobs=3, unit=UNIT, outer_s=OUTER_S,
        handoff=str(handoff), handoff_sha256=handoff_sha, reserved_slots=0,
        stages=list(STAGES), retries=0, no_build=True, no_software_change=True))
    print('PREPARED', str(out), sha(out/'plan.json'), flush=True)


def terminal_ok(results, cases, abort):
    require(not abort.is_set(), 'Sticky abort')
    require(len(results) == len(cases) and {r.name for r in results} == {c['id'] for c in cases}, 'Partial membership')
    require(all(r.status == 'PASS' and type(r.returncode) is int and r.returncode == 0 for r in results), 'Non-PASS outcome')


def run(out, approved):
    require(sha(out/'plan.json') == approved, 'Plan drift')
    p = read(out/'plan.json')
    cases, _ = scope()
    require(p['cases'] == cases and p['jobs'] == 3 and p['stages'] == list(STAGES), 'Case/ordering/budget drift')
    m7.base.verify_pins(p['pins'])
    ledger, repo, (parent, options, testcase, _) = image_context(p['image_sha256'])
    owner = dict(line.split('=',1) for line in subprocess.check_output([
        'systemctl','--user','show',UNIT,'-p','MainPID','-p','ControlGroup','-p','KillMode',
        '-p','Restart','-p','RuntimeMaxUSec'],text=True,timeout=15).splitlines())
    require(owner['MainPID'] == str(os.getpid()) and owner['KillMode'] == 'control-group' and
            owner['Restart'] == 'no' and owner['RuntimeMaxUSec'] == '1h 50min' and
            Path('/proc/self/cgroup').read_text().strip() == '0::'+owner['ControlGroup'], 'Direct bounded owner')
    save(out/'launch.json', dict(pid=os.getpid(), owner=owner, time=time.time(), plan_sha256=approved,
                               admission=m7.resources(out,3,p['reserved_slots'])))
    abort = threading.Event()
    started = time.monotonic()
    terminal = dict(status='NOT_PASS', results=[], aborted=False, retries=0,
                    pins_unchanged=False, plan_sha256=approved, image_sha256=p['image_sha256'])
    import ara_verify.runner as engine
    original, original_re = engine._run_monitored, engine.FAIL_RE
    def monitored(command,cwd,console,timeout_s,cancel_event=None):
        rc,elapsed,timed_out,failed = original(command,cwd,console,timeout_s,cancel_event)
        save(Path(console).parent/'child_exit.json',dict(returncode=rc,elapsed_s=elapsed,
            timed_out=timed_out,failure_seen=failed,abort_set=bool(cancel_event and cancel_event.is_set()),
            command=list(map(str,command)),cwd=str(cwd)))
        return rc,elapsed,timed_out,failed
    engine._run_monitored = monitored
    engine.FAIL_RE = re.compile(original_re.pattern+'|'+m7.BAD.pattern+
                               '|INDEXED_PREFIX_SV39_FAIL|MASK_DRAIN_SV39_FAIL',original_re.flags)
    entries = {c['id']:c for c in cases}
    class Runner(parent):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw)
            self.cancel_event = abort
        def _run_test(self,test,image):
            try:
                result = super()._run_test(test,image)
                c, root = entries[test.name], result.artifact_dir
                check_receipt(read(root/'child_exit.json'), c['timeout_s'])
                require(result.status == 'PASS' and not abort.is_set(), 'Runner failed/aborted')
                m7.check_artifacts(result,c,ledger)
                if c['kind'] in ('control', 'resident'):
                    perf = m7.compare_cycles(Path(c['baseline_csv']),root/'commit_trace.csv',root/'cycle_differences.csv')
                    save(root/'performance.json',perf)
                if c['kind'] != 'control':
                    cmd = [sys.executable,str(HERE/'check_case.py'),c['kind'],str(root/'commit_trace.csv'),
                           c['symbols'],str(root/'csv.json')]
                    save(root/'checker_invocation.json',dict(command=cmd))
                    with (root/'checker.log').open('x') as log:
                        child = subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,timeout=60)
                    save(root/'checker_exit.json',dict(returncode=child.returncode))
                    require(child.returncode == 0, 'Unchanged checker rejected evidence')
                    check_csv_result(c['kind'],read(root/'csv.json'))
                require(not abort.is_set(), 'Abort during checker')
                return result
            except BaseException:
                abort.set()
                raise
    with m7.abort_signals(abort):
        try:
            for stage in STAGES:
                require(not abort.is_set(), 'Aborted before stage')
                subset = [c for c in cases if c['stage'] == stage]
                opts = options(repo,out/stage,'default',min(3,len(subset)),1,False,False,True,Path(ledger['simv']),True,None)
                results = Runner(opts,[testcase(c['id'],'app','',Path(c['elf']),c['original_name'],c['timeout_s'])
                                       for c in subset],sys.argv).run()
                terminal['results'].extend(dict(asdict(r),artifact_dir=str(r.artifact_dir)) for r in results)
                terminal_ok(results,subset,abort)
                require(read(out/stage/'run.json')['status_counts'] == {'PASS':len(subset)} and
                        read(out/stage/'run.json')['status'] == 'COMPLETE', 'Stage not complete')
            m7.base.verify_pins(p['pins'])
            image_context(p['image_sha256'])
            require(time.monotonic()-started < 6300 and not abort.is_set(), 'Campaign deadline/abort')
            performance = {c['id']:read(out/c['stage']/'tests'/c['id']/'performance.json')
                           for c in cases if c['kind'] in ('control', 'resident')}
            evidence = {str(f):sha(f) for stage in STAGES for f in (out/stage).rglob('*') if f.is_file()}
            terminal.update(status='PASS_M8_RECOVERY3_CONTROLS16_RESIDENT1',pins_unchanged=True,performance=performance,
                performance_status='REVIEW_CYCLE_DIFFERENCES' if any(v['cycle_changed_rows'] for v in performance.values())
                                   else 'EXACT_M7_CONTROLS16_AND_M6_RESIDENT_CSV',evidence_pins=evidence)
        except BaseException as e:
            abort.set()
            terminal['firstfailure'] = f'{type(e).__name__}: {e}'
        finally:
            engine._run_monitored, engine.FAIL_RE = original, original_re
            blocked = signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
            try:
                terminal['aborted'] = abort.is_set() or bool(signal.sigpending() & {signal.SIGINT,signal.SIGTERM})
                if terminal['aborted']: terminal['status'] = 'NOT_PASS'
                terminal['elapsed_s'] = time.monotonic()-started
                save(out/'complete.json',terminal)
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK,blocked)
    print(terminal['status'],flush=True)
    return int(terminal['status'] == 'NOT_PASS')


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('mode',choices=['prepare','run'])
    cli.add_argument('--out',type=Path,default=HERE/'prepared01')
    cli.add_argument('--image-sha256')
    cli.add_argument('--build-handoff',type=Path)
    cli.add_argument('--handoff-sha256')
    cli.add_argument('--plan-sha256')
    args = cli.parse_args()
    require(args.out.resolve().parent == HERE, 'New owned output only')
    env = m7.base.shared.environment()
    env.update(XDG_RUNTIME_DIR=f'/run/user/{os.getuid()}',DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{os.getuid()}/bus')
    os.environ.clear()
    os.environ.update(env)
    if args.mode == 'prepare':
        require(args.build_handoff and args.handoff_sha256, 'Actual accepted build handoff required')
        prepare(args.out.resolve(),args.image_sha256,args.build_handoff.resolve(),args.handoff_sha256)
    else:
        sys.exit(run(args.out.resolve(),args.plan_sha256))
